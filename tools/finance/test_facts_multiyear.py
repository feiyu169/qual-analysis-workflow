"""B3 事实表多财年化 + 可复核测试

验收（路线图 B3-1/2/3/4）：
- ExtractedFacts.by_year 多财年结构（from_dict/to_dict 往返）
- 批次仲裁冲突保留首个 + warning（B3-3）
- 事实表格式：财务来源 Wind、未披露字段显式、页码 unverified（B3-2）
- prompt 含"宁缺毋滥/禁前批补值"规则（B3-4）
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import pytest

from finance.fact_extractor import (
    EXTRACTION_PROMPT,
    ExtractedFacts,
    OperationalFacts,
    _merge_chunk_data,
    format_facts_as_context,
)


def test_by_year_roundtrip():
    """B3-1：by_year 多财年结构序列化往返"""
    base = ExtractedFacts(company_name="小鹏集团-W", ticker="9868.HK", fiscal_year=2025)
    fy23 = ExtractedFacts(company_name="小鹏集团-W", ticker="9868.HK", fiscal_year=2023)
    fy23.operational.dau = 4.01
    fy24 = ExtractedFacts(company_name="小鹏集团-W", ticker="9868.HK", fiscal_year=2024)
    base.by_year = {2023: fy23, 2024: fy24}

    d = base.to_dict()
    restored = ExtractedFacts.from_dict(d)
    assert set(restored.by_year.keys()) == {2023, 2024}
    assert restored.by_year[2023].operational.dau == 4.01
    assert restored.by_year[2023].fiscal_year == 2023


def test_merge_conflict_keeps_first():
    """B3-3：跨批冲突保留首个 + warning（无静默覆盖）"""
    chunk1 = {"operational": {"dau": 4.01, "mau": 7.14}}
    chunk2 = {"operational": {"dau": 4.02, "mau": 7.14}}  # dau 冲突

    facts = _merge_chunk_data([chunk1, chunk2], "测试", "TEST")
    assert facts.operational.dau == 4.01, "冲突应保留首个"
    assert facts.operational.mau == 7.14
    assert any("批次仲裁" in w for w in facts.meta.warnings), "应有仲裁 warning"


def test_merge_no_conflict_keeps_all():
    """B3-3：无冲突正常合并"""
    chunk1 = {"operational": {"dau": 4.01}}
    chunk2 = {"operational": {"mau": 7.14}}
    facts = _merge_chunk_data([chunk1, chunk2], "测试", "TEST")
    assert facts.operational.dau == 4.01
    assert facts.operational.mau == 7.14
    assert not any("批次仲裁" in w for w in facts.meta.warnings)


def test_facts_format_wind_source_and_unverified_page():
    """B3-2：事实表财务来源 Wind、未披露显式、页码 unverified"""
    facts = ExtractedFacts(company_name="测试", ticker="T", fiscal_year=2025)
    facts.operational = OperationalFacts(dau=4.01, sources={"operational.dau": "业务概览"})
    # financial 由 Wind 填充场景：营收有值、有息负债未披露
    facts.financial.revenue = 767.20
    facts.financial.interest_bearing_debt = None

    text = format_facts_as_context(facts)
    assert "| 营业收入 | IFRS | 767.2 | 亿元 | Wind |" in text, "财务来源应为 Wind"
    assert "有息负债" in text and "未披露" in text, "未披露字段应显式标注"
    assert "页码" in text and "unverified" in text, "运营表应有页码列（unverified）"


def test_prompt_no_fabrication_rules():
    """B3-4：prompt 含宁缺毋滥与禁前批补值规则"""
    assert "宁可缺失不可杜撰" in EXTRACTION_PROMPT
    assert "禁止用本批次之外的数据补当前批次" in EXTRACTION_PROMPT


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
