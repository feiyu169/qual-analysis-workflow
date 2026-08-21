#!/usr/bin/env python3
"""阅文集团(00772.HK) 全链路买方定性分析运行脚本。

数据: Wind(已缓存 wind_data.json) + HKEX 年报(fetch_filing)
LLM: 宿主 llm-bridge (harness_llm)，无需独立 API key
"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
TMP = os.path.join(ROOT, ".pip-tmp")
sys.path.insert(0, os.path.join(ROOT, "tools"))

# 从 config/.env 加载密钥到环境变量（MinerU 云端解析 / Wind 数据 / LLM 走宿主桥接）
_env_file = os.path.join(ROOT, "config", ".env")
if os.path.exists(_env_file):
    with open(_env_file, encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and "=" in _line and not _line.startswith("#"):
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())
os.environ.setdefault("HS_WORKSPACE", ROOT)

START = time.time()


def log(msg):
    with open(os.path.join(TMP, "run-progress.log"), "a", encoding="utf-8") as f:
        f.write(f"[{time.time()-START:6.0f}s] {msg}\n")
    try:
        print(f"[{time.time()-START:6.0f}s] {msg}", flush=True)
    except UnicodeEncodeError:
        # GBK 控制台无法编码的字符用替代符
        safe = msg.encode("gbk", "replace").decode("gbk", "replace")
        print(f"[{time.time()-START:6.0f}s] {safe}", flush=True)


def main():
    # 1) Wind 数据
    with open(os.path.join(TMP, "wind_data.json"), encoding="utf-8") as f:
        bundle = json.load(f)
    wind_data, shares = bundle["wind_data"], bundle["shares"]
    company = bundle.get("company_name") or "阅文集团"
    log(f"Wind 数据就绪: shares={shares}亿股, 键={list(wind_data.keys())}")

    # 2) 财报原文（唯一解析手段：MinerU；失败即中断，报告等待处理）
    try:
        from finance.filing_downloader import fetch_filing
        filing = fetch_filing(ticker="00772.HK", market="hk", limit=1)
        if not filing:
            raise RuntimeError("fetch_filing 返回空结果")
        log(f"财报就绪: {len(filing.get('sections', {}))} 章节, meta={str(filing.get('metadata'))[:120]}")
    except Exception as e:  # noqa: BLE001 —— MinerU 解析失败走中断流程（降级而非崩溃）
        # 先写中断状态文件，再打日志（避免日志打印异常吞掉状态）
        with open(os.path.join(TMP, "run-aborted.json"), "w", encoding="utf-8") as f:
            json.dump({
                "aborted": True,
                "stage": "filing_parse",
                "reason": str(e),
                "action": "等待处理：检查 MinerU 云端连通性/配置后重试，或由用户决定是否启用降级解析",
            }, f, ensure_ascii=False, indent=1)
        log(f"[ABORT] 财报解析中断: {e}")
        return 3

    # 3) LLM 调用器（宿主桥接优先，失败降级直连 DeepSeek API）
    llm_route = "harness_bridge"
    _orig_caller = None

    try:
        from finance.harness_llm import create_harness_caller
        _orig_caller = create_harness_caller()
        log("harness llm_caller 就绪（宿主桥接）")
    except Exception as e:  # noqa: BLE001 —— 桥接初始化失败降级直连
        log(f"[WARN] 桥接初始化失败: {e}")

    if _orig_caller is None:
        from finance.llm_caller import create_deepseek_caller
        try:
            _orig_caller = create_deepseek_caller(model="deepseek-chat")
            llm_route = "direct_api"
            log("已降级：直连 DeepSeek API（llm_caller.py）")
        except Exception as e2:  # noqa: BLE001 —— 直连初始化失败中止运行
            log(f"[ERROR] 直连也失败: {e2}")
            return 3

    # v3.1 P0-2/4/5：共享 with_fallback 模块（白名单前置 + 逃生 deadline 预检）
    from finance.llm_fallback import with_fallback

    def _direct_factory():
        from finance.llm_caller import create_deepseek_caller
        return create_deepseek_caller(model="deepseek-chat")

    llm_caller = with_fallback(
        _orig_caller,
        _direct_factory,
        fail_threshold=4,
        window=8,
        deadline=None,  # 墙钟由 QualWorkflow.execute() 内 _deadline_guard 包装（与 _wall_deadline 同源）
    )
    log(f"LLM 路由: {llm_route}（with_fallback：滑动窗口 {4}/{8} 失败自动切直连）")

    # 4) 运行主工作流（v8 引擎优先，含前端闸门 + Gate8 红队；QUAL_MODE=legacy 回退 v2-v7）
    out_dir = os.path.join(ROOT, "output", "yuewen-00772")
    use_v8 = os.environ.get("QUAL_MODE", "v8") != "legacy"

    if use_v8:
        from finance.qual_v8.workflow import QualWorkflow
        log("开始 v8 QualWorkflow.execute（前端闸门 + Gate3-8 全链，预计 60-120 分钟）...")
        context = {
            "ticker": "00772.HK",
            "company_name": company,
            "market": "hk",
            "wind_data": wind_data,
            "filing_data": filing,
            "llm_caller": llm_caller,
            "shares": shares,
            "current_price": 21.48,
            "fiscal_year": 2025,
            "qual_mode": "soft",     # B1-2：A4 验收后默认从 shadow 翻转为 soft（告警不阻断；enforce 可阻断关键错误）
            "output_dir": out_dir,
            "human_confirmed": True,
        }
        wf = QualWorkflow()
        result = wf.execute(context)
        elapsed = round(time.time() - START, 1)
        # v8 结果转 summary（Gate 明细 + 报告）
        gate_results = result.get("gate_results", {})
        summary = {
            "success": result.get("passed", False),
            "workflow_passed": result.get("passed", False),
            "gate_summary": {
                g: {
                    "passed": (result.get("results", {}).get(f"gate_{g}", {}) or {}).get("passed"),
                    "errors": (result.get("results", {}).get(f"gate_{g}", {}) or {}).get("errors", [])[:2],
                }
                for g in range(9)
            },
            "elapsed_s": elapsed,
            "report_path": str(out_dir),
            "errors": [e for g in gate_results.values() for e in getattr(g, "errors", [])][:5],
        }
    else:
        from finance.workflow import run_analysis
        log("开始 run_analysis（legacy v2-v7 单体，预计 30-90 分钟）...")
        result = run_analysis(
            ticker="00772.HK",
            company_name=company,
            market="hk",
            wind_data=wind_data,
            filing_data=filing,
            search_results=None,
            llm_caller=llm_caller,
            output_dir=out_dir,
            shares=shares,
        )
        elapsed = round(time.time() - START, 1)
        log(f"完成，耗时 {elapsed}s")
        summary = {}
        for k, v in (result or {}).items():
            if isinstance(v, (str, int, float, bool, type(None))):
                summary[k] = v
            elif isinstance(v, dict):
                summary[k] = {kk: (str(vv)[:100]) for kk, vv in list(v.items())[:10]}
            elif isinstance(v, (list, tuple)):
                summary[k] = f"list[{len(v)}]"
            else:
                summary[k] = str(v)[:120]
        summary["elapsed_s"] = elapsed
        summary["report_path"] = str(out_dir)
    with open(os.path.join(TMP, "run-result.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1, default=str)
    log("结果已写入 .pip-tmp/run-result.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
