"""小鹏汽车(9868.HK) 分析运行脚本（3年年报适配版）

与 run_qual_full.py 结构相同，但：
- 从 xpev-wind.json 读 Wind 数据（3年 FY2023/24/25）
- 下载并解析 3 份年度报告（2023/2024/2025），合并为 filing_data
- LLM 走宿主桥接 + 直连 fallback
- 用 v8 QualWorkflow 或 v2-v7 run_analysis
"""
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
TMP = os.path.join(ROOT, ".pip-tmp")
sys.path.insert(0, os.path.join(ROOT, "tools"))

# 加载 .env
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
    with open(os.path.join(TMP, "xpev-progress.log"), "a", encoding="utf-8") as f:
        f.write(f"[{time.time()-START:6.0f}s] {msg}\n")
    try:
        print(f"[{time.time()-START:6.0f}s] {msg}", flush=True)
    except UnicodeEncodeError:
        print(msg.encode("gbk", "replace").decode("gbk", "replace"), flush=True)


def fetch_multi_annuals(ticker="9868.HK", market="hk", max_annuals=3):
    """下载并解析多份年度报告，合并 sections（每份标注 fiscal_year）"""
    from datetime import datetime, timedelta, timezone

    from finance.filing_downloader import ReportQuery, _create_downloader, _parse_pdf

    downloader = _create_downloader(market)
    end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start_date = (datetime.now(timezone.utc) - timedelta(days=365 * (max_annuals + 1))).strftime("%Y-%m-%d")
    query = ReportQuery(
        market=market.upper(), ticker=ticker,
        start_date=start_date, end_date=end_date,
        target_periods=("FY",),
    )

    try:
        filings = downloader.list_filings(ticker=query.ticker, form_types=None, limit=max_annuals * 2)
        annuals = [f for f in filings if getattr(f, "form_type", "") == "annual_report"]
        if not annuals:
            annuals = filings  # 降级
    except Exception as e:  # noqa: BLE001 —— 年报列表获取失败中止（降级路径）
        log(f"[ABORT] list_filings 失败: {e}")
        return None

    if not annuals:
        log("[ABORT] 未找到任何年报")
        return None

    annuals = annuals[:max_annuals]
    log(f"找到 {len(annuals)} 份年报，开始下载+解析（Latest-Year-Primary）...")

    # 策略：每份年报独立解析并标注财年，最后按财年排序
    # 最新年份的 sections 成为 filing_data["sections"]（主提取源）
    # 更早年份存入 metadata["prior_years"]（供章节生成引用，不喂 fact_extractor）
    parsed_by_fy = {}
    combined_tables = []

    for i, filing in enumerate(annuals):
        try:
            pdf_path = downloader.download_filing(filing)
            log(f"年报 {i+1}/{len(annuals)}: {pdf_path}")
            parsed = _parse_pdf(pdf_path)
            if not parsed["text"] and not parsed["sections"]:
                log(f"  [WARN] 年报 {i+1} 解析为空，跳过")
                continue

            # 推断财年
            all_text = "\n".join(parsed.get("sections", {}).values()) or parsed.get("text", "")
            fy = None
            m = re.search(r"截至\s*(\d{4})\s*年\s*12\s*月\s*31\s*日", all_text[:20000])
            if m:
                fy = int(m.group(1))
            if fy is None:
                fy_date = getattr(filing, "filing_date", "") or ""
                if fy_date:
                    fy = int(fy_date[:4]) - 1
            log(f"  推断财年: FY{fy or '未知'}")

            if fy and fy not in parsed_by_fy:
                parsed_by_fy[fy] = parsed
                combined_tables.extend(parsed.get("tables", []))
        except Exception as e:  # noqa: BLE001 —— 单份年报失败跳过（不影响其余年份）
            log(f"  [WARN] 年报 {i+1} 处理失败: {e}")

    if not parsed_by_fy:
        log("[ABORT] 所有年报解析均失败")
        return None

    all_years = sorted(parsed_by_fy.keys())
    latest_fy = all_years[-1]
    log(f"财年列表: {all_years}，最新财年: FY{latest_fy}（主提取源）")

    # filing_data：sections 只放最新年（供 fact_extractor 提取），prior_years 存旧年（供章节引用）
    latest_sections = parsed_by_fy[latest_fy].get("sections", {})
    prior_years = {}
    for fy in all_years[:-1]:
        prior_years[fy] = parsed_by_fy[fy].get("sections", {})

    return {
        "sections": latest_sections,
        "tables": combined_tables,
        "metadata": {
            "ticker": ticker,
            "market": market,
            "fiscal_year": latest_fy,
            "years": all_years,
            "prior_years": prior_years,   # 旧年章节，供 _build_chapter_prompt 引用
        },
    }


