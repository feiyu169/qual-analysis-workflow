"""金丝雀版本回归单元测试（漂移检测 + 真实金丝雀执行）"""

import canary


def test_drift_from_baseline_none():
    # V3.3.2（自审查 S2）：无 baseline 记录 → 自动重建基线快照
    # （重建成功 → 无漂移返回 []；目录不可写 → 返回"重建失败"信息，不崩溃）
    drift = canary.drift_from_baseline("C:/definitely/not/exists/dir")
    assert drift == [] or any("重建" in d for d in drift)


def test_drift_empty_when_versions_match(tmp_path):
    import baseline
    import gate_executor

    wd = str(tmp_path)
    # 建立 baseline（当前真实版本）
    ex = gate_executor.GateExecutor(canary.CONFIG_PATH)
    snap = baseline.snapshot(ex.config_path, ex.plugins)
    baseline.save(wd, snap)
    # 版本未变 → 无漂移
    drift = canary.drift_from_baseline(wd)
    assert drift == []


def test_drift_detects_version_change(tmp_path):
    import baseline

    wd = str(tmp_path)
    prev = {
        "config_sha256": "abc",
        "tool_versions": {"ruff": "ruff 0.99.0"},
        "plugins": ["ruff"],
    }
    baseline.save(wd, prev)
    drift = canary.drift_from_baseline(wd)
    assert any("ruff" in d for d in drift)


def test_check_skips_without_drift(tmp_path):
    result = canary.check(str(tmp_path))
    # 无 baseline → 有漂移 → 不跳过（真实跑金丝雀）
    assert result["skipped"] is False
    assert result["ok"] is True
    assert result["ruff"]["ok"] is True
    assert result["pytest"]["ok"] is True
