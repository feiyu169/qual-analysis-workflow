"""下载器强类型数据模型。

设计原则：
- 所有dataclass frozen=True
- 禁止Any、object
- 只保留下载链路必需字段

与Dayu对齐：
- CompanyProfile -> CnCompanyProfile
- ReportQuery -> CnReportQuery
- ReportCandidate -> CnReportCandidate
- DownloadedAsset -> DownloadedReportAsset
- HeadMeta -> _HeadMeta
- DownloaderEvent -> DownloaderEvent
- BrowseEdgarFiling -> BrowseEdgarFiling
- RemoteFileDescriptor -> RemoteFileDescriptor
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

# ============ 字面量类型 ============

MarketKind = Literal["US", "CN", "HK"]
"""市场标识。"""

FiscalPeriod = Literal["FY", "H1", "Q1", "Q2", "Q3", "Q4"]
"""财期字面量集合。

- FY: 年报
- H1: 半年报
- Q1/Q2/Q3/Q4: 季度报告
"""

SourceProvider = Literal["sec", "cninfo", "hkexnews"]
"""报告来源provider。"""

Language = Literal["zh", "en"]
"""候选语言。"""

DownloaderEventType = Literal["file_downloaded", "file_skipped", "file_failed"]
"""下载器事件类型。"""

# ============ 版本常量 ============

DOWNLOADER_VERSION: Final[str] = "hermes_downloader_v1.0.0"
"""下载器语义版本号。

