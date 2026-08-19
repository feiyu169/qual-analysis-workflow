"""结构化失败记录（HGF 纪律工具化）。

每次门禁失败由 GateExecutor 自动追加一条记录到 `<working_dir>/.hgf/failures.jsonl`；
agent 在复跑前必须补充 root_cause / fix 字段（update_failure），
failure_log 门禁检查记录是否完整——把"失败要记录"从口头纪律变成可执行门禁。
"""

import os
from datetime import datetime

try:
    from . import hgf_state
except ImportError:
    import hgf_state


def log_path(working_dir: str) -> str:
    """失败日志路径（.hgf/failures.jsonl）"""
    return os.path.join(working_dir, ".hgf", "failures.jsonl")


def record_failure(
    working_dir: str,
    gate: str,
    level: str,
    message: str,
    output_tail: str = "",
    root_cause: str | None = None,
    fix: str | None = None,
    re_run_result: str | None = None,
) -> dict:
    """追加一条失败记录（hgf.v1 信封，V3.2.5），返回该记录。"""
    entry = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "gate": gate,
        "level": level,
        "message": message,
        "output_tail": output_tail[-2000:],
        "root_cause": root_cause,
        "fix": fix,
        "re_run_result": re_run_result,
    }
    hgf_state.record("failures", working_dir, entry, writer="failure_log")
    return entry


def update_failure(working_dir: str, gate: str, **fields) -> dict | None:
    """为 gate 的最新一条记录补充字段（root_cause/fix/re_run_result 等）。

    V3.3-R1（架构评审修复 C）：原子重写整个日志文件——此前"先 os.remove
    再逐条追加"在进程崩溃时会丢失全部失败记录；现改为构造完整内容后
    write-temp + os.replace 原子替换。找不到对应记录时返回 None。
    """
    entries = load_failures(working_dir)
    target = None
    for entry in reversed(entries):
        if entry.get("gate") == gate:
            target = entry
            break
    if target is None:
        return None
    target.update(fields)
    p = log_path(working_dir)
    # 构造完整内容（hgf.v1 信封）→ 原子替换
    import json as _json
    from datetime import datetime as _dt

    lines = []
    for entry in entries:
        envelope = {
            "schema": hgf_state.SCHEMA_VERSION,
            "kind": "failures",
            "writer": "failure_log",
            "timestamp": _dt.now().isoformat(timespec="seconds"),
            "payload": entry,
        }
        lines.append(_json.dumps(envelope, ensure_ascii=False))
    try:
        from . import state_io as _io
    except ImportError:
        import state_io as _io
    _io.atomic_write_text(p, "\n".join(lines) + "\n")
    return target


def load_failures(working_dir: str) -> list[dict]:
    """读取全部失败记录（兼容旧版裸记录）。"""
    return hgf_state.records("failures", working_dir)


def is_resolved(entry: dict) -> bool:
    """约定式"已解决"判定（V3.2.8-A）：re_run_result 非空即视为已解决。

    复跑通过后由调用方写入 re_run_result（如 update_failure(..., re_run_result=...)
    或 gate_executor 自动回填），无需额外 resolved 状态位——
    保持 schema 不变的同时让"待处理"统计有明确口径。
    """
    return bool((entry.get("re_run_result") or "").strip())


def unresolved_failures(working_dir: str) -> list[dict]:
    """返回尚未解决的失败记录（re_run_result 为空）。"""
    return [e for e in load_failures(working_dir) if not is_resolved(e)]


def check_failure_log(working_dir: str) -> tuple:
    """一致性检查，供 failure_log 门禁使用。

    Returns:
        (ok, issues): ok 为 bool，issues 为问题描述列表。
    """
    entries = load_failures(working_dir)
    if not entries:
        return True, []

    issues = []
    for i, entry in enumerate(entries):
        missing = [
            k for k in ("timestamp", "gate", "level", "message") if not entry.get(k)
        ]
        if missing:
            issues.append(f"第 {i + 1} 条记录缺少字段: {', '.join(missing)}")
        if not entry.get("root_cause"):
            issues.append(
                f"门禁 [{entry.get('gate', '?')}] 的失败记录缺少 root_cause（根因分析）"
            )
        if not entry.get("fix"):
            issues.append(
                f"门禁 [{entry.get('gate', '?')}] 的失败记录缺少 fix（修复说明）"
            )
    return (len(issues) == 0), issues
