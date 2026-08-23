"""
Gate 执行引擎（从 workflow.py 拆出）。

负责 Gate 0-8 的顺序执行、重试、熔断、墙钟守卫。
workflow.py 只保留 QualWorkflow 门面类，GateRunner 承担实际执行逻辑。

设计参照：dayu-agent host/executor.py（Gate 生命周期管理）
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

from .contracts.types import (
    GateContext,
    GateResult,
    GateState,
)
from .core.audit_logger import AuditLogger
from .core.circuit_breaker import CircuitBreaker
from .core.error_classifier import ErrorClassifier
from .core.gate_engine import GateEngine
from .core.state_machine import GateState as LegacyGateState
from .core.state_machine import StateMachine, WorkflowState
from .core.supervisor import FlowComplianceChecker
from .engine.events import EventCollector, gate_complete, gate_failed, gate_start

logger = logging.getLogger(__name__)


class GateRunner:
    """Gate 执行引擎：顺序执行 Gate 0-8，含熔断器/重试/墙钟守卫。

    从 workflow.py QualWorkflow.execute() 拆出，workflow.py 只保留门面调用。

    Attributes:
        gate_engine: Gate 注册 + 分发引擎。
        state_machine: Gate 状态机。
        circuit_breakers: 每 Gate 一个熔断器。
        supervisor: 第三方监督。
        audit_logger: 审计日志。
        event_collector: 事件收集器。
    """

    def __init__(
        self,
        gate_engine: GateEngine,
        state_machine: StateMachine,
        circuit_breakers: dict[int, CircuitBreaker],
        supervisor: FlowComplianceChecker,
        audit_logger: AuditLogger,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.gate_engine = gate_engine
        self.state_machine = state_machine
        self.circuit_breakers = circuit_breakers
        self.supervisor = supervisor
        self.audit_logger = audit_logger
        self.event_collector = EventCollector()
        self.config = config or {}

    def run_all(
        self,
        ctx: GateContext,
        gate_attempts: int = 3,
    ) -> dict[int, GateResult]:
        """顺序执行 Gate 0-8，返回 gate_results。

        Args:
            ctx: Gate 执行上下文。
            gate_attempts: 每 Gate 最大执行次数。

        Returns:
            {gate_num: GateResult} 字典。
        """
        gate_results: dict[int, GateResult] = {}
        deadline = ctx.wall_deadline

        for gate_num in range(9):
            # 墙钟检查
            if deadline and time.monotonic() > deadline:
                logger.error(f"全局墙钟预算耗尽，Gate {gate_num} 起全部标记失败")
                for g in range(gate_num, 9):
                    gate_results[g] = GateResult(
                        gate_num=g, state=GateState.FAILED,
                        errors=("全局墙钟预算耗尽",),
                    )
                break

            result = self._run_single_gate(gate_num, ctx, gate_attempts)
            gate_results[gate_num] = result

            # 更新 ctx 中的 gate_results（供后续 Gate 读取）
            ctx = ctx.with_gate_result(gate_num, result)

            # B1-2 分级阻断（enforce 模式）
            if ctx.qual_mode == "enforce" and gate_num in {4, 8} and result.state == GateState.FAILED:
                    from .workflow_context import ComplianceBlockedException
                    err_text = "; ".join(result.errors[:6])
                    critical_keywords = ["数值矛盾", "财年错位", "跨章节一致性", "占位符", "空壳"]
                    if any(kw in err_text for kw in critical_keywords):
                        self.state_machine.transition_workflow(WorkflowState.FAILED)
                        raise ComplianceBlockedException(
                            f"Gate {gate_num} 关键错误阻断: {result.errors[:3]}"
                        )

        return gate_results

    def _run_single_gate(
        self,
        gate_num: int,
        ctx: GateContext,
        max_attempts: int,
    ) -> GateResult:
        """单 Gate 执行（含重试/熔断）。

        Args:
            gate_num: Gate 编号。
            ctx: Gate 执行上下文。
            max_attempts: 最大执行次数。

        Returns:
            GateResult。
        """
        self.event_collector.emit(gate_start(gate_num, f"Gate{gate_num}"))

        # 熔断器检查
        if not self.circuit_breakers[gate_num].can_execute():
            result = GateResult(
                gate_num=gate_num, state=GateState.FAILED,
                errors=("熔断器打开，跳过执行",),
            )
            self.event_collector.emit(gate_failed(gate_num, list(result.errors)))
            return result

        # 转换状态
        self.state_machine.transition_gate(gate_num, LegacyGateState.RUNNING)
        self.audit_logger.log(
            run_id=ctx.ticker, gate_num=gate_num,
            action="gate_started", details={},
        )

        result: GateResult | None = None
        attempts = 0

        while attempts < max_attempts:
            start_time = datetime.now()
            try:
                gate = self.gate_engine.gates[gate_num]
                legacy_result = self.gate_engine.execute_gate(gate_num, self._ctx_to_dict(ctx))
                end_time = datetime.now()
                elapsed = (end_time - start_time).total_seconds()

                # 转换为 contracts.GateResult
                state = GateState.PASSED if legacy_result.passed else GateState.FAILED
                result = GateResult(
                    gate_num=gate_num, state=state,
                    score=legacy_result.score,
                    errors=tuple(legacy_result.errors),
                    warnings=tuple(legacy_result.warnings),
                    execution_time=elapsed,
                    timestamp=datetime.now().isoformat(),
                )

                # check_criteria
                try:
                    _criteria_passed = gate.check_criteria(self._ctx_to_dict(ctx))
                except Exception as e:
                    logger.warning(f"Gate {gate_num} check_criteria 异常: {e}")

                if result.passed:
                    self.circuit_breakers[gate_num].record_success()
                    self.state_machine.transition_gate(gate_num, LegacyGateState.PASSED)
                    self.event_collector.emit(gate_complete(gate_num, result.score, elapsed))
                    break
                else:
                    classification = ErrorClassifier().classify_from_exception(
                        RuntimeError("; ".join(result.errors[:3]))
                    )
                    self.circuit_breakers[gate_num].record_failure(classification.error_type)
                    if gate.can_retry():
                        gate.increment_retry()
                        attempts += 1
                        continue
                    else:
                        self.state_machine.transition_gate(gate_num, LegacyGateState.FAILED)
                        self.event_collector.emit(gate_failed(gate_num, list(result.errors)))
                        break

            except Exception as e:
                logger.error(f"Gate {gate_num} 执行异常: {e}")
                result = GateResult(
                    gate_num=gate_num, state=GateState.FAILED,
                    errors=(f"执行异常: {e}",),
                    timestamp=datetime.now().isoformat(),
                )
                self.state_machine.transition_gate(gate_num, LegacyGateState.FAILED)
                self.event_collector.emit(gate_failed(gate_num, list(result.errors)))
                break

        # 审计日志
        self.audit_logger.log(
            run_id=ctx.ticker, gate_num=gate_num,
            action="gate_completed",
            details={
                "passed": result.passed if result else False,
                "score": result.score if result else 0.0,
                "state": result.state.value if result else "unknown",
            },
        )

        return result or GateResult(gate_num=gate_num, state=GateState.FAILED)

    @staticmethod
    def _ctx_to_dict(ctx: GateContext) -> dict[str, Any]:
        """将 GateContext 转换为旧 Gate 期望的 dict 格式（过渡期兼容）。"""
        return {
            "ticker": ctx.ticker,
            "company_name": ctx.company_name,
            "market": ctx.market,
            "qual_mode": ctx.qual_mode,
            "chapters": ctx.chapters,
            "wind_data": ctx.wind_data,
            "filing_data": ctx.filing_data,
            "gate_results": {k: {"passed": v.passed, "score": v.score, "errors": list(v.errors)}
                            for k, v in ctx.gate_results.items()},
            "llm_caller": ctx.llm_caller,
            "_wall_deadline": ctx.wall_deadline,
            "llm_call_budget": ctx.llm_call_budget,
            "advc_enable_t2": ctx.advc_enable_t2,
        }
