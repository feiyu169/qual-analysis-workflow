"""HGF → DSH 插件桥（V3.2.6 / V3.2.10）。

DSH 动态插件（JS）无法直接 import Python 模块，本桥提供 JSON-in/JSON-out
的命令入口：插件 spawn `python hgf_bridge.py <command> <json_args>`，
桥内复用 workflow 全部现有逻辑，结果以 JSON 返回模型。

V3.2.10（效能评审修复 1）：新增 `--serve` 长驻模式——stdio JSON-RPC 循环，
插件只 spawn 一次、后续复用进程（消除每次调用的 Python 冷启动，300ms→10ms）。
协议：stdin 每行一个请求 `{"id": <int>, "command": <str>, "args": {}}`，
stdout 每行一个响应 `{"id": <int>, "ok": true, "result": {...}}` 或
`{"id": <int>, "ok": false, "error": "..."}`；单条命令失败不退出进程。

命令：
- execute_gates: {level, files, working_dir} → GateExecutionReport.to_dict()
- classify_task: {description, files, line_count?, affected_areas?, labels?} → 分级
- assess_risk: {affected_areas, description?} → 风险评级
- lifecycle: {action: status|advance, gate?, working_dir, file?, confirm?} → 生命周期
- history: {working_dir, n?} → 运行历史摘要
"""

import json
import logging
import os
import sys

# 屏蔽 structlog 控制台日志：workflow 模块默认把 INFO 打到 stdout，
# 会污染桥的 JSON 输出（必须在导入 workflow 模块之前配置）
import structlog

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL)
)

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

CONFIG_PATH = os.path.join(_HERE, "config", "mcp-gates.yaml")
LIFECYCLE_CONFIG_PATH = os.path.join(_HERE, "config", "gates.yaml")


def _fail(message: str) -> None:
    sys.stderr.write(message + "\n")
    sys.exit(1)


def _force_utf8() -> None:
    """Windows 中文控制台默认 GBK：桥的 JSON 必须 UTF-8（V3.2.10 修复——
    否则 ensure_ascii=False 的中文经 GBK 编码，JS 侧按 UTF-8 解码会乱码）"""
    if sys.platform == "win32":
        for stream in (sys.stdin, sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, OSError):
                pass


def cmd_execute_gates(args: dict) -> dict:
    # V3.3-R4：DAG 接电经注入回调（执行器不再依赖生命周期模块）
    import lifecycle
    from gate_executor import GateExecutor

    executor = GateExecutor(
        CONFIG_PATH,
        matrix_evidence_callback=lifecycle.record_matrix_evidence,
    )
    report = executor.execute_gates(
        level=args["level"],
        files=args["files"],
        working_dir=args.get("working_dir", "."),
    )
    return report.to_dict()


def cmd_classify_task(args: dict) -> dict:
    from task_classifier import Task, TaskClassifier

    task = Task(
        description=args["description"],
        files=args["files"],
        file_count=len(args["files"]),
        line_count=args.get("line_count", 0),
        affected_areas=args.get("affected_areas") or [],
        labels=args.get("labels") or [],
    )
    result = TaskClassifier().classify_task(task)
    return {
        "level": result.level,
        "type": result.type,
        "types": result.types,
        "risk": result.risk,
        "change_lines": result.change_lines,
    }


def cmd_assess_risk(args: dict) -> dict:
    from risk_assessor import RiskAssessor

    result = RiskAssessor().assess_risk(
        affected_areas=args.get("affected_areas") or [],
        description=args.get("description", ""),
    )
    return {
        "risk": result.risk,
        "score": result.score,
        "matched_factors": result.matched_factors,
        "combination_bonus": result.combination_bonus,
        "reduction_applied": result.reduction_applied,
    }


def cmd_lifecycle(args: dict) -> dict:
    import lifecycle

    wd = args.get("working_dir", ".")
    gates = lifecycle.load_gates(LIFECYCLE_CONFIG_PATH)
    deps = lifecycle.build_dag(gates)

    if args.get("action") == "status":
        state = lifecycle.load_state(wd)
        status_map = lifecycle.status(gates, deps, state)
        return {"status": status_map}

    if args.get("action") == "advance":
        gate = args.get("gate")
        if not gate:
            _fail("lifecycle advance 需要 gate")
        rec = lifecycle.advance(
            wd,
            gates,
            deps,
            gate,
            file_hint=args.get("file"),
            confirm=bool(args.get("confirm")),
            notes=args.get("notes", ""),
        )
        return {"advanced": gate, "record": rec}

    if args.get("action") == "reopen":
        gate = args.get("gate")
        if not gate:
            _fail("lifecycle reopen 需要 gate")
        rec = lifecycle.reopen(wd, gates, gate, reason=args.get("notes", ""))
        return {"reopened": gate, "record": rec}

    _fail(
        f"lifecycle action 未知: {args.get('action')}（支持 status/advance/reopen）"
    )


def cmd_history(args: dict) -> dict:
    import run_history

    entries = run_history.history(args.get("working_dir", "."), args.get("n") or 10)
    return {"summary": run_history.summarize(entries), "runs": entries}


HANDLERS = {
    "execute_gates": cmd_execute_gates,
    "classify_task": cmd_classify_task,
    "assess_risk": cmd_assess_risk,
    "lifecycle": cmd_lifecycle,
    "history": cmd_history,
}


def serve() -> None:
    """长驻 stdio JSON-RPC 循环（V3.2.10）。

    每行一个请求 `{"id": int, "command": str, "args": dict}`，
    每行一个响应 `{"id": int, "ok": bool, "result"|"error": ...}`。
    单条命令失败不退出进程；stdin EOF 或异常时退出。
    """
    _force_utf8()
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as e:
            print(
                json.dumps(
                    {"id": None, "ok": False, "error": f"请求不是合法 JSON: {e}"},
                    ensure_ascii=False,
                ),
                flush=True,
            )
            continue
        rid = req.get("id")
        command = req.get("command")
        args = req.get("args") or {}
        try:
            handler = HANDLERS.get(command)
            if handler is None:
                raise ValueError(
                    f"未知命令: {command}（支持: {', '.join(sorted(HANDLERS))}）"
                )
            result = handler(args)
            print(
                json.dumps(
                    {"id": rid, "ok": True, "result": result}, ensure_ascii=False
                ),
                flush=True,
            )
        except Exception as e:
            print(
                json.dumps(
                    {"id": rid, "ok": False, "error": f"{type(e).__name__}: {e}"},
                    ensure_ascii=False,
                ),
                flush=True,
            )


def main() -> None:
    if len(sys.argv) < 2:
        _fail("用法: python hgf_bridge.py <command> [<json_args>] | --serve")
    if sys.argv[1] == "--serve":
        serve()
        return
    command = sys.argv[1]
    args = {}
    if len(sys.argv) > 2:
        try:
            args = json.loads(sys.argv[2])
        except json.JSONDecodeError as e:
            _fail(f"参数不是合法 JSON: {e}")

    handler = HANDLERS.get(command)
    if handler is None:
        _fail(f"未知命令: {command}（支持: {', '.join(sorted(HANDLERS))}）")

    try:
        result = handler(args)
    except Exception as e:
        _fail(f"执行失败: {type(e).__name__}: {e}")

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
