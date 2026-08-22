"""v3 质量层 shim：平铺在 quality/ 的 v3 模块在此以子包形式暴露。

兼容 workflow.py 的 `from .quality.v3.* import ...` 导入路径。

双专家 P2（2026-08-22）：补聚合导出——原为空包，`from finance.quality.v3 import X`
会 ImportError。子模块（v3/X.py）是平铺实现的两行式 re-export shim，
此处再聚合常用符号供 `from finance.quality.v3 import ...` 顶层导入。
"""
from .audit_validator import *  # noqa: F401,F403
from .authority_resolver import *  # noqa: F401,F403
from .capm_calculator import *  # noqa: F401,F403
from .conclusion_synthesizer import *  # noqa: F401,F403
from .config_validator import *  # noqa: F401,F403
from .content_validator import *  # noqa: F401,F403
from .dcf_service import *  # noqa: F401,F403
from .exception_handler import *  # noqa: F401,F403
from .fcf_calculator import *  # noqa: F401,F403
from .feature_flags import *  # noqa: F401,F403
from .financial_standards import *  # noqa: F401,F403
from .incremental_checker import *  # noqa: F401,F403
from .insight_audit import *  # noqa: F401,F403
from .metrics import *  # noqa: F401,F403
from .module_loader import *  # noqa: F401,F403
from .pipeline import *  # noqa: F401,F403
from .review_integrator import *  # noqa: F401,F403
from .review_repair_loop import *  # noqa: F401,F403
from .roic_checker import *  # noqa: F401,F403
from .roic_wacc_checker import *  # noqa: F401,F403
from .sensitivity_analyzer import *  # noqa: F401,F403
from .terminal_value import *  # noqa: F401,F403
from .terminal_value_arbitrator import *  # noqa: F401,F403
from .terminal_value_calculator import *  # noqa: F401,F403
from .wind_field_mapper import *  # noqa: F401,F403
from .workflow_integration import *  # noqa: F401,F403
from .year_anchor import *  # noqa: F401,F403

__all__ = []
