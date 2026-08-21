"""
data_repair.py — Layer 1: 数据修复模块

功能：
1. PE实时校验：调用Wind估值API，与报告PE交叉校验
2. 来源标注模板化：从fact_extractor的fiscal_year自动生成
3. 数据一致性审计：跨章节同一指标数值必须一致
4. AI痕迹清洗：正则+Prompt约束
"""

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ====================================================================
# 数据结构
# ====================================================================

@dataclass
class PEReport:
    """PE校验报告"""
    report_pe: float | None          # 报告中的PE值
    wind_pe: float | None            # Wind实时PE
    deviation: float | None          # 偏差百分比
    is_valid: bool                      # 是否通过校验
    warning: str | None = None       # 警告信息


@dataclass
class ConsistencyIssue:
    """数据一致性问题"""
    metric: str                         # 指标名称
    chapter1: int                       # 章节1
    value1: float                       # 章节1的值
    chapter2: int                       # 章节2
    value2: float                       # 章节2的值
    severity: str                       # P0/P1/P2


@dataclass
class RepairResult:
    """修复结果"""
    pe_report: PEReport | None = None
    consistency_issues: list[ConsistencyIssue] = field(default_factory=list)
    source_fixes: int = 0               # 来源标注修复数量
    ai_trace_fixes: int = 0             # AI痕迹修复数量
    warnings: list[str] = field(default_factory=list)


# ====================================================================
# Gate 1.1: PE实时校验
# ====================================================================

def validate_pe_against_wind(
    report_content: str,
    wind_valuation: dict,
    tolerance: float = 0.15,
) -> PEReport:
    """
    PE实时校验：从报告中提取PE值，与Wind估值API交叉校验。

    Args:
        report_content: 报告全文
        wind_valuation: Wind MCP valuation API 返回的数据
        tolerance: 允许偏差（默认15%）

    Returns:
        PEReport 校验结果
    """
    # 1. 从报告中提取PE值
    report_pe = _extract_pe_from_report(report_content)

    # 2. 从Wind数据中获取PE
    wind_pe = None
    if wind_valuation and isinstance(wind_valuation, dict):
        # Wind valuation API 返回格式：{"pe_ttm": 21.3, "pb": 3.2, ...}
        wind_pe = wind_valuation.get('pe_ttm') or wind_valuation.get('pe')

    # 3. 校验
    if report_pe is None:
        return PEReport(
            report_pe=None,
            wind_pe=wind_pe,
            deviation=None,
            is_valid=True,  # 报告中没有PE值，不校验
            warning="报告中未找到PE值，无法校验",
        )

    if wind_pe is None:
        return PEReport(
            report_pe=report_pe,
            wind_pe=None,
            deviation=None,
            is_valid=True,  # Wind数据不可用，不校验
            warning="Wind估值数据不可用，无法校验",
        )

    # 4. 计算偏差
    deviation = abs(report_pe - wind_pe) / wind_pe
    is_valid = deviation <= tolerance

    warning = None
    if not is_valid:
        warning = (
            f"PE校验失败：报告PE={report_pe:.1f}x，Wind PE={wind_pe:.1f}x，"
            f"偏差={deviation:.1%}（超过{tolerance:.0%}阈值）"
        )
        logger.error(warning)
    elif deviation > 0.05:
        warning = (
            f"PE偏差较大：报告PE={report_pe:.1f}x，Wind PE={wind_pe:.1f}x，"
            f"偏差={deviation:.1%}"
        )
        logger.warning(warning)

    return PEReport(
        report_pe=report_pe,
        wind_pe=wind_pe,
        deviation=deviation,
        is_valid=is_valid,
        warning=warning,
    )


