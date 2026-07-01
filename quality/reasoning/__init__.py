"""
quality/reasoning/__init__.py — 推理引擎模块

包含：
- CausalModeler: 因果建模器（Granger检验+敏感性分析+模板匹配）
- CounterArgumentValidator: 反面论证验证器
- CausalInferenceChain: 统一推理链（单链3阶段）
- DefaultColdStartPolicy: 默认冷启动策略
"""

from .causal_modeler import CausalModeler, TemplateMatcher, GrangerTester, SensitivityAnalyzer
from .counter_validator import CounterArgumentValidator
from .causal_inference import CausalInferenceChain
from .cold_start import DefaultColdStartPolicy

__all__ = [
    "CausalModeler",
    "TemplateMatcher",
    "GrangerTester",
    "SensitivityAnalyzer",
    "CounterArgumentValidator",
    "CausalInferenceChain",
    "DefaultColdStartPolicy",
]
