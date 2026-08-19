"""下载器单元测试。

测试：
1. models.py 辅助函数
2. http_client.py HTTP客户端
3. 各下载器的辅助方法
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

# 导入被测模块
from hermes_tools.finance.downloaders.models import (
    parse_chinese_digit_year,
    parse_filing_date,
    format_announcement_date,
    strip_html,
    clean_cninfo_text,
    contains_cjk,
    normalize_fingerprint_etag,
    normalize_fingerprint_last_modified,
    build_source_fingerprint,
    handle_conditional_response,
    RemoteFileDescriptor,
    CompanyProfile,
    ReportQuery,
    ReportCandidate,
    DownloaderError,
    CompanyNotFoundError,
)

from hermes_tools.finance.downloaders.http_client import HttpClient
from hermes_tools.finance.downloaders.hkexnews_downloader import HKEXNewsDownloader
from hermes_tools.finance.downloaders.sec_downloader import SECDownloader
from hermes_tools.finance.downloaders.cninfo_downloader import CNInfoDownloader


# ============ models.py 测试 ============

class TestParseChineseDigitYear:
    """测试parse_chinese_digit_year。"""
    
    def test_valid_year(self):
        """测试有效中文数字年份。"""
        assert parse_chinese_digit_year("二零二五") == 2025
        assert parse_chinese_digit_year("二零二四") == 2024
        assert parse_chinese_digit_year("一九九九") == 1999
    
    def test_invalid_length(self):
        """测试无效长度。"""
        assert parse_chinese_digit_year("二零二") is None
        assert parse_chinese_digit_year("二零二五四") is None
    
    def test_invalid_digit(self):
        """测试无效数字。"""
        assert parse_chinese_digit_year("二零二十") is None
        assert parse_chinese_digit_year("abcde") is None
    
    def test_out_of_range(self):
        """测试超出范围。"""
        assert parse_chinese_digit_year("零零零零") is None  # 0000
        assert parse_chinese_digit_year("三零零零") is None  # 3000


class TestParseFilingDate:
    """测试parse_filing_date。"""
    
    def test_iso_format(self):
        """测试ISO格式。"""
        assert parse_filing_date("2024-03-28") == "2024-03-28"
        assert parse_filing_date("2024/03/28") == "2024-03-28"
    
    def test_dd_mm_yyyy(self):
        """测试DD/MM/YYYY格式。"""
        assert parse_filing_date("28/03/2024") == "2024-03-28"
    
    def test_with_time(self):
        """测试带时间的格式。"""
        assert parse_filing_date("28/03/2024 16:55") == "2024-03-28"
    
    def test_none(self):
        """测试None输入。"""
        assert parse_filing_date(None) is None
    
    def test_invalid(self):
        """测试无效格式。"""
        assert parse_filing_date("invalid") is None


class TestFormatAnnouncementDate:
    """测试format_announcement_date。"""
    
    def test_timestamp(self):
        """测试毫秒时间戳。"""
        # 2024-03-28 00:00:00 UTC
        timestamp = 1711584000000
        result = format_announcement_date(timestamp)
        assert result == "2024-03-28"
    
    def test_iso_string(self):
        """测试ISO字符串。"""
        assert format_announcement_date("2024-03-28") == "2024-03-28"
    
    def test_none(self):
        """测试None输入。"""
        assert format_announcement_date(None) is None


class TestStripHtml:
    """测试strip_html。"""
    
    def test_basic(self):
        """测试基本HTML清洗。"""
        assert strip_html("<b>test</b>") == "test"
        assert strip_html("<br/>test") == "test"
    
    def test_entities(self):
        """测试HTML实体。"""
        assert strip_html("&amp;") == "&"
        assert strip_html("&lt;") == "<"


class TestContainsCjk:
    """测试contains_cjk。"""
    
    def test_chinese(self):
        """测试中文字符。"""
        assert contains_cjk("你好") is True
        assert contains_cjk("test") is False
        assert contains_cjk("test你好") is True


class TestNormalizeFingerprintEtag:
    """测试normalize_fingerprint_etag。"""
    
    def test_weak_etag(self):
        """测试Weak ETag。"""
        assert normalize_fingerprint_etag('W/"abc"') == "abc"
    
    def test_gzip_suffix(self):
        """测试gzip后缀。"""
        assert normalize_fingerprint_etag('"abc-gzip"') == "abc"
    
    def test_none(self):
        """测试None输入。"""
        assert normalize_fingerprint_etag(None) is None


class TestHandleConditionalResponse:
    """测试handle_conditional_response。"""
    
    def test_304(self):
        """测试304响应。"""
        status, content = handle_conditional_response(304, None)
        assert status == 304
        assert content is None
    
    def test_200(self):
        """测试200响应。"""
        status, content = handle_conditional_response(200, b"test")
        assert status == 200
        assert content == b"test"


# ============ http_client.py 测试 ============

class TestHttpClient:
    """测试HttpClient。"""
    
    def test_init_invalid_retries(self):
        """测试无效重试次数。"""
        with pytest.raises(ValueError, match="max_retries"):
            HttpClient(max_retries=0)
    
    def test_init_invalid_sleep(self):
        """测试无效sleep时间。"""
        with pytest.raises(ValueError, match="sleep_seconds"):
            HttpClient(sleep_seconds=-1)


# ============ hkexnews_downloader.py 测试 ============

class TestHKEXNewsDownloader:
    """测试港股下载器辅助方法。"""
    
    def test_normalize_ticker(self):
        """测试ticker规范化。"""
        downloader = HKEXNewsDownloader(http_client=Mock())
        assert downloader._normalize_ticker("0700") == "00700"
        assert downloader._normalize_ticker("0700.HK") == "00700"
        assert downloader._normalize_ticker("700") == "00700"
    
    def test_infer_fiscal_year_arabic(self):
        """测试阿拉伯数字年份推断。"""
        downloader = HKEXNewsDownloader(http_client=Mock())
        assert downloader._infer_fiscal_year("2024年年报", "2024-03-28") == 2024
    
    def test_infer_fiscal_year_chinese(self):
        """测试中文数字年份推断。"""
        downloader = HKEXNewsDownloader(http_client=Mock())
        assert downloader._infer_fiscal_year("二零二四年年报", "2024-03-28") == 2024
    
    def test_infer_fiscal_year_fallback(self):
        """测试年份推断回退。"""
        downloader = HKEXNewsDownloader(http_client=Mock())
        assert downloader._infer_fiscal_year("年报", "2024-03-28") == 2024
    
    def test_is_amended_title(self):
        """测试修订版识别。"""
        downloader = HKEXNewsDownloader(http_client=Mock())
        assert downloader._is_amended_title("更正公告") is True
        assert downloader._is_amended_title("年报") is False
    
    def test_split_stock_code_tokens(self):
        """测试多代码字段解析。"""
        downloader = HKEXNewsDownloader(http_client=Mock())
        tokens = downloader._split_stock_code_tokens("00700<br/>09988")
        assert "00700" in tokens
        assert "09988" in tokens
    
    def test_announcement_matches_stock(self):
        """测试多代码字段匹配。"""
        downloader = HKEXNewsDownloader(http_client=Mock())
        assert downloader._announcement_matches_stock("00700<br/>09988", "00700") is True
        assert downloader._announcement_matches_stock("00700<br/>09988", "09988") is True
        assert downloader._announcement_matches_stock("00700<br/>09988", "00001") is False


# ============ sec_downloader.py 测试 ============

class TestSECDownloader:
    """测试美股下载器辅助方法。"""
    
    def test_infer_period(self):
        """测试财期推断。"""
        downloader = SECDownloader(http_client=Mock())
        assert downloader._infer_period("10-K", "2024-03-28") == "FY"
        assert downloader._infer_period("10-Q", "2024-05-10") == "Q1"
        assert downloader._infer_period("10-Q", "2024-08-10") == "Q3"
        assert downloader._infer_period("20-F", "2024-03-28") == "FY"
    
    def test_infer_year(self):
        """测试财年推断。"""
        downloader = SECDownloader(http_client=Mock())
        # 10-K in March -> previous year
        assert downloader._infer_year("2024-03-28", "10-K") == 2023
        # 10-Q in May -> same year
        assert downloader._infer_year("2024-05-10", "10-Q") == 2024


# ============ cninfo_downloader.py 测试 ============

class TestCNInfoDownloader:
    """测试A股下载器辅助方法。"""
    
    def test_resolve_exchange_context(self):
        """测试市场识别。"""
        downloader = CNInfoDownloader(http_client=Mock())
        
        context = downloader._resolve_exchange_context("600519")
        assert context.column == "sse"
        assert context.plate == "sh"
        
        context = downloader._resolve_exchange_context("000858")
        assert context.column == "szse"
        assert context.plate == "sz"
    
    def test_resolve_exchange_context_invalid(self):
        """测试无效ticker。"""
        downloader = CNInfoDownloader(http_client=Mock())
        
        with pytest.raises(ValueError, match="6位"):
            downloader._resolve_exchange_context("123")
        
        with pytest.raises(ValueError, match="前缀"):
            downloader._resolve_exchange_context("999999")
    
    def test_is_title_blocked(self):
        """测试标题黑名单。"""
        downloader = CNInfoDownloader(http_client=Mock())
        
        assert downloader._is_title_blocked("摘要") is True
        assert downloader._is_title_blocked("ESG报告") is True
        assert downloader._is_title_blocked("年度报告") is False
    
    def test_infer_fiscal_year(self):
        """测试财年推断。"""
        downloader = CNInfoDownloader(http_client=Mock())
        
        assert downloader._infer_fiscal_year("2024年年度报告", "2024-03-28") == 2024
        assert downloader._infer_fiscal_year("年度报告", "2024-03-28") == 2024
    
    def test_is_amended_title(self):
        """测试修订版识别。"""
        downloader = CNInfoDownloader(http_client=Mock())
        
        assert downloader._is_amended_title("更正公告") is True
        assert downloader._is_amended_title("年度报告") is False


# ============ 运行测试 ============

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
