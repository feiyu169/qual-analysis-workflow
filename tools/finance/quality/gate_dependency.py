"""
gate_dependency.py — Gate 间依赖追踪模块

功能：
- 记录每个 Gate 发现的问题
- 记录问题修复状态
- 在新 Gate 开始前检查前序遗留问题
- 生成依赖报告
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ====================================================================
# 数据结构
# ====================================================================

@dataclass
class TrackedIssue:
    """追踪的问题"""
    issue_id: str
    gate_id: str
    severity: str
    message: str
    resolved: bool = False
    resolution: str = ""
    resolved_by: str = ""
    resolved_at: str = ""


@dataclass
class DependencyReport:
    """依赖报告"""
    total_issues: int = 0
    resolved_issues: int = 0
    pending_p0: int = 0
    pending_high: int = 0
    pending_issues: list[TrackedIssue] = field(default_factory=list)


# ====================================================================
# 依赖追踪器
# ====================================================================

class GateDependencyTracker:
    """Gate 间依赖追踪器"""
    
    def __init__(self, state_dir: Optional[str] = None):
        self.issues: dict[str, list[TrackedIssue]] = {}  # gate_id -> issues
        self.state_dir = Path(state_dir) if state_dir else None
    
    def record_issues(self, gate_id: str, issues: list[dict]):
        """
        记录 Gate 发现的问题。

        Args:
            gate_id: Gate 标识
            issues: 问题列表，每个问题有 id/severity/message 字段
        """
        tracked = []
        for issue in issues:
            tracked.append(TrackedIssue(
                issue_id=f"{gate_id}-{issue.get('id', 'unknown')}",
                gate_id=gate_id,
                severity=issue.get("severity", "UNKNOWN"),
                message=issue.get("message", ""),
            ))
        self.issues[gate_id] = tracked
        self._save_state()
    
    def record_resolution(self, gate_id: str, issue_id: str, resolution: str, resolved_by: str = "auto"):
        """
        记录问题修复。

        Args:
            gate_id: Gate 标识
            issue_id: 问题 ID
            resolution: 修复描述
            resolved_by: 修复者
        """
        if gate_id in self.issues:
            for issue in self.issues[gate_id]:
                if issue.issue_id == issue_id:
                    issue.resolved = True
                    issue.resolution = resolution
                    issue.resolved_by = resolved_by
                    from datetime import datetime
                    issue.resolved_at = datetime.now().isoformat()
                    break
        self._save_state()
    
    def check_prerequisites(self, gate_id: str, prerequisites: list[str]) -> list[TrackedIssue]:
        """
        检查前序 Gate 的遗留问题。

        Args:
            gate_id: 当前 Gate 标识
            prerequisites: 前序 Gate 列表

        Returns:
            未解决的 P0/HIGH 问题列表
        """
        pending = []
        for prereq in prerequisites:
            if prereq in self.issues:
                for issue in self.issues[prereq]:
                    if not issue.resolved and issue.severity in ["P0", "HIGH"]:
                        pending.append(issue)
        
        if pending:
            logger.warning(
                f"Gate {gate_id} 发现 {len(pending)} 个前序遗留问题: "
                + ", ".join(f"[{i.severity}] {i.message[:30]}" for i in pending)
            )
        
        return pending
    
    def generate_report(self) -> DependencyReport:
        """生成依赖报告"""
        total = 0
        resolved = 0
        pending_p0 = 0
        pending_high = 0
        pending_issues = []
        
        for gate_id, issues in self.issues.items():
            for issue in issues:
                total += 1
                if issue.resolved:
                    resolved += 1
                else:
                    if issue.severity == "P0":
                        pending_p0 += 1
                    elif issue.severity == "HIGH":
                        pending_high += 1
                    pending_issues.append(issue)
        
        return DependencyReport(
            total_issues=total,
            resolved_issues=resolved,
            pending_p0=pending_p0,
            pending_high=pending_high,
            pending_issues=pending_issues,
        )
    
    def format_report(self) -> str:
        """格式化依赖报告"""
        report = self.generate_report()
        
        lines = ["## Gate 间依赖报告"]
        lines.append("")
        lines.append(f"- 总问题数: {report.total_issues}")
        lines.append(f"- 已修复: {report.resolved_issues}")
        lines.append(f"- 待修复 P0: {report.pending_p0}")
        lines.append(f"- 待修复 HIGH: {report.pending_high}")
        lines.append("")
        
        if report.pending_issues:
            lines.append("### 待修复问题")
            for issue in report.pending_issues:
                lines.append(f"- [{issue.severity}] {issue.gate_id}: {issue.message}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _save_state(self):
        """保存状态到文件"""
        if self.state_dir:
            state_file = self.state_dir / "gate_dependencies.json"
            state = {}
            for gate_id, issues in self.issues.items():
                state[gate_id] = [asdict(i) for i in issues]
            state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    
    def load_state(self):
        """从文件加载状态"""
        if self.state_dir:
            state_file = self.state_dir / "gate_dependencies.json"
            if state_file.exists():
                state = json.loads(state_file.read_text())
                for gate_id, issues_data in state.items():
                    self.issues[gate_id] = [TrackedIssue(**i) for i in issues_data]
