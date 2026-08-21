"""
Filing Downloader — 统一财报获取入口

完整链路: 下载PDF → 解析 → 返回结构化数据给 workflow

修复历史:
- v1 (2026-06-30): 重写集成层，修复 3 个阻断性 bug:
  1. FilingInfo 不存在 → 使用 ReportQuery/DownloadedAsset
  2. HKEXNewsDownloader() 缺 http_client → 显式创建
  3. list_filings() 不存在 → 使用 download()
"""

import logging
import re
from pathlib import Path

from .downloaders.http_client import HttpClient
from .downloaders.models import ReportQuery

logger = logging.getLogger(__name__)

# 全局实例缓存
_http_client: HttpClient | None = None


def _get_http_client() -> HttpClient:
    """获取全局 HttpClient 实例"""
    global _http_client
    if _http_client is None:
        _http_client = HttpClient()
    return _http_client


def _create_downloader(market: str):
    """根据市场类型创建下载器实例"""
    http = _get_http_client()

    if market == "hk":
        from .downloaders.hkexnews_downloader import HKEXNewsDownloader
        return HKEXNewsDownloader()
    elif market == "us":
        from .downloaders.sec_downloader import SECDownloader
        return SECDownloader(http_client=http)
    elif market == "cn":
        from .downloaders.cninfo_downloader import CNInfoDownloader
        return CNInfoDownloader()
    else:
        raise ValueError(f"不支持的市场: {market}")


def _split_by_page_markers(text: str) -> dict[str, str]:
    """按 <!-- Page N --> 标记切分全文为章节

    适用于 FallbackParser 只返回 document 级别的情况。
    将连续页面合并为有意义的章节块（每 10-20 页一组）。
    """
    import re
    pages: list[tuple[int, str]] = []
    current_page = 0
    current_text: list[str] = []

    for line in text.split("\n"):
        m = re.match(r"<!-- Page (\d+) -->", line)
        if m:
            if current_text:
                pages.append((current_page, "\n".join(current_text)))
            current_page = int(m.group(1))
            current_text = []
        else:
            current_text.append(line)
    if current_text:
        pages.append((current_page, "\n".join(current_text)))

    if not pages:
        return {"全文": text}

    # 合并为 20 页一组
    sections: dict[str, str] = {}
    chunk_size = 20
    for i in range(0, len(pages), chunk_size):
        chunk = pages[i: i + chunk_size]
        start_p = chunk[0][0]
        end_p = chunk[-1][0]
        content = "\n".join(p[1] for p in chunk).strip()
        if content:
            sections[f"Pages {start_p}-{end_p}"] = content

    return sections


