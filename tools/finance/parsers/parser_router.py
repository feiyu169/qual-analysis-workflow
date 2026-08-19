"""解析器路由逻辑。

根据文件类型、服务健康状态自动选择合适解析器。

路由优先级：
1. DoclingParser（美股，支持多种格式，需 venv 环境）
2. MinerUParser（A股/港股，FastAPI服务）
3. FallbackParser（降级方案：pdfplumber → PyPDF2 → PyMuPDF）

venv 支持：
- DoclingParser 依赖 docling 库，与系统 Python 存在依赖冲突
- 解析器使用独立 venv (~/.hermes/tools/finance/.venv)
- 当系统 Python 无法导入 docling 时，自动切换到 venv Python 通过子进程调用
- MinerUParser 通过 HTTP 调用，不受 Python 环境影响

切换逻辑：
- DoclingParser失败 → 尝试MinerUParser
- MinerU服务不健康 → 跳过MinerUParser
- MinerUParser失败 → 使用FallbackParser
- FallbackParser内部：pdfplumber → PyPDF2 → PyMuPDF

认证支持：
- MinerU服务支持Bearer Token认证
- 通过MinerUConfig.token配置
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional

import httpx

from .document_store import (
    DocumentStore,
    SectionSummary,
    TableSummary,
    SectionContent,
    TableContent,
    SearchHit,
)
from .mineru_parser import MinerUParser, MinerUConfig
from .fallback_parser import FallbackParser

logger = logging.getLogger(__name__)

# ============ Venv 配置 ============

FINANCE_VENV = Path(__file__).parent.parent / ".venv"
FINANCE_VENV_PYTHON = FINANCE_VENV / "bin" / "python3"

# ============ 辅助函数 ============


def _get_venv_python() -> Optional[Path]:
    """获取 venv Python 路径。"""
    if FINANCE_VENV_PYTHON.exists():
        return FINANCE_VENV_PYTHON
    return None


def _is_venv_python() -> bool:
    """检查当前 Python 是否是 venv Python。"""
    venv_python = _get_venv_python()
    if venv_python is None:
        return False
    return Path(sys.executable).resolve() == venv_python.resolve()


def _can_import_docling() -> bool:
    """检查当前 Python 能否导入 docling。"""
    try:
        from .docling_parser import DoclingParser  # noqa: F401
        return True
    except Exception:
        return False


def _create_docling_via_subprocess(pdf_path: Path) -> Optional[DocumentStore]:
    """通过 venv 子进程创建 DoclingParser。

    在 venv Python 中运行一个脚本，解析 PDF 并返回 JSON 格式的结果。
    然后将结果包装为 SubprocessDoclingStore（实现 DocumentStore 接口）。

    Args:
        pdf_path: PDF 文件路径

    Returns:
        SubprocessDoclingStore 实例，或 None（如果失败）
    """
    venv_python = _get_venv_python()
    if venv_python is None:
        logger.debug("venv Python 不存在")
        return None

    # 构建子进程脚本
    script = f'''
import json
import sys
sys.path.insert(0, {str(Path(__file__).parent.parent)!r})

from pathlib import Path
from parsers.docling_parser import DoclingParser

pdf_path = Path({str(pdf_path)!r})
try:
    parser = DoclingParser(pdf_path)

    # 获取章节列表
    sections = []
    for s in parser.list_sections():
        sections.append({{
            "ref": s.ref,
            "title": s.title,
            "level": s.level,
            "parent_ref": s.parent_ref,
            "preview": s.preview[:200] if s.preview else "",
            "page_range": s.page_range,
        }})

    # 获取表格列表
    tables = []
    for t in parser.list_tables():
        tables.append({{
            "table_ref": t.table_ref,
            "caption": t.caption,
            "row_count": t.row_count,
            "col_count": t.col_count,
            "table_type": t.table_type,
            "headers": t.headers,
            "page_no": t.page_no,
        }})

    # 获取文档全文
    doc_content = parser.read_section(sections[0]["ref"] if sections else "document")

    result = {{
        "success": True,
        "page_count": parser._page_count,
        "parser_version": parser.PARSER_VERSION,
        "sections": sections,
        "tables": tables,
        "markdown": doc_content.content,
        "word_count": doc_content.word_count,
    }}
    print(json.dumps(result, ensure_ascii=False))
except Exception as e:
    print(json.dumps({{"success": False, "error": str(e)}}, ensure_ascii=False))
'''
    try:
        result = subprocess.run(
            [str(venv_python), "-c", script],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            logger.warning(f"DoclingParser 子进程失败: {result.stderr[:500]}")
            return None

        data = json.loads(result.stdout.strip())
        if not data.get("success"):
            logger.warning(f"DoclingParser 解析失败: {data.get('error')}")
            return None

        logger.info(
            f"DoclingParser 子进程成功: {data['page_count']} 页, "
            f"{len(data['sections'])} 章节, {len(data['tables'])} 表格"
        )
        return SubprocessDoclingStore(pdf_path, data)

    except subprocess.TimeoutExpired:
        logger.warning("DoclingParser 子进程超时")
        return None
    except json.JSONDecodeError as e:
        logger.warning(f"DoclingParser 子进程输出解析失败: {e}")
        return None
    except Exception as e:
        logger.warning(f"DoclingParser 子进程异常: {e}")
        return None


# ============ 子进程结果包装 ============


class SubprocessDoclingStore(DocumentStore):
    """将子进程 DoclingParser 的 JSON 结果包装为 DocumentStore。"""

    PARSER_VERSION = "hermes_docling_subprocess_v1.0.0"

    def __init__(self, pdf_path: Path, data: dict):
        self._pdf_path = pdf_path
        self._data = data
        self._page_count = data.get("page_count", 0)
        self._markdown = data.get("markdown", "")
        self._sections_data = data.get("sections", [])
        self._tables_data = data.get("tables", [])
        self._word_count = data.get("word_count", 0)

    def list_sections(self) -> list[SectionSummary]:
        return [
            SectionSummary(
                ref=s["ref"],
                title=s["title"],
                level=s.get("level", 0),
                parent_ref=s.get("parent_ref"),
                preview=s.get("preview", ""),
                page_range=s.get("page_range", []),
                internal_ref=None,
            )
            for s in self._sections_data
        ]

    def list_tables(self) -> list[TableSummary]:
        return [
            TableSummary(
                table_ref=t["table_ref"],
                caption=t.get("caption"),
                context_before="",
                row_count=t.get("row_count", 0),
                col_count=t.get("col_count", 0),
                table_type=t.get("table_type", "unknown"),
                headers=t.get("headers"),
                section_ref=None,
                page_no=t.get("page_no"),
                internal_ref=None,
                is_financial=None,
            )
            for t in self._tables_data
        ]

    def read_section(self, ref: str) -> SectionContent:
        # 找到对应章节
        for s in self._sections_data:
            if s["ref"] == ref:
                return SectionContent(
                    ref=ref,
                    title=s["title"],
                    content=self._markdown,
                    tables=[t["table_ref"] for t in self._tables_data],
                    word_count=self._word_count,
                    contains_full_text=True,
                    page_range=s.get("page_range", list(range(1, self._page_count + 1))),
                    internal_ref=None,
                )
        # 默认返回全文
        return SectionContent(
            ref=ref,
            title=self._pdf_path.stem,
            content=self._markdown,
            tables=[t["table_ref"] for t in self._tables_data],
            word_count=self._word_count,
            contains_full_text=True,
            page_range=list(range(1, self._page_count + 1)),
            internal_ref=None,
        )

    def read_table(self, table_ref: str) -> TableContent:
        for t in self._tables_data:
            if t["table_ref"] == table_ref:
                return TableContent(
                    table_ref=table_ref,
                    caption=t.get("caption"),
                    data_format="records",
                    data=[],
                    columns=t.get("headers"),
                    row_count=t.get("row_count", 0),
                    col_count=t.get("col_count", 0),
                    section_ref=None,
                    table_type=t.get("table_type", "unknown"),
                    page_no=t.get("page_no"),
                    internal_ref=None,
                )
        raise KeyError(f"表格不存在: {table_ref}")

    def search(self, query: str, within_ref=None) -> list[SearchHit]:
        hits = []
        if query.lower() in self._markdown.lower():
            idx = self._markdown.lower().find(query.lower())
            start = max(0, idx - 200)
            end = min(len(self._markdown), idx + len(query) + 200)
            snippet = self._markdown[start:end]
            hits.append(SearchHit(
                ref="document",
                title=self._pdf_path.stem,
                snippet=snippet,
                score=1.0,
                section_ref="document",
            ))
        return hits

    def get_section_title(self, ref: str) -> Optional[str]:
        for s in self._sections_data:
            if s["ref"] == ref:
                return s["title"]
        return None

    @classmethod
    def supports(cls, source: Path) -> bool:
        return source.suffix.lower() == ".pdf"

    @classmethod
    def get_parser_version(cls) -> str:
        return cls.PARSER_VERSION


# ============ MinerU 健康检查 ============


def check_mineru_health(config: Optional[MinerUConfig] = None) -> dict:
    """检查MinerU API健康状态。

    Returns:
        {"precise": bool, "agent": bool, "has_token": bool}
    """
    from .mineru_parser import check_mineru_api_health
    return check_mineru_api_health(config.token if config else None)


# ============ 路由逻辑 ============


def create_parser(
    pdf_path: Path,
    config: Optional[MinerUConfig] = None,
) -> DocumentStore:
    """创建解析器（自动路由）。

    路由优先级：
    1. MinerU 精准API（需Token，≤200页，最佳质量）
    2. DoclingParser（直接导入或venv子进程）
    3. MinerU Agent API（免登录，≤20页）
    4. FallbackParser（pdfplumber → PyPDF2 → PyMuPDF）
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF文件不存在: {pdf_path}")

    if config is None:
        config = MinerUConfig()

    health = check_mineru_health(config)

    # Step 1: MinerU 精准API（最佳质量，有Token时优先）
    if health.get("precise_api") and config.token:
        try:
            logger.info(f"尝试MinerU精准API: {pdf_path}")
            config.api_mode = "precise"
            return MinerUParser(pdf_path, config=config)
        except Exception as exc:
            logger.warning(f"MinerU精准API失败: {exc}")

    # Step 2: DoclingParser
    if _can_import_docling():
        try:
            from .docling_parser import DoclingParser
            logger.info(f"尝试DoclingParser: {pdf_path}")
            return DoclingParser(pdf_path)
        except Exception as exc:
            logger.warning(f"DoclingParser失败: {exc}")

    if _get_venv_python() is not None:
        logger.info(f"尝试DoclingParser(venv): {pdf_path}")
        store = _create_docling_via_subprocess(pdf_path)
        if store is not None:
            return store

    # Step 3: MinerU Agent API（降级，免登录）
    if health.get("agent_api"):
        try:
            logger.info(f"尝试MinerU Agent API: {pdf_path}")
            config.api_mode = "agent"
            return MinerUParser(pdf_path, config=config)
        except Exception as exc:
            logger.warning(f"MinerU Agent失败: {exc}")

    # Step 4: FallbackParser
    logger.info(f"使用FallbackParser: {pdf_path}")
    return FallbackParser(pdf_path)


def get_parser_info() -> dict:
    """获取解析器环境信息（用于诊断）。"""
    health = check_mineru_health()
    return {
        "current_python": sys.executable,
        "venv_python": str(FINANCE_VENV_PYTHON) if FINANCE_VENV_PYTHON.exists() else None,
        "is_venv": _is_venv_python(),
        "can_import_docling": _can_import_docling(),
        "mineru_health": health,
    }
