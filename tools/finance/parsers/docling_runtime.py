"""Docling运行时管理。

与Dayu的docling_runtime.py完全对齐。
所有接口命名与Dayu一致。

核心功能：
1. resolve_docling_device_name(): 解析设备名
2. _resolve_backend_class(): 映射backend到实现类
3. run_docling_pdf_conversion(): 执行PDF转换（含重试）
4. convert_pdf_bytes_with_docling(): 字节流形式调用Docling

设备配置：
- 环境变量：HERMES_DOCLING_DEVICE
- 支持值：auto/cpu/cuda
- 默认值：auto
"""

from __future__ import annotations

import logging
import os
from io import BytesIO

logger = logging.getLogger(__name__)

# ============ 常量 ============

DOCLING_DEVICE_ENV = "HERMES_DOCLING_DEVICE"
SUPPORTED_DEVICES = {"auto", "cpu", "cuda"}
SUPPORTED_BACKENDS = {"docling-parse", "pypdfium2"}


class DoclingRuntimeInitializationError(RuntimeError):
    """Docling运行时初始化错误。"""


def resolve_docling_device_name() -> str:
    """解析设备名。

    与Dayu的resolve_docling_device_name()签名一致。

    从环境变量HERMES_DOCLING_DEVICE读取设备配置，
    默认为"auto"。

    Returns:
        设备名（auto/cpu/cuda）。

    Raises:
        DoclingRuntimeInitializationError: 设备名不在支持列表时抛出。
    """
    configured = os.environ.get(DOCLING_DEVICE_ENV, "").strip()
    if configured:
        if configured not in SUPPORTED_DEVICES:
            supported = ", ".join(sorted(SUPPORTED_DEVICES))
            raise DoclingRuntimeInitializationError(
                f"{DOCLING_DEVICE_ENV} 不支持 {configured!r}；"
                f"允许值: {supported}"
            )
        return configured
    return "auto"


def _resolve_backend_class(backend_name: str):
    """映射backend到实现类。

    与Dayu的_resolve_backend_class()签名一致。

    Args:
        backend_name: backend名称（docling-parse/pypdfium2）。

    Returns:
        backend实现类。

    Raises:
        ValueError: backend名称不在支持列表时抛出。
        DoclingRuntimeInitializationError: Docling未安装时抛出。
    """
    if backend_name not in SUPPORTED_BACKENDS:
        supported = ", ".join(sorted(SUPPORTED_BACKENDS))
        raise ValueError(
            f"不支持的 Docling backend {backend_name!r}；"
            f"允许值: {supported}"
        )

    try:
        if backend_name == "docling-parse":
            from docling.backend.docling_parse_backend import DoclingParseDocumentBackend
            return DoclingParseDocumentBackend
        else:
            from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
            return PyPdfiumDocumentBackend
    except ImportError as exc:
        raise DoclingRuntimeInitializationError(
            f"Docling 未安装，无法解析 backend {backend_name!r}"
        ) from exc


def build_docling_pdf_converter(
    *,
    do_ocr: bool = True,
    do_table_structure: bool = True,
    backend_name: str = "docling-parse",
):
    """构造带稳定设备与backend策略的Docling PDF转换器。

    Args:
        do_ocr: 是否开启OCR（docling 2.92+自动处理，此参数保留兼容）。
        do_table_structure: 是否开启表格结构识别（docling 2.92+自动处理）。
        backend_name: PDF backend名（docling-parse/pypdfium2）。

    Returns:
        配置完成的Docling DocumentConverter。

    Raises:
        DoclingRuntimeInitializationError: Docling依赖未安装或配置非法时抛出。
    """
    try:
        from docling.document_converter import DocumentConverter
    except ImportError as exc:
        raise DoclingRuntimeInitializationError(
            "Docling 未安装，无法构造 PDF 转换器"
        ) from exc

    # docling 2.92+ 使用简化的 DocumentConverter 构造
    # OCR 和表格结构识别由内部 pipeline 自动处理
    return DocumentConverter()


def run_docling_pdf_conversion(
    pdf_path: str,
    *,
    do_ocr: bool = True,
    do_table_structure: bool = True,
    max_retries: int = 2,
):
    """执行PDF转换，支持重试。

    与Dayu的run_docling_pdf_conversion()签名一致。

    Args:
        pdf_path: PDF文件路径。
        do_ocr: 是否启用OCR。
        do_table_structure: 是否启用表格结构识别。
        max_retries: 最大重试次数。

    Returns:
        Docling转换结果。

    Raises:
        DoclingRuntimeInitializationError: Docling未安装或转换失败时抛出。
    """
    last_exc = None

    for attempt in range(max_retries):
        try:
            converter = build_docling_pdf_converter(
                do_ocr=do_ocr,
                do_table_structure=do_table_structure,
            )
            result = converter.convert(pdf_path)
            return result
        except DoclingRuntimeInitializationError:
            raise
        except Exception as exc:
            last_exc = exc
            logger.warning(f"PDF转换失败 (attempt {attempt + 1}): {exc}")

    raise DoclingRuntimeInitializationError(
        f"PDF转换失败: {last_exc}"
    ) from last_exc


def convert_pdf_bytes_with_docling(
    pdf_bytes: bytes,
    *,
    stream_name: str = "document.pdf",
    do_ocr: bool = True,
    do_table_structure: bool = True,
    max_retries: int = 2,
):
    """字节流形式调用Docling。

    与Dayu的convert_pdf_bytes_with_docling()签名一致。

    以字节流形式调用Docling，规避Windows非ASCII路径编码问题。

    Args:
        pdf_bytes: PDF原始字节内容。
        stream_name: 流名称，建议直接传文件名以保留扩展名。
        do_ocr: 是否启用OCR。
        do_table_structure: 是否启用表格结构识别。
        max_retries: 最大重试次数。

    Returns:
        Docling转换结果。

    Raises:
        DoclingRuntimeInitializationError: Docling未安装或转换失败时抛出。
    """
    try:
        from docling.datamodel.base_models import DocumentStream
    except ImportError as exc:
        raise DoclingRuntimeInitializationError(
            "Docling 未安装，无法构造 DocumentStream"
        ) from exc

    last_exc = None

    for attempt in range(max_retries):
        try:
            # 构造字节流
            stream = DocumentStream(name=stream_name, stream=BytesIO(pdf_bytes))

            # 构造转换器
            converter = build_docling_pdf_converter(
                do_ocr=do_ocr,
                do_table_structure=do_table_structure,
            )

            # 执行转换
            result = converter.convert(stream)
            return result
        except DoclingRuntimeInitializationError:
            raise
        except Exception as exc:
            last_exc = exc
            logger.warning(f"PDF字节流转换失败 (attempt {attempt + 1}): {exc}")

    raise DoclingRuntimeInitializationError(
        f"PDF字节流转换失败: {last_exc}"
    ) from last_exc
