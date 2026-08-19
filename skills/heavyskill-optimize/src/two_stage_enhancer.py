"""HeavySkill 两阶段注入增强器

方案 A：两阶段注入
- Stage 1：原始 query（不含清单）→ K 个自由探索轨迹
- Stage 2：清单注入审议器 → 完整性检查 + 遗漏检测
"""

import os
import json
import subprocess
from typing import List, Dict, Optional, Any
from datetime import datetime

from .enhancer import DomainClassifier, ChecklistManager
from .models import Severity, Verdict, Issue
from .validator import ConclusionValidator
from .parser import ChecklistResultParser
from .utils import infer_llm_verdict, deduplicate_issues


class TwoStageEnhancer:
    """两阶段注入增强器"""
    
    DEFAULT_HEAVYSKILL_DIR = os.path.expanduser("~/.hermes/skills/heavyskill")
    DEFAULT_OUTPUT_DIR = os.path.expanduser("~/.hermes/output")
    DEFAULT_CHECKLISTS_DIR = os.path.expanduser("~/.hermes/skills/heavyskill-optimize/checklists")
    
    def __init__(self, heavyskill_dir: Optional[str] = None,
                 checklists_dir: Optional[str] = None,
                 output_dir: Optional[str] = None):
        self.heavyskill_dir = heavyskill_dir or self.DEFAULT_HEAVYSKILL_DIR
        self.checklists_dir = checklists_dir or self.DEFAULT_CHECKLISTS_DIR
        self.output_dir = output_dir or self.DEFAULT_OUTPUT_DIR
        
        # 初始化组件
        self.classifier = DomainClassifier()
        self.checklist_manager = ChecklistManager(self.checklists_dir)
        self.validator = ConclusionValidator()
        self.parser = ChecklistResultParser()
        
        # 确保输出目录存在
        os.makedirs(self.output_dir, exist_ok=True)
    
    def run_two_stage_review(self, query: str, file_path: str,
                             reason_k: int = 4, summary_k: int = 2) -> Optional[Dict[str, Any]]:
        """
        运行两阶段审查
        
        Args:
            query: 原始查询
            file_path: 待审查文件路径
            reason_k: HeavySkill reason_k
            summary_k: HeavySkill summary_k
            
        Returns:
            增强后的审查结果
        """
        print("=" * 60)
        print("HeavySkill 两阶段审查")
        print("=" * 60)
        print()
        
        # 读取文件内容
        with open(file_path, 'r', encoding='utf-8') as f:
            file_content = f.read()
        
        # 识别领域
        domains = self.classifier.classify(file_content)
        print(f"【识别领域】{', '.join(domains)}")
        print()
        
        # Stage 1：自由探索（不含清单）
        print("【Stage 1】自由探索（不含清单）...")
        stage1_output = self._run_stage1(query, file_path, reason_k, summary_k)
        
        if not stage1_output:
            print("  ❌ Stage 1 执行失败")
            return None
        
        stage1_trajectories = stage1_output.get('reasoning', {}).get('trajectories', [])
        print(f"  轨迹数: {len(stage1_trajectories)}")
        print(f"  Token 数: {stage1_output.get('total_tokens', 0)}")
        print()
        
        # Stage 2：清单验证（完整性检查）
        print("【Stage 2】清单验证（完整性检查）...")
        stage2_result = self._run_stage2(stage1_output, domains, file_content)
        
        print(f"  清单项数: {stage2_result['checklist_count']}")
        print(f"  已覆盖: {stage2_result['covered_count']}")
        print(f"  遗漏: {stage2_result['missed_count']}")
        print()
        
        # 合并结果
        print("【合并结果】...")
        final_output = self._merge_results(stage1_output, stage2_result, domains)
        print()
        
        # 生成报告
        print("【生成报告】...")
        self._print_report(final_output)
        
        return final_output
    
    def _run_stage1(self, query: str, file_path: str,
                    reason_k: int, summary_k: int) -> Optional[Dict[str, Any]]:
        """Stage 1：自由探索（不含清单）"""
        output_file = os.path.join(self.output_dir, "heavyskill-stage1-output.json")
        
        # 使用原始 query，不注入清单
        cmd = f'cd {self.heavyskill_dir} && python3 scripts/run_heavyskill.py -q "{query}" -f {file_path} --reason_k {reason_k} --summary_k {summary_k} --language cn -o {output_file} --quiet'
        
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
        
        if result.returncode != 0:
            print(f"  错误: {result.stderr}")
            return None
        
        with open(output_file) as f:
            return json.load(f)
    
    def _run_stage2(self, stage1_output: Dict[str, Any], 
                    domains: List[str], file_content: str) -> Dict[str, Any]:
        """Stage 2：清单验证（完整性检查）"""
        # 获取检查清单
        checklist = self.checklist_manager.get_checklist(domains)
        checklist_items = checklist.get('items', [])
        
        # 提取 Stage 1 的轨迹内容
        trajectories = stage1_output.get('reasoning', {}).get('trajectories', [])
        all_text = ' '.join(trajectories)
        final_answer = stage1_output.get('final_answer', '')
        all_text += ' ' + final_answer
        
        # 检查每个清单项的覆盖情况
        covered = []
        missed = []
        
        for item in checklist_items:
            item_id = item['id']
            question = item['question']
            severity = item.get('severity', 'P2')
            
            # 提取关键词进行匹配
            keywords = self._extract_keywords(question)
            
            # 检查是否在轨迹中被提及
            is_covered = any(kw in all_text for kw in keywords)
            
            if is_covered:
                covered.append({
                    'id': item_id,
                    'question': question,
                    'severity': severity,
                    'status': 'covered'
                })
            else:
                missed.append({
                    'id': item_id,
                    'question': question,
                    'severity': severity,
                    'status': 'missed'
                })
        
        return {
            'checklist_count': len(checklist_items),
            'covered_count': len(covered),
            'missed_count': len(missed),
            'covered': covered,
            'missed': missed,
            'checklist': checklist
        }
    
    def _extract_keywords(self, question: str) -> List[str]:
        """从问题中提取关键词"""
        # 移除标点符号和常见词汇
        stop_words = {'是否', '有', '的', '吗', '？', '?', '、', '，', '。', '！', '!'}
        
        # 提取中文词汇
        keywords = []
        
        # 直接提取问题中的关键词
        # 例如："是否有分页设计？" → ["分页", "设计"]
        import re
        # 提取中文词组
        chinese_words = re.findall(r'[\u4e00-\u9fa5]+', question)
        for word in chinese_words:
            if word not in stop_words and len(word) >= 2:
                keywords.append(word)
        
        # 如果没有提取到关键词，使用整个问题
        if not keywords:
            keywords = [question]
        
        return keywords
    
    def _merge_results(self, stage1_output: Dict[str, Any],
                       stage2_result: Dict[str, Any],
                       domains: List[str]) -> Dict[str, Any]:
        """合并 Stage 1 和 Stage 2 的结果"""
        # 提取 Stage 1 的轨迹
        trajectories = stage1_output.get('reasoning', {}).get('trajectories', [])
        final_answer = stage1_output.get('final_answer', '')
        
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
        enhanced = stage1_output.copy()
        enhanced['domains'] = domains
        enhanced['stage2'] = {
            'checklist_count': stage2_result['checklist_count'],
            'covered_count': stage2_result['covered_count'],
            'missed_count': stage2_result['missed_count'],
            'covered': stage2_result['covered'],
            'missed': stage2_result['missed']
        }
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
        
        # 如果有遗漏的清单项，补充到最终答案
        if stage2_result['missed']:
            missed_summary = "\n".join([
                f"  - [{m['severity']}] {m['id']}: {m['question']}"
                for m in stage2_result['missed']
            ])
            enhanced['final_answer'] += f"\n\n[清单验证] 以下清单项未被覆盖：\n{missed_summary}"
        
        return enhanced
    
    def _print_report(self, enhanced: Dict[str, Any]):
        """打印报告"""
        validation = enhanced.get('validation', {})
        domains = enhanced.get('domains', [])
        stage2 = enhanced.get('stage2', {})
        
        print("=" * 60)
        print("两阶段审查报告")
        print("=" * 60)
        print()
        
        # 领域信息
        print("【识别领域】")
        print(f"  {', '.join(domains)}")
        print()
        
        # Stage 2 清单验证结果
        print("【清单验证结果】")
        print(f"  清单项数: {stage2.get('checklist_count', 0)}")
        print(f"  已覆盖: {stage2.get('covered_count', 0)}")
        print(f"  遗漏: {stage2.get('missed_count', 0)}")
        
        if stage2.get('missed'):
            print()
            print("  遗漏清单项:")
            for m in stage2['missed']:
                print(f"    - [{m['severity']}] {m['id']}: {m['question']}")
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
    
    def save_result(self, enhanced: Dict[str, Any], output_file: Optional[str] = None):
        """保存结果"""
        output_file = output_file or os.path.join(self.output_dir, "heavyskill-two-stage-output.json")
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(enhanced, f, ensure_ascii=False, indent=2)
        
        print(f"✅ 结果已保存到: {output_file}")