写入缓存元数据，用于判断是否需要重新下载。
"""

# ============ 正则表达式 ============

_TITLE_YEAR_PATTERN: Final[re.Pattern[str]] = re.compile(r"(20\d{2}|19\d{2})")
"""从标题提取4位年份。"""

_TITLE_CHINESE_YEAR_PATTERN: Final[re.Pattern[str]] = re.compile(r"([零〇一二三四五六七八九]{4})年")
"""从标题提取中文数字年份。"""

_DATE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?P<year>\d{4})[-/](?P<month>\d{1,2})[-/](?P<day>\d{1,2})"
)
"""日期格式匹配。"""

_BR_PATTERN: Final[re.Pattern[str]] = re.compile(r"<br\s*/?>", re.IGNORECASE)
"""HTML br标签。"""

_TAG_PATTERN: Final[re.Pattern[str]] = re.compile(r"<[^>]+>")
"""HTML标签。"""

_CNINFO_HTML_TAG_PATTERN: Final[re.Pattern[str]] = re.compile(r"<[^>]+>")
"""巨潮HTML标签。"""

_TITLE_FY_PATTERN: Final[re.Pattern[str]] = re.compile(r"(\d{4})\s*年[年度]?\s*(年度报告|年报)")
"""A股年报标题模式。"""

_TITLE_FISCAL_YEAR_FALLBACK: Final[re.Pattern[str]] = re.compile(r"(\d{4})\s*年")
"""A股财年回退模式。"""

# ============ 中文数字映射 ============

_CHINESE_DIGIT_TO_INT: Final[dict[str, int]] = {
    "零": 0, "〇": 0, "一": 1, "二": 2, "三": 3,
    "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}
"""中文数字到阿拉伯数字映射。"""

# ============ ETag标准化常量 ============

_ETAG_WEAK_PREFIX: Final[str] = "W/"
_ETAG_GZIP_SUFFIX: Final[str] = "-gzip"

# ============ 英文财报Token ============

_ENGLISH_REPORT_TITLE_TOKENS: Final[tuple[str, ...]] = (
    "ANNUAL REPORT",
    "INTERIM REPORT",
    "QUARTERLY REPORT",
    "QUARTERLY RESULTS",
    "FIRST QUARTER",
    "SECOND QUARTER",
    "THIRD QUARTER",
    "FOURTH QUARTER",
)

# ============ 修订版Token ============

_TITLE_AMENDED_TOKENS: Final[tuple[str, ...]] = (
    "更正", "修訂", "修订", "補充", "补充", "REVISED", "SUPPLEMENTAL",
)


# ============ 数据类 ============

@dataclass(frozen=True)
class CompanyProfile:
    """公司基础元数据。

    对应Dayu的CnCompanyProfile。

    Attributes:
        provider: 报告来源provider
        company_id: 公司主体ID
            - US: CIK编号 (如 "0000320193")
            - CN: orgId (如 "gssh0600519")
            - HK: stockId (如 "12345")
        company_name: 公司名称
        ticker: 已归一化的股票代码
    """

    provider: SourceProvider
    company_id: str
    company_name: str
    ticker: str


@dataclass(frozen=True)
class ReportQuery:
    """单ticker单次download的查询参数集合。

    对应Dayu的CnReportQuery。

    Attributes:
        market: 市场标识
        ticker: 已归一化的股票代码
        start_date: 窗口起点 YYYY-MM-DD
        end_date: 窗口终点 YYYY-MM-DD（包含）
        target_periods: 期望的财期集合
    """

    market: MarketKind
    ticker: str
    start_date: str
    end_date: str
    target_periods: tuple[FiscalPeriod, ...]


@dataclass(frozen=True)
class ReportCandidate:
    """单份候选报告的远端元数据。

    对应Dayu的CnReportCandidate。

    Attributes:
        provider: 报告来源provider
        source_id: provider内部唯一ID
        source_url: 直接可下载PDF的绝对URL
        title: 公告标题
        language: 候选语言
        filing_date: 公告披露日期 YYYY-MM-DD
        fiscal_year: 推断财年
        fiscal_period: 推断财期
        amended: 是否修订/更正版本
        content_length: HEAD返回的Content-Length
        etag: HEAD返回的ETag
        last_modified: HEAD返回的Last-Modified
    """

    provider: SourceProvider
    source_id: str
    source_url: str
    title: str
    language: Language
    filing_date: str
    fiscal_year: int
    fiscal_period: FiscalPeriod
    amended: bool
    content_length: int | None = None
    etag: str | None = None
    last_modified: str | None = None


@dataclass(frozen=True)
class DownloadedAsset:
    """下载完成后的资产对象。

    对应Dayu的DownloadedReportAsset。

    Attributes:
        candidate: 对应的远端候选元数据
        pdf_path: PDF本地路径
        sha256: PDF字节内容的SHA-256
        content_length: 实际字节数
        downloaded_at: ISO-8601时间戳
    """

    candidate: ReportCandidate
    pdf_path: Path
    sha256: str
    content_length: int
    downloaded_at: str


@dataclass(frozen=True)
class HeadMeta:
    """HEAD响应元数据。

    对应Dayu的_HeadMeta。

    Attributes:
        content_length: Content-Length头
        etag: ETag头
        last_modified: Last-Modified头
    """

    content_length: int | None
    etag: str | None
    last_modified: str | None


@dataclass(frozen=True)
class DownloaderEvent:
    """下载器文件级事件。

    对应Dayu的DownloaderEvent。

    Attributes:
        event_type: 事件类型
        name: 文件名
        source_url: 源URL
        http_etag: ETag
        http_last_modified: Last-Modified
        http_status: HTTP状态码
        file_meta: 文件元数据（可选）
        reason_code: 失败原因代码
        reason_message: 失败原因消息
        error: 错误信息
    """

    event_type: DownloaderEventType
    name: str
    source_url: str
    http_etag: str | None
    http_last_modified: str | None
    http_status: int | None
    file_meta: dict | None = None
    reason_code: str | None = None
    reason_message: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class BrowseEdgarFiling:
    """browse-edgar记录。

    对应Dayu的BrowseEdgarFiling。

    Attributes:
        form_type: 表单类型
        filing_date: 提交日期
        accession_number: accession number
        cik: CIK编号
        index_url: index.json URL
    """

    form_type: str
    filing_date: str
    accession_number: str
    cik: str
    index_url: str


@dataclass(frozen=True)
class RemoteFileDescriptor:
    """远端文件描述。

    对应Dayu的RemoteFileDescriptor。

    Attributes:
        name: 文件名
        source_url: 源URL
        http_etag: ETag
        http_last_modified: Last-Modified
        remote_size: 远端文件大小
        http_status: HTTP状态码
        sec_document_type: SEC文档类型
        sec_description: SEC描述
    """

    name: str
    source_url: str
    http_etag: str | None
    http_last_modified: str | None
    remote_size: int | None
    http_status: int | None = None
    sec_document_type: str | None = None
    sec_description: str | None = None


# ============ 异常类 ============

class DownloaderError(Exception):
    """下载器基础异常。"""


class CompanyNotFoundError(DownloaderError):
    """公司未找到。"""


class FilingNotFoundError(DownloaderError):
    """财报未找到。"""


class DownloadFailedError(DownloaderError):
    """下载失败。"""


class ValidationError(DownloaderError):
    """数据验证失败。"""


# ============ 辅助函数 ============

def parse_chinese_digit_year(value: str) -> int | None:
    """解析中文数字年份（如'二零二五'）。

    对应Dayu的_parse_chinese_digit_year。

    Args:
        value: 四位中文数字年份

    Returns:
        公历年份；格式或范围异常返回None
    """
    if len(value) != 4:
        return None
    digits: list[str] = []
    for char in value:
        digit = _CHINESE_DIGIT_TO_INT.get(char)
        if digit is None:
            return None
        digits.append(str(digit))
    year = int("".join(digits))
    if 1900 <= year <= 2099:
        return year
    return None


def parse_filing_date(raw_date: str | None) -> str | None:
    """解析披露日期为YYYY-MM-DD。

    对应Dayu的_parse_filing_date。

    Args:
        raw_date: 原始日期字符串

    Returns:
        规范日期；无法解析返回None
    """
    if raw_date is None:
        return None

    # 尝试 YYYY-MM-DD 或 YYYY/MM/DD
    matched = _DATE_PATTERN.search(raw_date)
    if matched is not None:
        year = int(matched.group("year"))
        month = int(matched.group("month"))
        day = int(matched.group("day"))
        return f"{year:04d}-{month:02d}-{day:02d}"

    # 尝试 DD/MM/YYYY 格式
    slash_parts = raw_date.strip().split("/")
    if len(slash_parts) >= 3 and all(part.isdigit() for part in slash_parts[:3]):
        day = int(slash_parts[0])
        month = int(slash_parts[1])
        year = int(slash_parts[2])
        if year >= 1900:
            return f"{year:04d}-{month:02d}-{day:02d}"

    # 尝试 DD/MM/YYYY HH:MM 格式
    slash_time_parts = raw_date.strip().split()
    if slash_time_parts:
        slash_parts = slash_time_parts[0].split("/")
        if len(slash_parts) == 3 and all(part.isdigit() for part in slash_parts):
            day = int(slash_parts[0])
            month = int(slash_parts[1])
            year = int(slash_parts[2])
            if year >= 1900:
                return f"{year:04d}-{month:02d}-{day:02d}"

    return None


def format_announcement_date(raw_time) -> str | None:
    """把巨潮announcementTime规范为YYYY-MM-DD。

    对应Dayu的_format_announcement_date。

    兼容毫秒级时间戳整数和YYYY-MM-DD字符串。

    Args:
        raw_time: 原始字段

    Returns:
        YYYY-MM-DD字符串；无法解析返回None
    """
    if isinstance(raw_time, (int, float)):
        try:
            timestamp = float(raw_time) / 1000.0
            local = time.gmtime(timestamp)
            return time.strftime("%Y-%m-%d", local)
        except (OverflowError, OSError, ValueError):
            return None

    if isinstance(raw_time, str):
        text = raw_time.strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return text
        if text.isdigit():
            try:
                timestamp = float(text) / 1000.0
                local = time.gmtime(timestamp)
                return time.strftime("%Y-%m-%d", local)
            except (OverflowError, OSError, ValueError):
                return None

    return None


def strip_html(raw: str) -> str:
    """清洗HTML标签与多余空白。

    对应Dayu的_strip_html。

    Args:
        raw: 原始文本

    Returns:
        清洗后的文本
    """
    import html as html_module

    unescaped = html_module.unescape(raw)
    without_br = _BR_PATTERN.sub(" ", unescaped)
    without_tags = _TAG_PATTERN.sub("", without_br)
    return " ".join(without_tags.split())


def clean_cninfo_text(text: str) -> str:
    """清洗巨潮返回的高亮HTML文本。

    对应Dayu的_clean_cninfo_text。

    Args:
        text: 巨潮文本字段，可能包含<em>高亮标签

    Returns:
        去掉HTML标签并压缩首尾空白后的文本
    """
    without_tags = _CNINFO_HTML_TAG_PATTERN.sub("", text)
    return without_tags.strip()


def contains_cjk(text: str) -> bool:
    """判断文本是否包含中日韩统一表意文字。

    对应Dayu的_contains_cjk。

    Args:
        text: 待检测文本

    Returns:
        包含中文/繁中文字符返回True
    """
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def normalize_fingerprint_etag(raw_etag: str | None) -> str | None:
    """标准化用于指纹的ETag。

    对应Dayu的_normalize_fingerprint_etag。

    处理：
    - Weak ETag前缀 (W/)
    - 引号包裹
    - Gzip后缀

    Args:
        raw_etag: 原始HTTP ETag

    Returns:
        标准化ETag；无有效值时返回None
    """
    if raw_etag is None:
        return None

    normalized = str(raw_etag).strip()
    if not normalized:
        return None

    # 移除Weak前缀
    if normalized.upper().startswith(_ETAG_WEAK_PREFIX):
        normalized = normalized[2:].strip()

    # 移除引号
    if normalized.startswith('"') and normalized.endswith('"') and len(normalized) >= 2:
        normalized = normalized[1:-1]

    # 移除gzip后缀
    if normalized.lower().endswith(_ETAG_GZIP_SUFFIX):
        normalized = normalized[:-len(_ETAG_GZIP_SUFFIX)]

    normalized = normalized.strip().lower()
    return normalized or None


def normalize_fingerprint_last_modified(raw_last_modified: str | None) -> str | None:
    """标准化用于指纹的Last-Modified。

    对应Dayu的_normalize_fingerprint_last_modified。

    Args:
        raw_last_modified: 原始Last-Modified

    Returns:
        标准化时间字符串；无有效值时返回None
    """
    if raw_last_modified is None:
        return None
    normalized = str(raw_last_modified).strip()
    return normalized or None


def build_source_fingerprint(descriptors: list[RemoteFileDescriptor]) -> str:
    """构建source_fingerprint。

    对应Dayu的build_source_fingerprint。

    基于文件名、ETag、Last-Modified计算SHA256指纹。

    Args:
        descriptors: 远端文件描述列表

    Returns:
        指纹字符串（sha256）
    """
    payload = [
        {
            "name": d.name,
            "etag": normalize_fingerprint_etag(d.http_etag),
            "last_modified": normalize_fingerprint_last_modified(d.http_last_modified),
        }
        for d in sorted(descriptors, key=lambda x: x.name)
    ]
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def handle_conditional_response(
    status_code: int,
    content: bytes | None,
) -> tuple[int, bytes | None]:
    """处理条件下载响应。

    对应Dayu的_handle_conditional_download_response。

    Args:
        status_code: HTTP状态码
        content: 响应内容

    Returns:
        (status_code, payload)；若命中304，则payload为None
    """
    if status_code == 304:
        return 304, None
    return status_code, content
