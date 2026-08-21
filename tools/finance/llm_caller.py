"""DeepSeek LLM 调用器

用于买方投资分析工作流的 LLM 调用函数。
使用阿里云百炼 DashScope 的 DeepSeek-V3 模型。

配置来源：~/.hermes/config.yaml 中 gbrain MCP 的 env
"""

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


def _load_deepseek_config() -> tuple[str, str]:
    """加载 DeepSeek 配置

    Returns:
        (api_key, base_url)
    """
    import os

    # 1. 环境变量
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

    # 2. .env 文件
    if not api_key:
        env_file = Path.home() / ".hermes" / ".env"
        key_prefix = "DEEPSEEK" + "_API_KEY="
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith(key_prefix):
                    api_key = line.split("=", 1)[1].strip()

    # 3. config.yaml (gbrain MCP env)
    if not api_key:
        config_path = Path.home() / ".hermes" / "config.yaml"
        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f)
            gbrain_env = config.get("mcp_servers", {}).get("gbrain", {}).get("env", {})
            api_key = gbrain_env.get("DEEPSEEK_API_KEY", "")
            if "dashscope" in gbrain_env.get("OPENAI_BASE_URL", ""):
                base_url = gbrain_env.get("OPENAI_BASE_URL", base_url)

    return api_key, base_url


def create_deepseek_caller(
    model: str = "deepseek-chat",
    temperature: float = 0.2,  # 从0.3降到0.2，进一步提高格式遵从度
    max_tokens: int = 12000,   # 从4096提到12000（长章节/审查输出；推理模型思考吃预算）
    timeout: float = 300.0,    # 从60提到300（推理模型长任务 60-180s 常态）
    max_retries: int = 2,      # 新增：瞬时失败重试（与 harness_llm 对齐）
):
    """创建 DeepSeek LLM 调用函数

    Args:
        model: 模型名称（默认 deepseek-chat）
        temperature: 温度参数（0.2=更确定性，0.7=更随机）
        max_tokens: 最大 token 数（默认 12000，长任务可调大）
        timeout: 单次 API 调用超时秒数（默认 300，推理模型长任务）
        max_retries: 失败重试次数（默认 2）

    Returns:
        llm_caller(chapter_name: str, prompt: str) -> str
    """
    import openai

    api_key, base_url = _load_deepseek_config()
    if not api_key:
        raise ValueError("DeepSeek API key 未配置。请在 ~/.hermes/config.yaml 的 mcp_servers.gbrain.env 中设置 DEEPSEEK_API_KEY")

    client = openai.OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
    )

    def llm_caller(chapter_name: str, prompt: str) -> str:
        """调用 DeepSeek 生成章节内容

        Args:
            chapter_name: 章节名称
            prompt: 写作提示

        Returns:
            生成的章节内容
        """
        logger.info(f"调用 DeepSeek 生成: {chapter_name}")

        last_err = None
        for attempt in range(max_retries + 1):
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": """你是一位资深投资分析师，擅长撰写买方研究报告。

【格式要求 - 必须严格遵守】
1. 每章必须包含以下三个小节，标题必须完全匹配：
   - ## 结论要点
   - ## 详细情况
   - ## 证据与出处

2. ⚠️ 标题格式必须是 Markdown H2（##），绝对禁止使用 H3（###）

3. 禁止使用以下变体标题：
   - ❌ ### 结论要点、### 详细情况、### 证据与出处（禁止使用###）
   - ❌ 核心观点、投资要点、总结、Key Takeaway
   - ❌ 分析详情、详细内容、深入分析
   - ❌ 数据来源、参考、信息来源

4. 必须使用以下标准标题：
   - ✅ ## 结论要点
   - ✅ ## 详细情况
   - ✅ ## 证据与出处

5. 标题前后必须有空行

请用专业、客观的语言撰写分析内容。"""},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

                content = response.choices[0].message.content
                logger.info(f"{chapter_name} 生成完成: {len(content)} 字符")
                return content

            except Exception as e:
                last_err = e
                logger.error(f"DeepSeek 调用失败 尝试{attempt+1}: {e}")
                if attempt < max_retries:
                    import time
                    time.sleep(2 * (attempt + 1))
        raise last_err

    return llm_caller


# 默认调用器（懒加载）
_default_caller = None


def get_default_caller():
    """获取默认的 DeepSeek 调用器"""
    global _default_caller
    if _default_caller is None:
        _default_caller = create_deepseek_caller()
    return _default_caller
