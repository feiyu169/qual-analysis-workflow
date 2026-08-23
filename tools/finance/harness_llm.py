"""Harness LLM 调用器：通过宿主 llm 桥接路由调用 DSH 自身模型配置。

替代 create_deepseek_caller()，无需独立 DeepSeek API key。
依赖：llm-bridge 动态插件（宿主 web 服务器 /api/llm-bridge 路由）运行中。

用法:
    from finance.harness_llm import create_harness_caller
    llm_caller = create_harness_caller()   # -> llm_caller(chapter_name, prompt) -> str
"""
import json
import os
import time
import urllib.request


def _log(msg: str):
    """调用日志（追加到工作区 .pip-tmp/llm-calls.log），便于观察进度/卡点"""
    try:
        root = os.environ.get("HS_WORKSPACE", "")
        path = os.path.join(root, ".pip-tmp", "llm-calls.log") if root else os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", ".pip-tmp", "llm-calls.log")
        path = os.path.abspath(path)
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass

SYSTEM_PROMPT = """你是一位资深的投资分析师，擅长撰写买方研究报告。

【格式要求-必须严格遵守】
1. 每章必须包含以下三个小节，标题必须完全匹配：
   - ## 结论要点
   - ## 详细情况
   - ## 证据与出处
2. ⚠️ 标题格式必须是 Markdown H2（##），绝对禁止使用 H3（###）。
3. 禁止使用以下变体标题：
   - ### 结论要点、## 详细情况、## 证据与出处（禁止###）
   - 核心观点、投资要点、总结、Key Takeaway
   - 分析详情、详细内容、深入分析
   - 数据来源、参考、信息来源
4. 必须使用以下标准标题：
   - ✅ ## 结论要点
   - ✅ ## 详细情况
   - ✅ ## 证据与出处
5. 标题前后必须有空行。
请用专业、客观的语言撰写分析内容。"""


def _default_base_url() -> str:
    return os.environ.get("DSH_WEB_URL", "http://127.0.0.1:3080")


def _call_bridge(payload: dict, base_url: str, timeout: int) -> dict:
    """调用 llm-bridge（带 socket 级超时——urlopen timeout 对流式响应不保证，
    宿主 LLM 流中断会无限挂起；用 socket.setdefaulttimeout 兜底防长挂）"""
    import socket as _socket
    req = urllib.request.Request(
        base_url.rstrip("/") + "/api/llm-bridge",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    # 双专家 P2（2026-08-22）：socket 级超时兜底——urlopen 的 timeout 对已开始
    # 的流式响应不生效（读超时），宿主 LLM 流中断会无限挂起（实测 run 卡 8 分钟）
    old_timeout = _socket.getdefaulttimeout()
    _socket.setdefaulttimeout(timeout)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    finally:
        _socket.setdefaulttimeout(old_timeout)


def create_harness_caller(
    base_url: str = None,
    model: str = None,
    provider: str = None,
    timeout: int = 120,
    max_retries: int = 2,
    temperature: float = 0.2,
    max_tokens: int = 12000,
    system: str = None,
    deadline: float = None,
):
    """创建 llm_caller(chapter_name, prompt) -> str。

    优先通过 llm-bridge（DSH 宿主模型路由）调用；
    bridge 不可用时自动 fallback 到直接 DeepSeek API（llm_caller.py）。

    Args:
        base_url: DSH web 地址（默认取 DSH_WEB_URL 环境变量）
        model/provider: 覆盖宿主默认模型路由
        timeout: 单次调用超时（秒）
        max_retries: 失败重试次数
        temperature: 生成温度
        max_tokens: 最大输出 token
        system: 自定义 system prompt
        deadline: 墙钟截止时间
    """
    import time as _time

    from .llm_errors import DeterministicLLMFailure, WallClockDeadlineExceeded

    base = base_url or _default_base_url()
    sys_prompt = system if system is not None else SYSTEM_PROMPT

    # 检测 bridge 是否可用（启动时一次探测）
    _bridge_available = False
    try:
        import urllib.request as _urllib
        _probe = _urllib.Request(
            base.rstrip("/") + "/api/llm-bridge",
            data=b"{}",
            headers={"Content-Type": "application/json"},
        )
        with _urllib.urlopen(_probe, timeout=3) as _r:
            _bridge_available = _r.status != 404
    except Exception:
        _bridge_available = False

    # bridge 不可用时准备 fallback caller
    _fallback_caller = None
    if not _bridge_available:
        _log("bridge 不可用（404），启用直接 API fallback")
        try:
            from .llm_caller import create_deepseek_caller
            _fallback_caller = create_deepseek_caller(
                model="deepseek-chat",
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
                max_retries=max_retries,
            )
        except Exception as e:
            _log(f"fallback caller 创建失败: {e}")

    def llm_caller(chapter_name: str, prompt: str) -> str:
        # 若 bridge 不可用且 fallback 可用，直接走 fallback
        if not _bridge_available and _fallback_caller is not None:
            if deadline is not None and _time.monotonic() > deadline:
                raise WallClockDeadlineExceeded(f"墙钟预算耗尽: {chapter_name}")
            return _fallback_caller(chapter_name, prompt)

        # 正常路径：通过 bridge 调用
        payload = {
            "system": sys_prompt,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "maxTokens": max_tokens,
        }
        if model:
            payload["model"] = model
        if provider:
            payload["provider"] = provider

        _log(f"开始 {chapter_name} (prompt={len(prompt)}字符, maxTokens={max_tokens})")
        last_err = None
        for attempt in range(max_retries + 1):
            t0 = time.time()
            if deadline is not None and _time.monotonic() > deadline:
                _log(f"失败 {chapter_name}: 墙钟截止时间耗尽（不重试）")
                raise WallClockDeadlineExceeded(f"墙钟预算耗尽: {chapter_name}")
            try:
                data = _call_bridge(payload, base, timeout)
                if not data.get("ok"):
                    finish = data.get("finishReason") or data.get("finish") or {}
                    text = data.get("text") or ""
                    if (isinstance(finish, dict) and finish.get("kind") == "max-tokens") or \
                       (isinstance(finish, str) and "max" in finish):
                        if text and len(text.strip()) > 0:
                            _log(f"⚠️ 完成 {chapter_name} 尝试{attempt+1}: max-tokens 截断，保留 {len(text)} 字符")
                            return text + "\n\n<!-- ⚠️ LLM 输出被 max-tokens 截断，内容不完整 -->"
                        raise DeterministicLLMFailure(
                            f"LLM 输出为空（finish={finish}），确定性失败，不重试",
                            finish_reason=finish, model=model,
                        )
                    raise RuntimeError(data.get("error") or ("finish=" + json.dumps(finish) if finish else "llm bridge 调用失败"))
                text = data["text"]
                _log(f"完成 {chapter_name} 尝试{attempt+1} ({round(time.time()-t0,1)}s, {len(text)}字符)")
                return text
            except DeterministicLLMFailure:
                raise
            except Exception as e:
                last_err = e
                _log(f"失败 {chapter_name} 尝试{attempt+1}: {repr(e)[:200]} ({round(time.time()-t0,1)}s)")
                if attempt < max_retries:
                    time.sleep(2 * (attempt + 1))
        raise last_err

    return llm_caller


if __name__ == "__main__":
    caller = create_harness_caller()
    print(caller("test", "用一句话说明你是谁，最后给出：最终答案：<答案>"))
