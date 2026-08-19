#!/usr/bin/env python3
"""
HeavySkill 增强集成脚本

将 ConclusionValidator 和 ChecklistResultParser 集成到 HeavySkill Pipeline 中，
提升结论准确率和问题发现率。

用法:
    python3 heavyskill_enhanced.py --input /tmp/heavyskill-output.json --output /tmp/enhanced-output.json
    python3 heavyskill_enhanced.py --run-heavyskill --query "审查方案" --file /tmp/proposal.md
"""

import sys
import os
import json
import argparse
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

# 添加优化模块路径
sys.path.insert(0, str(Path(__file__).parent))

from src.models import Severity, Verdict, Issue
from src.validator import ConclusionValidator, ConclusionValidatorConfig
from src.parser import ChecklistResultParser
from src.integration import integrate_with_heavyskill
from src.utils import infer_llm_verdict, deduplicate_issues

# 默认配置
DEFAULT_HEAVYSKILL_DIR = os.path.expanduser("~/.hermes/skills/heavyskill")
DEFAULT_OUTPUT_DIR = os.path.expanduser("~/.hermes/output")
DEFAULT_TEMP_DIR = os.path.expanduser("~/.hermes/tmp")


def run_heavyskill(query: str, file_path: str, reason_k: int = 4, summary_k: int = 2, 
                   heavyskill_dir: Optional[str] = None, output_dir: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """运行 HeavySkill 并返回结果"""
    heavyskill_dir = heavyskill_dir or DEFAULT_HEAVYSKILL_DIR
    output_dir = output_dir or DEFAULT_TEMP_DIR
    
    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)
    
    output_file = os.path.join(output_dir, "heavyskill-temp-output.json")
    
    cmd = [
        "cd", heavyskill_dir, "&&",
        "python3", "scripts/run_heavyskill.py",
        "-q", f'"{query}"',
        "-f", file_path,
        "--reason_k", str(reason_k),
        "--summary_k", str(summary_k),
        "--language", "cn",
        "-o", output_file,
        "--quiet"
    ]
    
    print(f"运行 HeavySkill...")
    result = subprocess.run(" ".join(cmd), shell=True, capture_output=True, text=True, timeout=300)
    
    if result.returncode != 0:
        print(f"HeavySkill 执行失败: {result.stderr}")
        return None
    
    with open(output_file) as f:
        return json.load(f)


def enhance_output(heavyskill_output: Dict[str, Any], config: Optional[ConclusionValidatorConfig] = None) -> Dict[str, Any]:
    """增强 HeavySkill 输出"""
    # 初始化组件
    validator = ConclusionValidator(config)
    parser = ChecklistResultParser()
    
    # 提取轨迹
    trajectories = heavyskill_output.get('reasoning', {}).get('trajectories', [])
    
    # 从轨迹中提取问题
    all_issues = []
    for i, traj in enumerate(trajectories):
        issues = parser.parse(traj)
        for issue in issues:
            issue.source = f"trajectory-{i}"
        all_issues.extend(issues)
    
    # 从最终答案中提取问题
    final_answer = heavyskill_output.get('final_answer', '')
    final_issues = parser.parse(final_answer)
    all_issues.extend(final_issues)
    
    # 去重
    unique_issues = deduplicate_issues(all_issues)
    
    # 推断 LLM 结论
    llm_verdict = infer_llm_verdict(final_answer)
    
    # 运行校验引擎
    validation_result = validator.validate(unique_issues, llm_verdict)
    
    # 构建增强输出
    enhanced = heavyskill_output.copy()
    enhanced['validation'] = {
        'verdict': validation_result.verdict.value,
        'original_verdict': llm_verdict.value,
        'verdict_changed': validation_result.verdict != llm_verdict,
        'rules_applied': [
            {
                'rule': r.rule_name,
                'triggered': r.triggered,
                'verdict': r.verdict.value,
                'reason': r.reason
            }
            for r in validation_result.rules_applied
        ],
        'issues': [
            {
                'id': i.id,
                'title': i.title,
                'severity': i.severity.value,
                'domain': i.domain,
                'confidence': i.confidence,
                'source': i.source
            }
            for i in validation_result.issues
        ],
        'issue_count': len(validation_result.issues),
        'p0_count': len([i for i in validation_result.issues if i.severity == Severity.P0]),
        'p1_count': len([i for i in validation_result.issues if i.severity == Severity.P1]),
        'confidence': validation_result.confidence,
        'human_review_required': validation_result.human_review_required,
        'fallback': validation_result.fallback,
        'shadow_mode': validation_result.shadow_mode
    }
    
    # 如果结论被覆盖，更新最终答案
    if validation_result.verdict != llm_verdict:
        enhanced['final_answer'] = (
            f"[规则引擎覆盖] {validation_result.verdict.value}\n"
            f"[原始 LLM 结论] {llm_verdict.value}\n"
            f"[覆盖原因] {', '.join(r.reason for r in validation_result.rules_applied if r.triggered)}\n"
            f"\n{final_answer}"
        )
    
    return enhanced


