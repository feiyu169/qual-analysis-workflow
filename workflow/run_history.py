"""运行历史（V3.2.0）：每次门禁执行追加 `.hgf/runs.jsonl`，
支持趋势统计与回归可见（哪些门禁反复失败）。
"""

import os

try:
    from . import hgf_state
except ImportError:
    import hgf_state


def path(working_dir: str) -> str:
    return os.path.join(working_dir, ".hgf", "runs.jsonl")


def append_run(working_dir: str, report_dict: dict) -> dict:
    """追加一次执行记录（hgf.v1 信封，V3.2.5）"""
    hgf_state.record("runs", working_dir, report_dict, writer="run_history")
    return report_dict


def history(working_dir: str, n: int = 10) -> list[dict]:
    """最近 n 次执行记录（旧→新，兼容旧版裸记录）"""
    entries = hgf_state.records("runs", working_dir)
    return entries[-n:]


def summarize(entries: list[dict]) -> dict:
    """趋势摘要"""
    if not entries:
        return {}
    total = len(entries)
    success = sum(1 for e in entries if e.get("success"))
    # 反复失败的门禁
    failed_counts: dict[str, int] = {}
    for e in entries:
        for gate in e.get("must_pass_failed", []):
            failed_counts[gate] = failed_counts.get(gate, 0) + 1
    return {
        "runs": total,
        "success_rate": round(success / total * 100, 1),
        "last_success": entries[-1].get("success"),
        "last_level": entries[-1].get("level"),
        "repeated_failures": dict(sorted(failed_counts.items(), key=lambda kv: -kv[1])),
    }


def gate_health(entries: list[dict]) -> dict:
    """门禁健康报告（V3.2.11 Phase 4：度量驱动校准，修评审"逃逸舱口"发现）。

    逐门禁统计：
    - runs：该门禁出现（被选中执行）的次数；
    - failed：失败次数；
    - fail_rate：失败率；
    - always_failed：是否**从未通过过**（runs>0 且 failed==runs）——
      一个永远失败的门禁若被降级（SHOULD_PASS/OPTIONAL）就是"逃逸舱口"：
      门禁损坏被降级而不是被修复。报告标记出来供人工校准。
    """
    stats: dict[str, dict] = {}
    for e in entries:
        for r in e.get("results", []):
            name = r.get("name")
            if not name:
                continue
            s = stats.setdefault(name, {"runs": 0, "failed": 0, "statuses": []})
            s["runs"] += 1
            status = r.get("status")
            s["statuses"].append(status)
            if status in ("failed", "error"):
                s["failed"] += 1
    health = {}
    for name, s in stats.items():
        fail_rate = round(s["failed"] / s["runs"], 3) if s["runs"] else 0.0
        health[name] = {
            "runs": s["runs"],
            "failed": s["failed"],
            "fail_rate": fail_rate,
            "always_failed": s["runs"] > 0 and s["failed"] == s["runs"],
        }
    return health