def _parse_pdf(pdf_path: Path) -> dict:
    """解析 PDF 文件（唯一手段：MinerU 云端精准 API）。

    瞬时网络错误（SSL/连接/超时）自动重试 1 次；
    真实失败（配置/鉴权/HTTP/解析失败）抛出异常中断工作流，由上层报告等待处理。

    Returns:
        {
            "text": str,           # 全文文本
            "sections": dict,      # {title: content}
            "tables": list,        # [{title, rows, ...}]
            "page_count": int,
            "source_path": str,
        }
    """
    result = {
        "text": "",
        "sections": {},
        "tables": [],
        "page_count": 0,
        "source_path": str(pdf_path),
        "parse_log": [],
    }

    # ---- 唯一手段: MinerU 精准 API（云端，章节识别最佳）----
    # 页数探测用 PyMuPDF(fitz)，不使用其他解析器，保持"唯一手段"语义
    try:
        import fitz
        with fitz.open(pdf_path) as doc:
            total_pages = doc.page_count
    except Exception as e:
        raise RuntimeError(f"MinerU 解析失败（工作流中断）：无法探测 PDF 页数: {e}") from e

    import time as _time

    for _attempt in range(2):  # 最多尝试 2 次（第 2 次仅针对瞬时网络错误）
        try:
            from .parsers.mineru_parser import MinerUConfig, MinerUParser, _load_token
            if not _load_token():
                raise RuntimeError("MinerU 解析失败（工作流中断）：MINERU_TOKEN 未配置，无法调用 MinerU 精准 API")

            import math
            all_text_parts: list[str] = []
            all_sections: dict[str, str] = {}
            all_tables: list = []

            if total_pages > 200:
                chunk = 200
                n_chunks = math.ceil(total_pages / chunk)
                for i in range(n_chunks):
                    start = i * chunk + 1
                    end = min((i + 1) * chunk, total_pages)
                    logger.info(f"MinerU 分段 {i+1}/{n_chunks}: pages {start}-{end}")
                    config = MinerUConfig(api_mode="precise", page_range=f"{start}-{end}")
                    parser = MinerUParser(Path(pdf_path), config=config)
                    all_text_parts.append(parser.get_full_text() or "")
                    for sec in parser.list_sections():
                        ref = getattr(sec, 'ref', None)
                        title = getattr(sec, 'title', '') or str(ref)
                        if ref:
                            sc = parser.read_section(ref)
                            if sc:
                                t = getattr(sc, 'text', None) or str(sc)
                                if t:
                                    all_sections[title] = t
                    for tbl in parser.list_tables():
                        ref = getattr(tbl, 'ref', None)
                        if ref:
                            tc = parser.read_table(ref)
                            if tc:
                                all_tables.append(tc)
            else:
                config = MinerUConfig(api_mode="precise")
                parser = MinerUParser(Path(pdf_path), config=config)
                all_text_parts.append(parser.get_full_text() or "")
                for sec in parser.list_sections():
                    ref = getattr(sec, 'ref', None)
                    title = getattr(sec, 'title', '') or str(ref)
                    if ref:
                        sc = parser.read_section(ref)
                        if sc:
                            t = getattr(sc, 'text', None) or str(sc)
                            if t:
                                all_sections[title] = t
                for tbl in parser.list_tables():
                    ref = getattr(tbl, 'ref', None)
                    if ref:
                        tc = parser.read_table(ref)
                        if tc:
                            all_tables.append(tc)

            result["text"] = "\n".join(all_text_parts)
            result["sections"] = all_sections
            result["tables"] = all_tables
            result["page_count"] = total_pages
            result["parse_log"].append({
                "parser": "MinerU", "api_mode": "precise",
                "total_pages": total_pages,
                "n_chunks": n_chunks if total_pages > 200 else 1,
                "text_length": len(result["text"]),
                "sections_count": len(result["sections"]),
                "tables_count": len(result["tables"]),
            })
            logger.info(f"MinerU: {len(result['text'])} 字符, {len(result['sections'])} 章节, {len(result['tables'])} 表格")
            return result

        except RuntimeError:
            raise  # 已明确的配置/中断错误，不重试
        except Exception as e:
            msg = str(e)
            # 仅对瞬时网络错误重试一次；其余失败立即中断
            transient = any(k in msg for k in (
                "SSL", "UNEXPECTED_EOF", "ConnectError", "Connection",
                "Timeout", "ReadTimeout", "RemoteProtocolError", "BrokenPipe",
            ))
            if transient and _attempt == 0:
                logger.warning(f"MinerU 瞬时网络错误（{msg[:120]}），{_time.sleep(5)}后重试")
                continue
            # 唯一手段：MinerU 失败即中断工作流，报告等待处理
            raise RuntimeError(f"MinerU 解析失败（工作流中断）：{e}") from e

    raise RuntimeError("MinerU 解析失败（工作流中断）：瞬时网络错误重试后仍失败")


def list_filings(
    ticker: str,
    market: str,
    form_types: list[str] | None = None,
    limit: int = 10,
) -> list:
    """列出可用财报文件（HGF 遗留项①修复：filing_service 引用的模块级接口）。

    包装 _create_downloader + 下载器实例 list_filings 方法。

    Args:
        ticker: 股票代码
        market: 市场 (us/cn/hk)
        form_types: 过滤的表单类型列表
        limit: 最大返回数量

    Returns:
        FilingInfo 列表
    """
    try:
        downloader = _create_downloader(market)
    except Exception as e:
        logger.error(f"创建下载器失败（list_filings）: {e}")
        return []
    try:
        return downloader.list_filings(
            ticker=ticker, form_types=form_types, limit=max(limit, 5),
        )
    except Exception as e:
        logger.error(f"列出财报失败（list_filings）: {e}")
        return []


