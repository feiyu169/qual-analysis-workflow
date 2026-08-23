"""
报告版本协议与文件系统实现。

存储最终报告 + 质量标注 + Gate 结果，支持追溯和对比。
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from ..contracts.types import GateResult


@runtime_checkable
class ReportVersionProtocol(Protocol):
    """报告版本协议。"""

    def save_report(
        self,
        run_id: str,
        report: str,
        quality_markers: dict[str, Any],
        gate_results: dict[int, GateResult],
    ) -> str:
        """保存报告版本，返回版本路径。"""
        ...

    def load_report(self, run_id: str) -> dict[str, Any] | None:
        """加载报告版本。"""
        ...


class FileReportVersion:
    """文件系统报告版本实现。

    存储结构：
        workspace/reports/{run_id}/
            report.md
            quality_markers.json
            gate_results.json
            metadata.json
    """

    def __init__(self, base_dir: str) -> None:
        self._base_dir = base_dir
        self._reports_dir = os.path.join(base_dir, "reports")
        os.makedirs(self._reports_dir, exist_ok=True)

    def save_report(
        self,
        run_id: str,
        report: str,
        quality_markers: dict[str, Any],
        gate_results: dict[int, GateResult],
    ) -> str:
        """保存报告版本，返回版本路径。"""
        report_dir = os.path.join(self._reports_dir, run_id)
        os.makedirs(report_dir, exist_ok=True)

        with open(os.path.join(report_dir, "report.md"), "w", encoding="utf-8") as f:
            f.write(report)

        with open(os.path.join(report_dir, "quality_markers.json"), "w", encoding="utf-8") as f:
            json.dump(quality_markers, f, ensure_ascii=False, indent=2, default=str)

        gate_data = {}
        for num, gr in gate_results.items():
            gate_data[str(num)] = {
                "state": gr.state.value,
                "score": gr.score,
                "errors": list(gr.errors),
                "warnings": list(gr.warnings),
                "execution_time": gr.execution_time,
            }
        with open(os.path.join(report_dir, "gate_results.json"), "w", encoding="utf-8") as f:
            json.dump(gate_data, f, ensure_ascii=False, indent=2)

        metadata = {
            "run_id": run_id,
            "created_at": datetime.now().isoformat(),
            "report_length": len(report),
            "quality_degraded": quality_markers.get("quality_degraded", False),
        }
        with open(os.path.join(report_dir, "metadata.json"), "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        return report_dir

    def load_report(self, run_id: str) -> dict[str, Any] | None:
        """加载报告版本。"""
        report_dir = os.path.join(self._reports_dir, run_id)
        report_path = os.path.join(report_dir, "report.md")
        if not os.path.exists(report_path):
            return None

        result: dict[str, Any] = {"run_id": run_id}
        with open(report_path, encoding="utf-8") as f:
            result["report"] = f.read()

        qm_path = os.path.join(report_dir, "quality_markers.json")
        if os.path.exists(qm_path):
            with open(qm_path, encoding="utf-8") as f:
                result["quality_markers"] = json.load(f)

        gr_path = os.path.join(report_dir, "gate_results.json")
        if os.path.exists(gr_path):
            with open(gr_path, encoding="utf-8") as f:
                result["gate_results"] = json.load(f)

        meta_path = os.path.join(report_dir, "metadata.json")
        if os.path.exists(meta_path):
            with open(meta_path, encoding="utf-8") as f:
                result["metadata"] = json.load(f)

        return result
