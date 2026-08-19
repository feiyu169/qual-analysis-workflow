#!/usr/bin/env python3
"""
Hermes Workflow CLI
用法: python3 workflow_cli.py --task "任务描述" --files "file1.py,file2.py"
"""

import argparse
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 屏蔽 structlog 控制台日志（V3.2.9 修复）：workflow 模块默认把 INFO 打到
# stdout，会污染 --json 输出（--execute 的 JSON 无法被管道/脚本解析）。
# 与 hgf_bridge 的屏蔽方式一致；非 JSON 模式的报告由 format_report 自绘，
# 不依赖 structlog，故全局屏蔽无副作用。
import structlog

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL)
)

from __init__ import __version__  # noqa: E402
from gate_executor import GateExecutor  # noqa: E402
from risk_assessor import RiskAssessor  # noqa: E402
from task_classifier import Task, TaskClassifier  # noqa: E402


def main():
    # 中文 Windows 控制台默认 GBK：统一 UTF-8 输出，避免报告乱码/编码异常
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Hermes Workflow CLI")
    parser.add_argument("--version", action="version", version=f"HGF {__version__}")
    parser.add_argument("--task", help="任务描述（--history 时可不填）")
    parser.add_argument("--files", help="文件列表，逗号分隔（--history 时可不填）")
    parser.add_argument("--lines", type=int, default=0, help="变更行数")
    parser.add_argument(
        "--level",
        choices=["L0", "L1", "L2", "L3", "L3_LITE", "IAC", "CONFIG", "DOCS"],
        help="人工覆盖分级（机器建议、人确认；覆盖原因记录在输出中）",
    )
    parser.add_argument("--areas", default="", help="影响区域，逗号分隔")
    parser.add_argument("--labels", default="", help="标签，逗号分隔")
    parser.add_argument("--execute", action="store_true", help="执行质量门禁")
    parser.add_argument("--dir", default=".", help="门禁执行的工作目录（默认当前目录）")
    parser.add_argument("--history", action="store_true", help="查看门禁运行历史与趋势")
    parser.add_argument(
        "--failures",
        action="store_true",
        help="查看未解决的失败记录（V3.2.8-A：re_run_result 非空视为已解决）",
    )
    parser.add_argument(
        "--canary",
        action="store_true",
        help="金丝雀版本回归：工具版本漂移时跑轻量金丝雀集（ruff+快速测试）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="配合 --canary：忽略漂移检测，强制跑金丝雀",
    )
    parser.add_argument(
        "--lifecycle",
        choices=["status", "advance", "reopen"],
        help="生命周期（config/gates.yaml DAG）：status=查看状态，advance=推进门禁",
    )
    parser.add_argument("--gate", help="--lifecycle advance 的 gate id（如 gate_0_1）")
    parser.add_argument(
        "--file", help="准出检查器使用的证据文件路径（--file docs/x.md）"
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="人工确认兜底：无自动检查器的准出条件视为通过",
    )
    parser.add_argument("--notes", default="", help="推进备注")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument(
        "--review-build",
        metavar="FILE",
        help="V3.2.8 审查打包：把单个文件内联成审查包（供 heavyskill 等只读外部审查器使用）",
    )
    parser.add_argument(
        "--review-out",
        default="",
        help="--review-build 的输出路径（默认 .hgf/review-packs/<basename>.md）",
    )
    parser.add_argument(
        "--review-record",
        metavar="GATE",
        help="V3.2.8 记录一次审查结论（双签名：reviewer/verifier 写入 .hgf/reviews.jsonl）",
    )
    parser.add_argument(
        "--verdict",
        choices=["pass", "fail"],
        help="--review-record 的审查结论",
    )
    parser.add_argument(
        "--verifier",
        default="heavyskill",
        help="--review-record 的验证者（默认 heavyskill）",
    )
    parser.add_argument(
        "--reviewer",
        default="agent",
        help="--review-record 的审查者（默认 agent）",
    )
    parser.add_argument(
        "--kind",
        choices=["independent", "self-check"],
        default="independent",
        help="--review-record 的评审类型：independent=独立评审（默认）/"
        "self-check=结构化自检（user_acceptance/review_checklist 拒绝）",
    )
    parser.add_argument(
        "--review-fresh",
        metavar="FILE",
        help="V3.2.11 生成 fresh-context 独立二验请求（无会话种子的独立审查 prompt）",
    )
    parser.add_argument(
        "--metrics", action="store_true",
        help="V3.2.11 流程度量：phase_time / rework_count / escape_rate",
    )

    args = parser.parse_args()

    # 生命周期模式（V3.2：让 gates.yaml 从设计稿变成可执行 DAG）
    if args.lifecycle:
        import lifecycle

        _HERE = os.path.dirname(os.path.abspath(__file__))
        cfg = os.path.join(_HERE, "config", "gates.yaml")
        gates = lifecycle.load_gates(cfg)
        deps = lifecycle.build_dag(gates)
        state = lifecycle.load_state(args.dir)

        if args.lifecycle == "status":
            if args.json:
                print(
                    json.dumps(
                        {
                            g["id"]: lifecycle.status(gates, deps, state).get(g["id"])
                            for g in gates
                        },
                        indent=2,
                        ensure_ascii=False,
                    )
                )
            else:
                print("=" * 60)
                print("HGF 生命周期状态（config/gates.yaml）")
                print("=" * 60)
                for g in gates:
                    print(
                        f"  {g['id']:10s} {lifecycle.status(gates, deps, state).get(g['id']):9s} "
                        f"Phase {g.get('phase')}: {g['name']}"
                    )
            sys.exit(0)

        if args.lifecycle == "advance":
            if not args.gate:
                parser.error(
                    "--lifecycle advance 需要 --gate <id>（先 --lifecycle status 查看可推进项）"
                )
            try:
                rec = lifecycle.advance(
                    args.dir,
                    gates,
                    deps,
                    args.gate,
                    file_hint=args.file,
                    confirm=args.confirm,
                    notes=args.notes,
                )
                print(f"✅ gate [{args.gate}] 已推进完成（{rec['completed_at']}）")
                sys.exit(0)
            except lifecycle.LifecycleError as e:
                print(f"❌ {e}")
                sys.exit(1)

        if args.lifecycle == "reopen":
            if not args.gate:
                parser.error(
                    "--lifecycle reopen 需要 --gate <id>（返工：把 done 的 gate 重新打开）"
                )
            try:
                rec = lifecycle.reopen(args.dir, gates, args.gate, reason=args.notes)
                print(
                    f"🔄 gate [{rec['reopened']}] 已重开（返工 #{rec['rework_count']}）"
                )
                if rec["affected_blocked"]:
                    print(
                        f"   ⛔ 级联回退 {len(rec['affected_blocked'])} 个下游 gate: "
                        + ", ".join(rec["affected_blocked"])
                    )
                print("   返工已写入 .hgf/failures.jsonl（需补 root_cause/fix）")
                sys.exit(0)
            except lifecycle.LifecycleError as e:
                print(f"❌ {e}")
                sys.exit(1)

    # 金丝雀模式（V3.2.8）：工具版本漂移 → 跑金丝雀回归
    if args.canary:
        import canary

        result = canary.check(args.dir, force=args.force)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print("=" * 60)
            print("金丝雀版本回归")
            print("=" * 60)
            if result.get("skipped"):
                print("无工具版本漂移，金丝雀跳过")
            else:
                for d in result.get("drift", []):
                    print(f"  ⚠️ {d}")
                print(f"  ruff   : {'✅' if result['ruff']['ok'] else '❌'}")
                print(f"  pytest : {'✅' if result['pytest']['ok'] else '❌'}")
                print(f"  耗时   : {result['duration_s']}s")
                print(f"  总体   : {'✅ 通过' if result.get('ok') else '❌ 失败'}")
            print("=" * 60)
        sys.exit(0 if result.get("skipped") or result.get("ok") else 1)

    # 审查模式（V3.2.8）：打包 → 外部审查 → 双签名记录
    if args.review_build:
        import review

        pack = review.build_pack(args.dir, args.review_build)
        out = args.review_out or os.path.join(
            args.dir,
            ".hgf",
            "review-packs",
            os.path.basename(args.review_build) + ".md",
        )
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            f.write(review.pack_markdown(pack))
        if args.json:
            print(
                json.dumps(
                    {
                        "ok": True,
                        "out": out,
                        "source": args.review_build,
                        "chars": pack["full_chars"],
                        "truncated": pack["truncated"],
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
        else:
            print(f"✅ 审查包已生成: {out}")
            print(f"   源文件: {args.review_build}（内联 {pack['full_chars']} 字符）")
            if pack["truncated"]:
                print("   ⚠️ 已截断（超过最大内联长度）")
        sys.exit(0)

    if args.review_record:
        import review

        if not args.verdict:
            parser.error("--review-record 需要 --verdict pass|fail")
        try:
            rec = review.record_review(
                args.dir,
                args.review_record,
                args.verdict,
                reviewer=args.reviewer,
                verifier=args.verifier,
                notes=args.notes,
                kind=args.kind,
            )
        except ValueError as e:
            print(f"❌ {e}")
            sys.exit(1)
        if args.json:
            print(json.dumps(rec, indent=2, ensure_ascii=False))
        else:
            print(
                f"✅ 审查已记录 [{args.review_record}] "
                f"verdict={rec['verdict']} kind={rec['kind']} "
                f"reviewer={rec['reviewer']} verifier={rec['verifier']} "
                f"-> .hgf/reviews.jsonl"
            )
        sys.exit(0)

    # fresh-context 独立二验请求（V3.2.11 Phase 2）
    if args.review_fresh:
        import review

        pack = review.build_pack(args.dir, args.review_fresh)
        req = review.verify_fresh(args.review_record or "review_passed", review.pack_markdown(pack))
        print(req["request"])
        sys.exit(0)

    # 流程度量（V3.2.11 Phase 2）
    if args.metrics:
        import lifecycle

        m = lifecycle.metrics(args.dir)
        if args.json:
            print(json.dumps(m, indent=2, ensure_ascii=False))
        else:
            print("=" * 60)
            print("HGF 流程度量（.hgf/lifecycle.json + failures.jsonl）")
            print("=" * 60)
            print(f"Phase 时间跨度（小时）: {m['phase_time_hours'] or '无完成记录'}")
            print(f"累计返工次数: {m['rework_count']}")
            print(
                f"缺陷逃逸率: {m['escape_rate']} "
                f"（Phase3+ 失败 {m['late_failures']}/{m['total_failures']}）"
            )
            print("=" * 60)
        sys.exit(0)

    # 失败记录视图（V3.2.8-A）：未解决 = re_run_result 为空
    if args.failures:
        import failure_log

        entries = failure_log.load_failures(args.dir)
        unresolved = failure_log.unresolved_failures(args.dir)
        if args.json:
            print(
                json.dumps(
                    {
                        "total": len(entries),
                        "unresolved": len(unresolved),
                        "unresolved_items": [
                            {
                                "gate": e.get("gate"),
                                "level": e.get("level"),
                                "message": e.get("message"),
                                "timestamp": e.get("timestamp"),
                            }
                            for e in unresolved
                        ],
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
        else:
            print("=" * 60)
            print(f"失败记录（.hgf/failures.jsonl）：共 {len(entries)} 条")
            print(f"未解决（re_run_result 为空）：{len(unresolved)} 条")
            print("=" * 60)
            if not unresolved:
                print("✅ 无未解决的失败记录（全部已复跑通过或有根因/修复）")
            for e in unresolved:
                print(
                    f"  ⚠️ [{e.get('timestamp')}] {e.get('gate')} "
                    f"({e.get('level')}) {e.get('message')}"
                )
            print("=" * 60)
        sys.exit(0)

    # 运行历史模式
    if args.history:
        import run_history

        entries = run_history.history(args.dir)
        summary = run_history.summarize(entries)
        health = run_history.gate_health(entries)
        if args.json:
            print(
                json.dumps(
                    {"summary": summary, "gate_health": health, "runs": entries},
                    indent=2,
                    ensure_ascii=False,
                )
            )
        else:
            print("=" * 60)
            print("门禁运行历史")
            print("=" * 60)
            if not entries:
                print("尚无运行记录（.hgf/runs.jsonl 不存在）")
            else:
                print(f"运行次数: {summary['runs']}")
                print(f"通过率: {summary['success_rate']}%")
                print(
                    f"最近一次: {'通过' if summary['last_success'] else '失败'} (等级 {summary['last_level']})"
                )
                if summary.get("repeated_failures"):
                    print("反复失败的门禁:")
                    for gate, count in summary["repeated_failures"].items():
                        print(f"  - {gate}: {count} 次")
                # V3.2.11 Phase 4：门禁健康（永远失败 = 逃逸舱口，需人工校准）
                always_failed = [
                    (name, h) for name, h in health.items() if h["always_failed"]
                ]
                if always_failed:
                    print("⚠️ 门禁健康——从未通过过的门禁（若被降级即逃逸舱口，需修复或显式记录债务）:")
                    for name, h in always_failed:
                        print(
                            f"  - {name}: {h['failed']}/{h['runs']} 次失败 "
                            f"(失败率 {h['fail_rate']*100:.0f}%)"
                        )
                print("")
                for e in entries[-5:]:
                    print(
                        f"  [{e['timestamp']}] {e['level']} 通过={e['passed']} 失败={e['failed']} "
                        f"{'✅' if e['success'] else '❌'}"
                    )
            print("=" * 60)
        sys.exit(0)

    if not args.task or not args.files:
        parser.error(
            "--task 与 --files 必填（或使用 --history / --canary / --review-build / --review-record）"
        )

    # 解析参数
    files = [f.strip() for f in args.files.split(",")]
    areas = [a.strip() for a in args.areas.split(",")] if args.areas else []
    labels = [label.strip() for label in args.labels.split(",")] if args.labels else []

    # 创建任务
    task = Task(
        description=args.task,
        files=files,
        file_count=len(files),
        line_count=args.lines,
        affected_areas=areas,
        labels=labels,
    )

    # 1. 任务分级
    classifier = TaskClassifier()
    classification = classifier.classify_task(task)

    # 1b. 人工覆盖分级（V3.2.5：--level，机器建议、人确认）
    if args.level and classification.level != args.level:
        print(
            f"[覆盖] 分级由 {classification.level} 人工覆盖为 {args.level}（原因：--level 参数）",
            file=sys.stderr,
        )
        classification.level = args.level

    # 2. 风险评估
    assessor = RiskAssessor()
    risk = assessor.assess_risk(task.affected_areas, task.description)

    # 输出结果
    result = {
        "task": args.task,
        "files": files,
        "classification": {
            "level": classification.level,
            "type": classification.type,
            "types": classification.types,
            "change_lines": classification.change_lines,
        },
        "risk": {
            "level": risk.risk,
            "score": risk.score,
            "matched_factors": risk.matched_factors,
            "combination_bonus": risk.combination_bonus,
        },
    }

    if args.json:
        # V3.2.9 修复：--execute 时延迟打印，避免输出两个 JSON 文档
        # （分级结果 + 完整结果）导致管道/脚本无法解析。
        if not args.execute:
            print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("=" * 60)
        print("Hermes Workflow 分级结果")
        print("=" * 60)
        print(f"任务: {args.task}")
        print(f"文件数: {len(files)}")
        print(f"变更行数: {classification.change_lines}")
        print()
        print(f"任务等级: {classification.level}")
        print(f"任务类型: {classification.type}")
        if classification.types:
            print(f"混合类型: {', '.join(classification.types)}")
        print()
        print(f"风险等级: {risk.risk}")
        print(f"风险分数: {risk.score}")
        print(f"风险因子: {', '.join(risk.matched_factors)}")
        print(f"组合加成: {risk.combination_bonus}")
        print("=" * 60)

    # 3. 执行质量门禁（可选）
    if args.execute:
        _HERE = os.path.dirname(os.path.abspath(__file__))

        # V3.3-R4：DAG 接电经注入回调（执行器本身不再依赖生命周期）
        def _matrix_evidence_cb(wd, report_dict):
            try:
                from . import lifecycle
            except ImportError:
                import lifecycle
            return lifecycle.record_matrix_evidence(wd, report_dict)

        executor = GateExecutor(
            os.path.join(_HERE, "config", "mcp-gates.yaml"),
            matrix_evidence_callback=_matrix_evidence_cb,
        )
        report = executor.execute_gates(
            classification.level, files=files, working_dir=args.dir
        )

        if args.json:
            out = result
            out["gates_report"] = report.to_dict()
            print(json.dumps(out, indent=2, ensure_ascii=False))
        else:
            print()
            print(report.format_report())

        # 门禁结果决定进程退出码：0=全部 MUST_PASS 通过，1=存在失败
        sys.exit(report.exit_code)


if __name__ == "__main__":
    main()
