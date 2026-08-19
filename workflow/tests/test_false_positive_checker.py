"""误报检查器单元测试（加载配置、永久误报、过期判断、豁免）"""

import os

import yaml

from false_positive_checker import FalsePositiveChecker


def _make_config():
    return {
        "known_false_positives": [
            {
                "id": "fp-001",
                "rule": "RULE_A",
                "file": "tests/test_x.py",
                "reason": "测试文件",
                "approved_by": "tech_lead",
                "expiry": None,
                "permanent": True,
            },
            {
                "id": "fp-002",
                "rule": "RULE_B",
                "file": "config/test.yaml",
                "reason": "测试配置",
                "approved_by": "security_team",
                "expiry": "2000-01-01",
                "permanent": False,
            },
        ],
        "exemptions": [
            {
                "id": "ex-001",
                "type": "legacy_code",
                "description": "存量代码",
                "scope": "incremental_only",
                "approved_by": "tech_lead",
                "expiry": None,
                "conditions": [],
            },
            {
                "id": "ex-002",
                "type": "emergency_fix",
                "description": "紧急修复",
                "scope": "all",
                "approved_by": "tech_lead",
                "expiry": "2000-01-01",
                "conditions": ["涉及认证"],
            },
        ],
    }


def _checker(tmp_path):
    path = os.path.join(str(tmp_path), "exceptions.yaml")
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(_make_config(), f, allow_unicode=True)
    return FalsePositiveChecker(config_path=path)


def test_loads_real_workflow_config():
    # 默认配置路径应指向 workflow/config/exceptions.yaml（迁移后无 ~/.hermes）
    checker = FalsePositiveChecker()
    assert os.path.exists(checker.config_path)
    assert len(checker.list_false_positives()) > 0


def test_permanent_false_positive_matches(tmp_path):
    checker = _checker(tmp_path)
    assert checker.is_false_positive("RULE_A", "tests/test_x.py") is True


def test_expired_false_positive_does_not_match(tmp_path):
    checker = _checker(tmp_path)
    assert checker.is_false_positive("RULE_B", "config/test.yaml") is False


def test_get_and_list(tmp_path):
    checker = _checker(tmp_path)
    assert checker.get_false_positive("RULE_A", "tests/test_x.py").id == "fp-001"
    assert len(checker.list_false_positives()) == 2
    assert checker.get_exemption("legacy_code").id == "ex-001"


def test_exemption_without_expiry_matches(tmp_path):
    checker = _checker(tmp_path)
    assert checker.has_exemption("legacy_code") is True


def test_expired_exemption_does_not_match(tmp_path):
    checker = _checker(tmp_path)
    assert checker.has_exemption("emergency_fix", {"has_auth": True}) is False


def test_is_expired(tmp_path):
    checker = _checker(tmp_path)
    assert checker.is_expired(checker.false_positives[0]) is False
    assert checker.is_expired(checker.false_positives[1]) is True
