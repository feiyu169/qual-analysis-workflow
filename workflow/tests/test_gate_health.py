"""门禁健康熔断测试（V3.4-A，heavyskill 审查修正版）。

覆盖：CLOSED→OPEN 熔断 / HALF_OPEN 显式状态 / 单试运行保护 /
安全底线不熔断 / 原子写 / tripped_at 清理 / 试运行失败回 OPEN。
"""

import json
import os
import time

import gate_health


def _mk_wd(tmp_path) -> str:
    wd = str(tmp_path)
    os.makedirs(os.path.join(wd, ".hgf"), exist_ok=True)
    return wd


def test_trips_after_max_failures(tmp_path):
    wd = _mk_wd(tmp_path)
    for _ in range(3):
        gate_health.record(wd, "format_check", passed=False)
    assert gate_health.decide(wd, "format_check") == "skip"
    report = gate_health.health_report(wd)
    assert any(g["gate"] == "format_check" for g in report["open"])


def test_critical_gates_never_trip(tmp_path):
    wd = _mk_wd(tmp_path)
    for _ in range(5):
        gate_health.record(wd, "unit_test", passed=False)
    assert gate_health.decide(wd, "unit_test") == "execute"


def test_half_open_explicit_after_cooldown(tmp_path):
    """A1 修正：冷却结束 → 显式 half_open（trial）而非直接 execute"""
    wd = _mk_wd(tmp_path)
    for _ in range(3):
        gate_health.record(wd, "format_check", passed=False)
    # 冷却期内 → skip
    assert gate_health.decide(wd, "format_check") == "skip"
    # 模拟冷却结束（改写 opened_at 为过去）
    state_path = os.path.join(wd, ".hgf", "gate_health.json")
    with open(state_path, encoding="utf-8") as f:
        state = json.load(f)
    state["format_check"]["opened_at"] = time.time() - 1000
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    # 冷却后首次 decide → trial（进入 half_open）
    assert gate_health.decide(wd, "format_check") == "trial"
    # 状态持久化为 half_open
    with open(state_path, encoding="utf-8") as f:
        after = json.load(f)
    assert after["format_check"]["status"] == "half_open"


def test_single_trial_protection(tmp_path):
    """A1 修正：half_open 窗口内多次 decide 只返回一次 trial"""
    wd = _mk_wd(tmp_path)
    for _ in range(3):
        gate_health.record(wd, "format_check", passed=False)
    state_path = os.path.join(wd, ".hgf", "gate_health.json")
    with open(state_path, encoding="utf-8") as f:
        state = json.load(f)
    state["format_check"]["opened_at"] = time.time() - 1000
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    # 第一次 → trial；第二次（窗口内）→ 仍 trial（单试运行，重复调用不重复开）
    assert gate_health.decide(wd, "format_check") == "trial"
    assert gate_health.decide(wd, "format_check") == "trial"


def test_trial_failure_reopens(tmp_path):
    """A1 修正：HALF_OPEN 试运行失败 → 回 OPEN（opened_at 重置）"""
    wd = _mk_wd(tmp_path)
    for _ in range(3):
        gate_health.record(wd, "format_check", passed=False)
    state_path = os.path.join(wd, ".hgf", "gate_health.json")
    with open(state_path, encoding="utf-8") as f:
        state = json.load(f)
    state["format_check"]["opened_at"] = time.time() - 1000
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    gate_health.decide(wd, "format_check")  # → trial
    gate_health.record(wd, "format_check", passed=False)  # 试运行失败
    assert gate_health.decide(wd, "format_check") == "skip"  # 重新 open
    report = gate_health.health_report(wd)
    assert any(g["gate"] == "format_check" for g in report["open"])


def test_passed_clears_all_temporal_fields(tmp_path):
    """A3 修正：passed 时清理 opened_at/tripped_at/trial_started_at"""
    wd = _mk_wd(tmp_path)
    for _ in range(3):
        gate_health.record(wd, "format_check", passed=False)
    gate_health.record(wd, "format_check", passed=True)
    state_path = os.path.join(wd, ".hgf", "gate_health.json")
    with open(state_path, encoding="utf-8") as f:
        state = json.load(f)
    g = state["format_check"]
    assert g["status"] == "closed"
    assert "opened_at" not in g
    assert "tripped_at" not in g
    assert "trial_started_at" not in g


def test_recovers_after_pass(tmp_path):
    wd = _mk_wd(tmp_path)
    for _ in range(3):
        gate_health.record(wd, "format_check", passed=False)
    gate_health.record(wd, "format_check", passed=True)
    assert gate_health.decide(wd, "format_check") == "execute"


def test_atomic_write_creates_valid_json(tmp_path):
    """A2 修正：原子写后文件为有效 JSON（无临时文件残留）"""
    wd = _mk_wd(tmp_path)
    gate_health.record(wd, "format_check", passed=False)
    state_path = os.path.join(wd, ".hgf", "gate_health.json")
    with open(state_path, encoding="utf-8") as f:
        data = json.load(f)
    assert data["format_check"]["status"] == "closed"
    # 无 .tmp 残留
    assert not os.path.exists(state_path + ".tmp")
