"""SEC EDGAR下载器。

关键设计（与Dayu完全对齐）：
1. 动态CIK映射（SEC_TICKER_MAP_URL）
2. Submissions API调用
3. Form类型过滤（10-K, 10-Q, 20-F等）
4. 304条件下载（ETag/Last-Modified）
5. Browse Edgar备用查询
6. 事件模型（DownloaderEvent）
7. ETag标准化
8. Source Fingerprint构建
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, Optional

from .base import BaseDownloader
from .http_client import HttpClient
from .models import (
    BrowseEdgarFiling,
    CompanyNotFoundError,
    CompanyProfile,
    DownloadedAsset,
    DownloaderEvent,
    DownloaderEventType,
    FiscalPeriod,
    RemoteFileDescriptor,
    ReportCandidate,
    ReportQuery,
    ValidationError,
    build_source_fingerprint,
    normalize_fingerprint_etag,
    normalize_fingerprint_last_modified,
)

logger = logging.getLogger(__name__)

# ============ API端点 ============

SEC_TICKER_MAP_URL: Final[str] = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL: Final[str] = "https://data.sec.gov/submissions/CIK{cik10}.json"
SEC_ARCHIVES_BASE: Final[str] = "https://www.sec.gov/Archives/edgar/data"
BROWSE_EDGAR_ATOM_URL: Final[str] = (
    "https://www.sec.gov/cgi-bin/browse-edgar?"
    "action=getcompany&filenum={filenum}&owner=include&count={count}&output=atom"
)
BROWSE_EDGAR_TICKER_ATOM_URL: Final[str] = (
    "https://www.sec.gov/cgi-bin/browse-edgar?"
    "action=getcompany&CIK={ticker}&owner=exclude&count={count}&output=atom"
)


# ============ 下载器类 ============

class SECDownloader(BaseDownloader):
    """SEC EDGAR下载器。
    
    与Dayu的SecDownloader对齐。
    """
    
    def __init__(
        self,
        http_client: HttpClient,
        cache_base_dir: Optional[Path] = None,
    ) -> None:
        """初始化下载器。
        
        Args:
            http_client: HTTP客户端
            cache_base_dir: 缓存基础目录
        """
        super().__init__(http_client, cache_base_dir)
        self._cik_cache: Optional[dict[str, str]] = None
    
    def resolve_company(self, query: ReportQuery) -> CompanyProfile:
        """解析美股公司元数据。
        
        对应Dayu的resolve_company。
        
        实现：
        1. 从SEC API获取ticker→CIK映射
        2. 返回CompanyProfile
        """
        if query.market != "US":
            raise ValueError(f"SECDownloader仅支持US，收到market={query.market}")
        
        ticker = query.ticker.upper().strip()
        cik = self._fetch_cik(ticker)
        
        if cik is None:
            raise CompanyNotFoundError(f"SEC未找到ticker={query.ticker}")
        
        return CompanyProfile(
            provider="sec",
            company_id=cik,
            company_name="",  # 从submissions获取
            ticker=ticker,
        )
    
    def list_candidates(
        self,
        query: ReportQuery,
        profile: CompanyProfile,
    ) -> tuple[ReportCandidate, ...]:
        """列出美股候选报告。
        
        对应Dayu的list_report_candidates。
        
        实现：
        1. 优先使用Submissions API
        2. 失败时回退到Browse Edgar
        """
        cik = profile.company_id
        ticker = profile.ticker
        
        # 优先使用Submissions API
        candidates = self._fetch_via_submissions(query, cik)
        
        # 如果失败，回退到Browse Edgar
        if not candidates:
            logger.info(f"Submissions API无结果，尝试Browse Edgar: {ticker}")
            browse_filings = self._fetch_filings_via_browse_edgar(ticker, cik)
            candidates = self._convert_browse_filings(browse_filings, query)
        
        return tuple(candidates)
    
    def _fetch_via_submissions(
        self,
        query: ReportQuery,
        cik: str,
    ) -> list[ReportCandidate]:
        """通过Submissions API获取候选。"""
        url = SEC_SUBMISSIONS_URL.format(cik10=cik)
        
        try:
            data = self._http.get_json(url)
        except Exception as exc:
            logger.warning(f"Submissions API失败: {cik} -> {exc}")
            return []
        
        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])
        
        # 主要财务报告类型
        main_forms = {"10-K", "10-Q", "20-F", "8-K", "10-K/A", "10-Q/A", "20-F/A"}
        
        candidates: list[ReportCandidate] = []
        
        for i in range(len(forms)):
            form = forms[i]
            date = dates[i] if i < len(dates) else ""
            
            # 过滤
            if form not in main_forms:
                continue
            if date < query.start_date or date > query.end_date:
                continue
            
            # 推断财期
            period = self._infer_period(form, date)
            if period not in query.target_periods:
                continue
            
            accession = accessions[i] if i < len(accessions) else ""
            primary_doc = primary_docs[i] if i < len(primary_docs) else ""
            
            # 构造URL
            acc_clean = accession.replace("-", "")
            source_url = f"{SEC_ARCHIVES_BASE}/{cik}/{acc_clean}/{primary_doc}"
            
            # 推断财年
            fiscal_year = self._infer_year(date, form)
            
            candidates.append(ReportCandidate(
                provider="sec",
                source_id=accession,
                source_url=source_url,
                title=f"{form} - {date}",
                language="en",
                filing_date=date,
                fiscal_year=fiscal_year,
                fiscal_period=period,
                amended="/A" in form,
            ))
        
        return candidates
    
    def _fetch_filings_via_browse_edgar(
        self,
        ticker: str,
        cik: str,
    ) -> list[BrowseEdgarFiling]:
        """通过Browse Edgar API获取财报列表（备用路径）。
        
        对应Dayu的Browse Edgar逻辑。
        
        Args:
            ticker: 股票代码
            cik: CIK编号
            
        Returns:
            BrowseEdgarFiling列表
        """
        url = BROWSE_EDGAR_TICKER_ATOM_URL.format(ticker=ticker, count=40)
        
        try:
            response = self._http.get_bytes(url)
            return self._parse_browse_edgar_atom(response, cik)
        except Exception as exc:
            logger.warning(f"Browse Edgar查询失败: {ticker} -> {exc}")
            return []
    
    def _parse_browse_edgar_atom(
        self,
        content: bytes,
        cik: str,
    ) -> list[BrowseEdgarFiling]:
        """解析Browse Edgar Atom响应。
        
        Args:
            content: Atom XML内容
            cik: CIK编号
            
        Returns:
            BrowseEdgarFiling列表
        """
        filings: list[BrowseEdgarFiling] = []
        
        try:
            root = ET.fromstring(content)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            
            for entry in root.findall("atom:entry", ns):
                title = entry.findtext("atom:title", "", ns)
                link_elem = entry.find("atom:link[@rel='alternate']", ns)
                link = link_elem.get("href", "") if link_elem is not None else ""
                
                if not title or not link:
                    continue
                
                # 解析form类型
                parts = title.split(" - ", 1)
                form_type = parts[0].strip() if parts else ""
                
                # 从link提取accession number
                accession = ""
                if "/Archives/edgar/data/" in link:
                    url_parts = link.split("/")
                    for i, part in enumerate(url_parts):
                        if part == "data" and i + 2 < len(url_parts):
                            accession = url_parts[i + 2].replace("-", "")
                            break
                
                if form_type and accession:
                    index_url = (
                        f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/index.json"
                    )
                    filings.append(BrowseEdgarFiling(
                        form_type=form_type,
                        filing_date="",  # 需要额外解析
                        accession_number=accession,
                        cik=cik,
                        index_url=index_url,
                    ))
            
        except ET.ParseError as exc:
            logger.warning(f"Browse Edgar XML解析失败: {exc}")
        
        return filings
    
    def _convert_browse_filings(
        self,
        browse_filings: list[BrowseEdgarFiling],
        query: ReportQuery,
    ) -> list[ReportCandidate]:
        """将BrowseEdgarFiling转换为ReportCandidate。"""
        candidates: list[ReportCandidate] = []
        
        for filing in browse_filings:
            # 推断财期
            period = self._infer_period(filing.form_type, filing.filing_date)
            if period not in query.target_periods:
                continue
            
            # 构造URL
            source_url = f"{SEC_ARCHIVES_BASE}/{filing.cik}/{filing.accession_number}/"
            
            candidates.append(ReportCandidate(
                provider="sec",
                source_id=filing.accession_number,
                source_url=source_url,
                title=f"{filing.form_type} - {filing.filing_date}",
                language="en",
                filing_date=filing.filing_date,
                fiscal_year=self._infer_year(filing.filing_date, filing.form_type),
                fiscal_period=period,
                amended="/A" in filing.form_type,
            ))
        
        return candidates
    
    def _download_pdf(self, candidate: ReportCandidate) -> bytes:
        """下载SEC文件。
        
        实现：
        1. 如果是HTML，尝试找PDF版本
        2. 下载并验证
        """
        url = candidate.source_url
        
        # 尝试PDF版本
        if url.endswith((".htm", ".html")):
            pdf_url = url.rsplit(".", 1)[0] + ".pdf"
            try:
                pdf_bytes = self._http.get_bytes(pdf_url)
                if pdf_bytes.startswith(b"%PDF-"):
                    return pdf_bytes
            except Exception:
                pass
        
        # 下载原始文件
        content = self._http.get_bytes(url)
        
        # 验证
        if len(content) < 1024:
            raise ValidationError(f"文件过小: {len(content)} bytes")
        
        return content
    
    # ============ 辅助方法 ============
    
    def _fetch_cik(self, ticker: str) -> Optional[str]:
        """获取ticker对应的CIK。
        
        对应Dayu的动态CIK映射。
        """
        if self._cik_cache is not None:
            return self._cik_cache.get(ticker)
        
        try:
            data = self._http.get_json(SEC_TICKER_MAP_URL)
            
            cache: dict[str, str] = {}
            for entry in data.values():
                if isinstance(entry, dict):
                    t = entry.get("ticker", "").upper()
                    cik = str(entry.get("cik_str", "")).zfill(10)
                    if t and cik:
                        cache[t] = cik
            
            self._cik_cache = cache
            return cache.get(ticker)
            
        except Exception as exc:
            logger.warning(f"查询SEC ticker映射失败: {exc}")
            return None
    
    def _infer_period(self, form: str, date: str) -> FiscalPeriod:
        """从form类型推断财期。"""
        if form.startswith("10-K"):
            return "FY"
        elif form.startswith("10-Q"):
            # 根据日期推断季度
            if date:
                month = int(date.split("-")[1])
                if month <= 3:
                    return "Q1"
                elif month <= 6:
                    return "Q2"
                elif month <= 9:
                    return "Q3"
                else:
                    return "Q4"
            return "Q1"  # 默认
        elif form.startswith("20-F"):
            return "FY"
        else:
            return "FY"  # 默认
    
    def _infer_year(self, date: str, form: str) -> int:
        """从日期推断财年。"""
        if not date:
            return datetime.now().year
        
        year = int(date.split("-")[0])
        month = int(date.split("-")[1])
        
        # 10-K通常是上一财年
        if form.startswith("10-K") and month <= 3:
            return year - 1
        
        return year
