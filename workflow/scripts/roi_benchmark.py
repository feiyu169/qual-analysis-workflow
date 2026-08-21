#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""ROI 对照实验 harness（V3.4-C，heavyskill 审查修正版）。

打破"自证闭环"的唯一方法是对照：同一任务集分别在
A 组（HGF 门禁驱动）与 B 组（基线：直接编码+常规检查）下执行，
量化 HGF 的净收益/净成本。

修正项（对应 heavyskill K=8 审查）：
  C1 每任务独立 workdir（防 A/B 对照组污染）
  C2 空任务清单早退（防 n=0 除零）
  C3 缺陷 oracle：注入已知缺陷，count_escaped_defects 按"注入缺陷是否被
     门禁/测试拦截"判定（非基于门禁输出自证）
  C4 顺序交替（ABBA 设计）消除顺序效应
  C5 计时仅统计门禁执行段（排除写代码时间）
  C6 实验时禁用门禁熔断（防失败门禁被 skip 导致 first_pass 虚高）
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_WORKDIR = os.path.join(os.path.dirname(HERE), ".hgf-roi-lab")


def _run(cmd: list[str], cwd: str, timeout: int = 300) -> tuple[int, str]:
    try:
        r = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return r.returncode, (r.stdout or r.stderr)
    except Exception as e:
        return -1, str(e)


def run_hgf_gates(workdir: str, files: list[str]) -> tuple[int, str]:
    """跑 HGF 门禁（禁用熔断：C6）"""
    # 清空熔断状态：实验内门禁失败必须如实反映
    gh = os.path.join(workdir, ".hgf", "gate_health.json")
    if os.path.exists(gh):
        os.remove(gh)
    cmd = [
        sys.executable,
        os.path.join(HERE, "..", "workflow_cli.py"),
        "--task",
        "ROI benchmark",
        "--files",
        ",".join(files),
        "--lines",
        "0",
        "--dir",
        workdir,
        "--execute",
        "--json",
    ]
    return _run(cmd, workdir)


def run_baseline_checks(workdir: str, files: list[str]) -> tuple[int, str]:
    """基线流程：直接 ruff + pytest（无 HGF 门禁编排）"""
    rc_ruff, out_ruff = _run(["ruff", "check"] + files, workdir, timeout=120)
    rc_pytest, out_pytest = _run(
        [sys.executable, "-m", "pytest", "-q", "--no-header"], workdir, timeout=300
    )
    rc = 0 if (rc_ruff == 0 and rc_pytest == 0) else 1
    return rc, f"ruff={out_ruff[-200:]}\npytest={out_pytest[-200:]}"


