"""HGF 测试质量度量脚本（V3.2.0）

被技能文档引用但此前缺失（文档-代码一致性治理补齐）。
度量：测试函数总数、断言总数、无断言测试（空桩）列表。
用法:
    python scripts/test_quality_metrics.py --dir <项目根>
退出码：0=无空桩，1=存在空桩。
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gate_plugins import TestQualityPlugin  # noqa: E402
from gate_types import GateConfig  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="HGF 测试质量度量")
    parser.add_argument("--dir", default=".", help="项目根目录（含 tests/）")
    args = parser.parse_args()

    plugin = TestQualityPlugin(
        GateConfig(name="test_quality", tool="test-quality", command="")
    )
    result = plugin.execute([], args.dir)

    print(f"状态: {result.status.value}")
    print(result.message)
    for issue in result.issues:
        print(f"  ✗ {issue.message}")
    for suggestion in result.suggestions:
        print(f"  建议: {suggestion}")

    sys.exit(0 if result.status.value == "passed" else 1)


if __name__ == "__main__":
    main()
