"""
输入快照协议与文件系统实现。

不可变输入快照，用于回溯和回归测试。
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SnapshotProtocol(Protocol):
    """输入快照协议。"""

    def save_snapshot(
        self,
        run_id: str,
        wind_data: dict[str, Any],
        filing_data: dict[str, Any] | None = None,
        facts: dict[str, Any] | None = None,
    ) -> str:
        """保存不可变快照，返回 snapshot_id。"""
        ...

    def load_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        """加载快照。"""
        ...

    def list_snapshots(self) -> list[str]:
        """列出所有快照 ID。"""
        ...


class FileSnapshot:
    """文件系统快照实现。

    存储结构：
        workspace/snapshots/{snapshot_id}/
            wind_data.json
            filing_data.json (optional)
            facts.json (optional)
            metadata.json
    """

    def __init__(self, base_dir: str) -> None:
        self._base_dir = base_dir
        self._snap_dir = os.path.join(base_dir, "snapshots")
        os.makedirs(self._snap_dir, exist_ok=True)

    def save_snapshot(
        self,
        run_id: str,
        wind_data: dict[str, Any],
        filing_data: dict[str, Any] | None = None,
        facts: dict[str, Any] | None = None,
    ) -> str:
        """保存不可变快照，返回 snapshot_id。"""
        # 用内容哈希作为 snapshot_id（相同输入 → 相同 ID，去重）
        content_str = json.dumps(wind_data, sort_keys=True, ensure_ascii=False, default=str)
        snapshot_id = hashlib.sha256(content_str.encode()).hexdigest()[:12]

        snap_dir = os.path.join(self._snap_dir, snapshot_id)
        os.makedirs(snap_dir, exist_ok=True)

        with open(os.path.join(snap_dir, "wind_data.json"), "w", encoding="utf-8") as f:
            json.dump(wind_data, f, ensure_ascii=False, indent=2, default=str)

        if filing_data is not None:
            with open(os.path.join(snap_dir, "filing_data.json"), "w", encoding="utf-8") as f:
                json.dump(filing_data, f, ensure_ascii=False, indent=2, default=str)

        if facts is not None:
            with open(os.path.join(snap_dir, "facts.json"), "w", encoding="utf-8") as f:
                json.dump(facts, f, ensure_ascii=False, indent=2, default=str)

        metadata = {
            "snapshot_id": snapshot_id,
            "run_id": run_id,
            "created_at": __import__("datetime").datetime.now().isoformat(),
            "has_filing": filing_data is not None,
            "has_facts": facts is not None,
        }
        with open(os.path.join(snap_dir, "metadata.json"), "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        return snapshot_id

    def load_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        """加载快照。"""
        snap_dir = os.path.join(self._snap_dir, snapshot_id)
        wind_path = os.path.join(snap_dir, "wind_data.json")
        if not os.path.exists(wind_path):
            return None

        result: dict[str, Any] = {}
        with open(wind_path, encoding="utf-8") as f:
            result["wind_data"] = json.load(f)

        filing_path = os.path.join(snap_dir, "filing_data.json")
        if os.path.exists(filing_path):
            with open(filing_path, encoding="utf-8") as f:
                result["filing_data"] = json.load(f)

        facts_path = os.path.join(snap_dir, "facts.json")
        if os.path.exists(facts_path):
            with open(facts_path, encoding="utf-8") as f:
                result["facts"] = json.load(f)

        meta_path = os.path.join(snap_dir, "metadata.json")
        if os.path.exists(meta_path):
            with open(meta_path, encoding="utf-8") as f:
                result["metadata"] = json.load(f)

        return result

    def list_snapshots(self) -> list[str]:
        """列出所有快照 ID。"""
        if not os.path.exists(self._snap_dir):
            return []
        return [
            d for d in os.listdir(self._snap_dir)
            if os.path.isdir(os.path.join(self._snap_dir, d))
        ]