def _extract_pe_from_report(content: str) -> float | None:
    """从报告中提取PE值"""
    # 匹配模式：PE 12-15倍、PE约为21x、市盈率12-15倍、PE(TTM) 21x
    patterns = [
        r'PE[^\d]{0,10}(\d+\.?\d*)\s*[-~]\s*(\d+\.?\d*)\s*倍',
        r'PE[^\d]{0,10}(\d+\.?\d*)\s*倍',
        r'PE[^\d]{0,10}(\d+\.?\d*)\s*[xX]',
        r'市盈率[^\d]{0,10}(\d+\.?\d*)\s*[-~]\s*(\d+\.?\d*)',
        r'市盈率[^\d]{0,10}(\d+\.?\d*)\s*[倍xX]',
        r'PE\(TTM\)[^\d]{0,10}(\d+\.?\d*)',
        r'约为[^\d]{0,5}(\d+\.?\d*)\s*倍',
    ]

    for pattern in patterns:
        match = re.search(pattern, content)
        if match:
            groups = match.groups()
            if len(groups) == 2:
                # 范围值，取中间值
                return (float(groups[0]) + float(groups[1])) / 2
            elif len(groups) == 1:
                return float(groups[0])

    return None


def fix_pe_in_report(
    report_content: str,
    wind_pe: float,
) -> str:
    """
    修复报告中的PE值，保持原文格式。

    Args:
        report_content: 报告原文
        wind_pe: Wind实时PE

    Returns:
        修复后的报告内容
    """
    pe_str = f'{wind_pe:.1f}'
    fixes = 0
    fixed_content = report_content

    # 匹配范围值 "12-15倍" → "约21倍"
    pattern = r'(PE[^\d]{0,10})\d+\.?\d*\s*[-~]\s*\d+\.?\d*\s*倍'
    if re.search(pattern, fixed_content):
        fixed_content = re.sub(pattern, f'\\g<1>约{pe_str}倍', fixed_content)
        fixes += 1

    # 匹配单值 "21x" → "21.3x"
    pattern = r'(PE[^\d]{0,10})\d+\.?\d*\s*x'
    if re.search(pattern, fixed_content):
        fixed_content = re.sub(pattern, f'\\g<1>{pe_str}x', fixed_content)
        fixes += 1

    # 匹配单值 "21倍" → "21.3倍"
    pattern = r'(PE[^\d]{0,10})\d+\.?\d*\s*倍'
    if re.search(pattern, fixed_content):
        fixed_content = re.sub(pattern, f'\\g<1>{pe_str}倍', fixed_content)
        fixes += 1

    # 匹配市盈率范围 "12-15" → "约21"
    pattern = r'(市盈率[^\d]{0,10})\d+\.?\d*\s*[-~]\s*\d+\.?\d*'
    if re.search(pattern, fixed_content):
        fixed_content = re.sub(pattern, f'\\g<1>约{pe_str}', fixed_content)
        fixes += 1

    # 匹配表格中的PE值 "12-15x" → "约21x"
    pattern = r'(\|\s*[^|]*PE[^|]*\|\s*)\d+\.?\d*\s*[-~]\s*\d+\.?\d*\s*x'
    if re.search(pattern, fixed_content):
        fixed_content = re.sub(pattern, f'\\g<1>约{pe_str}x', fixed_content)
        fixes += 1

    if fixes > 0:
        logger.info(f"PE修复完成：{fixes}处替换为约{pe_str}倍/x")

    return fixed_content


# ====================================================================
# Gate 1.2: 来源标注模板化
# ====================================================================

