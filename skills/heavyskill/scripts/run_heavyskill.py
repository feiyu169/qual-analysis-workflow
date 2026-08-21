#!/usr/bin/env python3
"""
HeavySkill CLI Entry Point

Command-line interface for running the HeavySkill pipeline.
Supports bilingual prompts (English/Chinese) and domain-specific reasoning.

Usage:
    python -m heavyskill.scripts.run_heavyskill --query "What is 2+2?"
    python -m heavyskill.scripts.run_heavyskill --query "求解方程 x^2 - 5x + 6 = 0" --language cn --prompt_type stem
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Optional

# Add parent directory to path for relative imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from heavyskill.configuration import (
    HeavySkillConfig,
    Language,
    PromptType,
    SelectionStrategy,
)
from heavyskill.workflow.pipeline import HeavySkillPipeline


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the CLI."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Suppress noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    P54-R1/R4：可配置参数一律 default=None（便于 build_config 做
    CLI > config.yaml > 内置默认 三级解析）；`--max-tokens` 与 `--max_tokens`
    双拼写兼容（旧文档/旧命令用下划线，新文档用短横线）。
    """
    parser = argparse.ArgumentParser(
        description="HeavySkill: Enhanced LLM Reasoning Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python -m heavyskill.scripts.run_heavyskill --query "What is the capital of France?"

  # STEM problem in Chinese
  python -m heavyskill.scripts.run_heavyskill \\
    --query "求解微分方程 dy/dx = 2xy" \\
    --language cn --prompt_type stem

  # Custom configuration
  python -m heavyskill.scripts.run_heavyskill \\
    --query "Explain quantum entanglement" \\
    --reason_k 16 --summary_k 8 --iterations 3 \\
    --strategy max_diversity --output results.json
        """,
    )

    # Required arguments
    parser.add_argument(
        "--query",
        "-q",
        type=str,
        required=True,
        help="The question/problem to reason about.",
    )
    parser.add_argument(
        "--include-file",
        "-f",
        type=str,
        action="append",
        default=[],
        dest="include_files",
        help="File(s) to read and embed into the query. Can be specified multiple times. "
        "File content is appended to the query as context.",
    )

    # Model configuration
    parser.add_argument(
        "--model",
        "-m",
        type=str,
        default=None,
        help="Model name for reasoning (default: from config.yaml, fallback deepseek-chat).",
    )
    parser.add_argument(
        "--summary_model",
        type=str,
        default=None,
        help="Model for deliberation (default: same as --model).",
    )
    parser.add_argument(
        "--api_base",
        type=str,
        default=None,
        help="API base URL (default: from config.yaml, fallback https://api.deepseek.com).",
    )
    parser.add_argument(
        "--api_key",
        type=str,
        default=None,
        help="API authentication key (default: from config.yaml).",
    )

    # Pipeline configuration
    parser.add_argument(
        "--reason_k",
        "-k",
        type=int,
        default=None,
        help="Number of parallel reasoning trajectories (default: from config.yaml, fallback 8).",
    )
    parser.add_argument(
        "--summary_k",
        type=int,
        default=None,
        help="Number of trajectories for deliberation (default: from config.yaml, fallback 4).",
    )
    parser.add_argument(
        "--iterations",
        "-i",
        type=int,
        default=None,
        help="Number of deliberation iterations (default: from config.yaml, fallback 1).",
    )

    # Prompt configuration
    parser.add_argument(
        "--prompt_type",
        "-p",
        type=str,
        choices=["general", "stem"],
        default=None,
        help="Domain type for prompts (default: from config.yaml, fallback general).",
    )
    parser.add_argument(
        "--language",
        "-l",
        type=str,
        choices=["en", "cn"],
        default=None,
        help="Language for deliberation prompts (default: from config.yaml, fallback en).",
    )
    parser.add_argument(
        "--strategy",
        "-s",
        type=str,
        choices=["random", "max_answer_frequency", "max_diversity"],
        default=None,
        help="Trajectory selection strategy (default: from config.yaml, fallback max_answer_frequency).",
    )

    # Generation parameters
    parser.add_argument(
        "--temperature",
        "-t",
        type=float,
        default=None,
        help="Temperature for reasoning (default: from config.yaml, fallback 1.0).",
    )
    parser.add_argument(
        "--summary_temperature",
        type=float,
        default=None,
        help="Temperature for deliberation (default: from config.yaml, fallback 0.7).",
    )
    # P54-R1：短横线为主拼写（文档/告警一致），下划线为兼容旧命令
    parser.add_argument(
        "--max-tokens",
        "--max_tokens",
        type=int,
        default=None,
        dest="max_tokens",
        help="Max tokens per response (default: from config.yaml, fallback 32768).",
    )
    parser.add_argument(
        "--summary-max-tokens",
        "--summary_max_tokens",
        type=int,
        default=None,
        dest="summary_max_tokens",
        help="Max tokens for deliberation response (default: from config.yaml, fallback 16384). "
        "P54: 审议结论被截断时增大此值。",
    )
    parser.add_argument(
        "--token_budget",
        type=int,
        default=None,
        help="Total token budget (default: from config.yaml, fallback 80000).",
    )

    # Output configuration
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Output file path for JSON results.",
    )
    parser.add_argument(
        "--accept-partial",
        action="store_true",
        help="P54-R5: 显式接受截断/退化的部分结果（否则截断且无答案时 exit 2）。",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress console output (useful with --output).",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose debug logging.",
    )

    return parser.parse_args()


def build_config(args: argparse.Namespace, defaults: dict) -> HeavySkillConfig:
    """P54-R4：统一 CLI > config.yaml > 内置默认 的三级配置解析。

    修复旧版"只有 max_tokens/summary_max_tokens 从 config.yaml 加载，而
    temperature/language/summary_temperature 等键因 argparse default 非 None
    被 `or` 短路、config.yaml 值永远不生效"的配置断裂（HGF 复审 P2-2）。
    """

    def pick(name: str, fallback):
        """CLI 显式传参 > config.yaml > 内置默认。"""
        v = getattr(args, name, None)
        if v is None:
            v = defaults.get(name, fallback)
        return v

    model = pick("model", "deepseek-chat")
    return HeavySkillConfig(
        api_base=pick("api_base", "https://api.deepseek.com"),
        api_key=pick("api_key", ""),
        model=model,
        summary_model=pick("summary_model", model),
        reason_k=pick("reason_k", 8),
        summary_k=pick("summary_k", 4),
        max_iterations=pick("iterations", 1),
        temperature=pick("temperature", 1.0),
        summary_temperature=pick("summary_temperature", 0.7),
        max_tokens=pick("max_tokens", 32768),
        summary_max_tokens=pick("summary_max_tokens", 16384),
        token_budget=pick("token_budget", 80000),
        prompt_type=PromptType(pick("prompt_type", "general")),
        language=Language(pick("language", "en")),
        selection_strategy=SelectionStrategy(pick("strategy", "max_answer_frequency")),
        timeout=defaults.get("timeout", 120.0),
        verbose=args.verbose,
    )


def load_config_defaults() -> dict:
    """加载 config.yaml 为默认值字典（文件不存在/不可解析时返回空 dict）。"""
    import yaml as _yaml

    _config_path = Path(__file__).parent.parent / "config.yaml"
    _defaults: dict = {}
    if _config_path.exists():
        with open(_config_path, encoding="utf-8") as _f:
            loaded = _yaml.safe_load(_f)
            if isinstance(loaded, dict):
                _defaults = loaded
    return _defaults


async def main() -> int:
    """Main entry point for the CLI."""
    args = parse_args()

    # Setup logging
    setup_logging(args.verbose)
    logger = logging.getLogger("heavyskill.cli")

    # Build configuration（P54-R4：CLI > config.yaml > 内置默认）
    config = build_config(args, load_config_defaults())
    if args.max_tokens is not None or args.summary_max_tokens is not None:
        logger.info(
            f"Token budgets: max_tokens={config.max_tokens}, "
            f"summary_max_tokens={config.summary_max_tokens}"
        )

    # Read and embed files into the query
    query = args.query
    if args.include_files:
        file_contents = []
        for file_path in args.include_files:
            p = Path(file_path).expanduser().resolve()
            if not p.exists():
                logger.error(f"File not found: {file_path}")
                return 1
            if not p.is_file():
                logger.error(f"Not a file: {file_path}")
                return 1
            try:
                content = p.read_text(encoding="utf-8")
                file_contents.append(
                    f"\n\n--- 文件: {p.name} ---\n{content}\n--- 文件结束 ---"
                )
                logger.info(f"Read file: {p} ({len(content)} chars)")
            except Exception as e:
                logger.error(f"Failed to read file {file_path}: {e}")
                return 1
        query = query + "\n\n以下是需要审查的文件内容：" + "".join(file_contents)
        logger.info(
            f"Query augmented with {len(file_contents)} file(s), total length: {len(query)} chars"
        )

    # Run pipeline
    pipeline = HeavySkillPipeline(config)

    try:
        result = await pipeline.run(query=query)
    except KeyboardInterrupt:
        logger.info("Pipeline interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=args.verbose)
        return 1

    # Output results
    if not args.quiet:
        print(result.summary())

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result.to_json(), encoding="utf-8")
        logger.info(f"Results saved to {output_path}")

    # P54-R1/R5：截断/退化必须显式告警；无可用答案时非 0 退出（除非 --accept-partial）
    if result.has_truncation():
        logger.warning(
            "⚠️ 本次运行存在截断或退化（见输出 JSON 的 truncation 字段）："
            "推理轨迹截断 %d 条 / 思维链回退 %d 条 / 审议截断 %s。"
            "处理：增大 --max-tokens / --summary-max-tokens 后重跑，"
            "或使用 --accept-partial 显式接受部分结果。",
            result.reasoning_result.truncated_count if result.reasoning_result else 0,
            result.reasoning_result.content_fallback_count
            if result.reasoning_result
            else 0,
            any(d.truncated for d in result.deliberation_results),
        )
        if result.final_answer is None and not args.accept_partial:
            logger.error(
                "截断且无可用最终答案：请增大 --max-tokens / --summary-max-tokens 重跑，"
                "或加 --accept-partial 显式接受部分结果（exit 2）"
            )
            return 2

    return 0


def cli_main() -> None:
    """Synchronous entry point for console_scripts."""
    sys.exit(asyncio.run(main()))


if __name__ == "__main__":
    cli_main()
