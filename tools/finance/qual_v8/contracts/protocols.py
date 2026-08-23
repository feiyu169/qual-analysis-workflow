"""
Qual v9 跨层稳定协议定义（Protocol）。

所有 Gate / 检查器 / 修复器的接口协议在此定义。
参照：dayu-agent contracts/protocols.py（ToolExecutor / ToolTraceRecorder Protocol）
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from .types import (
    ConsistencyIssue,
    GateContext,
    GateResult,
    NumericViolation,
    RepairAction,
    ReviewIssue,
    StructuralViolation,
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
        check: 执行检查，返回违规列表。
        name: 检查器名称。
    """

    @property
    def name(self) -> str:
        """检查器名称。"""
        ...

    def check(self, chapters: dict[int, str], ctx: GateContext) -> tuple[
        list[NumericViolation] | list[StructuralViolation] | list[ConsistencyIssue],
        ...,
    ]:
        """执行检查，返回违规列表。"""
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