def print_report(enhanced: Dict[str, Any]):
    """打印增强报告"""
    validation = enhanced.get('validation', {})
    
    print("=" * 60)
    print("HeavySkill 增强报告")
    print("=" * 60)
    print()
    
    # 结论对比
    print("【结论对比】")
    print(f"  原始 LLM 结论: {validation.get('original_verdict', 'N/A')}")
    print(f"  规则引擎结论: {validation.get('verdict', 'N/A')}")
    print(f"  结论是否覆盖: {'是' if validation.get('verdict_changed') else '否'}")
    print()
    
    # 问题统计
    print("【问题统计】")
    print(f"  总问题数: {validation.get('issue_count', 0)}")
    print(f"  P0 问题: {validation.get('p0_count', 0)}")
    print(f"  P1 问题: {validation.get('p1_count', 0)}")
    print()
    
    # 规则触发情况
    print("【规则触发情况】")
    for rule in validation.get('rules_applied', []):
        status = "触发" if rule['triggered'] else "未触发"
        print(f"  {rule['rule']}: {status} ({rule['reason']})")
    print()
    
    # 问题列表
    issues = validation.get('issues', [])
    if issues:
        print("【问题列表】")
        for issue in issues:
            print(f"  [{issue['severity']}] {issue['title']} (领域: {issue['domain']}, 置信度: {issue['confidence']:.2f})")
        print()
    
    # 其他信息
    print("【其他信息】")
    print(f"  置信度: {validation.get('confidence', 0):.2f}")
    print(f"  需要人工审核: {'是' if validation.get('human_review_required') else '否'}")
    print(f"  使用回退: {'是' if validation.get('fallback') else '否'}")
    print(f"  影子模式: {'是' if validation.get('shadow_mode') else '否'}")


def main():
    parser = argparse.ArgumentParser(description="HeavySkill 增强集成脚本")
    parser.add_argument("--input", "-i", help="HeavySkill 输出 JSON 文件")
    parser.add_argument("--output", "-o", help="增强输出文件")
    parser.add_argument("--run-heavyskill", action="store_true", help="运行 HeavySkill")
    parser.add_argument("--query", "-q", help="HeavySkill 查询")
    parser.add_argument("--file", "-f", help="待审查文件")
    parser.add_argument("--reason_k", type=int, default=4, help="HeavySkill reason_k")
    parser.add_argument("--summary_k", type=int, default=2, help="HeavySkill summary_k")
    parser.add_argument("--shadow-mode", action="store_true", help="启用影子模式")
    parser.add_argument("--report", action="store_true", help="打印报告")
    parser.add_argument("--heavyskill-dir", help="HeavySkill 目录路径")
    parser.add_argument("--output-dir", help="输出目录路径")
    
    args = parser.parse_args()
    
    # 配置
    config = ConclusionValidatorConfig()
    if args.shadow_mode:
        config.shadow_mode = True
    
    # 运行 HeavySkill 或读取输入
    if args.run_heavyskill:
        if not args.query or not args.file:
            print("错误: --run-heavyskill 需要 --query 和 --file")
            sys.exit(1)
        heavyskill_output = run_heavyskill(args.query, args.file, args.reason_k, args.summary_k,
                                            args.heavyskill_dir, args.output_dir)
        if not heavyskill_output:
            sys.exit(1)
    elif args.input:
        with open(args.input) as f:
            heavyskill_output = json.load(f)
    else:
        print("错误: 需要 --input 或 --run-heavyskill")
        sys.exit(1)
    
    # 增强输出
    enhanced = enhance_output(heavyskill_output, config)
    
    # 保存输出
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(enhanced, f, ensure_ascii=False, indent=2)
        print(f"增强输出已保存到: {args.output}")
    
    # 打印报告
    if args.report or not args.output:
        print_report(enhanced)


if __name__ == "__main__":
    main()
