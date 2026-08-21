"""
第三方监督模块

实现轻量级流程合规性检查
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ComplianceCheck:
    """合规性检查结果"""
    name: str
    category: str  # "precondition", "execution", "criteria", "failure_handling", "human_intervention"
    passed: bool = False
    message: str = ""
    details: dict[str, Any] | None = None


@dataclass
class ComplianceResult:
    """合规性检查结果"""
    gate_num: int
    passed: bool
    checks: list[ComplianceCheck] = field(default_factory=list)
    failed_checks: list[ComplianceCheck] = field(default_factory=list)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


class FlowComplianceChecker:
    """流程合规性检查器（轻量级）"""

    def __init__(self, flow_definition: dict[str, Any]):
        self.flow_definition = flow_definition

    def check_gate(self, gate_num: int, execution_log: dict[str, Any]) -> ComplianceResult:
        """检查单个Gate的合规性"""
        gate_key = f"gate_{gate_num}"
        if gate_key not in self.flow_definition:
            return ComplianceResult(
                gate_num=gate_num,
                passed=False,
                failed_checks=[ComplianceCheck(
                    name="Gate定义",
                    category="precondition",
                    passed=False,
                    message=f"Gate {gate_num} 未在流程定义中找到",
                )],
            )

        gate_spec = self.flow_definition[gate_key]
        checks = []

        checks.extend(self._check_preconditions(gate_spec, execution_log))
        checks.extend(self._check_execution_content(gate_spec, execution_log))
        checks.extend(self._check_pass_criteria(gate_spec, execution_log))
        checks.extend(self._check_failure_handling(gate_spec, execution_log))
        checks.extend(self._check_human_intervention(gate_spec, execution_log))

        passed = all(check.passed for check in checks)
        failed_checks = [check for check in checks if not check.passed]

        return ComplianceResult(
            gate_num=gate_num,
            passed=passed,
            checks=checks,
            failed_checks=failed_checks,
        )

    def _check_preconditions(self, gate_spec: dict[str, Any], execution_log: dict[str, Any]) -> list[ComplianceCheck]:
        """检查前置条件"""
        checks = []

        for precondition in gate_spec.get("preconditions", []):
            passed = False
            message = ""

            if precondition["type"] == "gate_passed":
                required_gate = precondition["gate_num"]
                gate_result = execution_log.get(f"gate_{required_gate}", {})
                passed = gate_result.get("passed", False)
                message = f"Gate {required_gate} {'通过' if passed else '未通过'}"

            elif precondition["type"] == "data_available":
                data_key = precondition["data_key"]
                passed = data_key in execution_log.get("data", {})
                message = f"数据 {data_key} {'可用' if passed else '不可用'}"

            elif precondition["type"] == "component_ready":
                component_name = precondition["component"]
                passed = execution_log.get("components", {}).get(component_name, {}).get("ready", False)
                message = f"组件 {component_name} {'就绪' if passed else '未就绪'}"

            checks.append(ComplianceCheck(
                name=f"前置条件: {precondition['name']}",
                category="precondition",
                passed=passed,
                message=message,
            ))

        return checks

    def _check_execution_content(self, gate_spec: dict[str, Any], execution_log: dict[str, Any]) -> list[ComplianceCheck]:
        """检查执行内容"""
        checks = []

        for step in gate_spec.get("execution_steps", []):
            step_log = execution_log.get("steps", {}).get(step["name"], {})
            passed = step_log.get("executed", False)
            message = f"步骤 {step['name']} {'已执行' if passed else '未执行'}"

            # 检查执行顺序
            if passed and "order" in step:
                expected_order = step["order"]
                actual_order = step_log.get("order", -1)
                if actual_order != expected_order:
                    passed = False
                    message = f"步骤 {step['name']} 执行顺序错误: 期望 {expected_order}, 实际 {actual_order}"

            checks.append(ComplianceCheck(
                name=f"执行步骤: {step['name']}",
                category="execution",
                passed=passed,
                message=message,
            ))

        return checks

    def _check_pass_criteria(self, gate_spec: dict[str, Any], execution_log: dict[str, Any]) -> list[ComplianceCheck]:
        """检查通过标准"""
        checks = []

        for criteria in gate_spec.get("pass_criteria", []):
            passed = False
            message = ""

            if criteria["type"] == "quantitative":
                metric_name = criteria["metric"]
                threshold = criteria["threshold"]
                actual_value = execution_log.get("metrics", {}).get(metric_name, 0)
                passed = actual_value >= threshold
                message = f"{metric_name}: {actual_value} {'≥' if passed else '<'} {threshold}"

            elif criteria["type"] == "condition":
                condition_name = criteria["condition"]
                passed = execution_log.get("conditions", {}).get(condition_name, False)
                message = f"条件 {condition_name} {'满足' if passed else '不满足'}"

            checks.append(ComplianceCheck(
                name=f"通过标准: {criteria['name']}",
                category="criteria",
                passed=passed,
                message=message,
            ))

        return checks

    def _check_failure_handling(self, gate_spec: dict[str, Any], execution_log: dict[str, Any]) -> list[ComplianceCheck]:
        """检查失败处理"""
        checks = []

        has_failure = execution_log.get("has_failure", False)

        if has_failure:
            for retry_spec in gate_spec.get("retry_specs", []):
                retry_log = execution_log.get("retries", {}).get(retry_spec["name"], {})
                passed = retry_log.get("executed", False)
                message = f"重试 {retry_spec['name']} {'已执行' if passed else '未执行'}"

                checks.append(ComplianceCheck(
                    name=f"重试处理: {retry_spec['name']}",
                    category="failure_handling",
                    passed=passed,
                    message=message,
                ))

        return checks

    def _check_human_intervention(self, gate_spec: dict[str, Any], execution_log: dict[str, Any]) -> list[ComplianceCheck]:
        """检查人工介入"""
        checks = []

        for intervention_spec in gate_spec.get("human_interventions", []):
            intervention_log = execution_log.get("human_interventions", {}).get(intervention_spec["name"], {})

            passed = True
            message = ""

            if intervention_spec.get("required", False):
                passed = intervention_log.get("triggered", False)
                message = f"人工介入 {intervention_spec['name']} {'已触发' if passed else '未触发'}"

            if passed and intervention_spec.get("approval_required", False):
                passed = intervention_log.get("approved", False)
                message = f"人工同意 {intervention_spec['name']} {'已获取' if passed else '未获取'}"

            checks.append(ComplianceCheck(
                name=f"人工介入: {intervention_spec['name']}",
                category="human_intervention",
                passed=passed,
                message=message,
            ))

        return checks
