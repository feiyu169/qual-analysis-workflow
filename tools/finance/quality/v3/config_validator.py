"""v3 兼容 shim：config_validator —— HGF P0-① 修复（2026-08-22）

平铺在 quality/ 的模块以 v3.X 路径暴露（兼容历史测试 import）。
"""
from ..config_validator import *  # noqa: F403
from ..config_validator import ConfigValidator, ValidationResult  # noqa: F401
