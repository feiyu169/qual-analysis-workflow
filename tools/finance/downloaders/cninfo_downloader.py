"""
CNInfo Downloader - 巨潮资讯网下载器

支持下载 A 股上市公司的年报、半年报、季报等。
包含速率限制 (5 req/sec)。
"""

import json
import logging
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..rate_limiter import CNINFO_RATE_LIMITER
from .base import BaseDownloader, FilingInfo

logger = logging.getLogger(__name__)

# 巨潮资讯网 API
CNINFO_SEARCH_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
CNINFO_DOWNLOAD_URL = "http://static.cninfo.com.cn/"

# 表单类型映射
CN_FORM_TYPES = {
    "annual": ("年度报告", "category_ndbg_szsh"),
    "semi_annual": ("半年度报告", "category_bndbg_szsh"),
    "quarterly_q1": ("第一季度报告", "category_sjdbg_szsh"),
    "quarterly_q3": ("第三季度报告", "category_sjdbg_szsh"),
}

# 常用 A 股代码 → orgId 映射
TICKER_ORG_MAP: dict[str, str] = {
    "600519": "gssh0600519",     # 贵州茅台
    "000858": "gssz0000858",     # 五粮液
    "601318": "gssh0601318",     # 中国平安
    "000333": "gssz0000333",     # 美的集团
    "002714": "gssz002714",      # 牧原股份
}


class CNInfoDownloader(BaseDownloader):
    """巨潮资讯网下载器

    实现 Gate 2.2:
    - list_filings(): 通过巨潮 API 列出 A 股可用文件
    - download_filing(): 下载指定的 A 股财报
    - 支持年报/半年报/季报
    """

    def __init__(self, cache_base_dir: Path | None = None):
        super().__init__(cache_base_dir)

    def _make_request(self, url: str, data: bytes | None = None, method: str = "GET") -> bytes:
        """发起巨潮 API 请求（带速率限制）

        Args:
            url: 请求 URL
            data: POST 数据
            method: HTTP 方法

        Returns:
            响应内容
        """
        CNINFO_RATE_LIMITER.acquire()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        req = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(req, timeout=30) as resp:
                return resp.read()
        except HTTPError as e:
            logger.error(f"巨潮 API 请求失败: {url} -> {e.code}")
            raise
        except URLError as e:
            logger.error(f"巨潮 API 连接失败: {url} -> {e.reason}")
            raise

    def _search_announcements(
        self,
        stock_code: str,
        category: str = "",
        page_num: int = 1,
        page_size: int = 10,
    ) -> list[dict]:
        """搜索公告列表

        Args:
            stock_code: 股票代码 (如 600519)
            category: 公告类别
            page_num: 页码
            page_size: 每页数量

        Returns:
            公告列表
        """
        # 构造搜索参数
        params = (
            f"stock={stock_code}"
            f"&tabName=fulltext"
            f"&pageNum={page_num}"
            f"&pageSize={page_size}"
            f"&column=szse"  # 深交所; sse 为上交所
            f"&category=category_ndbg_szsh"
            f"&seDate="
        )

        try:
            data = self._make_request(
                CNINFO_SEARCH_URL,
                data=params.encode("utf-8"),
                method="POST",
            )
            result = json.loads(data.decode("utf-8"))
            return result.get("announcements", [])
        except Exception as e:
            logger.error(f"巨潮搜索失败: {e}")
            return []

    def list_filings(
        self,
        ticker: str,
        form_types: list[str] | None = None,
        limit: int = 10,
    ) -> list[FilingInfo]:
        """列出巨潮资讯网上可用的 A 股财报

        Args:
            ticker: 股票代码 (如 600519, 600519.SH)
            form_types: 过滤的表单类型
            limit: 最大返回数量

        Returns:
            FilingInfo 列表
        """
        # 清理 ticker
        stock_code = ticker.split(".")[0].strip()

        announcements = self._search_announcements(stock_code, page_size=limit)
        results: list[FilingInfo] = []

        for ann in announcements:
            title = ann.get("announcementTitle", "")
            adjunct_url = ann.get("adjunctUrl", "")
            ann_time = ann.get("announcementTime", "")

            # 过滤非 PDF 文件
            if not adjunct_url or not adjunct_url.endswith(".pdf"):
                continue

            # 推断表单类型
            form_type = self._infer_form_type(title)
            if form_types and form_type not in form_types:
                continue

            # 转换时间戳
            if ann_time:
                try:
                    from datetime import datetime
                    filing_date = datetime.fromtimestamp(ann_time / 1000).strftime("%Y-%m-%d")
                except Exception:
                    filing_date = ""
            else:
                filing_date = ""

            filing_url = CNINFO_DOWNLOAD_URL + adjunct_url

            results.append(
                FilingInfo(
                    ticker=ticker,
                    form_type=form_type,
                    filing_date=filing_date,
                    filing_url=filing_url,
                    market="cn",
                    description=title,
                    metadata={
                        "org_id": ann.get("orgId", ""),
                        "sec_code": stock_code,
                        "announcement_id": ann.get("announcementId", ""),
                    },
                )
            )

            if len(results) >= limit:
                break

        logger.info(f"巨潮: 找到 {len(results)} 个 {ticker} 的财报")
        return results

    def _infer_form_type(self, title: str) -> str:
        """根据标题推断表单类型

        Args:
            title: 公告标题

        Returns:
            表单类型字符串
        """
        title_lower = title.lower()
        if "年度报告" in title or "年报" in title:
            return "annual_report"
        elif "半年度报告" in title or "半年报" in title:
            return "semi_annual_report"
        elif "第一季度" in title or "一季度" in title:
            return "quarterly_q1"
        elif "第三季度" in title or "三季度" in title:
            return "quarterly_q3"
        elif "半年度" in title:
            return "semi_annual_report"
        else:
            return "other"

    def _download(self, filing: FilingInfo, save_path: Path) -> Path:
        """下载巨潮财报文件

        Args:
            filing: 财报信息
            save_path: 保存路径

        Returns:
            下载后的文件路径
        """
        content = self._make_request(filing.filing_url)
        save_path.write_bytes(content)
        return save_path
