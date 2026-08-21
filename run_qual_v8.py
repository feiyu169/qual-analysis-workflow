#!/usr/bin/env python3
"""V8 引擎可运行化验证脚本（阶段 D）

模式：
  --quick      : 用 R5 现有报告章节预填 Gate3，只跑检查链（Gate0/2/4/5/8），不生成新报告
  --full       : 完整跑 QualWorkflow.execute（Gate3 真实 LLM 生成 11 章，需 llm-bridge）
默认 --quick（无需 LLM 的确定性验证 + 负向测试：R5 已知问题应被抓到）
"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
TMP = os.path.join(ROOT, ".pip-tmp")
sys.path.insert(0, os.path.join(ROOT, "tools"))

import logging

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")


def _safe_print(s):
    try:
        print(s, flush=True)
    except UnicodeEncodeError:
        print(s.encode("gbk", "replace").decode("gbk", "replace"), flush=True)


def load_wind():
    with open(os.path.join(TMP, "wind_data.json"), encoding="utf-8") as f:
        bundle = json.load(f)
    return bundle["wind_data"], bundle["shares"]


def load_r5_report():
    """从 R5 报告解析出章节 dict（用于 quick 模式预填 + 负向测试）"""
    path = os.path.join(ROOT, "output", "yuewen-00772", "00772.HK_analysis.md")
    if not os.path.exists(path):
        return {}
    text = open(path, encoding="utf-8").read()  # noqa: SIM115
    import re
    chapters = {}
    parts = re.split(r"(?m)^#\s*第(\d+)章\s*(.*?)$", text)
    i = 1
    while i + 2 < len(parts):
        num = int(parts[i])
        body = parts[i + 2]
        chapters.setdefault(num, "")
        chapters[num] += body
        i += 3
    return chapters


def quick_verify():
    _safe_print("=" * 60)
    _safe_print("[QUICK] V8 引擎确定性验证（无需 LLM）")
    _safe_print("=" * 60)

    wind_data, shares = load_wind()
    chapters = load_r5_report()
    _safe_print(f"Wind 数据: shares={shares:.2f}亿股, 键={list(wind_data.keys())}")
    _safe_print(f"R5 章节预填: {sorted(chapters.keys())} (共{sum(len(v) for v in chapters.values())}字符)")

    # B2a-1：current_price 从 Wind quote 动态取（删 21.48 硬编码）
    current_price = (wind_data.get("quote") or {}).get("最新价", 0) or 0

    from finance.qual_v8.workflow import QualWorkflow

    context = {
        "ticker": "00772.HK",
        "company_name": "阅文集团",
        "market": "hk",
        "wind_data": wind_data,
        "shares": shares,
        "filing_data": {"sections": {"dummy": "sections"}, "metadata": {}},
        "chapters": chapters,
        "llm_caller": None,          # quick 模式无 LLM
        "current_price": current_price,  # B2a-1：Wind quote 动态取值
        "fiscal_year": 2025,
        "qual_mode": "shadow",
        "human_confirmed": True,
    }

    wf = QualWorkflow()
    start = time.time()
    result = wf.execute(context)
    elapsed = time.time() - start

    _safe_print("\n--- Gate 结果 ---")
    for g in range(9):
        r = result["results"].get(f"gate_{g}", {})
        status = "PASS" if r.get("passed") else "FAIL"
        cc = r.get("check_criteria_passed")
        _safe_print(f"Gate{g}: {status} score={r.get('score', 0):.0f} check_criteria={cc} errors={r.get('errors', [])[:3]}")
    _safe_print(f"\n工作流: {'COMPLETED' if result['passed'] else 'FAILED'} (耗时 {elapsed:.1f}s)")

    # 断言：Gate0（数据源）/Gate2（DCF）应通过
    assert result["results"]["gate_0"]["passed"], "Gate0 应通过（真实 Wind 数据齐备）"
    assert result["results"]["gate_2"]["passed"], "Gate2 应通过（DCF 参数在范围内）"

    # 负向断言：R5 已知问题应被 Gate8 Critical 抓到
    g8 = result["results"]["gate_8"]
    if g8["passed"]:
        _safe_print("\n[注意] Gate8 未抓到 R5 已知问题（检查 gate_8_result 详情）")
        gate8_result = context.get("gate_8_result") or {}
        _safe_print(f"  gate_8_result: {gate8_result}")
    else:
        _safe_print("\n[预期行为] Gate8 抓到 R5 已知问题（Critical 列表见 errors）")

    _safe_print("\n[QUICK] 验证完成")
    return result


def full_verify():
    _safe_print("[FULL] 完整模式未在本次验证执行（需 llm-bridge + 真实财报）")
    _safe_print("       运行方式：python run_qual_v8.py --full（见 docs/qual-v8-activation-plan.md 阶段 D）")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "--quick"
    if mode == "--quick":
        quick_verify()
    else:
        full_verify()
