"""
审计日志协议与文件系统实现。

记录每次 Gate 执行的输入/输出/修复，支持追溯和回归测试。
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from ..contracts.types import GateResult, RepairRecord


@runtime_checkable
class AuditLogProtocol(Protocol):
    """审计日志协议。"""

    def log_gate_execution(
        self,
        run_id: str,
        gate_num: int,
        result: GateResult,
        repair_records: tuple[RepairRecord, ...] = (),
    ) -> None:
        """记录一次 Gate 执行。"""
        ...

    def get_gate_history(self, run_id: str) -> list[dict[str, Any]]:
        """获取某次运行的所有 Gate 执行记录。"""
        ...


class FileAuditLog:
    """文件系统审计日志实现（JSONL 格式）。

    存储结构：
        workspace/audit_logs/{run_id}.jsonl
    """

    def __init__(self, base_dir: str) -> None:
        self._base_dir = base_dir
        self._log_dir = os.path.join(base_dir, "audit_logs")
        os.makedirs(self._log_dir, exist_ok=True)

    def log_gate_execution(
        self,
        run_id: str,
        gate_num: int,
        result: GateResult,
        repair_records: tuple[RepairRecord, ...] = (),
    ) -> None:
        """记录一次 Gate 执行。"""
        entry = {
            "run_id": run_id,
            "gate_num": gate_num,
            "state": result.state.value,
            "score": result.score,
            "errors": list(result.errors),
            "warnings": list(result.warnings),
            "execution_time": result.execution_time,
            "timestamp": result.timestamp or datetime.now().isoformat(),
            "repair_records": [
                {
                    "chapter_num": r.chapter_num,
                    "rule_id": r.rule_id,
                    "before_value": r.before_value,
                    "after_value": r.after_value,
                    "repair_type": r.repair_type,
                    "confidence": r.confidence,
                }
                for r in repair_records
            ],
        }
        log_path = os.path.join(self._log_dir, f"{run_id}.jsonl")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def get_gate_history(self, run_id: str) -> list[dict[str, Any]]:
        """获取某次运行的所有 Gate 执行记录。"""
        log_path = os.path.join(self._log_dir, f"{run_id}.jsonl")
        if not os.path.exists(log_path):
            return []
        entries = []
        with open(log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries
