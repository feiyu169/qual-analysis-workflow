"""HGF 流程度量 + DAG 接电（V3.3-R3 拆分自 lifecycle.py）。
矩阵证据映射（MATRIX_TO_EXIT/record_matrix_evidence/auto_advance）与
流程度量（phase_time/rework_count/escape_rate）。
外部 API 由 lifecycle.py re-export 保持兼容。
"""

import os
from datetime import datetime

try:
    from . import lifecycle_dag as _dag
except ImportError:
    import lifecycle_dag as _dag

# ── V3.2.11 Phase 1 诚实化：DAG 接电 + 迭代回路 ────────────────────────────
# 评审共识 C/I："生命周期 DAG 零使用，矩阵与 DAG 脱节"。现把工具矩阵的真实
# 运行结果映射为生命周期准出证据，可机械验证的 gate 全绿时自动推进；
# 并加 reopen 迭代回路（修 D）。


# 矩阵门禁名 → 生命周期准出类型（工具真跑结果可作该准出的证据）
MATRIX_TO_EXIT: dict[str, list[str]] = {
    "static_analysis": ["static_analysis"],
    "unit_test": ["unit_test_passed"],
    "security_scan": ["sast_scan"],
    "dependency_scan": ["dependency_scan"],
    "iac_scan": ["iac_security_audit"],
}


def record_matrix_evidence(working_dir: str, report_dict: dict) -> dict:
    """把一次矩阵运行结果映射为生命周期准出证据，写入 .hgf/matrix_evidence.jsonl。

    规则：仅记录 MUST_PASS 全绿（success=True）的运行中**通过**的门禁所
    对应的准出类型；SHOULD_PASS/OPTIONAL 通过不构成证据（不提高可信度）。
    """
    if not report_dict.get("success"):
        return {"recorded": [], "advanced": []}
    passed = {
        r["name"]
        for r in report_dict.get("results", [])
        if r.get("status") == "passed" and r.get("level") == "MUST_PASS"
    }
    satisfied: dict[str, str] = {}
    for tool, exit_types in MATRIX_TO_EXIT.items():
        if tool in passed:
            for t in exit_types:
                satisfied[t] = tool

    if satisfied:
        rec = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "level": report_dict.get("level"),
            "satisfied_exit_types": satisfied,
            "source": "gate_executor matrix run",
        }
        p = os.path.join(working_dir, ".hgf", "matrix_evidence.jsonl")
        try:
            from . import state_io as _io
        except ImportError:
            import state_io as _io
        _io.atomic_append_jsonl(p, rec)

    advanced = auto_advance(working_dir, satisfied)
    return {"recorded": sorted(satisfied), "advanced": advanced}


def auto_advance(working_dir: str, satisfied: dict) -> list[str]:
    """矩阵证据满足某 gate 的全部可自动验证准出 → 自动推进该 gate。

    注意：只推进 exit_criteria 全部 ∈ satisfied（且都在 MATRIX_TO_EXIT 中）
    的 gate——含 review/文档/人工类准出的 gate 不会被自动推进（保持诚实）。
    """
    gates = _dag.load_gates(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "gates.yaml")
    )
    state = _dag.load_state(working_dir)
    advanced = []
    for g in gates:
        gid = g["id"]
        if state.get(gid, {}).get("status") == "done":
            continue
        criteria = [c.get("type", "") for c in (g.get("exit_criteria") or [])]
        if not criteria:
            continue
        # 全部准出必须可被矩阵证据满足
        if all(c in satisfied for c in criteria):
            state[gid] = {
                "status": "done",
                "completed_at": datetime.now().isoformat(timespec="seconds"),
                "notes": "矩阵证据自动推进（V3.2.11 DAG 接电）",
                "auto": True,
            }
            advanced.append(gid)
    if advanced:
        _dag.save_state(working_dir, state)
    return advanced



# ── V3.2.11 Phase 2：流程度量（修评审共识 F）────────────────────────────────

# 门禁名 → 生命周期准出类型（用于缺陷逃逸归因：Phase 3+ 发现的、本应
# Phase 2 拦截的问题 = 逃逸）
_EXIT_TO_PHASE = {
    "static_analysis": 2,
    "unit_test_passed": 2,
    "sast_scan": 2,
    "dependency_scan": 2,
    "integration_test_passed": 3,
    "dast_scan": 3,
    "user_acceptance": 3,
}


def metrics(working_dir: str) -> dict:
    """流程度量（V3.2.11 Phase 2，修评审共识 F）。

    - phase_time：各 Phase 的 gate 完成时间跨度（从状态记录 completed_at）；
    - rework_count：累计返工次数（reopen 触发）；
    - escape_rate：缺陷逃逸率 = Phase 3+ 发现的问题 / 门禁检出问题
      （近似：failures.jsonl 中 gate 属 Phase 3+ 的失败次数 / 全部失败次数）。
    """
    state = _dag.load_state(working_dir)
    failures = []
    try:
        try:
            from . import failure_log
        except ImportError:
            import failure_log

        failures = failure_log.load_failures(working_dir)
    except Exception:
        failures = []

    # phase_time：按 gate 的 completed_at 聚类到 Phase
    gates = _dag.load_gates(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "gates.yaml")
    )
    phase_done = {}
    for g in gates:
        gid = g["id"]
        rec = state.get(gid, {})
        if rec.get("status") == "done" and rec.get("completed_at"):
            phase = g.get("phase", 0)
            phase_done.setdefault(phase, []).append(rec["completed_at"])
    phase_time = {}
    for phase, stamps in sorted(phase_done.items()):
        if len(stamps) >= 2:
            from datetime import datetime as _dt

            try:
                t0 = _dt.fromisoformat(min(stamps))
                t1 = _dt.fromisoformat(max(stamps))
                phase_time[phase] = round((t1 - t0).total_seconds() / 3600, 2)
            except ValueError:
                phase_time[phase] = None

    # rework_count
    rework_count = sum(
        rec.get("rework_count", 0) for rec in state.values() if isinstance(rec, dict)
    )

    # escape_rate：Phase>=3 gate 的失败 / 全部失败
    late_failures = 0
    total_failures = len(failures)
    for f in failures:
        gate_name = f.get("gate", "")
        # gate id（gate_3_1 等）→ phase
        if gate_name.startswith("gate_"):
            try:
                phase = int(gate_name.split("_")[1])
            except (IndexError, ValueError):
                phase = 0
        else:
            phase = _EXIT_TO_PHASE.get(gate_name, 2)
        if phase >= 3:
            late_failures += 1
    escape_rate = round(late_failures / total_failures, 3) if total_failures else 0.0

    return {
        "phase_time_hours": phase_time,
        "rework_count": rework_count,
        "escape_rate": escape_rate,
        "total_failures": total_failures,
        "late_failures": late_failures,
    }

