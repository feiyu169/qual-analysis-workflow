"""
Qual流程v8.4 - 主工作流引擎

整合所有Gate和组件
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .core.audit_logger import AuditLogger
from .core.circuit_breaker import CircuitBreaker
from .core.gate_engine import GateEngine, GateResult
from .core.state_machine import GateState, StateMachine, WorkflowState
from .core.supervisor import FlowComplianceChecker
from .engine.gate_dag import GateDAG
from .gates import (
    Gate0DataSourceValidation,
    Gate1TypeInference,
    Gate2DataCollection,
    Gate3ChapterWriting,
    Gate4AuditRepair,
    Gate5QualityEnhancement,
    Gate6Conclusion,
    Gate7ProblemTransformation,
    Gate8FinalValidation,
)
from .monitoring.alerts import AlertManager, MetricsCollector

logger = logging.getLogger(__name__)


# B1-2：enforce 分级阻断——关键错误关键词（数值矛盾/财年错位/占位符/量级）
# 命中任一 → ComplianceBlockedException；未命中（字段缺失/降级类）→ 降级标注不阻断
CRITICAL_GATE_ERROR_KEYWORDS = [
    "数值矛盾", "财年错位", "跨章节一致性", "量级", "矛盾",
    "占位符", "模板残留", "空壳", "空章",
]


def _is_critical_gate_error(err_text: str) -> bool:
    """B1-2：Gate 失败是否属关键错误（enforce 下阻断）"""
    if not err_text:
        return False
    return any(kw in err_text for kw in CRITICAL_GATE_ERROR_KEYWORDS)


@dataclass
class WorkflowConfig:
    """工作流配置"""
    max_retries: int = 3
    timeout_per_gate: int = 600  # 10分钟
    human_sla_working_hours: int = 30  # 分钟
    human_sla_non_working_hours: int = 240  # 分钟
    # v3.1 阶段 A 新增（docs/qual-loop-fix-design-v3.md）
    global_timeout_seconds: int = 5400          # 全局墙钟预算（90 分钟）
    max_llm_calls_per_gate: int = 200           # 单 Gate LLM 调用次数上限（v3.1 P1-1 60→200）
    shadow_skip_repair: bool = True             # shadow 模式 Gate4 跳过修复循环
    # P1（ADVC）：T2 低置信修复开关（弱签名+FY 上下文唯一仍自动替换；自证兜底）
    advc_enable_t2: bool = False                # 默认关——宁可不修不误修


# v3.1 P0-B-1/3：重试策略三模式（RETRY_POLICY 单一事实来源）
RETRY_POLICY = {
    # mode: {"gate_attempts": 执行次数, "gate_retries": 重试次数, "skip_repair": 是否跳过修复}
    "shadow": {"gate_attempts": 1, "gate_retries": 0, "skip_repair": True},
    "soft":   {"gate_attempts": 2, "gate_retries": 1, "skip_repair": False},
    "enforce": {"gate_attempts": 3, "gate_retries": 2, "skip_repair": False},
}


# 完整流程定义（与 workflow_context.WorkflowContext._get_flow_definition 保持一致，
# 供第三方监督使用；gate_0~8 全量定义，不再留注释占位）
_FLOW_DEFINITION: dict[str, Any] = {
    "gate_0": {
        "name": "数据源验证",
        "preconditions": [],
        "execution_steps": [
            {"name": "财报获取", "order": 1, "required": True},
            {"name": "Wind数据获取", "order": 2, "required": True},
            {"name": "严苛验证", "order": 3, "required": True},
        ],
        "pass_criteria": [
            {"name": "财报文件存在", "type": "condition", "condition": "filing_exists"},
            {"name": "Wind字段覆盖率", "type": "quantitative", "metric": "wind_coverage", "threshold": 0.95},
        ],
    },
    "gate_1": {
        "name": "类型推断 + 数据提取",
        "preconditions": [{"name": "Gate 0通过", "type": "gate_passed", "gate_num": 0}],
        "execution_steps": [
            {"name": "推断市场类型", "order": 1, "required": True},
            {"name": "提取结构化事实", "order": 2, "required": True},
            {"name": "交叉验证", "order": 3, "required": True},
        ],
        "pass_criteria": [
            {"name": "市场类型正确率", "type": "quantitative", "metric": "market_type_accuracy", "threshold": 0.95},
        ],
    },
    "gate_2": {
        "name": "数据收集 + 参数提取",
        "preconditions": [{"name": "Gate 1通过", "type": "gate_passed", "gate_num": 1}],
        "execution_steps": [
            {"name": "收集Wind数据", "order": 1, "required": True},
            {"name": "提取DCF参数", "order": 2, "required": True},
        ],
        "pass_criteria": [
            {"name": "FCF非零", "type": "condition", "condition": "fcf_nonzero"},
            {"name": "WACC范围", "type": "condition", "condition": "wacc_in_range"},
            {"name": "永续增长率范围", "type": "condition", "condition": "terminal_growth_in_range"},
            {"name": "营收增长率范围", "type": "condition", "condition": "revenue_growth_in_range"},
            {"name": "税率范围", "type": "condition", "condition": "tax_rate_in_range"},
        ],
    },
    "gate_3": {
        "name": "逐章写作",
        "preconditions": [{"name": "Gate 2通过", "type": "gate_passed", "gate_num": 2}],
        "execution_steps": [
            {"name": "生成大纲", "order": 1, "required": True},
            {"name": "分章生成", "order": 2, "required": True},
            {"name": "交叉验证", "order": 3, "required": True},
        ],
        "pass_criteria": [
            {"name": "章节完整性", "type": "condition", "condition": "chapters_complete"},
            {"name": "无占位符", "type": "condition", "condition": "no_placeholders"},
            {"name": "数据一致性", "type": "condition", "condition": "data_consistent"},
        ],
    },
    "gate_4": {
        "name": "审计修复 + 深度审查",
        "preconditions": [{"name": "Gate 3通过", "type": "gate_passed", "gate_num": 3}],
        "execution_steps": [
            {"name": "形式审查", "order": 1, "required": True},
            {"name": "实质审查", "order": 2, "required": True},
            {"name": "修复循环", "order": 3, "required": True},
        ],
        "pass_criteria": [
            {"name": "格式错误数", "type": "quantitative", "metric": "format_errors", "threshold": 0},
            {"name": "逻辑矛盾数", "type": "quantitative", "metric": "logic_contradictions", "threshold": 2},
            {"name": "风险提示覆盖", "type": "quantitative", "metric": "risk_categories_covered", "threshold": 8},
        ],
    },
    "gate_5": {
        "name": "质量增强 + 组件集成",
        "preconditions": [{"name": "Gate 4通过", "type": "gate_passed", "gate_num": 4}],
        "execution_steps": [
            {"name": "估值计算", "order": 1, "required": True},
            {"name": "组件集成", "order": 2, "required": True},
            {"name": "交叉验证", "order": 3, "required": True},
        ],
        "pass_criteria": [
            {"name": "估值计算正确", "type": "condition", "condition": "valuation_correct"},
            {"name": "组件集成成功", "type": "condition", "condition": "components_integrated"},
        ],
    },
    "gate_6": {
        "name": "综合结论 + 决策章",
        "preconditions": [{"name": "Gate 5通过", "type": "gate_passed", "gate_num": 5}],
        "execution_steps": [
            {"name": "生成决策章", "order": 1, "required": True},
            {"name": "生成概览章", "order": 2, "required": True},
        ],
        "pass_criteria": [
            {"name": "决策章存在", "type": "condition", "condition": "decision_chapter_exists"},
            {"name": "投资评级有效", "type": "condition", "condition": "rating_valid"},
        ],
    },
    "gate_7": {
        "name": "问题转化 + 记忆存储",
        "preconditions": [{"name": "Gate 6通过", "type": "gate_passed", "gate_num": 6}],
        "execution_steps": [
            {"name": "问题转化", "order": 1, "required": True},
            {"name": "记忆存储", "order": 2, "required": True},
        ],
        "pass_criteria": [
            {"name": "问题转化成功", "type": "condition", "condition": "transformation_success"},
        ],
    },
    "gate_8": {
        "name": "最终验证",
        "preconditions": [{"name": "Gate 7通过", "type": "gate_passed", "gate_num": 7}],
        "execution_steps": [
            {"name": "最终质量评估", "order": 1, "required": True},
            {"name": "人工确认", "order": 2, "required": True},
        ],
        "pass_criteria": [
            {"name": "所有Gate通过", "type": "condition", "condition": "all_gates_passed"},
            {"name": "人工确认", "type": "condition", "condition": "human_confirmed"},
        ],
    },
}


class QualWorkflow:
    """Qual工作流引擎"""

    def __init__(self, config: WorkflowConfig | None = None):
        self.config = config or WorkflowConfig()
        self.run_id = str(uuid.uuid4())

        # 初始化组件
        self.state_machine = StateMachine()
        self.gate_engine = GateEngine()
        self.audit_logger = AuditLogger()
        self.supervisor = FlowComplianceChecker(self._get_flow_definition())
        self.alert_manager = AlertManager()
        self.metrics_collector = MetricsCollector()
        # 每 Gate 一个熔断器（v3.1 P0-1：failure_threshold 3→2，使 enforce 第3次尝试可被短路）
        self.circuit_breakers: dict[int, CircuitBreaker] = {
            n: CircuitBreaker(name=f"gate_{n}", failure_threshold=2, reset_timeout=60)
            for n in range(9)
        }

        # 注册Gate
        self._register_gates()

    def _get_flow_definition(self) -> dict[str, Any]:
        """获取流程定义（gate_0~8 全量，供第三方监督）"""
        return _FLOW_DEFINITION

    def _register_gates(self):
        """注册所有Gate"""
        gates = [
            Gate0DataSourceValidation(),
            Gate1TypeInference(),
            Gate2DataCollection(),
            Gate3ChapterWriting(),
            Gate4AuditRepair(),
            Gate5QualityEnhancement(),
            Gate6Conclusion(),
            Gate7ProblemTransformation(),
            Gate8FinalValidation(),
        ]

        for gate in gates:
            self.gate_engine.register_gate(gate)

        # 初始化状态机
        self.state_machine.initialize_gates(list(range(9)))  # Gate 0-8

    def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        """执行工作流

        context 约定（由调用方/适配层提供）：
            ticker / company_name / market / wind_data / filing_data / llm_caller
            qual_mode: "shadow"（默认，记录不阻断）| "soft"（告警）| "enforce"（阻断）
            human_confirmed: 是否视为人工确认通过（默认 True）
        """
        logger.info(f"开始执行工作流: {self.run_id}")

        # 运行模式（shadow 兼容旧行为；enforce 才阻断）
        qual_mode = str(context.get("qual_mode", "shadow")).lower()
        human_confirmed = bool(context.get("human_confirmed", True))  # noqa: F841

        # 记录开始
        self.audit_logger.log(
            run_id=self.run_id,
            gate_num=None,
            action="workflow_started",
            details={"context_keys": list(context.keys()), "qual_mode": qual_mode},
        )

        # 转换工作流状态
        self.state_machine.transition_workflow(WorkflowState.RUNNING)

        results = {}
        gate_results = {}

        # v3.1 P0-B-8：全局墙钟预算 + 调用预算注入 context
        import time as _time
        _wall_start = _time.monotonic()
        context["_wall_deadline"] = _wall_start + self.config.global_timeout_seconds
        context["llm_call_budget"] = self.config.max_llm_calls_per_gate
        # shadow_skip_repair 消费方：Gate4 读取（v3.1 P0-B-10）
        context["shadow_skip_repair"] = (
            qual_mode == "shadow" and self.config.shadow_skip_repair
        )
        # P1（ADVC）：T2 低置信修复开关——消费方：Gate4 修复循环 / Gate8 组装闸门救援 sweep
        context["advc_enable_t2"] = self.config.advc_enable_t2
        # v3.1 P0-B-1：重试策略（按模式取表）
        retry_policy = RETRY_POLICY.get(qual_mode, RETRY_POLICY["soft"])
        gate_attempts = retry_policy["gate_attempts"]

        # v3.1 P0-B-1：单点包装主 caller——Gate1/3/4/5/6/8 全部经 context["llm_caller"] 调用，
        # 包装后 Gate3 写作主链路获得调用级墙钟检查（与 gate3 透传 deadline 双保险）
        if context.get("llm_caller") is not None:
            from ..workflow import (
                _deadline_guard,  # 惰性 import（gate3 同款，防循环依赖）
            )

            context["llm_caller"] = _deadline_guard(context["llm_caller"], context["_wall_deadline"])

        # v9 GateDAG 依赖图（替代旧 prerequisites 硬阻断）
        gate_dag = GateDAG()

        # 执行每个Gate
        for gate_num in range(9):  # Gate 0-8
            logger.info(f"执行Gate {gate_num} (mode={qual_mode})")

            # v3.1 P0-B-8：全局墙钟预算检查（每 Gate 循环顶部）
            if _time.monotonic() > context["_wall_deadline"]:
                logger.error(f"全局墙钟预算耗尽（{self.config.global_timeout_seconds}s），强制终止")
                for _g in range(gate_num, 9):
                    results[f"gate_{_g}"] = {
                        "passed": False, "score": 0.0, "execution_time": 0.0,
                        "errors": ["全局墙钟预算耗尽"], "check_criteria_passed": False,
                    }
                break

            # v9 GateDAG 依赖判断（HARD deps 阻断，SOFT deps 降级）
            # 直接传 gate_results 全集（含 GateResult 对象和 dict），不做过滤
            can_run, is_degraded = gate_dag.can_execute(gate_num, gate_results)
            if not can_run:
                # HARD 依赖未满足 → 标记 BLOCKED（替代旧 prerequisites 硬阻断）
                logger.warning(f"Gate {gate_num} BLOCKED（HARD 依赖未满足）")
                results[f"gate_{gate_num}"] = {
                    "passed": False, "score": 0.0, "execution_time": 0.0,
                    "errors": [f"Gate {gate_num} BLOCKED: HARD 依赖未满足"],
                    "check_criteria_passed": False,
                    "state": "blocked",
                }
                gate_results[gate_num] = {"passed": False, "state": "blocked"}
                continue

            if is_degraded:
                logger.info(f"Gate {gate_num} 降级执行（SOFT 依赖有 FAILED）")

            # 记录Gate开始
            self.audit_logger.log(
                run_id=self.run_id,
                gate_num=gate_num,
                action="gate_started",
                details={},
            )

            # 转换Gate状态
            self.state_machine.transition_gate(gate_num, GateState.RUNNING)

            gate = self.gate_engine.gates[gate_num]

            # 执行Gate（v3.1 P0-B-1：重试次数按 RETRY_POLICY 模式取）
            result: GateResult | None = None
            attempts = 0
            max_attempts = gate_attempts
            while attempts < max_attempts:
                if not self.circuit_breakers[gate_num].can_execute():
                    result = GateResult(
                        gate_num=gate_num, passed=False, score=0.0,
                        details={"error": "熔断器打开"},
                        errors=["熔断器打开，跳过执行"], warnings=[],
                        execution_time=0.0, timestamp=datetime.now().isoformat(),
                    )
                    break
                if attempts > 0:
                    context["gate_retry_errors"] = result.errors if result else []
                    logger.info(f"Gate {gate_num} 第{attempts}次重试 (上次errors={context['gate_retry_errors'][:2]})")

                start_time = datetime.now()
                try:
                    result = self.gate_engine.execute_gate(gate_num, context)
                except Exception as e:
                    logger.error(f"Gate {gate_num} 执行异常: {e}")
                    result = GateResult(
                        gate_num=gate_num, passed=False, score=0.0,
                        details={"error": str(e)}, errors=[f"执行异常: {e}"],
                        warnings=[], execution_time=0.0,
                        timestamp=datetime.now().isoformat(),
                    )
                end_time = datetime.now()
                result.execution_time = (end_time - start_time).total_seconds()

                # 追加 check_criteria 结果（真实校验，不再空转）
                try:
                    criteria_passed = gate.check_criteria(context)
                except Exception as e:
                    logger.warning(f"Gate {gate_num} check_criteria 异常: {e}")
                    criteria_passed = False
                result.details["check_criteria_passed"] = criteria_passed

                # 熔断器记录
                if result.passed:
                    self.circuit_breakers[gate_num].record_success()
                    break
                else:
                    from .core.error_classifier import ErrorClassifier
                    classification = ErrorClassifier().classify_from_exception(
                        RuntimeError("; ".join(result.errors[:3]))
                    )
                    self.circuit_breakers[gate_num].record_failure(classification.error_type)
                    if gate.can_retry():
                        gate.increment_retry()
                        attempts += 1
                        continue
                    else:
                        break

            # 记录结果
            gate_results[gate_num] = result
            results[f"gate_{gate_num}"] = {
                "passed": result.passed,
                "score": result.score,
                "execution_time": result.execution_time,
                "errors": result.errors,
                "check_criteria_passed": result.details.get("check_criteria_passed"),
                "state": "degraded" if is_degraded else ("passed" if result.passed else "failed"),
            }

            # 第三方监督
            compliance_result = self.supervisor.check_gate(gate_num, results)

            # 记录Gate完成
            self.audit_logger.log(
                run_id=self.run_id,
                gate_num=gate_num,
                action="gate_completed",
                details={
                    "passed": result.passed,
                    "score": result.score,
                    "compliance_passed": compliance_result.passed,
                    "check_criteria_passed": result.details.get("check_criteria_passed"),
                },
            )

            # 转换Gate状态
            if result.passed:
                self.state_machine.transition_gate(gate_num, GateState.PASSED)
            else:
                self.state_machine.transition_gate(gate_num, GateState.FAILED)
                logger.error(f"Gate {gate_num} 失败: {result.errors[:3]}")

            # 写回 context（每 Gate 完成后即更新，供后续 Gate 与 Gate8 读取）
            context["gate_results"] = gate_results
            context["results"] = results

            # B1-2 分级阻断：enforce 下仅"关键错误"阻断（数值矛盾/财年错位/占位符等）；
            # Gate0/2 数据源问题（字段缺失/降级）不阻断，产出带标注报告
            critical_gates = {4, 8}
            if qual_mode == "enforce" and gate_num in critical_gates:  # noqa: SIM102
                if not result.passed or not result.details.get("check_criteria_passed"):
                    err_text = "; ".join(result.errors[:6])
                    if _is_critical_gate_error(err_text):
                        from .workflow_context import ComplianceBlockedException
                        self.state_machine.transition_workflow(WorkflowState.FAILED)
                        raise ComplianceBlockedException(
                            f"Gate {gate_num} 关键错误阻断（B1-2 分级）: {result.errors[:3]}"
                        )
                    logger.warning(f"Gate {gate_num} 非关键失败（B1-2 降级标注，不阻断）: {err_text[:120]}")

            # 更新指标
            self.metrics_collector.record_gate_result(gate_num, results[f"gate_{gate_num}"])
            self.metrics_collector.record_execution_time(gate_num, result.execution_time)

        # 若未组装 report（quick 模式），从 chapters 组装
        if not context.get("report") and context.get("chapters"):
            try:
                chs = context["chapters"]
                parts = [f"# {context.get('company_name', '')} ({context.get('ticker', '')}) 买方定性分析报告\n"]
                for num in sorted(k for k in chs.keys() if isinstance(k, int)):  # noqa: SIM118
                    parts.append(f"# 第{num}章\n{chs[num]}")
                context["report"] = "\n".join(parts)
            except Exception as e:
                logger.warning(f"quick 报告组装失败: {e}")

        # v3.1 P0-B-3d：失败报告打"未修复"标记（shadow 语义：显式标注而非静默产出）
        # 双专家 P1（2026-08-22）：标注从 HTML 注释改为**报告头部可见** markdown 块——
        # 原 <!-- --> 渲染后不可见，读者看不到"报告未经完整验证"
        _all_passed = all(r["passed"] for r in results.values())
        if not _all_passed:
            _failed = [g for g, r in results.items() if not r["passed"]]
            _marker = (
                f"\n\n> ⚠️ **质量受限声明**：本报告由 **{qual_mode}** 模式产出，"
                f"以下 Gate 未通过：{_failed}。\n"
                f"> 部分章节可能未完成审查/修复，数字未经最终验证。"
                f"投资结论需人工复核后再使用。\n"
            )
            # 插入报告头部（可见），而非追加文末 HTML 注释
            _report = context.get("report") or ""
            context["report"] = _marker + "\n" + _report
            context["quality_degraded"] = True

        # 转换工作流状态
        if _all_passed:
            self.state_machine.transition_workflow(WorkflowState.COMPLETED)
        else:
            self.state_machine.transition_workflow(WorkflowState.FAILED)

        # 记录工作流完成
        self.audit_logger.log(
            run_id=self.run_id,
            gate_num=None,
            action="workflow_completed",
            details={
                "passed": all(r["passed"] for r in results.values()),
                "gate_results": {k: v["passed"] for k, v in results.items()},
            },
        )

        return {
            "run_id": self.run_id,
            "passed": all(r["passed"] for r in results.values()),
            "results": results,
            "gate_results": gate_results,
            "state_history": self.state_machine.get_state_history(),
            "audit_log": self.audit_logger.get_entries(self.run_id),
        }

    def get_status(self) -> dict[str, Any]:
        """获取工作流状态"""
        return {
            "run_id": self.run_id,
            "workflow_state": self.state_machine.get_workflow_state().value,
            "gate_states": {
                gate_num: state.value
                for gate_num, state in self.state_machine.gate_states.items()
            },
        }
