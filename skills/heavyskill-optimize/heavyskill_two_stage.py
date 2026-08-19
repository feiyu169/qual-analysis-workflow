#!/usr/bin/env python3
"""
HeavySkill 两阶段审查脚本

方案 A：两阶段注入
- Stage 1：原始 query（不含清单）→ K 个自由探索轨迹
- Stage 2：清单注入审议器 → 完整性检查 + 遗漏检测

用法:
    python3 heavyskill_two_stage.py --query "审查方案" --file /tmp/proposal.md
"""

import sys
import os
import argparse
from pathlib import Path

# 添加模块路径
sys.path.insert(0, str(Path(__file__).parent))

from src.two_stage_enhancer import TwoStageEnhancer


def main():
    parser = argparse.ArgumentParser(description="HeavySkill 两阶段审查")
    parser.add_argument("--query", "-q", required=True, help="审查查询")
    parser.add_argument("--file", "-f", required=True, help="待审查文件")
    parser.add_argument("--output", "-o", help="输出文件")
    parser.add_argument("--reason_k", type=int, default=4, help="HeavySkill reason_k")
    parser.add_argument("--summary_k", type=int, default=2, help="HeavySkill summary_k")
    parser.add_argument("--heavyskill-dir", help="HeavySkill 目录路径")
    parser.add_argument("--checklists-dir", help="检查清单目录路径")
    parser.add_argument("--output-dir", help="输出目录路径")
    
    args = parser.parse_args()
    
    # 初始化增强器
    enhancer = TwoStageEnhancer(
        heavyskill_dir=args.heavyskill_dir,
        checklists_dir=args.checklists_dir,
        output_dir=args.output_dir
    )
    
    # 运行两阶段审查
    result = enhancer.run_two_stage_review(
        args.query, args.file, args.reason_k, args.summary_k
    )
    
    # 保存结果
    if result and args.output:
        enhancer.save_result(result, args.output)


if __name__ == "__main__":
    main()
