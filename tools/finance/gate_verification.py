"""
Gate Verification - Gate 验证工具

提供真实执行验证功能，确保代码不仅存在，而且可执行。
"""

import importlib
import logging
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)


class GateVerificationError(Exception):
    """Gate 验证失败异常"""


def verify_import(module_path: str, class_name: str) -> bool:
    """验证模块是否可导入

    Args:
        module_path: 模块路径（如 finance.downloaders.hkexnews_downloader）
        class_name: 类名（如 HKEXNewsDownloader）

    Returns:
        是否可导入

    Raises:
        GateVerificationError: 导入失败时抛出
    """
    try:
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        logger.info(f"✅ 可导入: {module_path}.{class_name}")
        return True
    except ImportError as e:
        raise GateVerificationError(f"无法导入 {module_path}: {e}")
    except AttributeError as e:
        raise GateVerificationError(f"模块 {module_path} 中不存在 {class_name}: {e}")


def verify_callable(func: Callable, *args, **kwargs) -> bool:
    """验证函数是否可调用

    Args:
        func: 函数
        *args: 位置参数
        **kwargs: 关键字参数

    Returns:
        是否可调用

    Raises:
        GateVerificationError: 调用失败时抛出
    """
    try:
        result = func(*args, **kwargs)
        logger.info(f"✅ 可调用: {func.__name__}")
        return True
    except Exception as e:
        raise GateVerificationError(f"函数 {func.__name__} 调用失败: {e}")


def verify_file_content(file_path: str, required_patterns: list[str]) -> bool:
    """验证文件是否包含必需的内容

    Args:
        file_path: 文件路径
        required_patterns: 必需的模式列表（如 ["class XXX", "def yyy"]）

    Returns:
        是否包含所有必需内容

    Raises:
        GateVerificationError: 缺少必需内容时抛出
    """
    path = Path(file_path)
    if not path.exists():
        raise GateVerificationError(f"文件不存在: {file_path}")

    content = path.read_text()
    missing = []
    for pattern in required_patterns:
        if pattern not in content:
            missing.append(pattern)

    if missing:
        raise GateVerificationError(f"文件 {file_path} 缺少必需内容: {missing}")

    logger.info(f"✅ 文件内容验证通过: {file_path}")
    return True


def verify_real_execution(
    test_func: Callable,
    expected_success: bool = True,
    error_check: Callable | None = None,
) -> bool:
    """验证真实执行

    Args:
        test_func: 测试函数
        expected_success: 是否期望成功
        error_check: 错误检查函数（可选）

    Returns:
        是否符合预期

    Raises:
        GateVerificationError: 执行结果不符合预期时抛出
    """
    try:
        result = test_func()
        if expected_success:
            logger.info(f"✅ 真实执行成功: {test_func.__name__}")
            return True
        else:
            raise GateVerificationError(f"期望失败但成功了: {test_func.__name__}")
    except Exception as e:
        if not expected_success:
            if error_check and not error_check(e):
                raise GateVerificationError(f"错误类型不符合预期: {type(e).__name__}")
            logger.info(f"✅ 真实执行失败（符合预期）: {test_func.__name__}")
            return True
        else:
            raise GateVerificationError(f"真实执行失败: {test_func.__name__}: {e}")


def run_gate_verification(gate_name: str, verifications: list[tuple[str, Callable]]) -> dict:
    """运行 Gate 验证

    Args:
        gate_name: Gate 名称
        verifications: 验证列表 [(验证名, 验证函数), ...]

    Returns:
        验证结果字典
    """
    results = {
        "gate": gate_name,
        "passed": True,
        "verifications": [],
        "errors": []
    }

    for name, verify_func in verifications:
        try:
            verify_func()
            results["verifications"].append({"name": name, "status": "passed"})
        except GateVerificationError as e:
            results["passed"] = False
            results["verifications"].append({"name": name, "status": "failed", "error": str(e)})
            results["errors"].append(f"{name}: {e}")
        except Exception as e:
            results["passed"] = False
            results["verifications"].append({"name": name, "status": "error", "error": str(e)})
            results["errors"].append(f"{name}: unexpected error: {e}")

    if results["passed"]:
        logger.info(f"✅ Gate {gate_name} 验证通过")
    else:
        logger.error(f"❌ Gate {gate_name} 验证失败: {results['errors']}")

    return results
