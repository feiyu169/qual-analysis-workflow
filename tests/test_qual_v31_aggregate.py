"""qual v3.1 阶段 A 测试聚合（HGF unit_test 门禁入口）。

pytest 收集本模块 import 引入的 test_* 函数；聚合 qual 相关全部测试，
使 `pytest tests/`（HGF 根目录约定）真实执行而非收集 0 项。
"""
# 核心循环（v3.1 P0-A：签名/豁免/单调/预算/墙钟/shadow）
from finance.quality.test_v31_p0a import *  # noqa: F401,F403

# 数值闸门（既有）
from finance.quality.test_numeric_guard import *  # noqa: F401,F403

# with_fallback 降级（v3.1 P0-2/4/5）
from finance.test_llm_fallback import *  # noqa: F401,F403

# run 脚本一致性（v3.1 P0-2 同模块接线）
from finance.test_run_scripts_consistent import *  # noqa: F401,F403

# qual_v8 引擎核心（既有）
from finance.qual_v8.tests.test_core import *  # noqa: F401,F403
