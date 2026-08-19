"""HeavySkill 优化方案 - 共享工具函数"""

from typing import List
from .models import Severity, Verdict, Issue


def infer_llm_verdict(text: str) -> Verdict:
    """
    从文本推断 LLM 结论
    
    优先级：长关键字 > 短关键字
    先检查"附意见通过"（包含"通过"），再检查"不通过"，最后检查"通过"
    """
    # 先检查长关键字
    if '附意见通过' in text:
        return Verdict.CONDITIONAL_PASS
    if '不通过' in text:
        return Verdict.REJECT
    if '通过' in text:
        return Verdict.PASS
    
    # 英文关键字
    text_lower = text.lower()
    if 'conditional' in text_lower:
        return Verdict.CONDITIONAL_PASS
    if 'reject' in text_lower:
        return Verdict.REJECT
    if 'pass' in text_lower:
        return Verdict.PASS
    
    return Verdict.PASS


def deduplicate_issues(issues: List[Issue]) -> List[Issue]:
    """
    去重问题
    
    基于 (title, severity, domain) 三元组去重
    """
    seen = set()
    unique = []
    for issue in issues:
        key = (issue.title, issue.severity, issue.domain)
        if key not in seen:
            seen.add(key)
            unique.append(issue)
    return unique
