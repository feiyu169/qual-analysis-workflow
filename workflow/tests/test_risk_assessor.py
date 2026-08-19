"""风险评估器单元测试（映射、组合加成、P32 护栏、阈值、配置驱动）"""

from risk_assessor import RiskAssessor


def _assess(areas, desc):
    return RiskAssessor().assess_risk(areas, desc)


def test_auth_payment_combination_is_high():
    result = _assess(["auth", "payment"], "login and checkout")
    assert result.risk == "high"
    assert result.combination_bonus == 3
    assert result.score == 9


def test_high_risk_factor_blocks_reduction():
    """P32 护栏：高危因子存在时，'fix' 不得降级风险"""
    result = _assess(["auth"], "fix critical authentication bypass")
    assert result.reduction_applied is False
    assert result.score == 3


def test_trivial_change_is_reduced():
    result = _assess(["config"], "fix typo in comment")
    assert result.reduction_applied is True
    assert result.risk == "low"


def test_unknown_area_maps_to_nothing():
    result = _assess(["calc"], "add a function")
    assert result.matched_factors == []
    assert result.score == 0


def test_crypto_database_combination_bonus():
    result = _assess(["crypto", "database"], "add encryption to storage")
    assert result.combination_bonus == 2
    assert result.score == 3 + 2 + 2  # crypto 3 + database 2 + bonus 2


def test_single_medium_factor_score():
    result = _assess(["database"], "change the schema")
    assert result.score == 2


def test_chinese_keyword_mapping():
    result = _assess([], "修复支付漏洞")
    assert "payment" in result.matched_factors or "security" in result.matched_factors


def test_chinese_affected_area_mapping():
    # 影响区域本身是中文（如 "支付"）也应映射到风险因子
    result = _assess(["支付"], "对接支付渠道")
    assert "payment" in result.matched_factors
    assert result.score >= 3


def test_config_driven_thresholds():
    config = {"risk_thresholds": {"low": 1, "medium": 2, "high": 10}}
    assessor = RiskAssessor(config)
    result = assessor.assess_risk(["auth"], "fix")
    assert result.risk == "medium"
