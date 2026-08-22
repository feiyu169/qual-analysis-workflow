"""B4 运营验证链 + 行业动态化 + 可比修复测试

验收（路线图 B4-1/2/3/6）：
- 结构性铁律 MAU≥DAU≥付费 阻断（B4-1）
- 派生钩稽 warning 级（DAU/MAU 比率、GMV 对照）（B4-1）
- 毛利率无默认值填充（B4-2）
- 行业动态映射（阅文→数字内容，非"新能源汽车"）（B4-3）
- 可比矩阵无错误 ticker（002024.SZ 修复）（B4-6）
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import pytest

from finance.fact_extractor import (
    ExtractedFacts,
    OperationalFacts,
    validate_operational_chain,
)
from finance.quality.peer_comparison import create_express_peers


def _facts_with_ops(**kwargs) -> ExtractedFacts:
    f = ExtractedFacts(company_name="测试", ticker="T", fiscal_year=2025)
    f.operational = OperationalFacts(**kwargs)
    return f


def test_chain_iron_rule_dau_gt_mau():
    """B4-1 铁律：DAU > MAU → 阻断级 violation"""
    facts = _facts_with_ops(dau=8.0, mau=7.0)
    v = validate_operational_chain(facts)
    assert any("DAU" in x and "MAU" in x for x in v)


def test_chain_iron_rule_paying_gt_dau():
    """B4-1 铁律：付费用户 > DAU → 阻断级 violation"""
    facts = _facts_with_ops(dau=4.0, paying_users=5.0)
    v = validate_operational_chain(facts)
    assert any("付费用户" in x for x in v)


def test_chain_valid_pass():
    """B4-1 正常数据通过（无 violation）"""
    facts = _facts_with_ops(dau=4.0, mau=7.0, paying_users=0.8)
    v = validate_operational_chain(facts)
    assert not v


def test_chain_derived_hook_ratio():
    """B4-1 派生钩稽：DAU/MAU 超范围 → warning"""
    facts = _facts_with_ops(dau=6.9, mau=7.0)  # 98.6%
    v = validate_operational_chain(facts)
    assert any("DAU/MAU" in x for x in v)


def test_no_default_gross_margin():
    """B4-2：毛利率无默认填充（50% 删除）"""
    from finance.fact_extractor import _calculate_unit_economics
    facts = _facts_with_ops(arpu=198.6, user_lifetime=24.0)
    facts.financial.gross_margin = None  # Wind 无源
    assumptions = _calculate_unit_economics(facts)
    assert facts.operational.gross_margin is None, "毛利率不得填充默认值"
    assert facts.operational.ltv is None, "LTV 在毛利率缺失时不得计算"
    assert any("毛利率未披露" in a for a in assumptions), "应标注数据不足"


def test_industry_dynamic_yuewen():
    """B4-3：阅文 → 数字内容（非"新能源汽车"）"""
    from finance.qual_v8.adapters import industry_for
    assert industry_for("阅文集团") == "数字内容"
    assert industry_for("小鹏集团-W") == "新能源汽车"


def test_peer_comparison_no_wrong_ticker():
    """B4-6：可比矩阵无错误 ticker（中通应为 ZTO.N，非 002024.SZ=分众传媒）"""
    peers = create_express_peers()
    zto = next(p for p in peers if p.name == "中通快递")
    assert zto.ticker == "ZTO.N", f"中通 ticker 应 ZTO.N，实为 {zto.ticker}"
    assert zto.market == "us"
    assert not any(p.ticker == "002024.SZ" for p in peers), "不得残留分众传媒 ticker"


# ====================================================================
# v3（用户原则：Wind 没有的由财报提供）：程序化运营提取 + LLM 提取原文核对
# ====================================================================

def test_extract_operational_from_filings():
    """v3：程序化财报运营提取（交付量/门店数/毛利率——不依赖 LLM，源=财报原文）"""
    from finance.fact_extractor import extract_operational_from_filings

    sections = {
        "业务概览": "全年交付389,000辆汽车，门店520家，毛利率14.5%",
        "管理层讨论": "公司经营稳健",
    }
    ops = extract_operational_from_filings(sections)
    assert "deliveries" in ops, f"应提取交付量: {ops}"
    assert ops["deliveries"]["value"] == pytest.approx(389000), "交付量应 389000 辆"
    assert ops["stores"]["value"] == pytest.approx(520), "门店数应 520 家"
    assert ops["gross_margin"]["value"] == pytest.approx(0.145), "毛利率应 14.5%→0.145"
    assert ops["deliveries"]["source"], "应有来源章节标注"


def test_parse_chunk_response_source_verified():
    """v3：LLM 提取运营值经财报原文核对——原文找到→high；未找到→low+warning（防编造）"""
    from finance.fact_extractor import _parse_chunk_response

    # 原文中有 389,000（交付量）
    sections = {"业务概览": "全年交付389,000辆汽车"}
    llm_ok = '{"operational": {"deliveries": {"value": 389000, "source": "业务概览"}}}'
    data_ok, warns_ok = _parse_chunk_response(llm_ok, 0, sections)
    conf = (data_ok or {}).get("confidences", {}).get("operational.deliveries")
    assert conf != "low", f"原文能找到的值不应标 low: {warns_ok}"

    # 原文中无 999999（编造）
    llm_bad = '{"operational": {"deliveries": {"value": 999999, "source": "业务概览"}}}'
    data_bad, warns_bad = _parse_chunk_response(llm_bad, 0, sections)
    conf_bad = (data_bad or {}).get("confidences", {}).get("operational.deliveries")
    assert conf_bad == "low", "原文找不到的值应标 low（防 LLM 编造运营数字）"
    assert any("原文核对" in w for w in warns_bad), "应有原文核对失败 warning"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
