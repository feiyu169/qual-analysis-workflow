"""HGF unit_test 门禁聚合入口（根 tests/ 约定桥接）。

HGF gate 的 unit_test 命令为 `pytest tests/`（根目录约定）。本工作区测试分散在
tools/finance/**/test_*.py，此处 import 聚合让 `pytest tests/` 能真实收集并执行。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
