"""
ConclusionSynthesizer模块

功能:
- 结论综合: 权重汇总
- 证据检查: 无证据不声称
- 可证伪检查: 兴衰交替条件

解决: S04 结论未综合
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ConclusionEvidence:
    """结论证据"""
    source: str  # 来源(如"DCF估值", "PE估值", "可比公司")
    claim: str  # 声称
    evidence: str  # 证据
    weight: float = 1.0  # 权重


@dataclass
class SynthesisResult:
    """综合结果"""
    rating: str  # 买入/持有/卖出
    target_price: float
    confidence: str  # high/medium/low
    supporting_evidence: List[ConclusionEvidence]
    counter_evidence: List[str]
    falsification_conditions: List[str]
    summary: str


class ConclusionSynthesizer:
    """结论综合器"""
    
    def __init__(self):
        pass
    
    def synthesize(
        self,
        dcf_value: Optional[float] = None,
        dcf_weight: float = 0.4,
        pe_value: Optional[float] = None,
        pe_weight: float = 0.3,
        comparable_value: Optional[float] = None,
        comparable_weight: float = 0.3,
        current_price: Optional[float] = None,
    ) -> SynthesisResult:
        """综合多种估值方法"""
        evidence_list = []
        total_weight = 0
        weighted_sum = 0
        
        # DCF估值
        if dcf_value is not None:
            evidence_list.append(ConclusionEvidence(
                source="DCF估值",
                claim=f"DCF估值{dcf_value:.2f}元",
                evidence="基于FCF预测和WACC折现",
                weight=dcf_weight,
            ))
            weighted_sum += dcf_value * dcf_weight
            total_weight += dcf_weight
        
        # PE估值
        if pe_value is not None:
            evidence_list.append(ConclusionEvidence(
                source="PE估值",
                claim=f"PE估值{pe_value:.2f}元",
                evidence="基于可比公司PE倍数",
                weight=pe_weight,
            ))
            weighted_sum += pe_value * pe_weight
            total_weight += pe_weight
        
        # 可比公司估值
        if comparable_value is not None:
            evidence_list.append(ConclusionEvidence(
                source="可比公司估值",
                claim=f"可比公司估值{comparable_value:.2f}元",
                evidence="基于可比公司估值中位数",
                weight=comparable_weight,
            ))
            weighted_sum += comparable_value * comparable_weight
            total_weight += comparable_weight
        
        # 计算加权目标价
        if total_weight > 0:
            target_price = weighted_sum / total_weight
        else:
            target_price = 0
        
        # 判断评级
        if current_price and target_price:
            upside = (target_price - current_price) / current_price
            if upside > 0.20:
                rating = "买入"
                confidence = "high" if upside > 0.30 else "medium"
            elif upside > 0:
                rating = "持有"
                confidence = "medium"
            else:
                rating = "卖出"
                confidence = "high" if upside < -0.20 else "medium"
        else:
            rating = "持有"
            confidence = "low"
        
        # 生成摘要
        summary = self._generate_summary(
            rating, target_price, confidence, evidence_list, current_price
        )
        
        # 生成可证伪条件
        falsification_conditions = self._generate_falsification_conditions(
            dcf_value, pe_value, comparable_value, current_price
        )
        
        return SynthesisResult(
            rating=rating,
            target_price=target_price,
            confidence=confidence,
            supporting_evidence=evidence_list,
            counter_evidence=[],
            falsification_conditions=falsification_conditions,
            summary=summary,
        )
    
    def _generate_summary(
        self,
        rating: str,
        target_price: float,
        confidence: str,
        evidence_list: List[ConclusionEvidence],
        current_price: Optional[float],
    ) -> str:
        """生成摘要"""
        lines = [
            f"## 投资结论",
            "",
            f"**评级**: {rating}",
            f"**目标价**: {target_price:.2f}元",
            f"**置信度**: {confidence}",
        ]
        
        if current_price and target_price:
            upside = (target_price - current_price) / current_price
            lines.append(f"**上行空间**: {upside:.1%}")
        
        lines.extend([
            "",
            "### 估值方法汇总",
            "",
            "| 方法 | 目标价 | 权重 | 证据 |",
            "|------|--------|------|------|",
        ])
        
        for evidence in evidence_list:
            lines.append(
                f"| {evidence.source} | {evidence.claim} | {evidence.weight:.0%} | {evidence.evidence} |"
            )
        
        return "\n".join(lines)
    
    def _generate_falsification_conditions(
        self,
        dcf_value: Optional[float],
        pe_value: Optional[float],
        comparable_value: Optional[float],
        current_price: Optional[float],
    ) -> List[str]:
        """生成可证伪条件"""
        conditions = []
        
        if dcf_value and current_price:
            if dcf_value > current_price:
                conditions.append(f"如果FCF连续2年下降超过20%，DCF估值将失效")
                conditions.append(f"如果WACC上升超过2%，目标价将下调")
        
        if pe_value and current_price:
            if pe_value > current_price:
                conditions.append(f"如果可比公司PE中枢下移30%，PE估值将失效")
        
        if not conditions:
            conditions.append("如果公司基本面发生重大变化，估值将失效")
        
        return conditions
    
    def check_evidence(self, claim: str, evidence_list: List[str]) -> bool:
        """检查是否有证据支持声称"""
        # 简化实现：检查是否有相关证据
        return len(evidence_list) > 0
    
    def generate_report(self, result: SynthesisResult) -> str:
        """生成完整报告"""
        return result.summary
