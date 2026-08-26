#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""业务缺陷评审（V3.4.1，分层收益模型标准实践 P56）。

分层收益模型（ROI 对照实验五轮实证）：
- 门禁层（L0-L3）：拦截**工具型缺陷**（导入/密钥/语法/格式）——自动化、即时、廉价
- 评审层（business_review）：拦截**业务语义缺陷**（边界条件/控制流/模式匹配）——
  需语义理解，静态门禁无能力；heavyskill 外部评审验证 3/3 拦截（ROI 第五轮）

本脚本：从变更文件构建评审包 → 调 heavyskill 模式2（K 路独立评审）→
记录 business_review 结论到 .hgf/reviews.jsonl（kind=independent）。

用法：
  python scripts/business_review.py --files "a.py,b.py" [--dir .] [--kind CODE|VALUATION|...]
                                     [--reason_k 8] [--api_key xxx] [--dry-run]
"""

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORKFLOW_DIR = os.path.dirname(HERE)


def build_review_pack(
    files: list[str], working_dir: str, max_chars: int = 30000
) -> dict:
    """从变更文件构建业务评审包（内联代码，供 heavyskill 子代理读取）。

    V3.4.1 P56：业务语义缺陷需要理解上下文——评审包内联代码 + 业务背景提示，
    让评审者找"门禁静态检查发现不了的业务缺陷"。
    """
    code_blocks = []
    for rel in files:
        path = os.path.join(working_dir, rel)
        if not os.path.exists(path):
            continue
        content = open(path, encoding="utf-8", errors="replace").read()
        if len(content) > max_chars:
            content = content[:max_chars] + "\n...[截断]..."
        code_blocks.append(f"### {rel}\n\n```python\n{content}\n```")
    return {
        "title": "HGF 业务缺陷评审包",
        "request": (
            "请以资深代码审查专家身份审查以下代码。这些代码能通过静态检查"
            "（ruff/pytest/语法均无问题）——缺陷是**业务语义**层面的："
            "边界条件处理、返回值语义、模式匹配与实际数据格式、资源/状态管理。\n"
            "输出：1) 每段代码的业务缺陷（P0 致命/P1 严重/P2 一般，行级引用）"
            "2) 结论 PASS / FAIL"
        ),
        "code": "\n\n".join(code_blocks),
        "files": files,
    }


def run_heavyskill(query: str, api_key: str, reason_k: int = 8) -> dict:
    """调 heavyskill 模式2（K 路独立评审 + 顺序审议）"""
    hs_dir = os.path.join(os.path.dirname(WORKFLOW_DIR), "skills", "heavyskill")
    script = os.path.join(hs_dir, "scripts", "run_heavyskill.py")
    out = os.path.join(WORKFLOW_DIR, ".hgf", "business-review-last.json")
    cmd = [
        sys.executable,
        script,
        "--query",
        query,
        "--reason_k",
        str(reason_k),
        "--summary_k",
        "4",
        "--language",
        "cn",
        "--api_key",
        api_key,
        "--output",
        out,
    ]
    r = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        check=False,
    )
    if r.returncode != 0:
        return {"ok": False, "error": r.stderr[-500:] or r.stdout[-500:]}
    try:
        with open(out, encoding="utf-8") as f:
            return {"ok": True, "result": json.load(f)}
    except Exception as e:
        return {"ok": False, "error": f"结果解析失败: {e}"}


def record_business_review(
    working_dir: str, files: list[str], verdict: str, findings: str, verifier: str
) -> dict:
    """记录 business_review 评审结论（kind=independent，verifier 外部）。

    V3.4.1 P56：业务缺陷评审必须独立（被审代码不得自证通过）——
    verifier 为外部评审方（heavyskill 多轨迹审议 / 人类专家）。
    """
    sys.path.insert(0, WORKFLOW_DIR)
    from review import record_review

    return record_review(
        working_dir,
        gate="gate_2_2",
        verdict=verdict,
        reviewer="agent",
        verifier=verifier,
        notes=f"业务缺陷评审（P56）: {', '.join(files)} | {findings[:200]}",
        kind="independent",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="HGF 业务缺陷评审（P56 分层收益）")
    parser.add_argument("--files", required=True, help="变更文件，逗号分隔")
    parser.add_argument("--dir", default=".", help="工作目录")
    parser.add_argument("--reason_k", type=int, default=8, help="heavyskill 轨迹数")
    parser.add_argument("--api_key", default="", help="DEEPSEEK_API_KEY")
    parser.add_argument("--dry-run", action="store_true", help="只构建评审包不调用")
    args = parser.parse_args()

    files = [f.strip() for f in args.files.split(",") if f.strip()]
    pack = build_review_pack(files, args.dir)

    if args.dry_run:
        print(pack["request"])
        print(pack["code"][:3000])
        return 0

    if not args.api_key:
        # 尝试从 config/.env 读
        env_path = os.path.join(os.path.dirname(WORKFLOW_DIR), "config", ".env")
        if os.path.exists(env_path):
            for line in open(env_path, encoding="utf-8"):
                if line.startswith("DEEPSEEK_API_KEY="):
                    args.api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not args.api_key:
        print("❌ 需要 --api_key（或 config/.env 的 DEEPSEEK_API_KEY）")
        return 1

    query = f"{pack['request']}\n\n{pack['code']}"
    print(f"🔍 调 heavyskill（K={args.reason_k}）审查 {len(files)} 个文件...")
    result = run_heavyskill(query, args.api_key, args.reason_k)
    if not result["ok"]:
        print(f"❌ {result['error']}")
        return 1

    final = (
        result["result"].get("final_answer")
        or result["result"].get("consensus_answer")
        or ""
    )
    verdict = "fail" if "发现" in final and "缺陷" in final else "pass"
    rec = record_business_review(args.dir, files, verdict, final, "heavyskill")
    print(f"✅ 业务评审已记录: verdict={rec['verdict']}")
    print(f"   结论: {final[:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
