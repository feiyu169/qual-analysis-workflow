"""
quality/reasoning/cold_start.py — 冷启动策略

定义系统在数据不足时的降级行为
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..interfaces import ColdStartPolicy
from ..types import (
    CausalGraph,
    ConfidenceLevel,
    CounterResult,
    EvidenceBundle,
    FalsificationIndicator,
    MonitoringPlan,
    ReasoningResult,
)

logger = logging.getLogger(__name__)


class DefaultColdStartPolicy(ColdStartPolicy):
    """默认冷启动策略"""
    
    def get_seed_data(self) -> EvidenceBundle:
        """获取种子数据"""
        return EvidenceBundle(
            financial_data={},
            news_data=[],
            industry_data={},
            filing_data={},
            source="cold_start_seed"
        )
    
    def get_min_data_threshold(self) -> dict[str, int]:
        """获取最小数据量阈值"""
        return {
            "financial_periods": 3,
            "news_count": 5,
            "industry_metrics": 2
        }
    
    def get_fallback_output(self) -> ReasoningResult:
        """获取降级输出
        
        当数据不足时返回低置信度的结果
        """
        logger.warning("使用冷启动降级输出")
        
        return ReasoningResult(
            causal_graph=CausalGraph(
                relations=[],
                confidence=0.3,
                assumptions=["数据不足，使用降级输出"]
            ),
            scenario_results=[],
            counter_result=CounterResult(
                counter_arguments=["数据不足，无法进行充分的反面论证"],
                falsification_indicators=[
                    FalsificationIndicator(
                        name="数据完整性",
                        description="检查数据是否满足最低要求",
                        measurement_method="数据条目计数",
                        threshold=0.5,
                        current_value=0.3,
                        is_triggered=True
                    )
                ],
                monitoring_plan=MonitoringPlan(
                    triggers=[{
                        "indicator": "数据完整性",
                        "threshold": 0.5,
                        "action": "补充数据后重新分析",
                        "frequency": "once"
                    }],
                    frequency="once",
                    alert_threshold=0.5
                ),
                confidence_adjustment=-0.2
            ),
            confidence=0.3,
            checkpoints_passed=[],
            checkpoints_failed=["cold_start"],
            trace_id="cold_start_fallback"
        )
    
    def is_cold_start(self, evidence: EvidenceBundle) -> bool:
        """判断是否冷启动
        
        当数据量低于阈值时触发冷启动
        """
        threshold = self.get_min_data_threshold()
        
        # 检查财务数据：检查是否有足够的数据字段
        financial_fields = len(evidence.financial_data)
        if financial_fields < 2:  # 至少需要2个财务字段（如收入+利润）
            logger.info(f"冷启动: 财务数据字段不足 ({financial_fields} < 2)")
            return True
        
        # 检查新闻数据
        news_count = len(evidence.news_data)
        if news_count < threshold["news_count"]:
            logger.info(f"冷启动: 新闻数据不足 ({news_count} < {threshold['news_count']})")
            return True
        
        # 检查行业数据
        industry_count = len(evidence.industry_data)
        if industry_count < threshold["industry_metrics"]:
            logger.info(f"冷启动: 行业数据不足 ({industry_count} < {threshold['industry_metrics']})")
            return True
        
        return False
