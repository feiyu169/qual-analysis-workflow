#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""HGF 会话收尾自检（V3.3.3 V2 记忆长效机制 L3，去 dsh-schedule 依赖）。

三问自检：
  Q1: workflow/ 有未提交改动？（git status）
  Q2: gate_5_3 状态是 done？（读 .hgf/lifecycle.json）
  Q3: 最近 workflow 提交是否含 docs/PROJECT_RECORD 变更？（git log --name-only，
      时间戳不可靠——改为内容对比，防 touch 伪造）

触发方式（任一即可，四触发点矩阵）：
  - pre-push hook（强制）
  - CI self-audit job（强制，防 --no-verify 绕过）
  - 会话收尾 / goal 完成前（提示）
  - dsh-schedule 定时（可选增强，不依赖）

用法：
  python scripts/self_check.py [--dir <工作目录>] [--json]
  退出码：0 = 全部通过；1 = 有未沉淀项（提示，不阻断）。
"""

import argparse
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DIR = os.path.dirname(HERE)  # scripts/.. → workflow/


def _git(working_dir: str, *args: str) -> str:
    """跑 git 命令（容忍失败返回空串）"""
    try:
        r = subprocess.run(
            ["git"] + list(args),
            cwd=working_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        return r.stdout.strip()
    except Exception:
        return ""


def check(working_dir: str) -> dict:
    """执行三问自检，返回 {passed, checks: [{name, ok, detail}]}"""
    checks = []

    # Q1: workflow/ 有未提交改动？
    q1 = _git(working_dir, "status", "--short", "--", "workflow/") or _git(
        working_dir, "status", "--short"
    )
    q1_ok = not q1
    checks.append(
        {
            "name": "Q1 未提交改动",
            "ok": q1_ok,
            "detail": "工作区干净" if q1_ok else f"有未提交改动:\n{q1[:500]}",
        }
    )

    # Q2: gate_5_3 状态是 done？
    lifecycle_path = os.path.join(working_dir, ".hgf", "lifecycle.json")
    q2_ok = False
    q2_detail = "gate_5_3 未推进（lifecycle.json 缺失或无记录）"
    if os.path.exists(lifecycle_path):
        try:
            with open(lifecycle_path, encoding="utf-8") as f:
                doc = json.load(f)
            state = (
                doc.get("state") if isinstance(doc, dict) and "state" in doc else doc
            )
            g = (state or {}).get("gate_5_3") or {}
            if g.get("status") == "done":
                q2_ok = True
                q2_detail = f"gate_5_3 done（{g.get('completed_at', '')}）"
            else:
                q2_detail = f"gate_5_3 状态 = {g.get('status', '未推进')}"
        except (json.JSONDecodeError, OSError) as e:
            q2_detail = f"lifecycle.json 读取失败: {e}"
    checks.append({"name": "Q2 自律门禁", "ok": q2_ok, "detail": q2_detail})

    # Q3: 最近 workflow 提交是否含 docs/PROJECT_RECORD 变更？
    last_commit = _git(working_dir, "log", "-1", "--format=%h %s")
    changed = _git(working_dir, "log", "-1", "--name-only", "--format=")
    has_docs = any(
        "docs/" in c or "PROJECT_RECORD" in c or "pitfalls" in c or "CHANGELOG" in c
        for c in changed.splitlines()
    )
    q3_ok = has_docs or not last_commit
    checks.append(
        {
            "name": "Q3 记录同步",
            "ok": q3_ok,
            "detail": (
                f"最近提交 {last_commit} 含 docs/记录变更"
                if has_docs
                else f"最近提交 {last_commit} 无 docs/记录变更（可能未沉淀）"
                if last_commit
                else "无提交记录"
            ),
        }
    )

    return {
        "passed": all(c["ok"] for c in checks),
        "checks": checks,
        "hint": "经验未沉淀完整：见 checks 中 ok=False 项，补记录后重跑",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="HGF 会话收尾三问自检（V3.3.3）")
    parser.add_argument(
        "--dir", default=DEFAULT_DIR, help="HGF 工作目录（默认 workflow/）"
    )
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    result = check(args.dir)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("=" * 60)
        print("HGF 会话收尾自检（P53 记忆长效机制 L3）")
        print("=" * 60)
        for c in result["checks"]:
            mark = "✅" if c["ok"] else "⚠️"
            print(f"  {mark} {c['name']}: {c['detail']}")
        print("=" * 60)
        if result["passed"]:
            print("✅ 全部通过——经验沉淀完整，可收尾")
        else:
            print(f"⚠️ {result['hint']}")
        print("=" * 60)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
