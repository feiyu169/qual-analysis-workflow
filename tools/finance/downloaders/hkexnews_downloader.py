"""
HKEXNews Downloader - 香港交易所披露易下载器

支持下载港股上市公司的年报、半年报、季报等。
包含速率限制 (5 req/sec)。
"""

import json
import logging
from pathlib import Path
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode

from .base import BaseDownloader, FilingInfo
from ..rate_limiter import HKEX_RATE_LIMITER
from ..exceptions import DataCollectionError

logger = logging.getLogger(__name__)

# 披露易 API
HKEXNEWS_BASE_URL = "https://www1.hkexnews.hk"
HKEXNEWS_ACTIVE_STOCK_URL = f"{HKEXNEWS_BASE_URL}/ncms/script/eds/activestock_sehk_c.json"
HKEXNEWS_TITLE_SEARCH_URL = f"{HKEXNEWS_BASE_URL}/search/titleSearchServlet.do"
HKEX_DOWNLOAD_BASE = HKEXNEWS_BASE_URL

# 港股表单类型
HK_FORM_TYPES = {
    "annual": "年度报告",
    "interim": "中期报告",
    "quarterly": "季度报告",
}

# 披露易分类代码
HKEX_T1_FINANCIAL_STATEMENTS = "40000"
HKEX_T1_ANNOUNCEMENTS = "10000"
HKEX_T2_ANNUAL_REPORT = "40100"
HKEX_T2_INTERIM_REPORT = "40200"
HKEX_T2_QUARTERLY_RESULTS = "13600"