def main():
    # 1) Wind 数据
    with open(os.path.join(TMP, "xpev-wind.json"), encoding="utf-8") as f:
        bundle = json.load(f)
    wind_data, shares = bundle["wind_data"], bundle["shares"]
    company = bundle.get("company_name") or "小鹏集团-W"
    log(f"Wind 数据就绪: shares={shares}亿股, 键={list(wind_data.keys())}")

    # 2) 多份年报下载+解析
    try:
        filing = fetch_multi_annuals(ticker="9868.HK", market="hk", max_annuals=3)
        if not filing:
            log("[ABORT] 年报获取失败")
            return 3
        log(f"财报就绪: {len(filing.get('sections', {}))} 章节, 年份={filing.get('metadata', {}).get('years')}")
    except Exception as e:  # noqa: BLE001 —— 财报解析失败中止（等待处理）
        log(f"[ABORT] 财报解析中断: {e}")
        return 3

    # 3) LLM 调用器（桥接优先，滑动窗口降级直连——v3.1 P0-2/4/5 共享模块）
    from finance.harness_llm import create_harness_caller
    from finance.llm_fallback import with_fallback

    _orig_caller = None
    llm_route = "harness_bridge"

    try:
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

    # 4) 运行分析（v8 引擎或 legacy）
    out_dir = os.path.join(ROOT, "output", "xpev-9868")
    use_v8 = os.environ.get("QUAL_MODE", "v8") != "legacy"

    if use_v8:
        from finance.qual_v8.workflow import QualWorkflow
        log("开始 v8 QualWorkflow.execute（小鹏分析）...")
        context = {
            "ticker": "9868.HK",
            "company_name": company,
            "market": "hk",
            "wind_data": wind_data,
            "filing_data": filing,
            "llm_caller": llm_caller,
            "shares": shares,
            "current_price": 46.52,
            "fiscal_year": 2025,
            "qual_mode": "shadow",
            "output_dir": out_dir,
            "human_confirmed": True,
        }
        wf = QualWorkflow()
        result = wf.execute(context)
        elapsed = round(time.time() - START, 1)
        log(f"v8 执行完成: passed={result.get('passed')}, 耗时={elapsed}s")
        summary = {
            "success": result.get("passed", False),
            "gate_summary": {
                g: {"passed": (result.get("results", {}).get(f"gate_{g}", {}) or {}).get("passed"),
                    "errors": (result.get("results", {}).get(f"gate_{g}", {}) or {}).get("errors", [])[:2]}
                for g in range(9)
            },
            "elapsed_s": elapsed,
        }
    else:
        from finance.workflow import run_analysis
        log("开始 legacy run_analysis（小鹏分析）...")
        result = run_analysis(
            ticker="9868.HK", company_name=company, market="hk",
            wind_data=wind_data, filing_data=filing,
            search_results=None, llm_caller=llm_caller,
            output_dir=out_dir, shares=shares,
        )
        elapsed = round(time.time() - START, 1)
        log(f"legacy 完成: elapsed={elapsed}s")
        summary = {
            "success": result.get("success", False),
            "elapsed_s": elapsed,
            "report_path": str(out_dir),
        }

    with open(os.path.join(TMP, "xpev-run-result.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1, default=str)
    log("结果已写入 .pip-tmp/xpev-run-result.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
