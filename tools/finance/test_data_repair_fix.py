"""B2b-3：data_repair 年份标注修复测试（canonicalize——删硬编码）

验收（路线图 B2b-3）：无硬编码 wrong_years/快手 pattern——
非目标财年的 20XX 年份动态识别，任意公司名通用。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import pytest

from finance.data_repair import fix_source_annotations


def test_fix_any_company_wrong_year():
    """任意公司名（非快手）的历史年份标注被修复"""
    content = "数据来源：小鹏集团2023年年报，归母净利润-103.76亿元。"
    fixed, count = fix_source_annotations(content, fiscal_year=2025)
    assert "小鹏集团2025年年报" in fixed
    assert count >= 1


def test_fix_multiple_wrong_years():
    """多个错误年份全部修复（2023/2024/2026）"""
    content = "来源：A公司2023年年报；来源：A公司2024年年报；来源：A公司2026年年报。"
    fixed, count = fix_source_annotations(content, fiscal_year=2025)
    assert "2023年" not in fixed
    assert "2024年" not in fixed
    assert "2026年" not in fixed
    assert fixed.count("2025年") == 3
    assert count == 3


def test_target_year_untouched():
    """目标财年不被修改"""
    content = "来源：公司2025年年报。"
    fixed, count = fix_source_annotations(content, fiscal_year=2025)
    assert "2025年" in fixed
    assert count == 0


def test_no_hardcoded_kuaishou():
    """修复后代码不含'快手'硬编码 pattern（防回归）"""
    import inspect

    import finance.data_repair as m
    src = inspect.getsource(m.fix_source_annotations)
    assert "快手" not in src, "不得含快手硬编码"
    assert "wrong_years = [y" in src, "wrong_years 应动态推导"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
