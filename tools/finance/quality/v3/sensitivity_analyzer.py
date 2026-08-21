"""v3 兼容 shim：sensitivity_analyzer —— HGF P0-① 修复（2026-08-22）

平铺在 quality/ 的模块以 v3.X 路径暴露（兼容历史测试 import）。
"""
from ..sensitivity_analyzer import *  # noqa: F403
from ..sensitivity_analyzer import SensitivityAnalyzer, SensitivityConfig  # noqa: F401
