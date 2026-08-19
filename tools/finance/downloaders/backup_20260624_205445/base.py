"""
Downloader Base - 下载器基类

所有下载器必须继承 BaseDownloader 并实现:
- list_filings(): 列出可用的财报文件
- download_filing(): 下载指定的财报文件
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

logger = logging.getLogger(__name__)


@dataclass
class FilingInfo:
    """财报文件信息

    Attributes:
        ticker: 股票代码
        form_type: 表单类型 (10-K, 10-Q, 20-F, 8-K, 年报, 半年报 等)
        filing_date: 提交日期 (YYYY-MM-DD)
        filing_url: 下载 URL
        market: 市场类型
        accession_no: SEC accession number (美股专用)
        description: 描述
        metadata: 额外元数据
    """

    ticker: str
    form_type: str
    filing_date: str
    filing_url: str
    market: Literal["us", "cn", "hk"] = "us"
    accession_no: Optional[str] = None
    description: str = ""
    metadata: dict = field(default_factory=dict)

    def cache_filename(self) -> str:
        """生成缓存文件名"""
        safe_form = self.form_type.replace("/", "_").replace("\\", "_")
        safe_date = self.filing_date.replace("-", "") if self.filing_date else "unknown"
        return f"{safe_date}_{safe_form}.pdf"


class BaseDownloader(ABC):
    """下载器基类

    所有下载器必须实现 list_filings 和 download_filing 方法。
    基类提供文件缓存逻辑。
    """

    def __init__(self, cache_base_dir: Optional[Path] = None):
        """
        Args:
            cache_base_dir: 缓存基础目录，默认 ~/.hermes/workspace/filings/
        """
        if cache_base_dir is None:
            cache_base_dir = Path.home() / ".hermes" / "workspace" / "filings"
        self.cache_base_dir = cache_base_dir

    def get_cache_dir(self, ticker: str) -> Path:
        """获取指定股票的缓存目录"""
        cache_dir = self.cache_base_dir / ticker
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    def get_cache_path(self, filing: FilingInfo) -> Path:
        """获取指定财报的缓存路径"""
        cache_dir = self.get_cache_dir(filing.ticker)
        return cache_dir / filing.cache_filename()

    def is_cached(self, filing: FilingInfo, min_size: int = 1024) -> bool:
        """检查是否已有有效缓存

        Args:
            filing: 财报信息
            min_size: 最小文件大小（字节），默认 1KB

        Returns:
            True 如果缓存存在且有效
        """
        cache_path = self.get_cache_path(filing)
        if cache_path.exists() and cache_path.stat().st_size > min_size:
            logger.info(f"缓存命中: {cache_path}")
            return True
        return False

    @abstractmethod
    def list_filings(
        self,
        ticker: str,
        form_types: Optional[list[str]] = None,
        limit: int = 10,
    ) -> list[FilingInfo]:
        """列出可用的财报文件

        Args:
            ticker: 股票代码
            form_types: 过滤的表单类型列表
            limit: 最大返回数量

        Returns:
            FilingInfo 列表，按提交日期降序排列
        """
        ...

    @abstractmethod
    def _download(self, filing: FilingInfo, save_path: Path) -> Path:
        """执行实际下载（子类实现）

        Args:
            filing: 财报信息
            save_path: 保存路径

        Returns:
            下载后的文件路径
        """
        ...

    def download_filing(
        self,
        filing: FilingInfo,
        cache_dir: Optional[Path] = None,
    ) -> Path:
        """下载财报文件（带缓存）

        Args:
            filing: 财报信息
            cache_dir: 缓存目录，为 None 则使用默认目录

        Returns:
            PDF 文件路径
        """
        if cache_dir is None:
            cache_dir = self.get_cache_dir(filing.ticker)

        cache_dir.mkdir(parents=True, exist_ok=True)
        save_path = cache_dir / filing.cache_filename()

        # 缓存检查
        if save_path.exists() and save_path.stat().st_size > 1024:
            logger.info(f"使用缓存: {save_path}")
            return save_path

        # 执行下载
        logger.info(f"下载 {filing.ticker} {filing.form_type} from {filing.filing_url}")
        result_path = self._download(filing, save_path)
        logger.info(f"下载完成: {result_path}")
        return result_path