class HKEXNewsDownloader(BaseDownloader):
    """香港交易所披露易下载器

    实现 Gate 2.3:
    - list_filings(): 通过披露易 API 列出港股可用文件
    - download_filing(): 下载指定的港股财报
    - 支持年报/半年报/季报
    """

    def __init__(self, cache_base_dir: Optional[Path] = None):
        super().__init__(cache_base_dir)
        self._stock_mapping_cache: dict[str, str] = {}  # stock_code -> stock_id

    def _make_request(self, url: str, timeout: int = 30) -> bytes:
        """发起披露易 API 请求（带速率限制）

        Args:
            url: 请求 URL
            timeout: 超时时间

        Returns:
            响应内容
        """
        HKEX_RATE_LIMITER.acquire()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/html",
        }
        req = Request(url, headers=headers)
        try:
            with urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except HTTPError as e:
            logger.error(f"披露易 API 请求失败: {url} -> {e.code}")
            raise
        except URLError as e:
            logger.error(f"披露易 API 连接失败: {url} -> {e.reason}")
            raise

    def _normalize_ticker(self, ticker: str) -> str:
        """规范化港股代码

        Args:
            ticker: 股票代码 (如 0700, 0700.HK, 700)

        Returns:
            5位数字代码
        """
        code = ticker.split(".")[0].strip()
        return code.zfill(5)

    def _fetch_stock_mapping(self) -> dict[str, str]:
        """获取披露易股票列表，建立 stock_code -> stock_id 映射

        Returns:
            {stock_code: stock_id} 映射
        """
        if self._stock_mapping_cache:
            return self._stock_mapping_cache

        logger.info("获取披露易股票列表...")
        try:
            data = self._make_request(HKEXNEWS_ACTIVE_STOCK_URL)
            stock_list = json.loads(data.decode("utf-8"))

            mapping = {}
            for stock in stock_list:
                if isinstance(stock, dict):
                    code = stock.get("c", "")
                    stock_id = stock.get("i", "")
                    if code and stock_id:
                        mapping[str(code).zfill(5)] = str(stock_id)

            self._stock_mapping_cache = mapping
            logger.info(f"获取到 {len(mapping)} 只股票")
            return mapping

        except Exception as e:
            logger.error(f"获取股票列表失败: {e}")
            raise DataCollectionError(f"无法获取披露易股票列表: {e}") from e

    def _get_stock_id(self, ticker: str) -> str:
        """获取股票的 stockId

        Args:
            ticker: 股票代码

        Returns:
            stockId
        """
        stock_code = self._normalize_ticker(ticker)
        mapping = self._fetch_stock_mapping()

        stock_id = mapping.get(stock_code)
        if not stock_id:
            raise DataCollectionError(f"披露易股票列表中未找到 {ticker}")

        return stock_id

    def list_filings(
        self,
        ticker: str,
        form_types: Optional[list[str]] = None,
        limit: int = 10,
    ) -> list[FilingInfo]:
        """列出披露易上可用的港股财报

        Args:
            ticker: 股票代码 (如 0700, 0700.HK)
            form_types: 过滤的表单类型
            limit: 最大返回数量

        Returns:
            FilingInfo 列表
        """
        stock_code = self._normalize_ticker(ticker)

        # 获取 stockId
        try:
            stock_id = self._get_stock_id(ticker)
        except DataCollectionError:
            # 如果找不到 stockId，使用 stock_code 作为备选
            logger.warning(f"未找到 {ticker} 的 stockId，使用 stock_code")
            stock_id = stock_code

        # 构造搜索参数
        # 搜索年报
        params = {
            "lang": "ZH",
            "category": "0",
            "market": "SEHK",
            "stockId": stock_id,
            "searchType": "1",
            "documentType": "-1",
            "t1code": HKEX_T1_FINANCIAL_STATEMENTS,
            "t2Gcode": "-2",
            "t2code": HKEX_T2_ANNUAL_REPORT,
            "fromDate": "20200101",
            "toDate": "20261231",
            "MB-Daterange": "0",
            "rowRange": str(limit),
            "sortByOptions": "DateTime",
            "sortDir": "0",
        }

        url = f"{HKEXNEWS_TITLE_SEARCH_URL}?{urlencode(params)}"

        try:
            data = self._make_request(url)
            result = json.loads(data.decode("utf-8"))

            # 解析结果
            # result["result"] 是一个 JSON 字符串，需要再次解析
            result_str = result.get("result", "[]")
            if isinstance(result_str, str):
                rows = json.loads(result_str)
            else:
                rows = result_str

            filings = []
            for row in rows:
                title = row.get("TITLE", "")
                file_link = row.get("FILE_LINK", "")
                date_time = row.get("DATE_TIME", "")
                stock_name = row.get("STOCK_NAME", "")

                # 推断表单类型
                form_type = self._infer_form_type(title)

                # 过滤表单类型
                if form_types and form_type not in form_types:
                    continue

                # 构造下载 URL
                if file_link and not file_link.startswith("http"):
                    filing_url = HKEX_DOWNLOAD_BASE + file_link
                else:
                    filing_url = file_link

                # 解析日期
                filing_date = self._parse_date(date_time)

                filings.append(FilingInfo(
                    ticker=ticker,
                    form_type=form_type,
                    filing_date=filing_date,
                    filing_url=filing_url,
                    market="hk",
                    description=f"{stock_name} - {title}",
                    metadata={
                        "stock_code": stock_code,
                        "stock_id": stock_id,
                        "news_id": row.get("NEWS_ID", ""),
                        "file_info": row.get("FILE_INFO", ""),
                    },
                ))

                if len(filings) >= limit:
                    break

            logger.info(f"披露易: 找到 {len(filings)} 个 {ticker} 的财报")
            return filings

        except json.JSONDecodeError as e:
            logger.error(f"披露易 JSON 解析失败: {e}")
            raise DataCollectionError(f"披露易返回数据格式错误: {e}") from e
        except Exception as e:
            logger.error(f"披露易搜索失败: {e}")
            raise DataCollectionError(f"无法从披露易获取 {ticker} 的财报列表: {e}") from e

    def _infer_form_type(self, title: str) -> str:
        """根据标题推断表单类型

        Args:
            title: 文档标题

        Returns:
            表单类型字符串
        """
        title_lower = title.lower()
        if ("年報" in title or "年报" in title or "年度報告" in title
                or "年度报告" in title or "annual" in title_lower):
            return "annual_report"
        elif "中期" in title or "interim" in title_lower:
            return "interim_report"
        elif "季度" in title or "quarterly" in title_lower:
            return "quarterly_report"
        else:
            return "other"

    def _parse_date(self, date_str: str) -> str:
        """解析日期字符串

        Args:
            date_str: 日期字符串 (如 "22/04/2026 16:55")

        Returns:
            YYYY-MM-DD 格式日期
        """
        try:
            # 格式: DD/MM/YYYY HH:MM
            parts = date_str.split(" ")[0].split("/")
            if len(parts) == 3:
                day, month, year = parts
                return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        except Exception:
            pass
        return date_str

    def _download(self, filing: FilingInfo, save_path: Path) -> Path:
        """下载披露易财报文件

        Args:
            filing: 财报信息
            save_path: 保存路径

        Returns:
            下载后的文件路径
        """
        if not filing.filing_url:
            raise DataCollectionError(f"财报 URL 为空: {filing.description}")

        logger.info(f"下载财报: {filing.filing_url}")

        try:
            data = self._make_request(filing.filing_url, timeout=120)

            # 验证 PDF
            if len(data) < 1024:
                raise DataCollectionError(f"PDF 文件过小: {len(data)} bytes")
            if not data.startswith(b"%PDF-"):
                raise DataCollectionError(f"不是有效的 PDF 文件")

            # 保存文件
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(data)

            logger.info(f"下载完成: {save_path} ({len(data)} bytes)")
            return save_path

        except Exception as e:
            logger.error(f"下载失败: {e}")
            raise DataCollectionError(f"无法下载财报: {e}") from e