def fix_source_annotations(
    report_content: str,
    fiscal_year: int = 2025,
) -> tuple[str, int]:
    """
    修复数据来源标注，确保年份正确（B2b-3：canonicalize——动态识别非目标财年，任意公司名通用）。

    Args:
        report_content: 报告原文
        fiscal_year: 正确的财年

    Returns:
        (修复后的报告内容, 修复数量)
    """
    # B2b-3：wrong_years 动态化（canonicalize——非目标财年的附近 20XX 年份，删硬编码 [2023,2024,2026]）
    # 范围 ±5 年（覆盖历史年报引用与手误未来年份），排除目标财年
    wrong_years = [y for y in range(fiscal_year - 5, fiscal_year + 6) if y != fiscal_year]
    fixes = 0

    fixed_content = report_content
    for wrong_year in wrong_years:
        if wrong_year == fiscal_year:
            continue

        # 替换 "来源：XXXX年年报" 中的年份（通用：任何 20XX 非目标财年）
        pattern = f'(来源[：:][^\\n]{{0,20}}){wrong_year}(年)'
        replacement = f'\\g<1>{fiscal_year}\\g<2>'
        new_content = re.sub(pattern, replacement, fixed_content)
        if new_content != fixed_content:
            count = len(re.findall(pattern, fixed_content))
            fixes += count
            fixed_content = new_content

        # 替换不带"来源："前缀的 "公司名XXXX年年报"（B2b-3：删公司名硬编码，通用匹配）
        pattern2 = f'([^0-9\\n]{{1,15}}){wrong_year}(年年报)'
        replacement2 = f'\\g<1>{fiscal_year}\\g<2>'
        new_content2 = re.sub(pattern2, replacement2, fixed_content)
        if new_content2 != fixed_content:
            count2 = len(re.findall(pattern2, fixed_content))
            fixes += count2
            fixed_content = new_content2

    # 替换 "财报原文摘要" 为规范格式
    pattern = r'\[来源:\s*财报原文摘要\s*\]'
    replacement = f'[来源: FY{fiscal_year} 年报]'
    new_content = re.sub(pattern, replacement, fixed_content)
    if new_content != fixed_content:
        count = len(re.findall(pattern, fixed_content))
        fixes += count
        fixed_content = new_content

    return fixed_content, fixes


# ====================================================================
# Gate 1.3: 数据一致性审计
# ====================================================================

# 需要检查一致性的关键指标（更精确的模式）
CONSISTENCY_METRICS = {
    '经营现金流': {
        'pattern': r'经营(?:活动)?(?:产生的)?(?:现金流量|现金流)[^\d]{0,10}(\d+\.?\d*)\s*亿',
        'exclude_keywords': ['行业', '市场', '对比', '比较', '通常', '一般', '平均'],
    },
    '净利润': {
        'pattern': r'(?:经调整)?净利润[^\d]{0,10}(\d+\.?\d*)\s*亿',
        'exclude_keywords': ['行业', '市场', '对比', '可比', '通常', '一般'],
    },
    '营业收入': {
        'pattern': r'(?:营业|总)收入[^\d]{0,10}(\d+\.?\d*)\s*亿',
        'exclude_keywords': ['行业', '市场', '对比', '可比'],
    },
    '毛利率': {
        'pattern': r'毛利率[^\d]{0,10}(\d+\.?\d*)\s*%',
        'exclude_keywords': ['行业', '市场', '对比', '可比', '通常', '一般', '平均', '范围', '区间'],
    },
}


def _is_valid_metric_context(content: str, match_pos: int, exclude_keywords: list[str]) -> bool:
    """检查匹配位置的上下文是否为公司数据（排除行业/对比数据）"""
    # 取匹配位置前50个字符作为上下文
    start = max(0, match_pos - 50)
    context = content[start:match_pos].lower()
    for kw in exclude_keywords:
        if kw in context:
            return False
    return True


