"""
SEC EDGAR Downloader - SEC 财报下载器

支持下载 SEC EDGAR 上的 10-K, 10-Q, 20-F, 8-K 等文件。
包含速率限制 (10 req/sec) 和文件缓存。
"""

import json
import logging
import re
from pathlib import Path
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from .base import BaseDownloader, FilingInfo
from ..rate_limiter import SEC_RATE_LIMITER

logger = logging.getLogger(__name__)

# SEC EDGAR 全文搜索 API
EDGAR_FULL_TEXT_SEARCH = "https://efts.sec.gov/LATEST/search-index?q="
EDGAR_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"
EDGAR_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"

# SEC 要求的 User-Agent
USER_AGENT = "Hermes-Agent research@example.com"

# 常见 ticker → CIK 映射（常用股票）
TICKER_CIK_MAP: dict[str, str] = {
    "AAPL": "0000320193",
    "MSFT": "0000789019",
    "GOOGL": "0001652044",
    "AMZN": "0001018724",
    "META": "0001326801",
    "TSLA": "0001318605",
    "NVDA": "0001045810",
    "BRK.B": "0001067983",
    "JPM": "0000019617",
    "V": "0001403161",
    "JNJ": "0000200406",
    "WMT": "0000104169",
    "PG": "0000080424",
    "MA": "0001141391",
    "UNH": "0000731766",
    "HD": "0000354950",
    "DIS": "0001001039",
    "BAC": "0000070858",
    "XOM": "0000034088",
    "KO": "0000021344",
}


def ticker_to_cik(ticker: str) -> Optional[str]:
    """将 ticker 转换为 CIK 编号

    先查本地映射表，如果找不到则查询 SEC API。

    Args:
        ticker: 股票代码

    Returns:
        CIK 编号字符串（10位，前补零），找不到返回 None
    """
    ticker = ticker.upper().strip()

    # 本地映射
    if ticker in TICKER_CIK_MAP:
        return TICKER_CIK_MAP[ticker]

    # 查询 SEC company tickers API
    try:
        SEC_RATE_LIMITER.acquire()
        url = "https://www.sec.gov/files/company_tickers.json"
        req = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        for _, entry in data.items():
            if entry.get("ticker", "").upper() == ticker:
                cik = str(entry["cik_str"]).zfill(10)
                TICKER_CIK_MAP[ticker] = cik
                return cik
    except Exception as e:
        logger.warning(f"查询 SEC ticker 映射失败: {e}")

    return None


class SECFilingDownloader(BaseDownloader):
    """SEC EDGAR 财报下载器

    实现 Gate 2.1:
    - list_filings(): 通过 SEC submissions API 列出可用文件
    - download_filing(): 下载指定的 SEC 文件
    - ticker_to_cik(): ticker → CIK 映射
    - 文件缓存逻辑
    """

    def __init__(self, cache_base_dir: Optional[Path] = None):
        super().__init__(cache_base_dir)

    def _make_request(self, url: str) -> bytes:
        """发起 SEC API 请求（带速率限制）

        Args:
            url: 请求 URL

        Returns:
            响应内容

        Raises:
            URLError: 请求失败
        """
        SEC_RATE_LIMITER.acquire()
        req = Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urlopen(req, timeout=30) as resp:
                return resp.read()
        except HTTPError as e:
            logger.error(f"SEC API 请求失败: {url} -> {e.code}")
            raise
        except URLError as e:
            logger.error(f"SEC API 连接失败: {url} -> {e.reason}")
            raise

    def list_filings(
        self,
        ticker: str,
        form_types: Optional[list[str]] = None,
        limit: int = 10,
    ) -> list[FilingInfo]:
        """列出 SEC EDGAR 上可用的财报文件

        Args:
            ticker: 股票代码
            form_types: 过滤的表单类型列表 (如 ["10-K", "10-Q"])
            limit: 最大返回数量

        Returns:
            FilingInfo 列表，按提交日期降序排列
        """
        cik = ticker_to_cik(ticker)
        if not cik:
            logger.error(f"无法找到 {ticker} 的 CIK 编号")
            return []

        # 获取提交列表
        url = EDGAR_SUBMISSIONS.format(cik=cik)
        try:
            data = self._make_request(url)
            submissions = json.loads(data.decode("utf-8"))
        except Exception as e:
            logger.error(f"获取 SEC submissions 失败: {e}")
            return []

        # 解析提交列表
        recent = submissions.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])
        descriptions = recent.get("primaryDocDescription", [])

        results: list[FilingInfo] = []
        for i in range(len(forms)):
            form = forms[i]
            date = dates[i] if i < len(dates) else ""

            # 类型过滤
            if form_types and form not in form_types:
                continue

            # 只处理主要财务报告
            main_forms = {"10-K", "10-Q", "20-F", "8-K", "10-K/A", "10-Q/A", "20-F/A"}
            if form not in main_forms:
                continue

            accession_no = accessions[i] if i < len(accessions) else ""
            primary_doc = primary_docs[i] if i < len(primary_docs) else ""
            description = descriptions[i] if i < len(descriptions) else ""

            # 构造下载 URL
            acc_no_clean = accession_no.replace("-", "")
            filing_url = f"{EDGAR_ARCHIVES}/{cik}/{acc_no_clean}/{primary_doc}"

            results.append(
                FilingInfo(
                    ticker=ticker.upper(),
                    form_type=form,
                    filing_date=date,
                    filing_url=filing_url,
                    market="us",
                    accession_no=accession_no,
                    description=description,
                    metadata={
                        "cik": cik,
                        "accession_no": accession_no,
                        "primary_doc": primary_doc,
                    },
                )
            )

            if len(results) >= limit:
                break

        logger.info(f"SEC: 找到 {len(results)} 个 {ticker} 的财报")
        return results

    def _download(self, filing: FilingInfo, save_path: Path) -> Path:
        """下载 SEC 财报文件

        Args:
            filing: 财报信息
            save_path: 保存路径

        Returns:
            下载后的文件路径
        """
        # 如果 URL 是 HTML 文件，尝试找到 PDF 版本
        url = filing.filing_url
        if url.endswith(".htm") or url.endswith(".html"):
            # 尝试将 .htm 替换为 .pdf
            pdf_url = re.sub(r"\.htm[l]?$", ".pdf", url)
            try:
                content = self._make_request(pdf_url)
                save_path.write_bytes(content)
                return save_path
            except Exception:
                # 如果 PDF 不可用，下载 HTML
                pass

        content = self._make_request(url)
        save_path.write_bytes(content)
        return save_path
