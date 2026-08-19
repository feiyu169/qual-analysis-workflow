#!/usr/bin/env python3
"""
HeavySkill 增强版集成脚本 V2

新增功能：
1. 领域识别器 - 自动识别待审查方案的领域
2. 检查清单注入 - 将专业检查清单注入到 query 中
3. 结论校验引擎 - 规则引擎覆盖 LLM 结论

用法:
    python3 heavyskill_enhanced_v2.py --query "审查方案" --file /tmp/proposal.md
    python3 heavyskill_enhanced_v2.py --input /tmp/heavyskill-output.json --enhance-only
"""

import sys
import os
import json
import argparse
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List

# 添加模块路径
sys.path.insert(0, str(Path(__file__).parent))

from src.models import Severity, Verdict, Issue
from src.validator import ConclusionValidator, ConclusionValidatorConfig
from src.parser import ChecklistResultParser
from src.enhancer import QueryEnhancer, DomainClassifier, ChecklistManager
from src.utils import infer_llm_verdict, deduplicate_issues

# 默认配置
DEFAULT_HEAVYSKILL_DIR = os.path.expanduser("~/.hermes/skills/heavyskill")
DEFAULT_OUTPUT_DIR = os.path.expanduser("~/.hermes/output")
DEFAULT_CHECKLISTS_DIR = os.path.expanduser("~/.hermes/skills/heavyskill-optimize/checklists")


class HeavySkillEnhancedV2:
    """HeavySkill 增强版 V2"""
    
    def __init__(self, heavyskill_dir: Optional[str] = None, 
                 checklists_dir: Optional[str] = None,
                 output_dir: Optional[str] = None):
        self.heavyskill_dir = heavyskill_dir or DEFAULT_HEAVYSKILL_DIR
        self.checklists_dir = checklists_dir or DEFAULT_CHECKLISTS_DIR
        self.output_dir = output_dir or DEFAULT_OUTPUT_DIR
        
        # 初始化组件
        self.enhancer = QueryEnhancer(self.checklists_dir)
        self.classifier = DomainClassifier()
        self.validator = ConclusionValidator()
        self.parser = ChecklistResultParser()
        
        # 确保输出目录存在
        os.makedirs(self.output_dir, exist_ok=True)
    
    def run_enhanced_review(self, query: str, file_path: str, 
                           reason_k: int = 4, summary_k: int = 2) -> Optional[Dict[str, Any]]:
        """
        运行增强版审查
        
        Args:
            query: 原始查询
            file_path: 待审查文件路径
            reason_k: HeavySkill reason_k
            summary_k: HeavySkill summary_k
            
        Returns:
            增强后的审查结果
        """
        print("=" * 60)
        print("HeavySkill 增强版审查 V2")
        print("=" * 60)
        print()
        
        # 1. 识别领域
        print("【步骤 1】识别领域...")
        with open(file_path, 'r', encoding='utf-8') as f:
            file_content = f.read()
        
        domains = self.classifier.classify(file_content)
        print(f"  识别领域: {', '.join(domains)}")
        print()
        
        # 2. 增强 query
        print("【步骤 2】增强 query...")
        enhanced_query = self.enhancer.enhance(query, file_content)
        print(f"  原始 query 长度: {len(query)}")
        print(f"  增强 query 长度: {len(enhanced_query)}")
        print()
        
        # 3. 运行 HeavySkill
        print("【步骤 3】运行 HeavySkill...")
        heavyskill_output = self._run_heavyskill(enhanced_query, file_path, reason_k, summary_k)
        
        if not heavyskill_output:
            print("  ❌ HeavySkill 执行失败")
            return None
        
        print(f"  轨迹数: {len(heavyskill_output.get('reasoning', {}).get('trajectories', []))}")
        print(f"  Token 数: {heavyskill_output.get('total_tokens', 0)}")
        print()
        
        # 4. 增强输出
        print("【步骤 4】增强输出...")
        enhanced_output = self._enhance_output(heavyskill_output, domains)
        print()
        
        # 5. 生成报告
        print("【步骤 5】生成报告...")
        self._print_report(enhanced_output)
        
        return enhanced_output
    
    def _run_heavyskill(self, query: str, file_path: str, 
                        reason_k: int, summary_k: int) -> Optional[Dict[str, Any]]:
        """运行 HeavySkill"""
        output_file = os.path.join(self.output_dir, "heavyskill-temp-output.json")
        
        cmd = f'cd {self.heavyskill_dir} && python3 scripts/run_heavyskill.py -q "{query}" -f {file_path} --reason_k {reason_k} --summary_k {summary_k} --language cn -o {output_file} --quiet'
        
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
        
        if result.returncode != 0:
            print(f"  错误: {result.stderr}")
            return None
        
        with open(output_file) as f:
            return json.load(f)
    
    def _enhance_output(self, heavyskill_output: Dict[str, Any], 
                        domains: List[str]) -> Dict[str, Any]:
        """增强输出"""
        # 提取轨迹
        trajectories = heavyskill_output.get('reasoning', {}).get('trajectories', [])
        final_answer = heavyskill_output.get('final_answer', '')
        
        # 从轨迹中提取问题
        all_issues = []
        for i, traj in enumerate(trajectories):
            issues = self.parser.parse(traj)
            for issue in issues:
                issue.source = f"trajectory-{i}"
            all_issues.extend(issues)
        
        # 从最终答案中提取问题
        final_issues = self.parser.parse(final_answer)
        all_issues.extend(final_issues)
        
        # 去重
        unique_issues = deduplicate_issues(all_issues)
        
        # 推断 LLM 结论
        llm_verdict = infer_llm_verdict(final_answer)
        
        # 运行校验引擎
        validation_result = self.validator.validate(unique_issues, llm_verdict)
        
        # 构建增强输出
        enhanced = heavyskill_output.copy()
        enhanced['domains'] = domains
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
            'fallback': validation_result.fallback
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
    
    def _print_report(self, enhanced: Dict[str, Any]):
        """打印报告"""
        validation = enhanced.get('validation', {})
        domains = enhanced.get('domains', [])
        
        print("=" * 60)
        print("增强版审查报告")
        print("=" * 60)
        print()
        
        # 领域信息
        print("【识别领域】")
        print(f"  {', '.join(domains)}")
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
    
    def save_result(self, enhanced: Dict[str, Any], output_file: Optional[str] = None):
        """保存结果"""
        output_file = output_file or os.path.join(self.output_dir, "heavyskill-enhanced-v2-output.json")
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(enhanced, f, ensure_ascii=False, indent=2)
        
        print(f"✅ 结果已保存到: {output_file}")