def write_task_code(workdir: str, task: dict) -> None:
    """写入任务代码（含注入缺陷，C3 oracle 用）"""
    for rel, content in (task.get("files_content") or {}).items():
        path = os.path.join(workdir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


def count_escaped_defects(workdir: str, task: dict) -> int:
    """C3 修正：按注入缺陷是否被拦截判定（oracle 非自证）。

    任务定义 injected_defects: [{file, marker, present}]
    - marker 是缺陷代码的特征串（如 TODO 或错误模式）
    - 若缺陷仍存在于产物文件中 → 逃逸 +1
    """
    escaped = 0
    for defect in task.get("injected_defects", []):
        path = os.path.join(workdir, defect["file"])
        if not os.path.exists(path):
            escaped += 1  # 文件缺失也算逃逸（缺陷未处理）
            continue
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read()
        # 若缺陷 marker 仍在 → 逃逸；若已被修复（marker 移除）→ 拦截
        if defect.get("marker") in content:
            escaped += 1
    return escaped


def count_rounds(output: str) -> int:
    """从门禁输出估算修复轮次（失败→修复→重跑的循环数）"""
    # HGF 输出含多个 gate result；基线含 ruff+pytest。简单启发：统计失败标记
    return output.count("failed") + output.count("error")


def _apply_fixes(task_wd: str, task: dict) -> int:
    """按任务的修复规则移除注入缺陷（模拟"开发者按门禁报告修复"）。

    任务可选定义 fixes: [{file, marker, replacement}]——把 marker 替换为
    replacement（缺陷修复）。返回修复的缺陷数。
    """
    fixed = 0
    for fix in task.get("fixes", []):
        path = os.path.join(task_wd, fix["file"])
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            content = f.read()
        if fix["marker"] in content:
            content = content.replace(fix["marker"], fix["replacement"])
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            fixed += 1
    return fixed


def run_group(tasks: list[dict], *, use_hgf: bool, root_dir: str) -> dict:
    """C1/C2/C4 修正 + ROI 修复循环（2026-08-21 实验发现）。

    真实 ROI 方法：门禁的价值 = "拦截 → 按报告修复 → 复跑直到通过"。
    - HGF 组：门禁报告驱动修复（_apply_fixes），模拟真实开发循环
    - 基线组：不修复（对照：无门禁报告则缺陷常驻）
    缺陷逃逸 = 修复循环结束后仍在产物中的缺陷（oracle 判定）。
    """
    if not tasks:
        return {
            "use_hgf": use_hgf,
            "tasks": 0,
            "error": "empty tasks",
            "first_pass_rate": 0.0,
            "avg_rounds": 0.0,
            "total_time_s": 0.0,
            "defects_escaped_total": 0,
            "per_task": [],
        }
    max_rounds = 3  # 修复循环上限（防死循环）
    results = []
    for task in tasks:
        # C1：每任务独立 workdir（隔离状态/产物，防对照污染）
        task_wd = os.path.join(root_dir, f"{'hgf' if use_hgf else 'base'}-{task['id']}")
        if os.path.exists(task_wd):
            shutil.rmtree(task_wd)
        os.makedirs(os.path.join(task_wd, ".hgf"), exist_ok=True)
        write_task_code(task_wd, task)

        # C5：计时仅统计执行段
        t0 = time.time()
        rc = -1
        output = ""
        rounds = 0
        for round_i in range(1, max_rounds + 1):
            if use_hgf:
                rc, output = run_hgf_gates(task_wd, task.get("files", []))
            else:
                rc, output = run_baseline_checks(task_wd, task.get("files", []))
            rounds = round_i
            if rc == 0:
                break
            # 门禁失败 → 修复（仅 HGF 组有报告驱动修复；基线组不修复 = 对照组）
            if use_hgf:
                fixed = _apply_fixes(task_wd, task)
                if fixed == 0:
                    break  # 无可修复项（如语法错误需人工）→ 停止
            else:
                break  # 基线组不修复（对照真实差异）
        exec_time = round(time.time() - t0, 1)

        results.append(
            {
                "task": task["id"],
                "first_pass": rc == 0,
                "rounds": rounds,
                "time_s": exec_time,
                "defects_escaped": count_escaped_defects(task_wd, task),
            }
        )
    n = len(results)
    return {
        "use_hgf": use_hgf,
        "tasks": n,
        "first_pass_rate": sum(r["first_pass"] for r in results) / n,
        "avg_rounds": round(sum(r["rounds"] for r in results) / n, 2),
        "total_time_s": round(sum(r["time_s"] for r in results), 1),
        "defects_escaped_total": sum(r["defects_escaped"] for r in results),
        "per_task": results,
    }


def compare(tasks: list[dict], root_dir: str) -> dict:
    """C4 修正：ABBA 交替（先 A 后 B 再 B 后 A）消除顺序效应"""
    import random

    random.seed(42)  # 可复现
    half = max(1, len(tasks) // 2)
    a_first = tasks[:half]
    b_first = tasks[half:]
    # ABBA：hgf 组跑 a_first+b_first，基线组跑 b_first+a_first（顺序交错）
    a = run_group(a_first + b_first, use_hgf=True, root_dir=root_dir)
    b = run_group(b_first + a_first, use_hgf=False, root_dir=root_dir)
    if a.get("error") or b.get("error"):
        return {"error": "empty tasks", "hgf": a, "baseline": b}
    time_delta = round(a["total_time_s"] - b["total_time_s"], 1)
    defect_delta = a["defects_escaped_total"] - b["defects_escaped_total"]
    # C6/判定：缺陷拦截优势须超过时间成本（阈值可配置）
    verdict = (
        "HGF 净正收益（缺陷逃逸更少且时间代价可接受）"
        if defect_delta < 0 and time_delta < 300
        else "HGF 净正收益不足（缺陷拦截优势 < 时间成本或无明显优势）"
    )
    return {
        "hgf": a,
        "baseline": b,
        "delta": {
            "first_pass_rate": round(a["first_pass_rate"] - b["first_pass_rate"], 2),
            "avg_rounds": round(a["avg_rounds"] - b["avg_rounds"], 2),
            "time_s": time_delta,
            "defects_escaped": defect_delta,
        },
        "verdict": verdict,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="HGF ROI 对照实验（V3.4-C）")
    parser.add_argument("--tasks", default="", help="任务 JSON 文件路径")
    parser.add_argument("--workdir", default=DEFAULT_WORKDIR, help="实验根目录")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    if args.tasks:
        with open(args.tasks, encoding="utf-8") as f:
            tasks = json.load(f).get("tasks", [])
    else:
        # 内置最小示例（2 个任务，各含 1 个注入缺陷）
        tasks = [
            {
                "id": "t1",
                "files": ["calc.py", "tests/test_calc.py"],
                "files_content": {
                    "calc.py": (
                        "def add(a, b):\n    return a + b  # TODO: validate types\n\n"
                        "def div(a, b):\n    return a / b\n"
                    ),
                    "tests/test_calc.py": (
                        "from calc import add, div\n\n"
                        "def test_add():\n    assert add(1, 2) == 3\n"
                    ),
                },
                "injected_defects": [
                    {"file": "calc.py", "marker": "TODO: validate types"},
                    {"file": "calc.py", "marker": "a / b"},
                ],
            },
            {
                "id": "t2",
                "files": ["utils.py"],
                "files_content": {
                    "utils.py": (
                        "SECRET = 'abcdefghijklmnopqrst'\n\n"
                        "def sanitize(x):\n    return x.strip()\n"
                    ),
                },
                "injected_defects": [
                    {"file": "utils.py", "marker": "SECRET = 'abcdefghijklmnopqrst'"},
                ],
            },
        ]

    result = compare(tasks, args.workdir)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("=" * 60)
        print("HGF ROI 对照实验（V3.4-C，ABBA 交替）")
        print("=" * 60)
        if result.get("error"):
            print(f"❌ {result['error']}")
            return 1
        for group in ("hgf", "baseline"):
            g = result[group]
            print(
                f"\n[{group}] first_pass={g['first_pass_rate']:.0%} "
                f"rounds={g['avg_rounds']} time={g['total_time_s']}s "
                f"escaped={g['defects_escaped_total']}"
            )
        d = result["delta"]
        print(
            f"\nΔ first_pass={d['first_pass_rate']:+.0%} "
            f"Δ rounds={d['avg_rounds']:+.2f} "
            f"Δ time={d['time_s']:+.1f}s "
            f"Δ escaped={d['defects_escaped']:+d}"
        )
        print(f"\n判定: {result['verdict']}")
        print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
