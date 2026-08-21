"""v3 兼容 shim：feature_flags —— HGF P0-① 修复（2026-08-22）

平铺在 quality/ 的模块以 v3.X 路径暴露（兼容历史测试 import）。
"""
from ..feature_flags import *  # noqa: F403
from ..feature_flags import FeatureDisabledError, FeatureFlags, FeatureModule  # noqa: F401
