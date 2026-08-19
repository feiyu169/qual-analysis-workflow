"""
ROICWACCChecker模块

功能:
- 四象限分析: Q1-Q4
- 增量ROIC计算
- 持续期判断

解决: S09 ROIC<WACC与价值创造冲突
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ROICResult:
    """ROIC计算结果"""
    roic: float = 0.0
    wacc: float = 0.0
    spread: float = 0.0  # ROIC - WACC
    is_creating_value: bool = False
    quadrant: str = ""
    message: str = ""


@dataclass
class IncrementalROICResult:
    """增量ROIC结果"""
    delta_nopat: float = 0.0
    delta_ic: float = 0.0
    incremental_roic: float = 0.0
    is_value_creating: bool = False


class ROICWACCChecker:
    """ROIC-WACC一致性检查器
    
    四象限分析:
    ┌─────────────────────────────────────────────────────────────┐
    │ 象限    │ ROIC vs WACC │ 趋势      │ 允许的声称            │
    ├─────────────────────────────────────────────────────────────┤
    │ Q1      │ ROIC > WACC  │ 改善中    │ "价值创造确立"        │
    │ Q2      │ ROIC > WACC  │ 稳定/恶化 │ "价值创造稳定"        │
    │ Q3      │ ROIC < WACC  │ 改善中    │ "拐点临近"            │
    │ Q4      │ ROIC < WACC  │ 稳定/恶化 │ "价值毁损持续"        │
    └─────────────────────────────────────────────────────────────┘
    """
    
    # 象限定义
    QUADRANTS = {
        "Q1": {
            "name": "价值创造+趋势改善",
            "roic_vs_wacc": "above",
            "trend": "improving",
            "allowed_claims": ["价值创造确立", "价值创造加速", "ROIC持续提升"],
            "blocked_claims": [],
        },
        "Q2": {
            "name": "价值创造但趋势平稳",
            "roic_vs_wacc": "above",
            "trend": ["stable", "deteriorating"],
            "allowed_claims": ["价值创造稳定", "ROIC高于WACC"],
            "blocked_claims": ["价值创造加速"],
        },
        "Q3": {
            "name": "价值毁损但趋势改善",
            "roic_vs_wacc": "below",
            "trend": "improving",
            "allowed_claims": ["拐点临近", "差距缩小", "改善趋势"],
            "blocked_claims": ["价值创造确立", "价值创造拐点确立"],
        },
        "Q4": {
            "name": "价值毁损且趋势恶化",
            "roic_vs_wacc": "below",
            "trend": ["stable", "deteriorating"],
            "allowed_claims": ["价值毁损持续", "ROIC低于WACC"],
            "blocked_claims": ["拐点临近", "价值创造确立"],
        },
    }
    
    def check(
        self,
        roic_current: float,
        roic_trend: str,  # "improving" | "stable" | "deteriorating"
        wacc: float,
        claim: str = "",
    ) -> ROICResult:
        """检查ROIC-WACC一致性"""
        spread = roic_current - wacc
        is_creating_value = spread > 0
        
        # 确定象限
        quadrant = self._determine_quadrant(is_creating_value, roic_trend)
        quadrant_config = self.QUADRANTS[quadrant]
        
        # 检查声称是否合理
        claim_allowed = self._check_claim(claim, quadrant_config)
        
        # 生成消息
        if claim_allowed:
            message = f"{quadrant_config['name']}: 声称'{claim}'合理"
        else:
            message = f"{quadrant_config['name']}: 声称'{claim}'与数据矛盾，允许的声称: {quadrant_config['allowed_claims']}"
        
        return ROICResult(
            roic=roic_current,
            wacc=wacc,
            spread=spread,
            is_creating_value=is_creating_value,
            quadrant=quadrant,
            message=message,
        )
    
    def _determine_quadrant(self, is_creating_value: bool, trend: str) -> str:
        """确定象限"""
        if is_creating_value:
            if trend == "improving":
                return "Q1"
            else:
                return "Q2"
        else:
            if trend == "improving":
                return "Q3"
            else:
                return "Q4"
    
    def _check_claim(self, claim: str, quadrant_config: Dict) -> bool:
        """检查声称是否合理"""
        if not claim:
            return True
        
        # 检查是否在阻止列表中
        for blocked in quadrant_config["blocked_claims"]:
            if blocked in claim:
                return False
        
        # 检查是否在允许列表中
        for allowed in quadrant_config["allowed_claims"]:
            if allowed in claim:
                return True
        
        # 默认允许（不在任何列表中）
        return True
    
    def calculate_incremental_roic(
        self,
        delta_nopat: float,
        delta_ic: float,
    ) -> IncrementalROICResult:
        """计算增量ROIC"""
        incremental_roic = delta_nopat / delta_ic if delta_ic != 0 else 0
        
        return IncrementalROICResult(
            delta_nopat=delta_nopat,
            delta_ic=delta_ic,
            incremental_roic=incremental_roic,
            is_value_creating=incremental_roic > 0,
        )
    
    def get_correct_claim(self, result: ROICResult) -> str:
        """获取正确的声称"""
        quadrant_config = self.QUADRANTS[result.quadrant]
        
        if result.is_creating_value:
            return f"公司已跨越价值创造门槛(ROIC {result.roic:.1%} > WACC {result.wacc:.1%})"
        else:
            return f"公司尚未跨越价值创造门槛(ROIC {result.roic:.1%} < WACC {result.wacc:.1%}), 但差距正在{result.spread:.1%}"
    
    def generate_report(self, result: ROICResult) -> str:
        """生成ROIC-WACC报告"""
        lines = [
            "## ROIC-WACC分析报告",
            "",
            f"| 指标 | 值 |",
            f"|------|-----|",
            f"| ROIC | {result.roic:.1%} |",
            f"| WACC | {result.wacc:.1%} |",
            f"| Spread | {result.spread:.1%} |",
            f"| 象限 | {result.quadrant} |",
            f"| 价值创造 | {'是' if result.is_creating_value else '否'} |",
            "",
            f"**判断**: {result.message}",
        ]
        
        return "\n".join(lines)
