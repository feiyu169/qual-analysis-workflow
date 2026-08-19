"""HeavySkill 优化方案 V3 - 集成指南"""

import copy
from typing import Dict, Any, List
from datetime import datetime

from .models import Severity, Verdict, Issue
from .validator import ConclusionValidator
from .parser import ChecklistResultParser
from .utils import infer_llm_verdict, deduplicate_issues


def integrate_with_heavyskill(heavyskill_output: Dict[str, Any]) -> Dict[str, Any]:
    """
    将 HeavySkill 输出与结论校验引擎集成
    
    Args:
        heavyskill_output: HeavySkill 的 JSON 输出
        
    Returns:
        增强后的输出，包含校验结果
    """
    # 1. 初始化组件
    validator = ConclusionValidator()
    parser = ChecklistResultParser()
    
    # 2. 提取轨迹
    trajectories = heavyskill_output.get('reasoning', {}).get('trajectories', [])
    
    # 3. 从轨迹中提取问题
    all_issues = []
    for i, traj in enumerate(trajectories):
        # 解析轨迹内容
        issues = parser.parse(traj)
        for issue in issues:
            issue.source = f"trajectory-{i}"
        all_issues.extend(issues)
    
    # 4. 从最终答案中提取问题
    final_answer = heavyskill_output.get('final_answer', '')
    final_issues = parser.parse(final_answer)
    all_issues.extend(final_issues)
    
    # 5. 去重
    unique_issues = deduplicate_issues(all_issues)
    
    # 6. 推断 LLM 结论
    llm_verdict = infer_llm_verdict(final_answer)
    
    # 7. 运行校验引擎
    validation_result = validator.validate(unique_issues, llm_verdict)
    
    # 8. 增强输出（深拷贝避免修改原始数据）
    enhanced_output = copy.deepcopy(heavyskill_output)
    enhanced_output['validation'] = {
        'verdict': validation_result.verdict.value,
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
                'confidence': i.confidence
            }
            for i in validation_result.issues
        ],
        'confidence': validation_result.confidence,
        'human_review_required': validation_result.human_review_required,
        'fallback': validation_result.fallback
    }
    
    # 如果规则引擎覆盖了 LLM 结论
    if validation_result.verdict != llm_verdict:
        enhanced_output['original_verdict'] = llm_verdict.value
        enhanced_output['final_answer'] = (
            f"[规则引擎覆盖] {validation_result.verdict.value}\n"
            f"[原始 LLM 结论] {llm_verdict.value}\n"
            f"\n{final_answer}"
        )
    
    return enhanced_output
