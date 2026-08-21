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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
