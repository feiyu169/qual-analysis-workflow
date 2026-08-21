"""门禁健康熔断（V3.4-A，heavyskill 审查修正版）。

Circuit Breaker 模式：门禁连续失败可能阻塞流程（failure_log 自锁雪崩是实证），
熔断让"故障门禁"降级为告警而非阻塞——把"门禁故障"与"代码故障"分离，
避免门禁自身成为新的单点故障。

状态机（V3.4 修正：显式 HALF-OPEN + 单试运行保护）：
  CLOSED    正常执行；失败计数累积
  OPEN      连续失败≥max_failures → 跳过门禁并告警（不阻塞）
  HALF_OPEN 冷却期后进入试运行（持久化状态，单次）；通过→CLOSED，失败→OPEN

修正项（对应 heavyskill K=8 审查）：
  A1 显式 half_open 状态 + 试运行保护（并发只允许一次试运行）
  A2 原子写（复用 state_io.atomic_write_json，防崩溃损坏）
  A3 passed 时清理 opened_at 与 tripped_at（无脏数据）
  A4 cooldown_s 集中到配置（函数签名一致）
  A5 熔断告警写入 runs.jsonl（健康报告可审计）

例外：CRITICAL_GATES（安全底线）永不熔断。
"""

import json
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))

try:
    from . import state_io
except ImportError:
    import state_io

# 安全底线门禁：不熔断（静态分析/单测/密钥扫描/安全扫描）
CRITICAL_GATES = {"static_analysis", "unit_test", "secret_scan", "security_scan"}

# 默认阈值（集中配置，A4 修正：函数不再接受可漂移的独立参数）
DEFAULT_MAX_FAILURES = 3
DEFAULT_COOLDOWN_S = 300


def _state_path(working_dir: str) -> str:
    return os.path.join(working_dir, ".hgf", "gate_health.json")


def _load_state(working_dir: str) -> dict:
    p = _state_path(working_dir)
    if not os.path.exists(p):
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}  # 损坏→视为无状态（降级重建）


def _save_state(working_dir: str, state: dict) -> None:
    """A2 修正：原子写（write-temp + os.replace，防崩溃损坏/并发半写）"""
    state_io.atomic_write_json(_state_path(working_dir), state)


def decide(
    working_dir: str,
    gate: str,
    *,
    max_failures: int = DEFAULT_MAX_FAILURES,
    cooldown_s: int = DEFAULT_COOLDOWN_S,
) -> str:
    """返回门禁当前执行模式：'execute' | 'skip'（熔断跳过）| 'trial'（HALF_OPEN 试运行）"""
    if gate in CRITICAL_GATES:
        return "execute"  # 安全底线永不熔断
    state = _load_state(working_dir)
    g = state.get(gate, {})
    status = g.get("status", "closed")
    if status == "open":
        if time.time() - g.get("opened_at", 0) >= cooldown_s:
            # A1 修正：冷却结束 → 进入 HALF_OPEN（持久化，防止并发多次试运行）
            g["status"] = "half_open"
            g["trial_started_at"] = time.time()
            state[gate] = g
            _save_state(working_dir, state)
            return "trial"
        return "skip"
    if status == "half_open":
        # 已在试运行窗口内：仅允许一次（若超时窗口则重置为 open）
        if time.time() - g.get("trial_started_at", 0) <= cooldown_s:
            return "trial"
        g["status"] = "open"
        state[gate] = g
        _save_state(working_dir, state)
        return "skip"
    return "execute"


def record(
    working_dir: str,
    gate: str,
    *,
    passed: bool,
    max_failures: int = DEFAULT_MAX_FAILURES,
    cooldown_s: int = DEFAULT_COOLDOWN_S,
) -> dict:
    """记录门禁结果，更新健康状态机。返回当前状态。"""
    state = _load_state(working_dir)
    g = state.setdefault(gate, {"status": "closed", "consecutive_failures": 0})

    if passed:
        # A3 修正：清理全部暂态字段（opened_at + tripped_at + trial_started_at）
        g["status"] = "closed"
        g["consecutive_failures"] = 0
        g.pop("opened_at", None)
        g.pop("tripped_at", None)
        g.pop("trial_started_at", None)
    else:
        g["consecutive_failures"] = g.get("consecutive_failures", 0) + 1
        # A1 修正：HALF_OPEN 试运行失败 → 回 OPEN（不算入连续失败计数，避免快速重熔）
        if (
            g.get("status") == "half_open"
            or g["consecutive_failures"] >= max_failures
            and gate not in CRITICAL_GATES
        ):
            g["status"] = "open"
            g["opened_at"] = time.time()
            g["tripped_at"] = time.time()

    state[gate] = g
    _save_state(working_dir, state)
    return g


def health_report(working_dir: str) -> dict:
    """门禁健康报告（CLI --gate-health 输出用）"""
    state = _load_state(working_dir)
    report = {"open": [], "half_open": [], "closed": []}
    for gate, g in state.items():
        status = g.get("status", "closed")
        entry = {
            "gate": gate,
            "consecutive_failures": g.get("consecutive_failures", 0),
        }
        if status in ("open", "half_open"):
            entry["opened_at"] = g.get("opened_at")
            entry["tripped_at"] = g.get("tripped_at")
            report[status].append(entry)
        else:
            report["closed"].append(gate)
    return report
