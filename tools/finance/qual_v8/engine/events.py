"""
结构化事件模型（参照 dayu-agent engine/events.py）。

定义 Engine 内部的事件类型与数据结构，用于 Gate 执行的事件流。
消除 dict 传事件，统一数据结构便于透传与日志记录。

事件分类：
- 内容事件: content_delta / content_complete
- Gate 事件: gate_start / gate_complete / gate_failed / gate_degraded
- 检查事件: checker_warning / checker_error
- 修复事件: repair_applied / repair_failed
- 控制事件: error / warning / done
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class QualEventType(str, Enum):  # noqa: UP042
    """Qual 事件类型枚举（对齐 dayu engine/events.py + write_pipeline）。"""

    # 内容生成事件
    CONTENT_DELTA = "content_delta"
    CONTENT_COMPLETE = "content_complete"

    # Gate 生命周期事件
    GATE_START = "gate_start"
    GATE_COMPLETE = "gate_complete"
    GATE_FAILED = "gate_failed"
    GATE_DEGRADED = "gate_degraded"
    GATE_BLOCKED = "gate_blocked"     # 新增：enforce 阻断
    GATE_SKIPPED = "gate_skipped"     # 新增：熔断跳过

    # Run 阶段事件（对标 dayu host RunPhase）
    PHASE_START = "phase_start"
    PHASE_COMPLETE = "phase_complete"

    # 写入管线事件（对标 dayu write_pipeline）
    DRAFT_START = "draft_start"
    REVIEW_START = "review_start"
    REPAIR_APPLIED = "repair_applied"
    CONFIRM_PASSED = "confirm_passed"
    CONFIRM_FAILED = "confirm_failed"
    COMMIT_DONE = "commit_done"

    # 检查器事件
    CHECKER_WARNING = "checker_warning"
    CHECKER_ERROR = "checker_error"

    # 修复事件
    REPAIR_FAILED = "repair_failed"

    # 控制事件
    ERROR = "error"
    WARNING = "warning"
    DONE = "done"

    # 元数据事件
    METADATA = "metadata"


@dataclass
class QualEvent:
    """Qual 标准事件（不可变语义）。

    Attributes:
        type: 事件类型。
        data: 事件数据（类型根据 type 不同而不同）。
        gate_num: 关联的 Gate 编号（可选）。
        chapter_num: 关联的章节编号（可选）。
        metadata: 额外元数据。
    """
    type: QualEventType
    data: Any = None
    gate_num: int | None = None
    chapter_num: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典（方便序列化）。"""
        result: dict[str, Any] = {"type": self.type.value}
        if self.data is not None:
            result["data"] = self.data
        if self.gate_num is not None:
            result["gate_num"] = self.gate_num
        if self.chapter_num is not None:
            result["chapter_num"] = self.chapter_num
        if self.metadata:
            result["metadata"] = self.metadata
        return result


# ============================================================
# 便捷构造函数
# ============================================================

def gate_start(gate_num: int, gate_name: str) -> QualEvent:
    """Gate 开始事件。"""
    return QualEvent(
        type=QualEventType.GATE_START,
        data={"gate_name": gate_name},
        gate_num=gate_num,
    )


def gate_complete(gate_num: int, score: float, elapsed: float) -> QualEvent:
    """Gate 完成事件。"""
    return QualEvent(
        type=QualEventType.GATE_COMPLETE,
        data={"score": score, "elapsed_seconds": elapsed},
        gate_num=gate_num,
    )


def gate_failed(gate_num: int, errors: list[str]) -> QualEvent:
    """Gate 失败事件。"""
    return QualEvent(
        type=QualEventType.GATE_FAILED,
        data={"errors": errors},
        gate_num=gate_num,
    )


def gate_degraded(gate_num: int, warnings: list[str]) -> QualEvent:
    """Gate 降级事件。"""
    return QualEvent(
        type=QualEventType.GATE_DEGRADED,
        data={"warnings": warnings},
        gate_num=gate_num,
    )


def checker_warning(gate_num: int, chapter_num: int, message: str) -> QualEvent:
    """检查器警告事件。"""
    return QualEvent(
        type=QualEventType.CHECKER_WARNING,
        data={"message": message},
        gate_num=gate_num,
        chapter_num=chapter_num,
    )


def repair_applied(gate_num: int, chapter_num: int, repair_type: str, detail: str) -> QualEvent:
    """修复应用事件。"""
    return QualEvent(
        type=QualEventType.REPAIR_APPLIED,
        data={"repair_type": repair_type, "detail": detail},
        gate_num=gate_num,
        chapter_num=chapter_num,
    )


def error_event(message: str, gate_num: int | None = None) -> QualEvent:
    """错误事件。"""
    return QualEvent(
        type=QualEventType.ERROR,
        data={"message": message},
        gate_num=gate_num,
    )


def done_event(report_length: int, elapsed: float) -> QualEvent:
    """完成事件。"""
    return QualEvent(
        type=QualEventType.DONE,
        data={"report_length": report_length, "elapsed_seconds": elapsed},
    )


# ============================================================
# 事件收集器（用于测试和日志）
# ============================================================

class EventCollector:
    """事件收集器，收集所有事件用于测试和日志。"""

    def __init__(self) -> None:
        self._events: list[QualEvent] = []

    def emit(self, event: QualEvent) -> None:
        """收集事件。"""
        self._events.append(event)

    @property
    def events(self) -> list[QualEvent]:
        return list(self._events)

    def get_events_by_type(self, event_type: QualEventType) -> list[QualEvent]:
        """按类型过滤事件。"""
        return [e for e in self._events if e.type == event_type]

    def get_events_for_gate(self, gate_num: int) -> list[QualEvent]:
        """获取某 Gate 的所有事件。"""
        return [e for e in self._events if e.gate_num == gate_num]

    def clear(self) -> None:
        """清空事件。"""
        self._events.clear()
