"""
决策聚合器（权重透明化+回测+专家覆写）

功能：
1. 各章判断聚合
2. 权重透明化
3. 回测验证
4. 专家覆写
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ChapterJudgment:
    """章节判断"""
    chapter_num: int
    judgment: str  # 看多, 中性, 看空
    confidence: float  # 0-100
    key_arguments: list[str] = field(default_factory=list)


@dataclass
class WeightJustification:
    """权重依据"""
    chapter_num: int
    weight: float
    justification: str
    historical_performance: float = 0
    last_backtested: str = ""


@dataclass
class BacktestResult:
    """回测结果"""
    timestamp: str
    total_predictions: int
    correct_predictions: int
    accuracy: float
    chapter_contributions: dict[int, float]


@dataclass
class AggregationRule:
    """聚合规则"""
    # 权重配置
    chapter_weights: dict[int, float]

    # 权重依据
    weight_justifications: dict[int, WeightJustification] = field(default_factory=dict)

    # 阈值配置
    bullish_threshold: float = 60
    bearish_threshold: float = 40

    # 冲突解决
    conflict_resolution: str = "weighted_average"

    # 专家覆写
    expert_overrides: dict[int, str] = field(default_factory=dict)


class DecisionAggregator:
    """决策聚合器"""

    # 默认规则
    DEFAULT_RULES = AggregationRule(
        chapter_weights={
            1: 0.10,  # 业务
            2: 0.10,  # 行业
            3: 0.10,  # 模式
            4: 0.10,  # 变化
            5: 0.15,  # 经营
            6: 0.15,  # 财务
            7: 0.10,  # 回报
            8: 0.05,  # 治理
            9: 0.10,  # 风险
            10: 0.05, # 决策
        },
        bullish_threshold=60,
        bearish_threshold=40,
    )

    def __init__(self):
        self.backtest_history: list[BacktestResult] = []

    @classmethod
    def aggregate(cls, judgments: list[ChapterJudgment],
                  rules: AggregationRule = None) -> str:
        """聚合各章判断为全局结论"""
        if rules is None:
            rules = cls.DEFAULT_RULES

        # 应用专家覆写
        for judgment in judgments:
            if judgment.chapter_num in rules.expert_overrides:
                override = rules.expert_overrides[judgment.chapter_num]
                logger.info(f"应用专家覆写: 第{judgment.chapter_num}章 {judgment.judgment} → {override}")
                judgment.judgment = override

        # 计算加权得分
        weighted_score = 0
        total_weight = 0

        for judgment in judgments:
            weight = rules.chapter_weights.get(judgment.chapter_num, 0.1)

            # 将判断转换为分数
            if judgment.judgment == "看多":
                score = 70 + judgment.confidence * 0.3
            elif judgment.judgment == "看空":
                score = 30 - judgment.confidence * 0.3
            else:  # 中性
                score = 50

            weighted_score += score * weight
            total_weight += weight

        # 计算最终得分
        final_score = weighted_score / total_weight if total_weight > 0 else 50

        # 根据阈值判断
        if final_score >= rules.bullish_threshold:
            return "看多"
        elif final_score <= rules.bearish_threshold:
            return "看空"
        else:
            return "中性"

    @classmethod
    def explain_aggregation(cls, judgments: list[ChapterJudgment],
                           rules: AggregationRule = None) -> str:
        """解释聚合过程"""
        if rules is None:
            rules = cls.DEFAULT_RULES

        explanation = "## 各章判断→全局结论聚合过程\n\n"
        explanation += "| 章节 | 判断 | 置信度 | 权重 | 加权得分 |\n"
        explanation += "|------|------|--------|------|----------|\n"

        weighted_score = 0
        total_weight = 0

        for judgment in judgments:
            weight = rules.chapter_weights.get(judgment.chapter_num, 0.1)

            if judgment.judgment == "看多":
                score = 70 + judgment.confidence * 0.3
            elif judgment.judgment == "看空":
                score = 30 - judgment.confidence * 0.3
            else:
                score = 50

            weighted_score += score * weight
            total_weight += weight

            explanation += f"| 第{judgment.chapter_num}章 | {judgment.judgment} | {judgment.confidence}% | {weight} | {score * weight:.1f} |\n"

        final_score = weighted_score / total_weight if total_weight > 0 else 50

        explanation += f"\n**加权平均得分**: {final_score:.1f}\n"
        explanation += f"**看多阈值**: {rules.bullish_threshold}\n"
        explanation += f"**看空阈值**: {rules.bearish_threshold}\n"

        if final_score >= rules.bullish_threshold:
            explanation += f"\n**最终结论**: 看多（{final_score:.1f} >= {rules.bullish_threshold}）"
        elif final_score <= rules.bearish_threshold:
            explanation += f"\n**最终结论**: 看空（{final_score:.1f} <= {rules.bearish_threshold}）"
        else:
            explanation += f"\n**最终结论**: 中性（{rules.bearish_threshold} < {final_score:.1f} < {rules.bullish_threshold}）"

        # 显示专家覆写
        if rules.expert_overrides:
            explanation += "\n\n## 专家覆写\n\n"
            for chapter, override in rules.expert_overrides.items():
                explanation += f"- 第{chapter}章: {override}\n"

        return explanation

    def backtest(self, historical_data: list[dict]) -> BacktestResult:
        """回测"""
        total = len(historical_data)
        correct = 0
        chapter_contributions = {i: 0 for i in range(1, 11)}

        for data in historical_data:
            predicted = self.aggregate(data["judgments"])
            actual = data["actual_outcome"]

            if predicted == actual:
                correct += 1

                for judgment in data["judgments"]:
                    if judgment.judgment == actual:
                        chapter_contributions[judgment.chapter_num] += 1

        accuracy = correct / total if total > 0 else 0

        for chapter in chapter_contributions:
            chapter_contributions[chapter] = chapter_contributions[chapter] / total if total > 0 else 0

        result = BacktestResult(
            timestamp=datetime.now().isoformat(),
            total_predictions=total,
            correct_predictions=correct,
            accuracy=accuracy,
            chapter_contributions=chapter_contributions,
        )

        self.backtest_history.append(result)

        return result

    def optimize_weights(self, backtest_result: BacktestResult) -> dict[int, float]:
        """优化权重"""
        total_contribution = sum(backtest_result.chapter_contributions.values())
        if total_contribution == 0:
            return self.DEFAULT_RULES.chapter_weights

        optimized_weights = {}
        for chapter, contribution in backtest_result.chapter_contributions.items():
            optimized_weights[chapter] = contribution / total_contribution

        return optimized_weights
