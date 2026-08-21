"""HGF 生命周期 DAG 状态机（V3.3-R3 拆分自 lifecycle.py）。

纯状态流转：准入（依赖完成）→ 准出检查（委托 lifecycle_checkers）→ done；
含 reopen 迭代回路（级联下游 + 返工计数）。
外部 API 由 lifecycle.py re-export 保持兼容。

分层（与工具矩阵层 mcp-gates.yaml 的职责划分）：
- 生命周期层管"现在该干什么"：gate 的准入（依赖完成）→ 执行准出检查器 → done；
- 工具矩阵层管"当前步骤怎么验"：GateExecutor 按等级跑工具门禁。

状态持久化在 `<working_dir>/.hgf/lifecycle.json`。
"""

import json
import os
from datetime import datetime

import structlog

try:
    from . import lifecycle_checkers as _checkers
except ImportError:
    import lifecycle_checkers as _checkers

logger = structlog.get_logger()


class LifecycleError(Exception):
    """生命周期错误"""


def load_gates(config_path: str) -> list[dict]:
    """加载 gates.yaml，按 phase 拓扑排序"""
    import yaml

    with open(config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    gates = []
    for gid, spec in (data.get("gates") or {}).items():
        gates.append({"id": gid, **(spec or {})})
    gates.sort(key=lambda g: (g.get("phase", 0), g.get("id", "")))
    return gates


def build_dag(gates: list[dict]) -> dict[str, list[str]]:
    """gate_id → depends_on 列表"""
    return {g["id"]: (g.get("depends_on") or []) for g in gates}


def state_path(working_dir: str) -> str:
    return os.path.join(working_dir, ".hgf", "lifecycle.json")


def save_state(working_dir: str, state: dict) -> None:
    try:
        from . import state_io
    except ImportError:
        import state_io
    doc = {
        "schema_version": "hgf.v1",
        "writer": "lifecycle",
        "state": state,
    }
    state_io.atomic_write_json(state_path(working_dir), doc)


def load_state(working_dir: str) -> dict:
    p = state_path(working_dir)
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        doc = json.load(f)
    if isinstance(doc, dict) and "state" in doc:
        return doc["state"]
    return doc  # 旧版裸状态


def status(gates: list[dict], deps: dict, state: dict) -> dict[str, str]:
    """每个 gate 的状态：done / runnable（依赖完成）/ blocked / pending"""
    result = {}
    for g in gates:
        gid = g["id"]
        if state.get(gid, {}).get("status") == "done":
            result[gid] = "done"
        elif all(state.get(d, {}).get("status") == "done" for d in deps.get(gid, [])):
            result[gid] = "runnable"
        else:
            result[gid] = "blocked"
    return result


def advance(
    working_dir: str,
    gates: list[dict],
    deps: dict,
    gate_id: str,
    file_hint: str | None = None,
    confirm: bool = False,
    notes: str = "",
) -> dict:
    """推进一个 gate：校验准入 → 准出检查 → 标记 done"""
    status_map = status(gates, deps, load_state(working_dir))
    if status_map.get(gate_id) != "runnable":
        raise LifecycleError(
            f"gate [{gate_id}] 当前状态 {status_map.get(gate_id, '未知')}，"
            "准入条件未满足（依赖未全部完成）"
        )
    gate = next(g for g in gates if g["id"] == gate_id)
    ok, issues = _checkers.check_exit_criteria(gate, working_dir, file_hint, confirm)
    if not ok:
        raise LifecycleError(
            f"gate [{gate_id}] 准出条件未满足:\n  - " + "\n  - ".join(issues)
        )

    state = load_state(working_dir)
    state[gate_id] = {
        "status": "done",
        "completed_at": datetime.now().isoformat(timespec="seconds"),
        "notes": notes,
    }
    save_state(working_dir, state)
    return state[gate_id]


def reopen(working_dir: str, gates: list[dict], gate_id: str, reason: str = "") -> dict:
    """迭代回路（V3.2.11 Phase 1，修评审共识 D）：把 done 的 gate 重新打开
    为 runnable/blocked，并级联下游所有依赖它的 gate 回 blocked。

    返工必须写失败纪律日志（failure_log）：记录 root_cause=reason，
    使返工可追溯、可计数（rework_count）。
    """
    state = load_state(working_dir)
    if state.get(gate_id, {}).get("status") != "done":
        raise LifecycleError(f"gate [{gate_id}] 不是 done 状态，无法 reopen")

    # 级联：下游依赖本 gate 的所有 gate 回 blocked
    deps = {g["id"]: (g.get("depends_on") or []) for g in gates}
    affected = [gate_id]
    for g in gates:
        gid = g["id"]
        if (
            gid != gate_id
            and state.get(gid, {}).get("status") == "done"
            and gate_id in deps.get(gid, [])
        ):
            state[gid]["status"] = "blocked"
            affected.append(gid)

    rec = state[gate_id]
    rec["status"] = "runnable"
    rec["reopened_at"] = datetime.now().isoformat(timespec="seconds")
    rec["reopen_reason"] = reason
    rec["rework_count"] = rec.get("rework_count", 0) + 1
    save_state(working_dir, state)

    # 返工写入失败纪律日志（root_cause=reopen 原因，fix=重做说明）
    try:
        from . import failure_log
    except ImportError:
        import failure_log
    try:
        failure_log.record_failure(
            working_dir=working_dir,
            gate=gate_id,
            level="MUST_PASS",
            message=f"gate 被 reopen（返工 #{rec['rework_count']}）",
            output_tail=reason,
            root_cause=reason or "未提供返工原因",
            fix="按 reopen 原因重做并重新推进",
        )
    except Exception as e:
        # V3.3.1（复审共识：可追溯性）：返工记录写入失败不再静默——
        # 违反"失败要记录"纪律，至少告警。
        logger.warning("reopen_failure_log_failed", error=str(e))

    return {
        "reopened": gate_id,
        "rework_count": rec["rework_count"],
        "affected_blocked": affected[1:],
    }
