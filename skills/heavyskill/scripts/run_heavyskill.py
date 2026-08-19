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
    """Parse command-line arguments."""
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
        "--query", "-q",
        type=str,
        required=True,
        help="The question/problem to reason about.",
    )
    parser.add_argument(
        "--include-file", "-f",
        type=str,
        action="append",
        default=[],
        dest="include_files",
        help="File(s) to read and embed into the query. Can be specified multiple times. "
             "File content is appended to the query as context.",
    )

    # Model configuration
    parser.add_argument(
        "--model", "-m",
        type=str,
        default="deepseek-v4-pro",
        help="Model name for reasoning (default: deepseek-v4-pro).",
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
        default="https://api.deepseek.com",
        help="API base URL (default: https://api.deepseek.com).",
    )
    parser.add_argument(
        "--api_key",
        type=str,
        default=None,
        help="API authentication key (default: from config.yaml).",
    )

    # Pipeline configuration
    parser.add_argument(
        "--reason_k", "-k",
        type=int,
        default=8,
        help="Number of parallel reasoning trajectories (default: 8).",
    )
    parser.add_argument(
        "--summary_k",
        type=int,
        default=4,
        help="Number of trajectories for deliberation (default: 4).",
    )
    parser.add_argument(
        "--iterations", "-i",
        type=int,
        default=1,
        help="Number of deliberation iterations (default: 1).",
    )

    # Prompt configuration
    parser.add_argument(
        "--prompt_type", "-p",
        type=str,
        choices=["general", "stem"],
        default="general",
        help="Domain type for prompts (default: general).",
    )
    parser.add_argument(
        "--language", "-l",
        type=str,
        choices=["en", "cn"],
        default="en",
        help="Language for deliberation prompts (default: en).",
    )
    parser.add_argument(
        "--strategy", "-s",
        type=str,
        choices=["random", "max_answer_frequency", "max_diversity"],
        default="max_answer_frequency",
        help="Trajectory selection strategy (default: max_answer_frequency).",
    )

    # Generation parameters
    parser.add_argument(
        "--temperature", "-t",
        type=float,
        default=1.0,
        help="Temperature for reasoning (default: 1.0).",
    )
    parser.add_argument(
        "--summary_temperature",
        type=float,
        default=0.7,
        help="Temperature for deliberation (default: 0.7).",
    )
    parser.add_argument(
        "--max_tokens",
        type=int,
        default=4096,
        help="Max tokens per response (default: 4096).",
    )
    parser.add_argument(
        "--token_budget",
        type=int,
        default=80000,
        help="Total token budget (default: 80000).",
    )

    # Output configuration
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Output file path for JSON results.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress console output (useful with --output).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose debug logging.",
    )

    return parser.parse_args()


async def main() -> int:
    """Main entry point for the CLI."""
    args = parse_args()

    # Setup logging
    setup_logging(args.verbose)
    logger = logging.getLogger("heavyskill.cli")

    # Build configuration
    # Load defaults from config.yaml if not provided via CLI
    import yaml as _yaml
    _config_path = Path(__file__).parent.parent / "config.yaml"
    _defaults = {}
    if _config_path.exists():
        with open(_config_path) as _f:
            _defaults = _yaml.safe_load(_f) or {}
    
    api_key = args.api_key or _defaults.get("api_key", "")
    api_base = args.api_base or _defaults.get("api_base", "https://api.deepseek.com")
    model = args.model or _defaults.get("model", "deepseek-chat")

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
                file_contents.append(f"\n\n--- 文件: {p.name} ---\n{content}\n--- 文件结束 ---")
                logger.info(f"Read file: {p} ({len(content)} chars)")
            except Exception as e:
                logger.error(f"Failed to read file {file_path}: {e}")
                return 1
        query = query + "\n\n以下是需要审查的文件内容：" + "".join(file_contents)
        logger.info(f"Query augmented with {len(file_contents)} file(s), total length: {len(query)} chars")
    
    config = HeavySkillConfig(
        api_base=api_base,
        api_key=api_key,
        model=model,
        summary_model=args.summary_model or args.model,
        reason_k=args.reason_k,
        summary_k=args.summary_k,
        max_iterations=args.iterations,
        temperature=args.temperature,
        summary_temperature=args.summary_temperature,
        max_tokens=args.max_tokens,
        token_budget=args.token_budget,
        prompt_type=PromptType(args.prompt_type),
        language=Language(args.language),
        selection_strategy=SelectionStrategy(args.strategy),
        timeout=_defaults.get("timeout", 120.0),
        verbose=args.verbose,
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

    return 0


def cli_main() -> None:
    """Synchronous entry point for console_scripts."""
    sys.exit(asyncio.run(main()))


if __name__ == "__main__":
    cli_main()
