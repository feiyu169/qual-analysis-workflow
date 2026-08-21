"""v3 兼容 shim：authority_resolver —— HGF P0-① 修复（2026-08-22）

平铺在 quality/ 的模块以 v3.X 路径暴露（兼容历史测试 import）。
"""
from ..authority_resolver import *  # noqa: F403
from ..authority_resolver import (  # noqa: F401
    AuthorityLevel,
    AuthorityResolver,
    AuthorityResult,
    ConflictMode,
)
