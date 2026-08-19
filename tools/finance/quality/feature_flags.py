"""
FeatureFlags模块

功能:
- 模块开关控制
- 4种profile: full/minimal/no_llm/valuation_only
- 环境变量覆盖
- 不可变配置(frozen=True)

解决: P0-4 缺少Feature Flag
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import FrozenSet, Optional


class FeatureModule(str, Enum):
    """可开关的功能模块"""
    
    # 核心（不可关闭）
    STRUCTURAL_CHECK = "structural_check"
    
    # 质量层（可选）
    SEMANTIC_AUDIT = "semantic_audit"
    CHAPTER_REPAIR = "chapter_repair"
    CHECKPOINT = "checkpoint"
    
    # 推理层（可选）
    CAUSAL_INFERENCE = "causal_inference"
    COUNTER_ARGUMENT = "counter_argument"
    SCENARIO_ANALYSIS = "scenario_analysis"
    
    # 估值层（可选）
    DCF = "dcf"
    SOTP = "sotp"
    SENSITIVITY = "sensitivity"
    STRESS_TEST = "stress_test"
    PEER_COMPARISON = "peer_comparison"
    
    # v3新增模块（可选）
    YEAR_ANCHOR = "year_anchor"
    FINANCIAL_STANDARDS = "financial_standards"
    FIELD_MAPPING = "field_mapping"
    AUTHORITY_RESOLVER = "authority_resolver"
    TERMINAL_VALUE_ARBITRATOR = "terminal_value_arbitrator"
    AUDIT_VALIDATOR = "audit_validator"
    CONCLUSION_SYNTHESIZER = "conclusion_synthesizer"
    INCREMENTAL_CHECKER = "incremental_checker"
    
    # 其他（可选）
    FALSIFICATION = "falsification"
    CATALYST_CALENDAR = "catalyst_calendar"
    RISK_QUANTIFICATION = "risk_quantification"
    MARGIN_OF_SAFETY = "margin_of_safety"


# 模块分类
CORE_MODULES = frozenset({FeatureModule.STRUCTURAL_CHECK})

QUALITY_MODULES = frozenset({
    FeatureModule.SEMANTIC_AUDIT,
    FeatureModule.CHAPTER_REPAIR,
    FeatureModule.CHECKPOINT,
})

REASONING_MODULES = frozenset({
    FeatureModule.CAUSAL_INFERENCE,
    FeatureModule.COUNTER_ARGUMENT,
    FeatureModule.SCENARIO_ANALYSIS,
})

VALUATION_MODULES = frozenset({
    FeatureModule.DCF,
    FeatureModule.SOTP,
    FeatureModule.SENSITIVITY,
    FeatureModule.STRESS_TEST,
    FeatureModule.PEER_COMPARISON,
})

V3_MODULES = frozenset({
    FeatureModule.YEAR_ANCHOR,
    FeatureModule.FINANCIAL_STANDARDS,
    FeatureModule.FIELD_MAPPING,
    FeatureModule.AUTHORITY_RESOLVER,
    FeatureModule.TERMINAL_VALUE_ARBITRATOR,
    FeatureModule.AUDIT_VALIDATOR,
    FeatureModule.CONCLUSION_SYNTHESIZER,
    FeatureModule.INCREMENTAL_CHECKER,
})


class FeatureDisabledError(Exception):
    """功能未启用异常"""
    pass


@dataclass(frozen=True)
class FeatureFlags:
    """Feature Flag配置（不可变）
    
    使用方式:
    1. 默认全部启用
    2. 通过profile裁剪（如"minimal"只启用核心）
    3. 通过环境变量覆盖单个模块
    
    Profile说明:
    - full: 全部启用（默认）
    - minimal: 仅核心模块
    - no_llm: 禁用所有需要LLM的模块
    - valuation_only: 仅估值相关模块
    """
    
    _enabled: FrozenSet[FeatureModule] = field(
        default_factory=lambda: frozenset(FeatureModule)
    )
    
    @classmethod
    def default(cls) -> FeatureFlags:
        """默认配置：全部启用"""
        return cls()
    
    @classmethod
    def minimal(cls) -> FeatureFlags:
        """最小配置：仅核心模块"""
        return cls(_enabled=CORE_MODULES)
    
    @classmethod
    def no_llm(cls) -> FeatureFlags:
        """无LLM配置：禁用所有需要LLM的模块"""
        llm_modules = {
            FeatureModule.SEMANTIC_AUDIT,
            FeatureModule.CHAPTER_REPAIR,
            FeatureModule.CAUSAL_INFERENCE,
            FeatureModule.COUNTER_ARGUMENT,
            FeatureModule.SCENARIO_ANALYSIS,
        }
        return cls(_enabled=frozenset(FeatureModule) - llm_modules)
    
    @classmethod
    def valuation_only(cls) -> FeatureFlags:
        """估值专项：仅估值相关模块"""
        return cls(_enabled=VALUATION_MODULES | CORE_MODULES)
    
    @classmethod
    def from_profile(cls, profile: str) -> FeatureFlags:
        """从预定义profile创建"""
        profiles = {
            "full": cls.default(),
            "minimal": cls.minimal(),
            "no_llm": cls.no_llm(),
            "valuation_only": cls.valuation_only(),
        }
        return profiles.get(profile, cls.default())
    
    @classmethod
    def from_env(cls) -> FeatureFlags:
        """从环境变量创建
        
        环境变量格式:
        - QUALITY_PROFILE=full|minimal|no_llm|valuation_only
        - QUALITY_DISABLE_<MODULE>=1|true|yes 禁用单个模块
        """
        # 从profile创建基础配置
        profile = os.environ.get("QUALITY_PROFILE", "full")
        flags = cls.from_profile(profile)
        
        # 环境变量覆盖单个模块
        disabled = set()
        for module in FeatureModule:
            env_key = f"QUALITY_DISABLE_{module.value.upper()}"
            if os.environ.get(env_key, "").lower() in ("1", "true", "yes"):
                disabled.add(module)
        
        if disabled:
            new_enabled = frozenset(FeatureModule) - frozenset(disabled)
            return cls(_enabled=new_enabled)
        
        return flags
    
    def is_enabled(self, module: FeatureModule) -> bool:
        """检查模块是否启用"""
        return module in self._enabled
    
    def require(self, module: FeatureModule) -> None:
        """要求模块启用，否则抛出异常"""
        if not self.is_enabled(module):
            raise FeatureDisabledError(
                f"模块 {module.value} 未启用。"
                f"当前profile可用模块: {[m.value for m in self._enabled]}"
            )
    
    def enabled_modules(self) -> list:
        """返回所有启用的模块"""
        return sorted([m.value for m in self._enabled])
    
    def disabled_modules(self) -> list:
        """返回所有禁用的模块"""
        all_modules = set(FeatureModule)
        return sorted([m.value for m in all_modules - self._enabled])
