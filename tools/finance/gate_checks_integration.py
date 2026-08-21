"""
Gate Checks 集成模块

将Gate Checks集成到qual-analysis工作流中

集成点：Step 4.5（质量增强）之后、Step 5（决策章和概览章）之前

使用方式：
    from finance.gate_checks_integration import run_gate_checks_in_workflow

    gate_report = run_gate_checks_in_workflow(wind_data, chapters, dcf_params)
"""

import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 添加Gate Checks模块路径
gate_checks_path = Path(__file__).parent.parent.parent / "projects" / "gate-checks" / "src"
if gate_checks_path.exists():
    sys.path.insert(0, str(gate_checks_path))

try:
    from gate_checks import run_all_gate_checks, save_gate_checks_report
    HAS_GATE_CHECKS = True
except ImportError:
    HAS_GATE_CHECKS = False
    logger.warning("Gate Checks模块未找到，跳过Gate Checks")


def run_gate_checks_in_workflow(
    wind_data: Any,
    chapters: dict[int, dict[str, Any]],
    dcf_params: dict[str, Any] | None = None,
    output_dir: str | None = None,
    ticker: str = "unknown"
) -> dict[str, Any] | None:
    """
    在工作流中执行Gate Checks

    Args:
        wind_data: Wind数据（DataContext.wind对象）
        chapters: 章节字典 {0: {...}, 1: {...}, ..., 10: {...}}
        dcf_params: DCF参数（可选）
        output_dir: 输出目录（可选）
        ticker: 股票代码

    Returns:
        dict: Gate Checks报告，如果Gate Checks未启用则返回None
    """
    if not HAS_GATE_CHECKS:
        logger.warning("Gate Checks未启用，跳过检查")
        return None

    # 转换wind_data为字典格式
    wind_dict = _convert_wind_data_to_dict(wind_data)

    # 转换chapters为列表格式
    chapters_list = _convert_chapters_to_list(chapters)

    # 执行Gate Checks
    logger.info("执行Gate Checks...")
    gate_report = run_all_gate_checks(wind_dict, chapters_list, dcf_params)

    # 保存Gate Checks报告
    if output_dir:
        output_path = Path(output_dir) / f"{ticker}_gate_checks_report.json"
        save_gate_checks_report(gate_report, str(output_path))
        logger.info(f"Gate Checks报告已保存: {output_path}")

    # 检查是否阻断
    summary = gate_report["gate_checks_report"]["summary"]
    if summary["overall_status"] == "BLOCK":
        fatal_issues = summary["blocking_issues"]
        logger.error(f"Gate Checks阻断: {fatal_issues}")
        raise GateChecksBlockedError(f"Gate Checks阻断: {fatal_issues}")

    if summary["warn"] > 0:
        warnings = summary["warnings_requiring_explanation"]
        logger.warning(f"Gate Checks警告（需人工解释）: {warnings}")

    logger.info(f"Gate Checks通过: {summary['total_checks']}项检查, {summary['passed']}项通过")
    return gate_report


def _convert_wind_data_to_dict(wind_data: Any) -> dict[str, Any]:
    """
    将WindData对象转换为字典格式
    """
    if wind_data is None:
        return {}

    if isinstance(wind_data, dict):
        return wind_data

    # 如果是DataContext.wind对象，转换为字典
    if hasattr(wind_data, '__dict__'):
        wind_dict = {}
        for key, value in wind_data.__dict__.items():
            if key.startswith('_'):
                # 内部属性（如_year_labels）
                wind_dict[key] = value
            elif hasattr(value, '__dict__'):
                # 嵌套对象（如income, balance, cashflow）
                wind_dict[key] = value.__dict__
            else:
                wind_dict[key] = value
        return wind_dict

    return {}


def _convert_chapters_to_list(chapters) -> list[dict[str, Any]]:
    """
    将章节字典转换为列表格式

    支持两种格式:
    - Dict[int, str]: 章节内容是字符串
    - Dict[int, Dict[str, Any]]: 章节内容是字典
    """
    chapters_list = []
    for i in range(11):  # ch00-ch10
        if i in chapters:
            chapter = chapters[i]
            if isinstance(chapter, str):
                # 章节内容是字符串，包装为字典
                chapter_with_id = {
                    "chapter_id": f"ch{i:02d}",
                    "content": chapter,
                }
            elif isinstance(chapter, dict):
                # 章节内容是字典，添加chapter_id字段
                chapter_with_id = {
                    "chapter_id": f"ch{i:02d}",
                    **chapter
                }
            else:
                # 其他类型，跳过
                continue
            chapters_list.append(chapter_with_id)
        else:
            # 章节缺失
            chapters_list.append({
                "chapter_id": f"ch{i:02d}",
                "content": "",
                "missing": True
            })

    return chapters_list


class GateChecksBlockedError(Exception):
    """Gate Checks阻断异常"""
