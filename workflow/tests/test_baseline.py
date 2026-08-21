"""门禁基线存档单元测试（快照/漂移检测/存档）"""

import json
import os

import baseline


def _snap(**kw):
    base = {
        "timestamp": "2026-08-17T00:00:00",
        "config_path": "x.yaml",
        "config_sha256": "abc123",
        "tool_versions": {"ruff": "0.16.3", "pytest": "9.1.1"},
        "plugins": ["ruff", "pytest"],
    }
    base.update(kw)
    return base


def test_snapshot_captures_config_hash(tmp_path):
    cfg = os.path.join(str(tmp_path), "gates.yaml")
    with open(cfg, "w", encoding="utf-8") as f:
        f.write("gates: {}\n")
    snap = baseline.snapshot(cfg, {})
    assert len(snap["config_sha256"]) == 12
    assert snap["plugins"] == []


def test_drift_detects_config_change():
    old = _snap(config_sha256="aaa")
    new = _snap(config_sha256="bbb")
    changes = baseline.drift(old, new)
    assert any("门禁配置变更" in c for c in changes)


def test_drift_detects_tool_version_change():
    old = _snap()
    new = _snap(tool_versions={"ruff": "0.16.4", "pytest": "9.1.1"})
    changes = baseline.drift(old, new)
    assert any("ruff" in c and "0.16.4" in c for c in changes)


def test_drift_empty_when_identical():
    old = _snap()
    new = _snap()
    assert baseline.drift(old, new) == []


def test_drift_first_run_message():
    assert baseline.drift(None, _snap()) == ["首次执行，已建立基线"]


def test_update_saves_and_returns_changes(tmp_path):
    wd = str(tmp_path)
    changes1 = baseline.update(wd, _snap())
    assert changes1 == ["首次执行，已建立基线"]
    assert os.path.exists(baseline.path(wd))
    changes2 = baseline.update(wd, _snap())
    assert changes2 == []
    with open(baseline.path(wd), encoding="utf-8") as f:
        assert json.load(f)["config_sha256"] == "abc123"


def test_load_returns_none_when_missing(tmp_path):
    """缺失文件 → None（无基线）"""
    assert baseline.load(str(tmp_path)) is None


def test_load_returns_none_when_corrupt(tmp_path):
    """V3.3.2 S2：损坏的 baseline.json → None 而非崩溃（实测旧版遗留文件
    末尾多一个 } 导致 --canary 抛未捕获 JSONDecodeError）"""
    wd = str(tmp_path)
    os.makedirs(os.path.join(wd, ".hgf"), exist_ok=True)
    with open(os.path.join(wd, ".hgf", "baseline.json"), "w", encoding="utf-8") as f:
        f.write('{"a": 1}\n}')  # 无效 JSON（Extra data）
    assert baseline.load(wd) is None


def test_load_returns_dict_when_valid(tmp_path):
    wd = str(tmp_path)
    os.makedirs(os.path.join(wd, ".hgf"), exist_ok=True)
    with open(os.path.join(wd, ".hgf", "baseline.json"), "w", encoding="utf-8") as f:
        f.write('{"config_sha256": "abc", "tool_versions": {}}')
    data = baseline.load(wd)
    assert data is not None
    assert data["config_sha256"] == "abc"
