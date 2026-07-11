"""
gate_evaluator.py — 统一评估标准模块

评估标准：
- 直接放行：≥80分，P0=0，HIGH=0
- 条件放行：60-79分，P0=0，HIGH≤2
- 不放行：<60分或P0>0
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ====================================================================
# 数据结构
# ====================================================================

@dataclass
class EvaluationIssue:
    """评估问题"""
    id: str
    severity: str        # P0, HIGH, MEDIUM, LOW
    message: str
    file_path: str = ""
    line: int = 0
    suggestion: str = ""
    gate_id: str = ""    # 发现问题的 Gate


@dataclass
class GateEvaluation:
    """Gate 评估结果"""
    gate_id: str
    score: int
    p0_count: int
    high_count: int
    medium_count: int
    low_count: int
    decision: str        # "pass" | "conditional" | "reject"
    conditions: list[str] = field(default_factory=list)
    issues: list[EvaluationIssue] = field(default_factory=list)


# ====================================================================
# 评估阈值
# ====================================================================

THRESHOLDS = {
    "pass": {
        "min_score": 80,
        "max_p0": 0,
        "max_high": 0,
    },
    "conditional": {
        "min_score": 60,
        "max_p0": 0,
        "max_high": 2,
    },
}


# ====================================================================
# 评估函数
# ====================================================================

def evaluate_gate(
    gate_id: str,
    issues: list[EvaluationIssue],
    score: int,
) -> GateEvaluation:
    """
    统一评估标准。

    Args:
        gate_id: Gate 标识
        issues: 问题列表
        score: 综合评分

    Returns:
        GateEvaluation 评估结果
    """
    p0_count = sum(1 for i in issues if i.severity == "P0")
    high_count = sum(1 for i in issues if i.severity == "HIGH")
    medium_count = sum(1 for i in issues if i.severity == "MEDIUM")
    low_count = sum(1 for i in issues if i.severity == "LOW")
    
    # 直接放行
    if (score >= THRESHOLDS["pass"]["min_score"]
        and p0_count <= THRESHOLDS["pass"]["max_p0"]
        and high_count <= THRESHOLDS["pass"]["max_high"]):
        return GateEvaluation(
            gate_id=gate_id,
            score=score,
            p0_count=p0_count,
            high_count=high_count,
            medium_count=medium_count,
            low_count=low_count,
            decision="pass",
            conditions=[],
            issues=issues,
        )
    
    # 条件放行
    if (score >= THRESHOLDS["conditional"]["min_score"]
        and p0_count <= THRESHOLDS["conditional"]["max_p0"]
        and high_count <= THRESHOLDS["conditional"]["max_high"]):
        return GateEvaluation(
            gate_id=gate_id,
            score=score,
            p0_count=p0_count,
            high_count=high_count,
            medium_count=medium_count,
            low_count=low_count,
            decision="conditional",
            conditions=[
                "所有 HIGH 问题必须在下一个 Gate 开始前修复",
                "修复后必须由独立专家复验",
            ],
            issues=issues,
        )
    
    # 不放行
    return GateEvaluation(
        gate_id=gate_id,
        score=score,
        p0_count=p0_count,
        high_count=high_count,
        medium_count=medium_count,
        low_count=low_count,
        decision="reject",
        conditions=[
            "所有 P0 和 HIGH 问题必须修复",
            "修复后必须重新评估",
        ],
        issues=issues,
    )


def format_evaluation_report(eval_result: GateEvaluation) -> str:
    """格式化评估报告"""
    decision_cn = {
        "pass": "直接放行 ✅",
        "conditional": "条件放行 ⚠️",
        "reject": "不放行 ❌",
    }
    
    lines = [f"## Gate {eval_result.gate_id} 评估报告"]
    lines.append("")
    lines.append(f"**评分**: {eval_result.score}/100")
    lines.append(f"**结论**: {decision_cn.get(eval_result.decision, eval_result.decision)}")
    lines.append("")
    
    lines.append("### 问题统计")
    lines.append(f"- P0 (阻塞级): {eval_result.p0_count}")
    lines.append(f"- HIGH (严重): {eval_result.high_count}")
    lines.append(f"- MEDIUM (中等): {eval_result.medium_count}")
    lines.append(f"- LOW (轻微): {eval_result.low_count}")
    lines.append("")
    
    if eval_result.conditions:
        lines.append("### 放行条件")
        for condition in eval_result.conditions:
            lines.append(f"- {condition}")
        lines.append("")
    
    if eval_result.issues:
        lines.append("### 问题清单")
        for issue in eval_result.issues:
            lines.append(f"- [{issue.severity}] {issue.message}")
            if issue.suggestion:
                lines.append(f"  建议: {issue.suggestion}")
        lines.append("")
    
    return "\n".join(lines)