def fetch_filing(
    ticker: str,
    market: str,
    fiscal_years: list[int] | None = None,
    fiscal_periods: list[str] | None = None,
    limit: int = 1,
) -> dict | None:
    """获取财报数据（下载 + 解析）

    Args:
        ticker: 股票代码
        market: 市场 (us/cn/hk)
        fiscal_years: 目标财年列表，如 [2024, 2025]
        fiscal_periods: 目标财期列表，如 ["FY", "Q1"]
        limit: 最大下载数量

    Returns:
        filing_data dict (可直接传给 workflow.run_analysis) 或 None
        {
            "sections": {title: content},
            "tables": [table_data],
            "metadata": {ticker, market, fiscal_year, ...},
            "source": "filing",
        }
    """
    try:
        downloader = _create_downloader(market)
    except Exception as e:
        logger.error(f"创建下载器失败: {e}")
        return None

    # 构造查询参数
    from datetime import datetime, timedelta
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=365 * 3)).strftime("%Y-%m-%d")

    target_periods = ("FY",)  # 默认只取年报
    if fiscal_periods:
        target_periods = tuple(fiscal_periods)

    query = ReportQuery(
        market=market.upper(),
        ticker=ticker,
        start_date=start_date,
        end_date=end_date,
        target_periods=target_periods,
    )

    # 下载
    logger.info(f"开始下载 {ticker} ({market}) 财报...")
    try:
        filings = downloader.list_filings(ticker=query.ticker, form_types=None, limit=max(limit, 5))
        # 优先取年报，其次取最新文件
        annual = [f for f in filings if getattr(f, "form_type", "") == "annual_report"]
        pick = annual or filings
        if not pick:
            logger.warning(f"未找到 {ticker} 的财报")
            return None
        filing = pick[0]
        pdf_path = downloader.download_filing(filing)
    except Exception as e:
        logger.error(f"下载失败: {e}")
        return None

    logger.info(f"解析财报: {pdf_path}")

    parsed = _parse_pdf(pdf_path)

    if not parsed["text"] and not parsed["sections"]:
        logger.warning("财报解析结果为空")
        return None

    # 推断财年（P0-B1 修复：发布日期年份≠报告期财年——FY2025 年报 2026-04 发布，filing_date[:4] 会错标 2026）
    # 策略：1) 从正文报告期推断（"截至2025年12月31日止年度" → 2025）
    #       2) 回退：年报发布日期年份减 1（2026-04 发布 → 2025）
    #       3) 最终由调用方（extract_facts）与 Wind labels[-1] 对齐校验
    fiscal_year = None
    try:
        _all_text = "\n".join(parsed.get("sections", {}).values()) if parsed.get("sections") else (parsed.get("text") or "")
        _m = re.search(r"截至\s*(\d{4})\s*年\s*12\s*月\s*31\s*日(?:\s*止)?\s*[之止的]?年度", _all_text[:20000])
        if _m:
            fiscal_year = int(_m.group(1))
        elif _m2 := re.search(r"报告期[：:]\s*(\d{4})", _all_text[:10000]):
            fiscal_year = int(_m2.group(1))
    except Exception:
        fiscal_year = None
    if fiscal_year is None:
        try:
            fy_date = getattr(filing, "filing_date", "") or ""
            if fy_date:
                fiscal_year = int(fy_date[:4]) - 1  # 年报发布日期次年 → 上一年度
        except (TypeError, ValueError):
            fiscal_year = None

    # 构造 filing_data
    filing_data = {
        "sections": parsed["sections"],
        "tables": parsed["tables"],
        "metadata": {
            "ticker": ticker,
            "market": market,
            "fiscal_year": fiscal_year,
            "fiscal_period": "FY" if getattr(filing, "form_type", "") == "annual_report" else getattr(filing, "form_type", ""),
            "filing_date": getattr(filing, "filing_date", None),
            "source_url": getattr(filing, "filing_url", None),
            "page_count": parsed["page_count"],
            "pdf_path": str(pdf_path),
        },
        "source": "filing",
    }

    # 如果没有 sections 但有 text，放入 text 字段供 _process_filing 使用
    if not parsed["sections"] and parsed["text"]:
        filing_data["text"] = parsed["text"]

    logger.info(
        f"财报获取完成: {len(parsed['sections'])} 章节, "
        f"{len(parsed['text'])} 字符, {len(parsed['tables'])} 表格"
    )

    return filing_data
