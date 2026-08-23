"""
Qual v9 跨层稳定协议定义（Protocol）。

所有 Gate / 检查器 / 修复器 / 数值仓储 / 写入管线的接口协议在此定义。
参照：dayu-agent contracts/protocols.py（ToolExecutor / ToolTraceRecorder Protocol）
      + dayu fins/storage/repository_protocols.py（窄 Protocol 设计）
      + dayu services/write_pipeline/（audit/confirm/repair 闭环）
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .types import (
    AuditDecision,
    CheckResult,
    DataPoint,
    FactBinding,
    GateContext,
    GateResult,
    RepairAction,
    ReviewIssue,
    WritePipelinePhase,
)


@runtime_checkable
class GateProtocol(Protocol):
    """Gate 执行协议（所有 Gate0-8 必须实现）。

    方法:
        execute: 执行 Gate，返回 GateResult。
        check_criteria: 检查通过标准。
    """

    def execute(self, ctx: GateContext) -> GateResult:
        """执行 Gate，返回结果。"""
        ...

    def check_criteria(self, ctx: GateContext) -> bool:
        """检查通过标准。"""
        ...


@runtime_checkable
class CheckerProtocol(Protocol):
    """检查器协议（3 个检查器必须实现）。

    方法:
        check: 执行检查，返回 CheckResult。
        name: 检查器名称。
    """

    @property
    def name(self) -> str:
        """检查器名称。"""
        ...

    def check(self, chapters: dict[int, str], ctx: GateContext) -> CheckResult:
        """执行检查，返回统一的 CheckResult。"""
        ...


@runtime_checkable
class RepairerProtocol(Protocol):
    """修复器协议（ADVC / PGNB / bind_fuzzy_dates 必须实现）。

    方法:
        repair: 执行修复，返回修复后内容和修复记录。
    """

    def repair(
        self,
        content: str,
        issues: list[ReviewIssue],
        ctx: GateContext,
    ) -> tuple[str, list[RepairAction]]:
        """执行修复，返回 (修复后内容, 修复记录列表)。"""
        ...


# ====================================================================
# 数值仓储协议（对标 dayu fins/storage/repository_protocols.py）
# ====================================================================

@runtime_checkable
class DataStoreProtocol(Protocol):
    """数值仓储窄协议——LLM 只能通过此接口读取数据。

    对标 dayu 的 SourceDocumentRepositoryProtocol + ProcessedDocumentRepositoryProtocol：
    - 只读接口供 Gate3 生成、Gate4 校验使用
    - set 方法仅供初始化阶段（Wind 数据加载时调用）
    - get 返回 None 表示无数据（不抛异常）
    """

    def get(self, key: str, fiscal_year: int | None = None) -> float | None:
        """获取数值（指定 key + 可选财年）。"""
        ...

    def set(self, key: str, value: float, unit: str,
            fiscal_year: int | None = None, source: str = "Wind") -> None:
        """写入数值（仅供初始化阶段）。"""
        ...

    def get_metric_points(self, metric: str) -> list[DataPoint]:
        """获取某指标的全部财年锚点。"""
        ...

    def attribute_value(
        self, metric: str, value: float, tolerance: float = 0.01,
    ) -> tuple[int | None, float | None]:
        """财年归因：数值 → 匹配的财年。"""
        ...


# ====================================================================
# 写入管线协议（对标 dayu write_pipeline/ ChapterAuditCoordinator）
# ====================================================================

@runtime_checkable
class WritePipelineProtocol(Protocol):
    """审计/确认/修复闭环协议（对标 dayu write_pipeline）。

    流转：DRAFT → REVIEW → REPAIR → CONFIRM → COMMIT
    """

    @property
    def phase(self) -> WritePipelinePhase:
        """当前阶段。"""
        ...

    def review(self, chapters: dict[int, str], ctx: Any) -> AuditDecision:
        """审计检查，返回 AuditDecision。"""
        ...

    def repair(
        self, chapters: dict[int, str],
        issues: tuple[ReviewIssue, ...], ctx: Any,
    ) -> tuple[dict[int, str], tuple[RepairAction, ...]]:
        """确定性修复，返回 (修复后章节, 修复记录)。"""
        ...

    def confirm(self, chapters: dict[int, str], ctx: Any) -> bool:
        """修复后复验，返回是否通过。"""
        ...

    def run_loop(
        self, chapters: dict[int, str], ctx: Any,
    ) -> tuple[dict[int, str], tuple[ReviewIssue, ...]]:
        """执行完整 review→repair→confirm 循环。"""
        ...


# ====================================================================
# 事实提取协议（对标 dayu fins/tools/ FinsToolService）
# ====================================================================

@runtime_checkable
class FactExtractorProtocol(Protocol):
    """事实提取协议（对标 dayu fins/tools/）。

    方法:
        extract: 从财报文本提取结构化事实。
        bind_to_anchor: 把提取结果绑定到 DataStoreProtocol。
    """

    def extract(self, filing_text: str, **kwargs: Any) -> dict[str, Any]:
        """从财报文本提取结构化事实。"""
        ...

    def bind_to_anchor(
        self, facts: dict[str, Any], store: DataStoreProtocol,
    ) -> tuple[FactBinding, ...]:
        """把提取结果绑定到数值仓储，返回绑定记录。"""
        ...


# ====================================================================
# 事件发射协议（对标 dayu engine/events.py EventSink）
# ====================================================================

@runtime_checkable
class EventSink(Protocol):
    """事件发射协议——所有需要发布事件的组件实现此接口。

    方法:
        emit: 发射一个事件。
    """

    def emit(self, event: Any) -> None:
        """发射事件（事件类型由调用方定义）。"""
        ...
