"""v3 兼容 shim：financial_standards —— HGF P0-① 修复（2026-08-22）

平铺在 quality/ 的模块以 v3.X 路径暴露（兼容历史测试 import）。
"""
from ..financial_standards import *  # noqa: F403
from ..financial_standards import FinancialStandards  # noqa: F401