def check_cross_chapter_consistency(
    chapters: dict[int, str],
) -> list[ConsistencyIssue]:
    """
    跨章节数据一致性审计（上下文感知版本）。

    Args:
        chapters: {章节号: 章节内容}

    Returns:
        一致性问题列表
    """
    issues = []

    for metric_name, metric_config in CONSISTENCY_METRICS.items():
        pattern = metric_config['pattern']
        exclude_keywords = metric_config['exclude_keywords']

        # 收集每个章节中该指标的值
        values = {}
        for ch_num, content in chapters.items():
            for match in re.finditer(pattern, content):
                # 检查上下文是否为公司数据
                if _is_valid_metric_context(content, match.start(), exclude_keywords):
                    val = float(match.group(1))
                    # 约数检查：如果数字是整数（如"4亿"vs"4.102亿"），跳过
                    if val == int(val) and '.' not in match.group(1):
                        continue  # 跳过约数
                    values[ch_num] = val
                    break  # 每章只取第一个有效匹配

        # 检查是否有冲突（需要至少2个不同的精确值）
        if len(values) >= 2:
            unique_values = set(values.values())
            if len(unique_values) > 1:
                # 检查是否是近似值（偏差<5%视为一致）
                val_list = sorted(unique_values)
                max_val = max(val_list)
                min_val = min(val_list)
                if max_val > 0 and (max_val - min_val) / max_val > 0.05:
                    # 真实冲突
                    ch_list = sorted(values.items())
                    for i in range(len(ch_list)):
                        for j in range(i + 1, len(ch_list)):
                            ch1, val1 = ch_list[i]
                            ch2, val2 = ch_list[j]
                            if abs(val1 - val2) / max(val1, val2) > 0.05:
                                issues.append(ConsistencyIssue(
                                    metric=metric_name,
                                    chapter1=ch1,
                                    value1=val1,
                                    chapter2=ch2,
                                    value2=val2,
                                    severity='P0' if metric_name in ['经营现金流', '净利润'] else 'P1',
                                ))

    return issues


def fix_consistency_issues(
    chapters: dict[int, str],
    issues: list[ConsistencyIssue],
    correct_values: dict[str, float],
) -> dict[int, str]:
    """
    修复数据一致性问题。

    Args:
        chapters: {章节号: 章节内容}
        issues: 一致性问题列表
        correct_values: {指标名: 正确值}（通常来自Wind数据）

    Returns:
        修复后的章节内容
    """
    fixed_chapters = dict(chapters)

    for issue in issues:
        if issue.metric not in correct_values:
            logger.warning(f"无法修复 {issue.metric}：缺少正确值")
            continue

        correct_val = correct_values[issue.metric]

        # 替换所有章节中的错误值
        for ch_num in [issue.chapter1, issue.chapter2]:
            content = fixed_chapters[ch_num]
            wrong_val = issue.value1 if ch_num == issue.chapter1 else issue.value2

            if wrong_val != correct_val:
                # 精确替换数值
                pattern = re.escape(str(wrong_val))  # noqa: F841
                new_content = content.replace(str(wrong_val), str(correct_val), 1)
                if new_content != content:
                    fixed_chapters[ch_num] = new_content
                    logger.info(
                        f"一致性修复：第{ch_num}章 {issue.metric} "
                        f"{wrong_val}→{correct_val}"
                    )

    return fixed_chapters


# ====================================================================
# Gate 1.4: AI痕迹清洗
# ====================================================================

# AI痕迹模式列表
AI_TRACE_PATTERNS = [
    # 自我介绍体
    (r'好的，作为您的[^。\n]{0,50}[。，]', ''),
    (r'作为[^。\n]{0,20}分析师，我将[^。\n]{0,30}[。，]', ''),
    (r'我将基于您提供的信息[^。\n]{0,30}[。，]', ''),

    # 过度使用加粗（连续3个以上加粗）
    (r'(\*\*[^*]{2,20}\*\*[，,、]?\s*){4,}', lambda m: m.group(0).replace('**', '')),

    # 模板化过渡语
    (r'综上所述[，,]', '总结：'),
    (r'值得注意的是[，,]', ''),
    (r'需要特别指出的是[，,]', ''),
    (r'不难看出[，,]', ''),
    (r'显而易见[，,]', ''),
    (r'众所周知[，,]', ''),
]


