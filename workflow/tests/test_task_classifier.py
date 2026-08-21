"""任务分级器单元测试（L0-L3、热修复、纯文档、关键模块、混合类型、输入校验）"""

import pytest

from task_classifier import Task, TaskClassifier, TaskClassifierError


def _classify(desc, files, lines, areas=None, labels=None, diff_stats=None):
    classifier = TaskClassifier()
    task = Task(
        description=desc,
        files=files,
        file_count=len(files),
        line_count=lines,
        affected_areas=areas,
        labels=labels,
        diff_stats=diff_stats,
    )
    return classifier.classify_task(task)


def test_hotfix_classified_as_l0():
    result = _classify("紧急修复线上故障", ["auth.py"], 5)
    assert result.level == "L0"


def test_hotfix_english_sev0_regex():
    result = _classify("sev0 incident on login", ["auth.py"], 5)
    assert result.level == "L0"


def test_hotfix_via_labels():
    result = _classify("fix login bug", ["auth.py"], 5, labels=["hotfix"])
    assert result.level == "L0"


def test_small_change_classified_as_l1_lite():
    """V3.4-B：单文件小改（<100 行 CODE）→ L1_LITE 轻量等级"""
    result = _classify("add helper function", ["utils.py"], 30)
    assert result.level == "L1_LITE"


def test_medium_change_classified_as_l2():
    result = _classify("refactor module", ["a.py", "b.py", "c.py", "d.py"], 200)
    assert result.level == "L2"


def test_large_change_classified_as_l3():
    files = [f"{c}.py" for c in "abcdefghijk"]
    result = _classify("big feature", files, 600)
    assert result.level == "L3"


def test_critical_module_upgrades_to_l2():
    result = _classify("add endpoint", ["routes.py"], 50, areas=["auth"])
    assert result.level == "L2"


def test_pure_docs_returns_docs_type():
    result = _classify("update readme", ["README.md"], 20)
    assert result.level == "DOCS"
    assert result.type == "DOCS"


def test_pure_config_returns_config_type():
    result = _classify("bump dependency", ["config.yaml"], 3)
    assert result.type == "CONFIG"
    assert result.level == "CONFIG"


def test_mixed_code_and_config_is_mixed():
    result = _classify("add feature", ["app.py", "config.yaml"], 60)
    assert result.type == "MIXED"
    assert set(result.types) == {"CODE", "CONFIG"}


def test_diff_stats_used_for_change_lines():
    result = _classify(
        "feature",
        ["app.py"],
        999,
        diff_stats={"additions": 40, "deletions": 5},
    )
    assert result.change_lines == 45
    # V3.4-B：45 行单文件小改 → L1_LITE（change_lines 来自 diff_stats）
    assert result.level == "L1_LITE"


def test_validation_rejects_empty_description():
    classifier = TaskClassifier()
    task = Task(description="", files=["a.py"], file_count=1, line_count=1)
    with pytest.raises(TaskClassifierError):
        classifier.classify_task(task)


def test_validation_rejects_empty_files():
    classifier = TaskClassifier()
    task = Task(description="x", files=[], file_count=0, line_count=1)
    with pytest.raises(TaskClassifierError):
        classifier.classify_task(task)


def test_select_level_empty_types_returns_none():
    """B1 修正：types=[] 时 select_level 返回 None（all([])=True 陷阱）"""
    classifier = TaskClassifier()
    assert classifier.select_level([], 1, 10) is None


def test_select_level_docs_small_l0_lite():
    classifier = TaskClassifier()
    assert classifier.select_level(["DOCS"], 1, 10) == "L0_LITE"
    # 大文档改 → 不轻量
    assert classifier.select_level(["DOCS"], 1, 100) is None


def test_select_level_code_single_l1_lite():
    classifier = TaskClassifier()
    assert classifier.select_level(["CODE"], 1, 50) == "L1_LITE"
    # 多文件/大改动 → 不轻量
    assert classifier.select_level(["CODE"], 2, 50) is None
    assert classifier.select_level(["CODE"], 1, 200) is None
    classifier = TaskClassifier()
    task = Task(description="x", files=[], file_count=0, line_count=1)
    with pytest.raises(TaskClassifierError):
        classifier.classify_task(task)
