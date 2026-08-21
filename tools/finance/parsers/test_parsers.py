"""解析器单元测试。

测试：
1. DocumentStore接口
2. DoclingParser
3. MinerUParser
4. FallbackParser
5. FinancialEnhancer
6. ParserRouter
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from finance.parsers.docling_parser import DoclingParser

# 导入被测模块
from finance.parsers.document_store import (
    SectionSummary,
    TableSummary,
)
from finance.parsers.fallback_parser import FallbackParser
from finance.parsers.financial_enhancer import relabel_tables
from finance.parsers.mineru_parser import MinerUConfig, MinerUParser
from finance.parsers.parser_router import create_parser

# ============ DocumentStore接口测试 ============

class TestSectionSummary:
    """测试SectionSummary数据类。"""

    def test_creation(self):
        """测试创建SectionSummary。"""
        section = SectionSummary(
            ref="section_0",
            title="Test Section",
            level=1,
            parent_ref=None,
            preview="Test preview",
            page_range=[1, 2],
            internal_ref=None,
        )
        assert section.ref == "section_0"
        assert section.title == "Test Section"
        assert section.level == 1
        assert section.parent_ref is None
        assert section.preview == "Test preview"
        assert section.page_range == [1, 2]
        assert section.internal_ref is None


class TestTableSummary:
    """测试TableSummary数据类。"""

    def test_creation(self):
        """测试创建TableSummary。"""
        table = TableSummary(
            table_ref="table_0",
            caption="Test Table",
            context_before="Context",
            row_count=10,
            col_count=5,
            table_type="unknown",
            headers=["Col1", "Col2"],
            section_ref="section_0",
            page_no=1,
            internal_ref=None,
            is_financial=None,
        )
        assert table.table_ref == "table_0"
        assert table.caption == "Test Table"
        assert table.row_count == 10
        assert table.col_count == 5
        assert table.is_financial is None


# ============ DoclingParser测试 ============

class TestDoclingParser:
    """测试DoclingParser。"""

    def test_supports(self):
        """测试supports方法。"""
        assert DoclingParser.supports(Path("test.pdf")) is True
        assert DoclingParser.supports(Path("test.docx")) is True
        assert DoclingParser.supports(Path("test.txt")) is False

    def test_get_parser_version(self):
        """测试get_parser_version方法。"""
        version = DoclingParser.get_parser_version()
        assert version.startswith("hermes_docling_parser")


# ============ MinerUParser测试 ============

class TestMinerUParser:
    """测试MinerUParser。"""

    def test_supports(self):
        """测试supports方法。"""
        assert MinerUParser.supports(Path("test.pdf")) is True
        assert MinerUParser.supports(Path("test.txt")) is False

    def test_get_parser_version(self):
        """测试get_parser_version方法。"""
        version = MinerUParser.get_parser_version()
        assert version.startswith("hermes_mineru_parser")

    def test_mineru_config(self):
        """测试MinerUConfig（HGF P0-①：对齐本地契约——hermes api_url/timeout 未随迁）"""
        config = MinerUConfig()
        # 本地实现契约：timeout 默认 120s、max_retries 3（非 hermes 版 300/3）
        assert config.timeout == 120
        assert config.max_retries == 3
        # 本地无 api_url 属性（api_url 按 api_mode 在调用时构造）——不断言 hermes 版默认


# ============ FallbackParser测试 ============

class TestFallbackParser:
    """测试FallbackParser。"""

    def test_supports(self):
        """测试supports方法。"""
        assert FallbackParser.supports(Path("test.pdf")) is True
        assert FallbackParser.supports(Path("test.txt")) is False

    def test_get_parser_version(self):
        """测试get_parser_version方法。"""
        version = FallbackParser.get_parser_version()
        assert version.startswith("hermes_fallback_parser")


# ============ FinancialEnhancer测试 ============

class TestFinancialEnhancer:
    """测试FinancialEnhancer。"""

    def test_relabel_tables_balance_sheet(self):
        """测试识别资产负债表。"""
        tables = [
            TableSummary(
                table_ref="table_0",
                caption="资产负债表",
                context_before="",
                row_count=10,
                col_count=5,
                table_type="unknown",
                headers=None,
                section_ref=None,
                page_no=None,
                internal_ref=None,
                is_financial=None,
            )
        ]

        result = relabel_tables(tables)

        assert len(result) == 1
        assert result[0].is_financial is True
        assert result[0].table_type == "balance_sheet"

    def test_relabel_tables_income_statement(self):
        """测试识别利润表。"""
        tables = [
            TableSummary(
                table_ref="table_0",
                caption="利润表",
                context_before="",
                row_count=10,
                col_count=5,
                table_type="unknown",
                headers=None,
                section_ref=None,
                page_no=None,
                internal_ref=None,
                is_financial=None,
            )
        ]

        result = relabel_tables(tables)

        assert len(result) == 1
        assert result[0].is_financial is True
        assert result[0].table_type == "income_statement"

    def test_relabel_tables_unknown(self):
        """测试未知表格。"""
        tables = [
            TableSummary(
                table_ref="table_0",
                caption="普通表格",
                context_before="",
                row_count=10,
                col_count=5,
                table_type="unknown",
                headers=None,
                section_ref=None,
                page_no=None,
                internal_ref=None,
                is_financial=None,
            )
        ]

        result = relabel_tables(tables)

        assert len(result) == 1
        # 本地实现语义：未命中任何金融关键词 → is_financial=False（非金融），
        # 非 hermes 版的 None（未知）——HGF P0-① 修复：对齐本地语义
        assert result[0].is_financial is False
        assert result[0].table_type == "unknown"


# ============ ParserRouter测试 ============

class TestParserRouter:
    """测试ParserRouter。"""

    def test_create_parser_file_not_found(self):
        """测试文件不存在。"""
        with pytest.raises(FileNotFoundError):
            create_parser(Path("nonexistent.pdf"))

    @patch('finance.parsers.parser_router.check_mineru_health')
    def test_create_parser_fallback(self, mock_health):
        """测试降级到FallbackParser（HGF P0-①：mock 对齐本地契约——返回 dict 非 bool）"""
        mock_health.return_value = {"agent_api": False, "precise_api": False,
                                    "has_token": False, "error": None}

        # 创建临时PDF文件
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4 test")
            pdf_path = Path(f.name)

        try:
            parser = create_parser(pdf_path)
            assert isinstance(parser, FallbackParser)
        finally:
            pdf_path.unlink()


# ============ 运行测试 ============

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
