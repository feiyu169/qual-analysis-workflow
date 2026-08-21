"""End-to-end HGF demo: classify_task -> assess_risk -> execute_gates.

Run from the workflow/ directory with the system Python 3.14:
    python demo_hgf/hgf_demo.py
"""

from __future__ import annotations

import sys

from gate_executor import GateExecutor
from risk_assessor import RiskAssessor
from task_classifier import Task, TaskClassifier


def main() -> None:
    # 中文 Windows 控制台默认 GBK，HGF 报告含 emoji，强制 UTF-8 输出
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    classifier = TaskClassifier()
    task = Task(
        description="Add a discount calculation module with unit tests",
        files=["demo_hgf/calc.py", "demo_hgf/tests/test_calc.py"],
        file_count=2,
        line_count=45,
        affected_areas=["calc", "business"],
    )

    print("=" * 60)
    print("Phase 1: classify_task")
    print("=" * 60)
    classification = classifier.classify_task(task)
    print(
        f"level={classification.level}  type={classification.type}  risk={classification.risk}"
    )

    print()
    print("=" * 60)
    print("Phase 2: assess_risk")
    print("=" * 60)
    assessor = RiskAssessor()
    risk = assessor.assess_risk(
        affected_areas=task.affected_areas, description=task.description
    )
    print(f"risk={risk.risk}  score={risk.score}")
    print(
        f"matched_factors={risk.matched_factors}  bonus={risk.combination_bonus}  reduction={risk.reduction_applied}"
    )

    print()
    print("=" * 60)
    print("Phase 3: execute_gates (level=" + classification.level + ")")
    print("=" * 60)
    executor = GateExecutor("config/mcp-gates.yaml")
    report = executor.execute_gates(
        level=classification.level, files=["calc.py"], working_dir="demo_hgf"
    )
    print(report.format_report())

    passed = report.passed if hasattr(report, "passed") else None
    print(f"\nOVERALL: passed={passed}")


if __name__ == "__main__":
    main()
