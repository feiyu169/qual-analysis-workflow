"""qual v3.1 阶段 A 测试聚合（HGF unit_test 门禁入口）。

pytest 收集本模块 import 引入的 test_* 函数；聚合 qual 相关全部测试，
使 `pytest tests/`（HGF 根目录约定）真实执行而非收集 0 项。
"""
# 核心循环（v3.1 P0-A：签名/豁免/单调/预算/墙钟/shadow）
from finance.downloaders.test_downloaders import *

# ====================================================================
# HGF P0-① 修复后激活的测试（v3 shim + 契约对齐——2026-08-22 接入）
# 此前 27 文件不可收集，现全部可跑（契约一致的通过，不兼容的显式 skip）
# ====================================================================
# 解析器/下载器（契约一致部分：models/http_client/DocumentStore/Fallback）
from finance.parsers.test_parsers import *

# qual_v8 引擎核心（既有）
from finance.qual_v8.tests.test_core import *

# 质量组件（v3 契约对齐后）
from finance.quality.test_capm_calculator import *
from finance.quality.test_e2e import *
from finance.quality.test_feature_flags import *
from finance.quality.test_golden_set import *
from finance.quality.test_integration import *

# 数值闸门（既有）
from finance.quality.test_numeric_guard import *
from finance.quality.test_sotp_valuation import *
from finance.quality.test_stress_test import *
from finance.quality.test_v31_p0a import *

# ADVC 黄金回归集（P2：历史错例正/负样本——防校验器回退）
from finance.test_advc_golden import *
from finance.test_advc_wiring import *

# ADVC 层0/层1/层2（P0 既有 + P1 T2 开关）
from finance.test_anchor_deviation import *
from finance.test_anchor_repair import *
from finance.test_b4_operational_chain import *
from finance.test_data_repair_fix import *

# 财务语义/回归（既有独立测试）
from finance.test_fiscal_semantics import *

# with_fallback 降级（v3.1 P0-2/4/5）
from finance.test_llm_fallback import *
from finance.test_normalize_values import *
from finance.test_qual_fix_regression import *
from finance.test_quality_enhancer import *

# run 脚本一致性（v3.1 P0-2 同模块接线）
from finance.test_run_scripts_consistent import *
from finance.test_stage_c import *
from finance.test_valuation_loss_failfast import *
from finance.test_wind_field_disposition import *
