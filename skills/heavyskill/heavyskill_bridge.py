"""HeavySkill → DSH 插件桥（一期，2026-08-22，参照 hgf_bridge.py --serve）。

DSH 动态插件（JS）无法直接 import Python 模块，本桥提供 JSON-in/JSON-out
命令入口：插件 spawn `python heavyskill_bridge.py --serve`，桥内复用
skills/heavyskill 全部逻辑，结果以 JSON 返回模型。

协议：stdin 每行一个请求 `{"id": <int>, "command": <str>, "args": {}}`，
stdout 每行一个响应 `{"id": <int>, "ok": true, "result": {...}}` 或
`{"id": <int>, "ok": false, "error": "..."}`；单条命令失败不退出进程。

命令：
- review: {query, content?, k?, mode?: basic|enhanced|chunked, api_key?, validator_api_key?,
           max_tokens?, summary_max_tokens?, language?} → {summary, file}
- verify: {conclusion, trajectories, query, validator_api_key?} → ValidationResult.to_dict()
- history: {limit?} → 样本库最近记录
- adjudicate: {sample_id, verdict: adopt|reject|amend, notes?} → {updated, sample_id}

安全要点（裁判裁决准出）：
- 完整结果写临时文件，桥只返回 ≤5KB 摘要（80KB JSON stdout 行缓冲 P0 缓解）
- 每次命令独立创建 pipeline（不共享 httpx client，防 asyncio 泄漏）
- safe_handle 结构化错误，不杀进程
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import tempfile
from datetime import datetime, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("hsk.bridge")


def _force_utf8() -> None:
    """Windows 中文控制台默认 GBK：桥的 JSON 必须 UTF-8（同 hgf_bridge）。"""
    if sys.platform == "win32":
        for stream in (sys.stdin, sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, OSError):
                pass


def _build_config(args: dict):
    """从工具参数构造 HeavySkillConfig（复用 configuration.py，键名与 CLI 一致）。"""
    from configuration import HeavySkillConfig, Language, PromptType

    def pick(name: str, fallback):
        v = args.get(name)
        return fallback if v is None else v

    mode = args.get("mode", "basic")
    return HeavySkillConfig(
        api_key=pick("api_key", os.environ.get("DEEPSEEK_API_KEY", "")),
        api_base=pick("api_base", "https://api.deepseek.com"),
        model=pick("model", "deepseek-v4-pro"),
        summary_model=pick("summary_model", "deepseek-v4-pro"),
        reason_k=pick("k", 8),
        summary_k=pick("summary_k", 4),
        max_tokens=pick("max_tokens", 32768),
        summary_max_tokens=pick("summary_max_tokens", 16384),
        temperature=pick("temperature", 0.7),
        summary_temperature=pick("summary_temperature", 0.3),
        language=Language(pick("language", "cn")),
        prompt_type=PromptType(pick("prompt_type", "general")),
        timeout=pick("timeout", 300.0),
        enable_validator=(mode == "enhanced"),
        enable_second_review=(mode == "enhanced"),
        validator_api_key=pick("validator_api_key", os.environ.get("XIAOMI_KEY", "")),
        validator_api_base=pick(
            "validator_api_base", "https://token-plan-cn.xiaomimimo.com/v1"
        ),
        validator_model=pick("validator_model", "mimo-v2.5-pro"),
    )


def _write_result_file(payload: dict) -> str:
    """完整结果写临时文件（桥只回传路径与摘要）。"""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = os.path.join(tempfile.gettempdir(), f"hsk-result-{ts}-{os.getpid()}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def summarize_result(result) -> dict:
    """HeavySkillResult → ≤5KB 摘要（trajectories 只保留元信息，deliberation 截断）。"""
    d = result.to_dict()
    r = d.get("reasoning") or {}
    traj = r.get("trajectories", [])
    answers = r.get("answers", [])
    d["reasoning"] = {
        "trajectories": [
            {
                "index": i,
                "chars": len(t),
                "answer": answers[i] if i < len(answers) else None,
            }
            for i, t in enumerate(traj)
        ],
        "successful_count": r.get("successful_count"),
        "truncated_count": r.get("truncated_count"),
        "content_fallback_count": r.get("content_fallback_count"),
    }
    for dd in d.get("deliberation", []):
        resp = dd.get("deliberation_response", "")
        dd["deliberation_response"] = resp[:2000]
    return d


def summarize_chunked(result) -> dict:
    d = result.to_dict()
    # 分块结果已带摘要（chunks 只含 index/final_answer/truncation），deliberation 截断
    if d.get("meta_deliberation"):
        d["meta_deliberation"] = d["meta_deliberation"][:2000]
    return d


async def _cmd_review(args: dict) -> dict:
    from workflow.chunked_review import ChunkedReviewer
    from workflow.pipeline import HeavySkillPipeline
    from workflow.sample_registry import record_sample

    config = _build_config(args)
    mode = args.get("mode", "basic")
    query = args.get("query", "")
    content = args.get("content", "")

    if mode == "chunked":
        reviewer = ChunkedReviewer(config)
        result = await reviewer.run(query=query, content=content)
        summary = summarize_chunked(result)
        file = _write_result_file(result.to_dict())
    else:
        pipe = HeavySkillPipeline(config)
        result = await pipe.run(query=query if not content else f"{query}\n\n{content}")
        summary = summarize_result(result)
        file = _write_result_file(result.to_dict())
        # 一期：样本采集 hook（占位，二期启用统计）
        try:
            record_sample(result, config)
        except Exception as e:  # noqa: BLE001 - 采集失败不阻断
            logger.warning(f"样本采集失败: {e}")

    return {"summary": summary, "file": file}


async def _cmd_verify(args: dict) -> dict:
    from workflow.validator import validate_conclusion

    config = _build_config(args)
    if not config.validator_api_key:
        config.validator_api_key = args.get("validator_api_key") or os.environ.get(
            "XIAOMI_KEY", ""
        )
    result = await validate_conclusion(
        deliberation_response=args.get("conclusion", ""),
        trajectories=args.get("trajectories", []),
        query=args.get("query", ""),
        config=config,
    )
    return result.to_dict()


async def _cmd_history(args: dict) -> dict:
    from workflow.sample_registry import read_samples

    samples = read_samples(limit=args.get("limit", 10))
    return {"total": len(samples), "samples": samples}


async def _cmd_adjudicate(args: dict) -> dict:
    from workflow.sample_registry import adjudicate

    ok = adjudicate(
        sample_id=args.get("sample_id", ""),
        verdict=args.get("verdict", ""),
        notes=args.get("notes", ""),
        adjudicator=args.get("adjudicator", "agent"),
    )
    return {"updated": ok, "sample_id": args.get("sample_id")}


HANDLERS = {
    "review": _cmd_review,
    "verify": _cmd_verify,
    "history": _cmd_history,
    "adjudicate": _cmd_adjudicate,
}


def serve() -> None:
    """长驻 stdio JSON-RPC 循环（单条命令失败不退出）。"""
    _force_utf8()
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as e:
            print(
                json.dumps(
                    {"id": None, "ok": False, "error": f"请求不是合法 JSON: {e}"},
                    ensure_ascii=False,
                ),
                flush=True,
            )
            continue
        rid = req.get("id")
        command = req.get("command")
        args = req.get("args") or {}
        try:
            handler = HANDLERS.get(command)
            if handler is None:
                raise ValueError(
                    f"未知命令: {command}（支持: {', '.join(sorted(HANDLERS))}）"
                )
            result = asyncio.run(handler(args))
            print(
                json.dumps(
                    {"id": rid, "ok": True, "result": result}, ensure_ascii=False
                ),
                flush=True,
            )
        except Exception as e:  # noqa: BLE001 - 协议兜底，单条命令失败不退出
            print(
                json.dumps(
                    {"id": rid, "ok": False, "error": f"{type(e).__name__}: {e}"},
                    ensure_ascii=False,
                ),
                flush=True,
            )


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] != "--serve":
        sys.stderr.write("用法: python heavyskill_bridge.py --serve\n")
        sys.exit(1)
    serve()


if __name__ == "__main__":
    main()
