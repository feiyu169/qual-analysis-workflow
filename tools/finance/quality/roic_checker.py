"""
ROIC<WACC强制回应模块

功能：
1. 检测ROIC<WACC
2. 强制在看多结论中回应
3. 生成回应模板（根据HeavySkill审查要求增强）

根据HeavySkill审查要求：
- 必须强制包含定量敏感性分析
- 历史趋势与可比公司对比
- 设置分析师复核节点
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ROICAnalysis:
    """ROIC分析"""
    roic: float
    wacc: float
    is_value_destruction: bool
    gap: float


class ROICChecker:
    """ROIC检查器"""

    @staticmethod
    def analyze(roic: float, wacc: float) -> ROICAnalysis:
        """分析ROIC与WACC关系"""
        is_value_destruction = roic < wacc
        gap = wacc - roic

        return ROICAnalysis(
            roic=roic,
            wacc=wacc,
            is_value_destruction=is_value_destruction,
            gap=gap,
        )

    @staticmethod
    def generate_prompt_injection(roic: float, wacc: float) -> str:
        """生成prompt注入（根据HeavySkill审查要求增强）"""
        analysis = ROICChecker.analyze(roic, wacc)

        if not analysis.is_value_destruction:
            return ""

        injection = f"""
⚠️ 重要提示：ROIC({roic:.1%}) < WACC({wacc:.1%})，存在价值毁灭信号。

在给出看多结论时，必须明确回应以下问题（按HeavySkill审查要求）：

1. **定量敏感性分析**：
   - ROIC需要提升多少才能达到WACC水平？
   - WACC下降多少才能使ROIC>WACC？
   - 如果ROIC提升1%/2%/3%，估值变化多少？

2. **ROIC改善路径**：
   - 通过什么具体措施提升ROIC？（提高利润率/提高周转率/优化资本结构）
   - 改善的时间表是什么？
   - 改善的确定性如何？

3. **历史趋势与可比公司对比**：
   - 公司历史ROIC趋势如何？（是否在改善？）
   - 同行业可比公司的ROIC水平如何？
   - 公司在行业中的相对位置？

4. **投资结论调整**：
   - 如果ROIC持续<WACC，投资结论如何调整？
   - 触发评级下调的具体条件是什么？

5. **风险提示**：
   - 明确说明ROIC<WACC意味着公司在毁灭价值
   - 如果无法合理回应上述问题，应给出中性或看空结论

⚠️ 分析师复核节点：本分析需要人工复核确认ROIC改善路径的可行性。
"""
        return injection

    @staticmethod
    def validate_response(response: str, roic: float, wacc: float) -> list[str]:
        """验证回应是否完整（根据HeavySkill审查要求增强）"""
        errors = []

        analysis = ROICChecker.analyze(roic, wacc)

        if not analysis.is_value_destruction:
            return errors

        # 检查是否回应了关键问题
        if "ROIC" not in response and "资本回报率" not in response:
            errors.append("未提及ROIC")

        if "WACC" not in response and "资本成本" not in response:
            errors.append("未提及WACC")

        # 检查是否有定量分析
        quantitative_keywords = ["提升", "下降", "改善", "百分点", "%", "倍"]
        has_quantitative = any(keyword in response for keyword in quantitative_keywords)
        if not has_quantitative:
            errors.append("缺少定量敏感性分析")

        # 检查是否有改善路径
        path_keywords = ["路径", "措施", "方案", "策略", "计划"]
        has_path = any(keyword in response for keyword in path_keywords)
        if not has_path:
            errors.append("缺少ROIC改善路径")

        # 检查是否有行业对比
        comparison_keywords = ["行业", "可比", "同行", "对比", "比较"]
        has_comparison = any(keyword in response for keyword in comparison_keywords)
        if not has_comparison:
            errors.append("缺少行业对比分析")

        # 检查是否有风险提示
        risk_keywords = ["风险", "毁灭", "下调", "调整", "警告"]
        has_risk = any(keyword in response for keyword in risk_keywords)
        if not has_risk:
            errors.append("缺少风险提示")

        # 检查是否有看多理由
        bullish_keywords = ["看多", "增长", "改善", "提升", "优化"]
        has_bullish_reason = any(keyword in response for keyword in bullish_keywords)

        if not has_bullish_reason:
            errors.append("未提供看多理由")

        return errors

    @staticmethod
    def generate_default_response(roic: float, wacc: float) -> str:
        """生成默认回应（根据HeavySkill审查要求增强）"""
        analysis = ROICChecker.analyze(roic, wacc)

        if not analysis.is_value_destruction:
            return ""

        response = f"""
**ROIC<WACC回应**（根据HeavySkill审查要求增强）：

1. **当前状况**：
   - ROIC({roic:.1%}) < WACC({wacc:.1%})，差距{analysis.gap:.1%}
   - 公司当前在毁灭价值（EVA为负）

2. **定量敏感性分析**：
   - ROIC需要提升{analysis.gap:.1%}才能达到WACC水平
   - 如果ROIC提升1%，估值提升约X%（需计算）
   - 如果ROIC提升2%，估值提升约X%（需计算）
   - 如果ROIC提升3%，估值提升约X%（需计算）

3. **ROIC改善路径**：
   - 路径1：提高利润率（当前利润率X%，目标Y%）
   - 路径2：提高资产周转率（当前X次，目标Y次）
   - 路径3：优化资本结构（当前负债率X%，目标Y%）
   - 改善时间表：预计X年内达到WACC水平

4. **历史趋势与可比公司对比**：
   - 公司历史ROIC趋势：X年ROIC为A%，Y年ROIC为B%，趋势向上/下
   - 行业平均ROIC：X%（来源：Wind）
   - 可比公司ROIC：公司A=X%，公司B=Y%，公司C=Z%
   - 公司在行业中处于X分位（高于/低于平均）

5. **投资结论调整**：
   - 如果ROIC在X年内未能超过WACC，应下调投资评级至中性
   - 如果ROIC持续下降，应下调投资评级至回避
   - 触发条件：ROIC连续X个季度<WACC

6. **风险提示**：
   - ⚠️ ROIC<WACC意味着公司在毁灭价值，投资需谨慎
   - 如果无法合理回应上述问题，应给出中性或看空结论

⚠️ 分析师复核节点：本分析需要人工复核确认ROIC改善路径的可行性。
"""
        return response
