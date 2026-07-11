"""
quality/sensitivity.py — 敏感性分析模块

实现投资分析中的敏感性分析：
- 单变量敏感性分析
- 双变量敏感性分析
- 情景分析
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

from .types import ConfidenceInterval

logger = logging.getLogger(__name__)


@dataclass
class SensitivityVariable:
    """敏感性变量"""
    name: str                    # 变量名称
    base_value: float            # 基准值
    range_values: list[float]    # 变化范围
    unit: str = ""               # 单位


@dataclass
class SensitivityResult:
    """敏感性分析结果"""
    variable_name: str
    base_value: float
    range_values: list[float]
    output_values: list[float]
    output_name: str
    elasticity: float = 0.0  # 弹性系数


@dataclass
class TwoWaySensitivityResult:
    """双变量敏感性分析结果"""
    variable1_name: str
    variable2_name: str
    variable1_values: list[float]
    variable2_values: list[float]
    output_matrix: list[list[float]]
    output_name: str


@dataclass
class ScenarioAnalysis:
    """情景分析"""
    scenario_name: str
    description: str
    variables: dict[str, float]  # 变量名 -> 值
    probability: float = 0.0     # 概率
    output_value: float = 0.0    # 输出值


@dataclass
class ScenarioAnalysisResult:
    """情景分析结果"""
    scenarios: list[ScenarioAnalysis]
    expected_value: float = 0.0  # 期望值
    best_case: float = 0.0       # 最佳情景
    worst_case: float = 0.0      # 最差情景
    base_case: float = 0.0       # 基准情景
    confidence_interval: Optional[ConfidenceInterval] = None  # 置信区间


class SensitivityAnalyzer:
    """敏感性分析器"""
    
    def one_way_sensitivity(
        self,
        base_inputs: dict[str, float],
        variable: SensitivityVariable,
        output_calculator: Callable[[dict[str, float]], float],
        output_name: str = "output"
    ) -> SensitivityResult:
        """单变量敏感性分析
        
        Args:
            base_inputs: 基准输入参数
            variable: 敏感性变量
            output_calculator: 输出计算函数
            output_name: 输出名称
            
        Returns:
            SensitivityResult: 敏感性分析结果
        """
        output_values = []
        
        for value in variable.range_values:
            # 修改变量值
            inputs = base_inputs.copy()
            inputs[variable.name] = value
            
            # 计算输出
            output = output_calculator(inputs)
            output_values.append(output)
        
        # 计算弹性系数
        base_output = output_calculator(base_inputs)
        elasticity = self._calculate_elasticity(
            variable.base_value,
            variable.range_values,
            base_output,
            output_values
        )
        
        return SensitivityResult(
            variable_name=variable.name,
            base_value=variable.base_value,
            range_values=variable.range_values,
            output_values=output_values,
            output_name=output_name,
            elasticity=elasticity
        )
    
    def two_way_sensitivity(
        self,
        base_inputs: dict[str, float],
        variable1: SensitivityVariable,
        variable2: SensitivityVariable,
        output_calculator: Callable[[dict[str, float]], float],
        output_name: str = "output"
    ) -> TwoWaySensitivityResult:
        """双变量敏感性分析
        
        Args:
            base_inputs: 基准输入参数
            variable1: 敏感性变量1
            variable2: 敏感性变量2
            output_calculator: 输出计算函数
            output_name: 输出名称
            
        Returns:
            TwoWaySensitivityResult: 双变量敏感性分析结果
        """
        output_matrix = []
        
        for value1 in variable1.range_values:
            row = []
            for value2 in variable2.range_values:
                # 修改变量值
                inputs = base_inputs.copy()
                inputs[variable1.name] = value1
                inputs[variable2.name] = value2
                
                # 计算输出
                output = output_calculator(inputs)
                row.append(output)
            
            output_matrix.append(row)
        
        return TwoWaySensitivityResult(
            variable1_name=variable1.name,
            variable2_name=variable2.name,
            variable1_values=variable1.range_values,
            variable2_values=variable2.range_values,
            output_matrix=output_matrix,
            output_name=output_name
        )
    
    def scenario_analysis(
        self,
        base_inputs: dict[str, float],
        scenarios: list[dict],
        output_calculator: Callable[[dict[str, float]], float]
    ) -> ScenarioAnalysisResult:
        """情景分析
        
        Args:
            base_inputs: 基准输入参数
            scenarios: 情景列表
                [
                    {
                        "name": "乐观情景",
                        "description": "...",
                        "variables": {"growth": 0.15, "margin": 0.25},
                        "probability": 0.3
                    },
                    ...
                ]
            output_calculator: 输出计算函数
            
        Returns:
            ScenarioAnalysisResult: 情景分析结果
        """
        analysis_scenarios = []
        
        for scenario in scenarios:
            # 合并变量
            inputs = base_inputs.copy()
            inputs.update(scenario.get("variables", {}))
            
            # 计算输出
            output = output_calculator(inputs)
            
            analysis_scenarios.append(ScenarioAnalysis(
                scenario_name=scenario.get("name", ""),
                description=scenario.get("description", ""),
                variables=scenario.get("variables", {}),
                probability=scenario.get("probability", 0.0),
                output_value=output
            ))
        
        # 计算期望值
        expected_value = sum(
            s.output_value * s.probability for s in analysis_scenarios
        )
        
        # 找出最佳和最差情景
        output_values = [s.output_value for s in analysis_scenarios]
        
        # 基准情景
        base_output = output_calculator(base_inputs)
        
        # 计算置信区间（基于情景分布）
        if len(output_values) >= 2:
            import statistics
            mean = statistics.mean(output_values)
            stdev = statistics.stdev(output_values)
            # 95%置信区间
            ci_lower = mean - 1.96 * stdev
            ci_upper = mean + 1.96 * stdev
            confidence_interval = ConfidenceInterval(
                lower=ci_lower,
                upper=ci_upper,
                method="scenario_distribution"
            )
        else:
            confidence_interval = None
        
        return ScenarioAnalysisResult(
            scenarios=analysis_scenarios,
            expected_value=expected_value,
            best_case=max(output_values) if output_values else 0.0,
            worst_case=min(output_values) if output_values else 0.0,
            base_case=base_output,
            confidence_interval=confidence_interval
        )
    
    def _calculate_elasticity(
        self,
        base_input: float,
        input_values: list[float],
        base_output: float,
        output_values: list[float]
    ) -> float:
        """计算弹性系数"""
        if base_input == 0 or base_output == 0:
            return 0.0
        
        # 使用中心差分法
        if len(input_values) >= 3:
            mid = len(input_values) // 2
            input_delta = input_values[mid + 1] - input_values[mid - 1]
            output_delta = output_values[mid + 1] - output_values[mid - 1]
            
            if input_delta != 0:
                elasticity = (output_delta / base_output) / (input_delta / base_input)
                return elasticity
        
        # 回退到简单计算
        if len(input_values) >= 2:
            input_delta = input_values[-1] - input_values[0]
            output_delta = output_values[-1] - output_values[0]
            
            if input_delta != 0:
                elasticity = (output_delta / base_output) / (input_delta / base_input)
                return elasticity
        
        return 0.0


def format_sensitivity_report(
    one_way_results: list[SensitivityResult],
    two_way_result: Optional[TwoWaySensitivityResult] = None,
    scenario_result: Optional[ScenarioAnalysisResult] = None
) -> str:
    """格式化敏感性分析报告"""
    lines = []
    lines.append("## 敏感性分析")
    lines.append("")
    
    # 单变量敏感性分析
    if one_way_results:
        lines.append("### 单变量敏感性分析")
        lines.append("")
        for result in one_way_results:
            lines.append(f"**{result.variable_name}** (弹性系数: {result.elasticity:.2f})")
            lines.append(f"| {result.variable_name} | {result.output_name} |")
            lines.append("|---|---|")
            for i, (inp, out) in enumerate(zip(result.range_values, result.output_values)):
                marker = " ← 基准" if i == len(result.range_values) // 2 else ""
                lines.append(f"| {inp:.2f} | {out:.2f}{marker} |")
            lines.append("")
    
    # 双变量敏感性分析
    if two_way_result:
        lines.append("### 双变量敏感性分析")
        lines.append("")
        lines.append(f"**{two_way_result.variable1_name} × {two_way_result.variable2_name}**")
        lines.append("")
        
        # 表头
        header = f"| {two_way_result.variable1_name} \\ {two_way_result.variable2_name} | "
        header += " | ".join([f"{v:.2f}" for v in two_way_result.variable2_values])
        header += " |"
        lines.append(header)
        
        # 分隔行
        separator = "|" + "---|" * (len(two_way_result.variable2_values) + 1)
        lines.append(separator)
        
        # 数据行
        for i, v1 in enumerate(two_way_result.variable1_values):
            row = f"| {v1:.2f} | "
            row += " | ".join([f"{two_way_result.output_matrix[i][j]:.2f}" for j in range(len(two_way_result.variable2_values))])
            row += " |"
            lines.append(row)
        lines.append("")
    
    # 情景分析
    if scenario_result:
        lines.append("### 情景分析")
        lines.append("")
        lines.append(f"- 基准情景: {scenario_result.base_case:.2f}")
        lines.append(f"- 最佳情景: {scenario_result.best_case:.2f}")
        lines.append(f"- 最差情景: {scenario_result.worst_case:.2f}")
        lines.append(f"- 期望值: {scenario_result.expected_value:.2f}")
        lines.append("")
        
        lines.append("| 情景 | 描述 | 概率 | 输出值 |")
        lines.append("|---|---|---|---|")
        for scenario in scenario_result.scenarios:
            lines.append(f"| {scenario.scenario_name} | {scenario.description} | {scenario.probability:.1%} | {scenario.output_value:.2f} |")
        lines.append("")
    
    return "\n".join(lines)
