"""MinerU解析器（云端API版）。

通过 MinerU 云端 API 解析 PDF，无需本地安装 magic-pdf。
实现完整 DocumentStore 接口（9个接口）。

API 模式：
1. 精准解析（默认，需Token）：≤200MB/≤200页，输出 ZIP（Markdown+JSON+图片）
   - 本地文件：POST /api/v4/file-urls/batch → PUT上传 → 自动解析 → GET轮询
   - 远程URL：POST /api/v4/extract/task → GET轮询
2. Agent 轻量解析（降级）：免登录，IP限频，≤10MB/≤20页，仅输出 Markdown

Token 配置（优先级从高到低）：
1. 构造函数传入 config.token
2. 环境变量 MINERU_TOKEN
3. ~/.hermes/.env 中的 MINERU_TOKEN
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import time
import zipfile
from pathlib import Path

import httpx

from .document_store import (
    DocumentStore,
    SearchHit,
    SectionContent,
    SectionSummary,
    TableContent,
    TableSummary,
)

logger = logging.getLogger(__name__)

# ============ 常量 ============

MINERU_AGENT_API = "https://mineru.net/api/v1/agent"
MINERU_PRECISE_API = "https://mineru.net/api/v4"
DEFAULT_TIMEOUT = 120
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 3
DEFAULT_POLL_INTERVAL = 3
DEFAULT_POLL_TIMEOUT = 600  # 10分钟


def _load_token() -> str | None:
    """从环境变量或 .env 文件加载 MinerU Token。"""
    token = os.environ.get("MINERU_TOKEN")
    if token:
        return token.strip()

    env_file = Path.home() / ".hermes" / ".env"
    key = "MINERU" + "_TOKEN="
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith(key):
                value = line.split("=", 1)[1].strip()
                if value:
                    return value
    return None


# ============ 配置 ============

class MinerUConfig:
    """MinerU配置。

    Attributes:
        api_mode: 'precise'（默认，需Token）或 'agent'（免登录降级）
        token: Bearer Token（precise模式必需）
        model_version: 'vlm'（推荐）或 'pipeline'
        language: 'ch', 'en', 'japan' 等
        is_ocr: 是否启用OCR
        enable_formula: 是否启用公式识别
        enable_table: 是否启用表格识别
        page_range: 页码范围（如 '1-200'）
    """

    def __init__(
        self,
        api_mode: str = "precise",
        token: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay: float = DEFAULT_RETRY_DELAY,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        poll_timeout: float = DEFAULT_POLL_TIMEOUT,
        language: str = "ch",
        is_ocr: bool = True,
        enable_formula: bool = True,
        enable_table: bool = True,
        model_version: str = "vlm",
        page_range: str | None = None,
    ):
        self.api_mode = api_mode
        self.token = token or _load_token()
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout
        self.language = language
        self.is_ocr = is_ocr
        self.enable_formula = enable_formula
        self.enable_table = enable_table
        self.model_version = model_version
        self.page_range = page_range

    @property
    def api_base(self) -> str:
        if self.api_mode == "precise":
            return MINERU_PRECISE_API
        return MINERU_AGENT_API

    def get_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def effective_mode(self) -> str:
        """返回实际可用的模式。无Token时降级到agent。"""
        if self.api_mode == "precise" and self.token:
            return "precise"
        if self.api_mode == "precise" and not self.token:
            logger.warning("精准解析模式需要Token，降级到Agent模式")
        return "agent"


# ============ 解析器 ============

class MinerUParser(DocumentStore):
    """MinerU解析器（云端API版）。

    支持两种模式：
    - precise（默认）：需Token，≤200页，输出ZIP（MD+JSON+图片）
    - agent（降级）：免登录，≤20页，仅Markdown
    """

    PARSER_VERSION = "hermes_mineru_parser_v4.0.0"

    def __init__(
        self,
        pdf_path: Path,
        config: MinerUConfig | None = None,
    ):
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF文件不存在: {pdf_path}")

        self._pdf_path = pdf_path
        self._config = config or MinerUConfig()
        self._markdown: str = ""
        self._content_list: list[dict] = []  # content_list.json 原始数据
        self._sections: list[SectionSummary] = []
        self._tables: list[TableSummary] = []
        self._section_map: dict[str, SectionSummary] = {}
        self._table_map: dict[str, TableSummary] = {}
        self._page_count = 0

        self._parse_document()

    def _parse_document(self):
        """解析文档，构建索引。"""
        mode = self._config.effective_mode()

        try:
            if mode == "precise":
                result = self._parse_with_precise_api()
            else:
                result = self._parse_with_agent_api()

            self._markdown = result.get("markdown", "")
            self._content_list = result.get("content_list", [])

            # 优先用 content_list.json 构建索引（更精确）
            if self._content_list:
                self._build_from_content_list()
            else:
                self._build_sections_from_markdown()
                self._build_tables_from_markdown()

            self._estimate_page_count()

            logger.info(
                f"MinerU解析完成[{mode}]: {len(self._sections)} 章节, "
                f"{len(self._tables)} 表格, {self._page_count} 页, "
                f"{len(self._markdown)} 字符"
            )

        except Exception as exc:
            logger.error(f"MinerU解析失败: {exc}")
            raise

    # ============ 精准解析 API ============

    def _parse_with_precise_api(self) -> dict:
        """精准解析API（本地文件流程）。

        流程：
        1. POST /api/v4/file-urls/batch → batch_id + 签名上传URL
        2. PUT 上传文件
        3. GET /api/v4/extract-results/batch/{batch_id} → 轮询
        4. 下载 ZIP → 提取 full.md + content_list.json
        """
        batch_id, upload_url = self._request_upload_url()
        self._upload_to_signed_url(upload_url)
        zip_url = self._poll_batch_result(batch_id)
        return self._download_and_extract(zip_url)

    def _request_upload_url(self) -> tuple[str, str]:
        """请求签名上传URL。

        Returns:
            (batch_id, upload_url)
        """
        api_url = f"{MINERU_PRECISE_API}/file-urls/batch"
        data = {
            "files": [{"name": self._pdf_path.name, "is_ocr": self._config.is_ocr}],
            "model_version": self._config.model_version,
            "enable_table": self._config.enable_table,
            "enable_formula": self._config.enable_formula,
            "language": self._config.language,
        }
        if self._config.page_range:
            data["files"][0]["page_ranges"] = self._config.page_range

        for attempt in range(self._config.max_retries):
            try:
                resp = httpx.post(
                    api_url,
                    json=data,
                    headers=self._config.get_headers(),
                    timeout=self._config.timeout,
                )
                if resp.status_code == 200:
                    result = resp.json()
                    if result.get("code") == 0:
                        batch_id = result["data"]["batch_id"]
                        upload_url = result["data"]["file_urls"][0]
                        logger.info(f"获取上传URL成功: batch_id={batch_id}")
                        return batch_id, upload_url
                    raise RuntimeError(f"API错误: {result}")
                if resp.status_code == 429:
                    wait = self._config.retry_delay * (2 ** attempt)
                    logger.warning(f"限频，等待 {wait}s")
                    time.sleep(wait)
                    continue
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")
            except httpx.TimeoutException:
                if attempt < self._config.max_retries - 1:
                    continue
                raise RuntimeError("请求上传URL超时")

        raise RuntimeError("请求上传URL失败，已达最大重试次数")

    def _upload_to_signed_url(self, upload_url: str):
        """PUT上传文件到签名URL。"""
        with open(self._pdf_path, "rb") as f:
            resp = httpx.put(upload_url, content=f.read(), timeout=300)
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"文件上传失败: HTTP {resp.status_code}")
        logger.info(f"文件上传成功: {self._pdf_path.name}")

    def _poll_batch_result(self, batch_id: str) -> str:
        """轮询批量任务结果。

        Returns:
            full_zip_url
        """
        poll_url = f"{MINERU_PRECISE_API}/extract-results/batch/{batch_id}"
        start = time.time()

        while True:
            elapsed = time.time() - start
            if elapsed > self._config.poll_timeout:
                raise RuntimeError(f"轮询超时({self._config.poll_timeout}s)")

            resp = httpx.get(
                poll_url,
                headers=self._config.get_headers(),
                timeout=self._config.timeout,
            )
            if resp.status_code == 200:
                result = resp.json()
                if result.get("code") == 0:
                    extract_results = result["data"].get("extract_result", [])
                    if not extract_results:
                        time.sleep(self._config.poll_interval)
                        continue

                    r = extract_results[0]
                    state = r.get("state")

                    if state == "done":
                        zip_url = r.get("full_zip_url", "")
                        if not zip_url:
                            raise RuntimeError("完成但无下载链接")
                        logger.info(f"精准解析完成: {int(elapsed)}s")
                        return zip_url
                    elif state == "failed":
                        raise RuntimeError(f"解析失败: {r.get('err_msg', '未知')}")
                    else:
                        prog = r.get("extract_progress", {})
                        pages = prog.get("extracted_pages", 0)
                        total = prog.get("total_pages", 0)
                        logger.debug(f"[{int(elapsed)}s] {state} {pages}/{total}")

            time.sleep(self._config.poll_interval)

    def _download_and_extract(self, zip_url: str) -> dict:
        """下载ZIP并提取内容。

        Returns:
            {"markdown": "...", "content_list": [...]}
        """
        resp = httpx.get(zip_url, timeout=120)
        if resp.status_code != 200:
            raise RuntimeError(f"下载ZIP失败: HTTP {resp.status_code}")

        markdown = ""
        content_list = []

        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            names = zf.namelist()

            # 提取 full.md
            md_files = [n for n in names if n.endswith("full.md")]
            if md_files:
                markdown = zf.read(md_files[0]).decode("utf-8")

            # 提取 content_list.json（非v2，更精确）
            cl_files = [n for n in names if n.endswith("content_list.json") and "v2" not in n]
            if cl_files:
                content_list = json.loads(zf.read(cl_files[0]))

        logger.info(f"ZIP提取完成: {len(markdown)} chars MD, {len(content_list)} content items")
        return {"markdown": markdown, "content_list": content_list}

    # ============ Agent 轻量解析 API（降级） ============

    def _parse_with_agent_api(self) -> dict:
        """Agent轻量解析API（免登录，≤20页）。

        超过20页时自动分块。
        """
        try:
            import fitz
            doc = fitz.open(str(self._pdf_path))
            total_pages = len(doc)
            doc.close()
        except ImportError:
            total_pages = 20

        if total_pages <= 20:
            task_id = self._submit_agent_task()
            self._wait_for_agent_completion(task_id)
            return self._download_agent_result(task_id)

        logger.info(f"{total_pages}页，超过Agent 20页限制，分块解析")
        return self._parse_in_chunks(total_pages)

    def _submit_agent_task(self) -> str:
        """提交Agent解析任务（签名上传模式）。"""
        api_url = f"{MINERU_AGENT_API}/parse/file"
        data = {
            "file_name": self._pdf_path.name,
            "language": self._config.language,
            "enable_table": self._config.enable_table,
            "is_ocr": self._config.is_ocr,
            "enable_formula": self._config.enable_formula,
        }
        if self._config.page_range:
            data["page_range"] = self._config.page_range

        for attempt in range(self._config.max_retries):
            try:
                resp = httpx.post(
                    api_url, json=data,
                    headers={"Content-Type": "application/json"},
                    timeout=self._config.timeout,
                )
                if resp.status_code == 200:
                    result = resp.json()
                    if result.get("code") == 0:
                        task_id = result["data"]["task_id"]
                        file_url = result["data"]["file_url"]
                        self._upload_to_signed_url(file_url)
                        logger.info(f"Agent任务已提交: {task_id}")
                        return task_id
                    raise RuntimeError(f"API错误: {result}")
                if resp.status_code == 429:
                    time.sleep(self._config.retry_delay * (2 ** attempt))
                    continue
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")
            except httpx.TimeoutException:
                if attempt < self._config.max_retries - 1:
                    continue
                raise RuntimeError("Agent API超时")

        raise RuntimeError("Agent API失败，已达最大重试次数")

    def _wait_for_agent_completion(self, task_id: str):
        """轮询Agent任务状态。"""
        poll_url = f"{MINERU_AGENT_API}/parse/{task_id}"
        start = time.time()

        while True:
            if time.time() - start > self._config.poll_timeout:
                raise RuntimeError(f"Agent轮询超时({self._config.poll_timeout}s)")

            try:
                resp = httpx.get(poll_url, timeout=self._config.timeout)
                if resp.status_code == 200:
                    result = resp.json()
                    if result.get("code") == 0:
                        state = result["data"]["state"]
                        if state == "done":
                            return
                        elif state == "failed":
                            raise RuntimeError(f"Agent解析失败: {result['data'].get('err_msg')}")
            except httpx.TimeoutException:
                pass

            time.sleep(self._config.poll_interval)

    def _download_agent_result(self, task_id: str) -> dict:
        """下载Agent解析结果（Markdown CDN链接）。"""
        poll_url = f"{MINERU_AGENT_API}/parse/{task_id}"
        resp = httpx.get(poll_url, timeout=self._config.timeout)
        if resp.status_code != 200:
            raise RuntimeError(f"获取结果失败: HTTP {resp.status_code}")

        result = resp.json()
        md_url = result["data"].get("markdown_url")
        if not md_url:
            raise RuntimeError("未获取到Markdown链接")

        md_resp = httpx.get(md_url, timeout=self._config.timeout)
        if md_resp.status_code != 200:
            raise RuntimeError(f"下载Markdown失败: HTTP {md_resp.status_code}")

        return {"markdown": md_resp.text, "content_list": []}

    def _parse_in_chunks(self, total_pages: int) -> dict:
        """分块解析大文件（仅Agent模式）。"""
        import fitz

        chunk_size = 20
        all_markdown = []
        temp_files = []

        try:
            doc = fitz.open(str(self._pdf_path))
            for start in range(0, total_pages, chunk_size):
                end = min(start + chunk_size, total_pages)

                chunk_doc = fitz.open()
                chunk_doc.insert_pdf(doc, from_page=start, to_page=end - 1)
                chunk_path = Path(f"/tmp/mineru_chunk_{start + 1}-{end}.pdf")
                chunk_doc.save(str(chunk_path))
                chunk_doc.close()
                temp_files.append(chunk_path)

                logger.info(f"解析分块 {start+1}-{end}...")
                task_id = self._submit_chunk_task(chunk_path)
                self._wait_for_agent_completion(task_id)
                result = self._download_agent_result(task_id)
                all_markdown.append(result.get("markdown", ""))

            doc.close()
            return {"markdown": "\n\n".join(all_markdown), "content_list": []}
        finally:
            for f in temp_files:
                try:
                    f.unlink(missing_ok=True)
                except Exception:
                    pass

    def _submit_chunk_task(self, chunk_path: Path) -> str:
        """提交分块解析任务。"""
        api_url = f"{MINERU_AGENT_API}/parse/file"
        data = {
            "file_name": chunk_path.name,
            "language": self._config.language,
            "enable_table": self._config.enable_table,
            "is_ocr": self._config.is_ocr,
            "enable_formula": self._config.enable_formula,
        }

        resp = httpx.post(
            api_url, json=data,
            headers={"Content-Type": "application/json"},
            timeout=self._config.timeout,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"提交分块失败: HTTP {resp.status_code}")

        result = resp.json()
        if result.get("code") != 0:
            raise RuntimeError(f"API错误: {result}")

        task_id = result["data"]["task_id"]
        file_url = result["data"]["file_url"]
        self._upload_to_signed_url(file_url)
        return task_id

    # ============ 索引构建（content_list.json 优先） ============

    def _build_from_content_list(self):
        """从 content_list.json 构建章节和表格索引。

        content_list.json item types: header, text, table, page_number, footer
        text item with text_level → 章节标题
        table item → 表格
        """
        section_idx = 0
        table_idx = 0

        for item in self._content_list:
            item_type = item.get("type")

            if item_type == "text" and item.get("text_level"):
                # 有 text_level 的 text 是标题
                level = item["text_level"]
                title = item.get("text", "").strip()
                if title:
                    ref = f"section_{section_idx}"
                    section = SectionSummary(
                        ref=ref,
                        title=title,
                        level=level,
                        parent_ref=None,
                        preview=title,
                        page_range=[item.get("page_idx", 0)],
                        internal_ref=None,
                    )
                    self._sections.append(section)
                    self._section_map[ref] = section
                    section_idx += 1

            elif item_type == "header":
                # header type 也是标题
                title = item.get("text", "").strip()
                level = item.get("text_level", 1)
                if title:
                    ref = f"section_{section_idx}"
                    section = SectionSummary(
                        ref=ref,
                        title=title,
                        level=level,
                        parent_ref=None,
                        preview=title,
                        page_range=[item.get("page_idx", 0)],
                        internal_ref=None,
                    )
                    self._sections.append(section)
                    self._section_map[ref] = section
                    section_idx += 1

            elif item_type == "table":
                ref = f"table_{table_idx}"
                table = TableSummary(
                    table_ref=ref,
                    caption=None,
                    context_before="",
                    row_count=0,  # content_list 不含行列数
                    col_count=0,
                    table_type="image",
                    headers=[],
                    section_ref=None,
                    page_no=item.get("page_idx"),
                    internal_ref=None,
                    is_financial=None,
                )
                self._tables.append(table)
                self._table_map[ref] = table
                table_idx += 1

        # 如果 content_list 没有标题，fallback 到 markdown 解析
        if not self._sections:
            self._build_sections_from_markdown()
        if not self._tables:
            self._build_tables_from_markdown()

    def _build_sections_from_markdown(self):
        """从Markdown构建章节索引（fallback）。"""
        if not self._markdown:
            return

        heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
        idx = 0
        for match in heading_pattern.finditer(self._markdown):
            level = len(match.group(1))
            title = match.group(2).strip()
            ref = f"section_{idx}"
            section = SectionSummary(
                ref=ref, title=title, level=level, parent_ref=None,
                preview=title, page_range=[], internal_ref=None,
            )
            self._sections.append(section)
            self._section_map[ref] = section
            idx += 1

    def _build_tables_from_markdown(self):
        """从Markdown构建表格索引（fallback）。"""
        if not self._markdown:
            return

        table_pattern = re.compile(r"(\|.+\|\n)+", re.MULTILINE)
        idx = 0
        for match in table_pattern.finditer(self._markdown):
            rows = match.group(0).strip().split("\n")
            if len(rows) < 2:
                continue
            headers = [c.strip() for c in rows[0].split("|") if c.strip()]
            if not headers:
                continue
            ref = f"table_{idx}"
            table = TableSummary(
                table_ref=ref, caption=None, context_before="",
                row_count=len(rows) - 2, col_count=len(headers),
                table_type="markdown", headers=headers,
                section_ref=None, page_no=None, internal_ref=None,
                is_financial=None,
            )
            self._tables.append(table)
            self._table_map[ref] = table
            idx += 1

    def _estimate_page_count(self):
        """估算页数。"""
        if self._content_list:
            pages = set()
            for item in self._content_list:
                p = item.get("page_idx")
                if p is not None:
                    pages.add(p)
            self._page_count = len(pages) if pages else max(1, len(self._markdown) // 2500)
        elif self._markdown:
            self._page_count = max(1, len(self._markdown) // 2500)

    # ============ DocumentStore 接口 ============

    def list_sections(self) -> list[SectionSummary]:
        return self._sections

    def list_tables(self) -> list[TableSummary]:
        return self._tables

    def read_section(self, ref: str) -> SectionContent:
        section = self._section_map.get(ref)
        if section is None:
            raise KeyError(f"章节不存在: {ref}")
        content = self._extract_section_content(section)
        return SectionContent(
            ref=ref, title=section.title, content=content,
            tables=[t.table_ref for t in self._tables],
            word_count=len(content.split()),
            contains_full_text=False,
            page_range=section.page_range, internal_ref=None,
        )

    def _extract_section_content(self, section: SectionSummary) -> str:
        """提取章节内容（从该标题到下一个同级标题）。"""
        pattern = re.compile(
            rf"^{'#' * section.level}\s+{re.escape(section.title)}$",
            re.MULTILINE,
        )
        match = pattern.search(self._markdown)
        if not match:
            return ""

        start = match.end()
        next_heading = re.compile(rf"^#{{{1},{section.level}}}\s+.+$", re.MULTILINE)
        next_match = next_heading.search(self._markdown, start)
        return self._markdown[start:next_match.start()].strip() if next_match else self._markdown[start:].strip()

    def read_table(self, table_ref: str) -> TableContent:
        table = self._table_map.get(table_ref)
        if table is None:
            raise KeyError(f"表格不存在: {table_ref}")
        data = self._extract_table_data(table)
        return TableContent(
            table_ref=table_ref, caption=table.caption,
            data_format="records", data=data, columns=table.headers,
            row_count=table.row_count, col_count=table.col_count,
            section_ref=table.section_ref, table_type=table.table_type,
            page_no=table.page_no, internal_ref=table.internal_ref,
        )

    def _extract_table_data(self, table: TableSummary) -> list[dict]:
        table_pattern = re.compile(r"(\|.+\|\n)+", re.MULTILINE)
        current_idx = 0
        for match in table_pattern.finditer(self._markdown):
            if current_idx == int(table.table_ref.split("_")[1]):
                rows = match.group(0).strip().split("\n")
                if len(rows) < 3:
                    return []
                headers = [c.strip() for c in rows[0].split("|") if c.strip()]
                data = []
                for row in rows[2:]:
                    cells = [c.strip() for c in row.split("|") if c.strip()]
                    if len(cells) == len(headers):
                        data.append(dict(zip(headers, cells)))
                return data
            current_idx += 1
        return []

    def search(self, query: str, within_ref: str | None = None) -> list[SearchHit]:
        hits = []
        if query.lower() in self._markdown.lower():
            idx = self._markdown.lower().find(query.lower())
            start = max(0, idx - 200)
            end = min(len(self._markdown), idx + len(query) + 200)
            hits.append(SearchHit(
                ref="document", title=self._pdf_path.stem,
                snippet=self._markdown[start:end], score=1.0,
                section_ref="document",
            ))
        return hits

    def get_section_title(self, ref: str) -> str | None:
        section = self._section_map.get(ref)
        return section.title if section else None

    @classmethod
    def supports(cls, source: Path) -> bool:
        return source.suffix.lower() in {".pdf", ".docx", ".pptx", ".xlsx", ".png", ".jpg", ".jpeg"}

    @classmethod
    def get_parser_version(cls) -> str:
        return cls.PARSER_VERSION


# ============ 工具函数 ============

def check_mineru_api_health(token: str | None = None) -> dict:
    """检查 MinerU API 健康状态。"""
    token = token or _load_token()
    result = {"agent_api": False, "precise_api": False, "has_token": bool(token), "error": None}

    try:
        resp = httpx.get(f"{MINERU_AGENT_API}/parse/test", timeout=10)
        result["agent_api"] = resp.status_code in (200, 404, 405)
    except Exception as e:
        result["error"] = f"Agent API不可达: {e}"

    if token:
        try:
            resp = httpx.get(
                f"{MINERU_PRECISE_API}/extract/task/test",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            result["precise_api"] = resp.status_code in (200, 401, 404)
        except Exception as e:
            result["error"] = f"精准API不可达: {e}"

    return result
