"""v3 兼容 shim：capm_calculator —— HGF P0-① 修复（2026-08-22）

平铺在 quality/ 的模块以 v3.X 路径暴露（兼容历史测试 import）。
"""
from ..capm_calculator import *  # noqa: F403
from ..capm_calculator import CAPMCalculator, CAPMConfig, CAPMResult  # noqa: F401