def main():
    parser = argparse.ArgumentParser(description="HeavySkill 增强版 V2")
    parser.add_argument("--query", "-q", help="审查查询")
    parser.add_argument("--file", "-f", help="待审查文件")
    parser.add_argument("--input", "-i", help="HeavySkill 输出 JSON 文件（仅增强）")
    parser.add_argument("--output", "-o", help="输出文件")
    parser.add_argument("--reason_k", type=int, default=4, help="HeavySkill reason_k")
    parser.add_argument("--summary_k", type=int, default=2, help="HeavySkill summary_k")
    parser.add_argument("--heavyskill-dir", help="HeavySkill 目录路径")
    parser.add_argument("--checklists-dir", help="检查清单目录路径")
    parser.add_argument("--output-dir", help="输出目录路径")
    parser.add_argument("--enhance-only", action="store_true", help="仅增强已有输出")
    
    args = parser.parse_args()
    
    # 初始化增强器
    enhancer = HeavySkillEnhancedV2(
        heavyskill_dir=args.heavyskill_dir,
        checklists_dir=args.checklists_dir,
        output_dir=args.output_dir
    )
    
    if args.enhance_only:
        # 仅增强已有输出
        if not args.input:
            print("错误: --enhance-only 需要 --input")
            sys.exit(1)
        
        with open(args.input) as f:
            heavyskill_output = json.load(f)
        
        # 读取文件内容识别领域
        file_path = heavyskill_output.get('file_path', '')
        if file_path and os.path.exists(file_path):
            with open(file_path) as f:
                file_content = f.read()
            domains = enhancer.classifier.classify(file_content)
        else:
            domains = ["general"]
        
        enhanced = enhancer._enhance_output(heavyskill_output, domains)
        enhancer._print_report(enhanced)
    else:
        # 运行完整审查
        if not args.query or not args.file:
            print("错误: 需要 --query 和 --file")
            sys.exit(1)
        
        enhanced = enhancer.run_enhanced_review(
            args.query, args.file, args.reason_k, args.summary_k
        )
    
    # 保存结果
    if enhanced and args.output:
        enhancer.save_result(enhanced, args.output)


if __name__ == "__main__":
    main()