def clean_ai_traces(content: str) -> tuple[str, int]:
    """
    清洗AI痕迹。

    Args:
        content: 报告内容

    Returns:
        (清洗后的内容, 修复数量)
    """
    fixes = 0
    cleaned = content

    for pattern, replacement in AI_TRACE_PATTERNS:
        if callable(replacement):
            new_content = re.sub(pattern, replacement, cleaned)
        else:
            new_content = re.sub(pattern, replacement, cleaned)

        if new_content != cleaned:
            count = len(re.findall(pattern, cleaned))
            fixes += count
            cleaned = new_content

    # 清理多余的空行
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)

    return cleaned, fixes


# ====================================================================
# 主修复流程
# ====================================================================

def repair_report(
    chapters: dict[int, str],
    wind_valuation: dict | None = None,
    wind_financials: dict | None = None,
    fiscal_year: int = 2025,
) -> tuple[dict[int, str], RepairResult]:
    """
    执行完整的数据修复流程（带错误处理和回滚）。

    Args:
        chapters: {章节号: 章节内容}
        wind_valuation: Wind估值数据
        wind_financials: Wind财务数据
        fiscal_year: 目标财年

    Returns:
        (修复后的章节, 修复结果报告)
    """
    result = RepairResult()
    original_chapters = dict(chapters)  # 备份用于回滚  # noqa: F841

    try:
        # === Step 1: PE实时校验 ===
        if wind_valuation:
            full_content = '\n\n'.join(chapters.values())
            pe_report = validate_pe_against_wind(full_content, wind_valuation)
            result.pe_report = pe_report

            if not pe_report.is_valid and pe_report.wind_pe:
                try:
                    fixed_chapters = {}
                    for ch_num, content in chapters.items():
                        fixed_content = fix_pe_in_report(content, pe_report.wind_pe)
                        fixed_chapters[ch_num] = fixed_content
                    chapters = fixed_chapters
                    logger.info(f"PE自动修复完成：→约{pe_report.wind_pe:.1f}倍")
                except Exception as e:
                    logger.warning(f"PE修复失败，保留原始值: {e}")

    except Exception as e:
        logger.error(f"PE校验异常: {e}")
        result.warnings.append(f"PE校验异常: {e}")

    try:
        # === Step 2: 来源标注模板化 ===
        total_source_fixes = 0
        fixed_chapters = {}
        for ch_num, content in chapters.items():
            try:
                fixed_content, fixes = fix_source_annotations(content, fiscal_year)
                total_source_fixes += fixes
                fixed_chapters[ch_num] = fixed_content
            except Exception as e:
                logger.warning(f"第{ch_num}章来源标注修复失败: {e}")
                fixed_chapters[ch_num] = content
        chapters = fixed_chapters
        result.source_fixes = total_source_fixes
    except Exception as e:
        logger.error(f"来源标注修复异常: {e}")
        result.warnings.append(f"来源标注修复异常: {e}")

    try:
        # === Step 3: 数据一致性审计 ===
        consistency_issues = check_cross_chapter_consistency(chapters)
        result.consistency_issues = consistency_issues

        if consistency_issues and wind_financials:
            correct_values = _build_correct_values(wind_financials)
            if correct_values:
                chapters = fix_consistency_issues(chapters, consistency_issues, correct_values)
    except Exception as e:
        logger.error(f"一致性审计异常: {e}")
        result.warnings.append(f"一致性审计异常: {e}")

    try:
        # === Step 4: AI痕迹清洗 ===
        total_ai_fixes = 0
        fixed_chapters = {}
        for ch_num, content in chapters.items():
            try:
                cleaned, fixes = clean_ai_traces(content)
                total_ai_fixes += fixes
                fixed_chapters[ch_num] = cleaned
            except Exception as e:
                logger.warning(f"第{ch_num}章AI痕迹清洗失败: {e}")
                fixed_chapters[ch_num] = content
        chapters = fixed_chapters
        result.ai_trace_fixes = total_ai_fixes
    except Exception as e:
        logger.error(f"AI痕迹清洗异常: {e}")
        result.warnings.append(f"AI痕迹清洗异常: {e}")

    # 汇总
    if result.pe_report and result.pe_report.warning:
        result.warnings.append(result.pe_report.warning)
    for issue in result.consistency_issues:
        result.warnings.append(
            f"{issue.severity} {issue.metric}冲突：第{issue.chapter1}章={issue.value1} vs 第{issue.chapter2}章={issue.value2}"
        )

    logger.info(
        f"数据修复完成：PE校验={'通过' if not result.pe_report or result.pe_report.is_valid else '失败'}，"
        f"来源标注修复={result.source_fixes}处，"
        f"一致性问题={len(result.consistency_issues)}个，"
        f"AI痕迹修复={result.ai_trace_fixes}处"
    )

    return chapters, result


