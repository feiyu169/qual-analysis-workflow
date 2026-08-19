"""
IncrementalChecker模块

功能:
- 增量检查: 仅检查变更章节
- 变更检测: 对比before/after内容
- 新旧问题对比

解决: P1-3 Step4.7增量检查边界
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class IncrementalCheckResult:
    """增量检查结果"""
    checked_chapters: Set[str] = field(default_factory=set)
    changed_chapters: Set[str] = field(default_factory=set)
    new_issues: List[str] = field(default_factory=list)
    resolved_issues: List[str] = field(default_factory=list)
    skipped_chapters: Set[str] = field(default_factory=set)


class IncrementalChecker:
    """增量检查器
    
    边界规则:
    ┌─────────────────────────────────────────────────────────────┐
    │ 场景                          │ 检查范围                    │
    ├─────────────────────────────────────────────────────────────┤
    │ Step4→Step4.5无变更           │ 跳过增量检查                │
    │ Step4→Step4.5有变更           │ 仅检查变更章节              │
    │ 辩论覆盖原始章节              │ 检查覆盖后的版本            │
    │ Step4.5→Step4.7有新内容       │ 检查新内容+受影响的旧内容   │
    │ 全量重检(首次运行)            │ 检查全部章节                │
    └─────────────────────────────────────────────────────────────┘
    """
    
    def __init__(self, check_function: Optional[Callable] = None):
        self.check_function = check_function
    
    def detect_changes(
        self,
        chapters_before: Dict[str, str],
        chapters_after: Dict[str, str],
    ) -> Set[str]:
        """检测变更章节"""
        changed = set()
        
        for ch_id in set(chapters_before.keys()) | set(chapters_after.keys()):
            old = chapters_before.get(ch_id, "")
            new = chapters_after.get(ch_id, "")
            
            if old != new:
                changed.add(ch_id)
        
        return changed
    
    def check_incremental(
        self,
        chapters_before: Dict[str, str],
        chapters_after: Dict[str, str],
        check_function: Optional[Callable] = None,
    ) -> IncrementalCheckResult:
        """增量检查"""
        check_fn = check_function or self.check_function
        
        if check_fn is None:
            raise ValueError("check_function未提供")
        
        result = IncrementalCheckResult()
        
        # 识别变更章节
        result.changed_chapters = self.detect_changes(chapters_before, chapters_after)
        
        if not result.changed_chapters:
            # 无变更，跳过检查
            logger.info("无章节变更，跳过增量检查")
            return result
        
        # 仅检查变更章节
        for ch_id in result.changed_chapters:
            old_content = chapters_before.get(ch_id, "")
            new_content = chapters_after.get(ch_id, "")
            
            # 检查新内容
            new_issues = check_fn(ch_id, new_content)
            
            # 检查旧内容
            old_issues = check_fn(ch_id, old_content)
            
            # 对比新旧问题
            for issue in new_issues:
                if issue not in old_issues:
                    result.new_issues.append(f"[新增] {ch_id}: {issue}")
            
            for old_issue in old_issues:
                if old_issue not in new_issues:
                    result.resolved_issues.append(f"[已解决] {ch_id}: {old_issue}")
            
            result.checked_chapters.add(ch_id)
        
        # 记录跳过的章节
        all_chapters = set(chapters_before.keys()) | set(chapters_after.keys())
        result.skipped_chapters = all_chapters - result.checked_chapters
        
        return result
    
    def check_full(
        self,
        chapters: Dict[str, str],
        check_function: Optional[Callable] = None,
    ) -> IncrementalCheckResult:
        """全量检查"""
        check_fn = check_function or self.check_function
        
        if check_fn is None:
            raise ValueError("check_function未提供")
        
        result = IncrementalCheckResult()
        
        for ch_id, content in chapters.items():
            issues = check_fn(ch_id, content)
            
            for issue in issues:
                result.new_issues.append(f"[问题] {ch_id}: {issue}")
            
            result.checked_chapters.add(ch_id)
        
        return result
    
    def get_affected_chapters(
        self,
        changed_chapters: Set[str],
        chapter_dependencies: Dict[str, List[str]],
    ) -> Set[str]:
        """获取受影响的章节"""
        affected = set(changed_chapters)
        
        for ch_id in changed_chapters:
            # 获取依赖此章节的其他章节
            for dep_ch, deps in chapter_dependencies.items():
                if ch_id in deps:
                    affected.add(dep_ch)
        
        return affected
    
    def generate_report(self, result: IncrementalCheckResult) -> str:
        """生成增量检查报告"""
        lines = [
            "## 增量检查报告",
            "",
            f"| 指标 | 值 |",
            f"|------|-----|",
            f"| 检查章节数 | {len(result.checked_chapters)} |",
            f"| 变更章节数 | {len(result.changed_chapters)} |",
            f"| 跳过章节数 | {len(result.skipped_chapters)} |",
            f"| 新增问题数 | {len(result.new_issues)} |",
            f"| 已解决问题数 | {len(result.resolved_issues)} |",
        ]
        
        if result.new_issues:
            lines.extend([
                "",
                "### 新增问题",
                "",
            ])
            for issue in result.new_issues:
                lines.append(f"- {issue}")
        
        if result.resolved_issues:
            lines.extend([
                "",
                "### 已解决问题",
                "",
            ])
            for issue in result.resolved_issues:
                lines.append(f"- {issue}")
        
        return "\n".join(lines)