def _build_correct_values(wind_financials: dict) -> dict[str, float]:
    """从Wind数据构建正确值映射

    支持多种字段名格式（兼容不同Wind API返回）
    """
    correct_values = {}
    income = wind_financials.get('income', {})

    # 净利润：支持多种字段名
    for key in ['年净利润', '净利润', '归母净利润']:
        if key in income:
            vals = income[key]
            if isinstance(vals, list) and vals:
                correct_values['净利润'] = vals[-1]
                break

    # 营业收入：支持多种字段名（年营业总收入/年营业收入）
    for key in ['年营业总收入', '年营业收入', '营业收入', '总收入']:
        if key in income:
            vals = income[key]
            if isinstance(vals, list) and vals:
                correct_values['营业收入'] = vals[-1]
                break

    # 毛利率：优先从Wind数据直接获取，否则从收入和成本计算
    # 根据HeavySkill审查要求：仅保留从营业成本直接计算，禁止使用估算值
    for key in ['年毛利率', '毛利率']:
        if key in income:
            vals = income[key]
            if isinstance(vals, list) and vals:
                correct_values['毛利率'] = vals[-1]
                break

    # 如果没有直接毛利率，尝试从毛利计算
    if '毛利率' not in correct_values:
        revenue = correct_values.get('营业收入')
        for key in ['年毛利', '毛利润']:
            if key in income:
                vals = income[key]
                if isinstance(vals, list) and vals and revenue:
                    gross_profit = vals[-1]
                    if revenue > 0:
                        correct_values['毛利率'] = round(gross_profit / revenue * 100, 1)
                    break

    # 如果仍然没有毛利率，尝试从营业成本计算（毛利率 = (营业收入-营业成本)/营业收入）
    if '毛利率' not in correct_values:
        revenue = correct_values.get('营业收入')
        for key in ['年营业成本', '营业成本']:
            if key in income:
                vals = income[key]
                if isinstance(vals, list) and vals and revenue:
                    cost = vals[-1]
                    if revenue > 0:
                        correct_values['毛利率'] = round((revenue - cost) / revenue * 100, 1)
                        logger.info(f"毛利率从营业成本计算: ({revenue}-{cost})/{revenue}={correct_values['毛利率']}%")
                    break

    # 如果仍然没有毛利率，标记为数据缺失（禁止使用估算值）
    if '毛利率' not in correct_values:
        logger.warning("毛利率数据缺失：Wind无直接数据，无毛利数据，无营业成本数据")
        correct_values['毛利率'] = None  # 标记为None，下游需要处理
        correct_values['毛利率_缺失'] = True  # 显式标记缺失

    # 经营现金流：支持多种字段名
    cashflow = wind_financials.get('cashflow', {})
    for key in ['经营活动现金流量净额', '过去三年每年经营活动产生的现金流量净额',
                '过去三年每年经营活动之现金流量', '经营活动之现金流量']:
        if key in cashflow:
            vals = cashflow[key]
            if isinstance(vals, list) and vals:
                correct_values['经营现金流'] = vals[-1]
                break

    return correct_values
