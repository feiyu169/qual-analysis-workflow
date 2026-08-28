"""
quality_enhancer.py — 质量增强集成模块

将所有改进模块整合为一个统一的入口：
1. 数据修复 (data_repair.py)
2. 基础估值 (base_valuation.py)
3. 辩论机制 (debate_coordinator.py)
4. 完整估值 (valuation_engine.py)
5. 深度优化 (depth_enhancer.py)
"""

import logging

# v3 新组件: UnifiedValuation (统一估值)
try:
    from .valuation.assumptions import create_default_assumptions  # noqa: F401
    from .valuation.unified import UnifiedValuation  # noqa: F401
    HAS_UNIFIED_VALUATION = True
except ImportError:
    HAS_UNIFIED_VALUATION = False

from collections.abc import Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class QualityEnhancementResult:
    """质量增强结果"""
    # 各阶段结果
    repair_result: dict | None = None
    base_valuation: dict | None = None
    debate_results: dict = field(default_factory=dict)
    valuation_result: dict | None = None
    depth_result: dict | None = None

    # 汇总
    chapters_enhanced: int = 0
    total_fixes: int = 0
    overall_score_improvement: int = 0
    warnings: list[str] = field(default_factory=list)


def enhance_report_quality(
    chapters: dict[int, str],
    financials: dict,
    wind_valuation: dict | None = None,
    company_name: str = "",
    ticker: str = "",
    shares: float = 0.0,
    current_price: float | None = None,  # B2a-1：不再内置快手默认值 41.6
    fiscal_year: int = 2025,
    market: str = "hk",  # B2a-2：币种断言（hk→港元，估值链统一币种）
    llm_caller: Callable | None = None,
    enable_debate: bool = True,
    enable_valuation: bool = True,
    enable_depth: bool = True,
) -> tuple[dict[int, str], QualityEnhancementResult]:
    """
    执行完整的质量增强流程。

    Args:
        chapters: {章节号: 章节内容}
        financials: Wind财务数据
        wind_valuation: Wind估值数据
        company_name: 公司名称
        ticker: 股票代码
        shares: 总股本
        current_price: 当前股价（B2a-1：必须由调用方传入，无默认）
        fiscal_year: 财年
        llm_caller: LLM调用函数
        enable_debate: 是否启用辩论
        enable_valuation: 是否启用估值
        enable_depth: 是否启用深度优化

    Returns:
        (增强后的章节, 增强结果)
    """
    result = QualityEnhancementResult()

    # === Stage 1: 数据修复 ===
    logger.info("[Quality] Stage 1: 数据修复")
    try:
        from .data_repair import repair_report
        chapters, repair_result = repair_report(
            chapters=chapters,
            wind_valuation=wind_valuation,
            wind_financials=financials,
            fiscal_year=fiscal_year,
        )
        result.repair_result = {
            'pe_valid': repair_result.pe_report.is_valid if repair_result.pe_report else True,
            'source_fixes': repair_result.source_fixes,
            'consistency_issues': len(repair_result.consistency_issues),
            'ai_trace_fixes': repair_result.ai_trace_fixes,
            'warnings': repair_result.warnings,
        }
        result.total_fixes += repair_result.source_fixes + repair_result.ai_trace_fixes
    except Exception as e:
        logger.error(f"Stage 1 失败: {e}")
        result.warnings.append(f"数据修复失败: {e}")

    # === Stage 2: 基础估值 ===
    logger.info("[Quality] Stage 2: 基础估值")
    try:
        from .base_valuation import compute_base_valuation
        base_val = compute_base_valuation(
            ticker=ticker,
            company_name=company_name,
            wind_valuation=wind_valuation,
            wind_financials=financials,
            shares=shares,
        )
        result.base_valuation = {
            'pe_ttm': base_val.pe_ttm,
            'pb': base_val.pb,
            'ps_ttm': base_val.ps_ttm,
            'market_cap': base_val.market_cap,
            'pe_history_avg': base_val.pe_history_avg,
        }
        valuation_summary = base_val.summary()
    except Exception as e:
        logger.error(f"Stage 2 失败: {e}")
        result.warnings.append(f"基础估值失败: {e}")
        valuation_summary = ""  # noqa: F841 —— 保留统一命名（Stage 2 结果占位，后续扩展审计用）

    # === Stage 3: 辩论机制（统一 DebateService：锚点 + 超时 240s + 部分成功降级） ===
    if enable_debate and llm_caller:
        logger.info("[Quality] Stage 3: 辩论机制（DebateService）")
        from .quality.debate_service import ENHANCE_DEBATE_CHAPTERS, DebateService

        # 锚点：从 financials 重建 wind_data 形态（income/balance/cashflow）
        wind_data = financials if isinstance(financials, dict) else {}
        svc = DebateService(
            llm_caller=llm_caller,
            wind_data=wind_data,
            timeout=240,          # 原 60 → 240（推理模型）
        )

        for ch_num in ENHANCE_DEBATE_CHAPTERS:  # 成本控制：关键 5 章（原 9 章全跑）
            if ch_num in chapters:
                try:
                    title = f"第{ch_num}章"
                    logger.info(f"[Debate] 开始第{ch_num}章辩论 (timeout=240s)")

                    enhanced = svc.run(
                        chapter_num=ch_num,
                        chapter_title=title,
                        chapter_content=chapters[ch_num],
                        contract={"must_answer": [], "must_not_cover": []},
                        mode="enhance",
                    )
                    if isinstance(enhanced, str) and len(enhanced) > len(chapters[ch_num]):
                        chapters[ch_num] = enhanced
                        result.chapters_enhanced += 1
                        logger.info(f"[Debate] 第{ch_num}章增强完成")
                    else:
                        logger.warning(f"[Debate] 第{ch_num}章增强无效（辩论降级或失败），保留原文")
                except Exception as e:
                    logger.warning(f"第{ch_num}章辩论失败: {e}")

    # === Stage 4: 完整估值 ===
    if enable_valuation:
        logger.info("[Quality] Stage 4: 完整估值")
        try:
            # v3: 优先使用UnifiedValuation
            if HAS_UNIFIED_VALUATION:
                from .valuation.unified import UnifiedValuation

                # v10：使用 accessor 统一取值（自动 canonical 化）
                from .data.accessor import get_revenue as _get_rev, get_operating_profit as _get_op
                revenue = _get_rev(financials) or financials.get('revenue', 0)
                operating_profit = _get_op(financials) or financials.get('operating_profit', 0)
                ebit_margin = operating_profit / revenue if revenue > 0 else 0.05

                # 修复：create_default_assumptions不支持base_ebit_margin参数
                # 使用自定义方式创建assumptions
                from .valuation.assumptions import (
                    AssumptionSource,
                    ValuationAssumptions,
                )

                assumptions = ValuationAssumptions(
                    base_revenue=revenue,
                    revenue_growth_rates=[0.05, 0.04, 0.03, 0.02, 0.02],
                    ebit_margins=[ebit_margin * 0.8, ebit_margin, ebit_margin * 1.1, ebit_margin * 1.15, ebit_margin * 1.2],
                    wacc=0.081,  # CAPM计算值
                    terminal_growth=0.02,
                )
                assumptions.add_audit(
                    name="ebit_margin",
                    value=ebit_margin,
                    source=AssumptionSource.CALCULATED,
                    confidence=70,
                    justification=f"基于营业利润/营收计算: {operating_profit}/{revenue}={ebit_margin:.2%}",
                )

                valuation = UnifiedValuation(
                    assumptions=assumptions,
                    shares=shares,
                    net_debt=financials.get('net_debt', 0),
                )

                dcf_value = valuation.calc_dcf()
                result.valuation_result = {
                    'dcf_value': dcf_value,
                    'target_bull': dcf_value * 1.2,
                    'target_base': dcf_value,
                    'target_bear': dcf_value * 0.8,
                    'upside': (dcf_value - current_price) / current_price
                    if current_price and current_price > 0 else 0,
                }
                logger.info(f"[Quality] UnifiedValuation DCF: {dcf_value:.2f}")
            else:
                # 降级到valuation_engine
                from .valuation_engine import (
                    compute_full_valuation,
                )
                val_result = compute_full_valuation(
                    ticker=ticker,
                    company_name=company_name,
                    financials=financials,
                    shares=shares,
                    current_price=current_price,
                )
                result.valuation_result = {
                    'dcf_value': val_result.dcf.value_per_share if val_result.dcf else None,
                    'target_bull': val_result.target_price_bull,
                    'target_base': val_result.target_price_base,
                    'target_bear': val_result.target_price_bear,
                    'upside': val_result.upside,
                }

            # 注入估值结果到第7章（v10：DCF 为负时完全跳过，避免红队致命）
            if result.valuation_result:
                _vr = result.valuation_result
                _dcf = _vr.get('dcf_value')
                # DCF 为负时完全不注入（亏损公司 DCF 无效，注入会导致估值矛盾）
                if _dcf is not None and _dcf < 0:
                    logger.info(f"[Quality] DCF={_dcf:.2f} 为负，跳过估值注入（避免红队致命）")
                else:
                    _ccy = "港元" if market == "hk" else "元"
                    _rating = _vr.get('rating', '')
                    _rating_rationale = _vr.get('rating_rationale', '')
                    _method = _vr.get('method', '')
                    _reconciliation = _vr.get('reconciliation', '')

                # v10 P0-3：标准化估值输出（CFA V-B/V-C）
                val_text = f"\n\n## 估值分析\n\n"
                val_text += f"- **投资评级**: {_rating}\n"
                if _rating_rationale:
                    val_text += f"  - 评级理由: {_rating_rationale}\n"
                val_text += f"- **主估值方法**: {_method}\n"
                if _reconciliation:
                    val_text += f"  - 仲裁说明: {_reconciliation}\n"
                val_text += f"- **目标价**: {_vr.get('target_base', 0):.2f}{_ccy}\n"
                val_text += f"- **目标价区间**: {_vr.get('target_bear', 0):.2f} - {_vr.get('target_bull', 0):.2f}{_ccy}\n"
                val_text += f"  - 悲观假设: {_vr.get('target_bear_assumptions', '')}\n"
                val_text += f"  - 乐观假设: {_vr.get('target_bull_assumptions', '')}\n"
                val_text += f"- **上行空间**: {_vr.get('upside', 0):.1%}\n"
                if _dcf is not None and _dcf > 0:
                    val_text += f"- DCF每股价值: {_dcf:.2f}{_ccy}\n"
                if _vr.get('is_loss_company'):
                    val_text += f"- ⚠️ 亏损公司，DCF 不适用，以 EV/Revenue 为主估值方法\n"

                if 7 in chapters:
                    chapters[7] = chapters[7] + val_text
                    logger.info(f"[Quality] 估值结果已注入第7章（评级={_rating}，方法={_method}）")

        except Exception as e:
            logger.error(f"Stage 4 失败: {e}")
            result.warnings.append(f"估值失败: {e}")

    # === Stage 5: 深度优化 ===
    if enable_depth:
        logger.info("[Quality] Stage 5: 深度优化")
        try:
            from .depth_enhancer import format_depth_for_report, run_depth_enhancement

            # 计算WACC（使用CAPM）
            rf = 0.023  # 无风险利率
            beta = 1.2  # Beta系数
            erp = 0.055  # 股权风险溢价
            ke = rf + beta * erp  # 0.089
            kd = 0.05  # 债务成本
            tax_rate = 0.25
            wacc = ke * 0.85 + kd * (1 - tax_rate) * 0.15  # 0.081

            depth = run_depth_enhancement(
                chapters=chapters,
                financials=financials,
                valuation_value=result.valuation_result.get('dcf_value', 0) if result.valuation_result else 0,
                current_price=current_price,
                shares=shares,
                base_wacc=wacc,
                base_terminal_growth=0.02,
            )
            result.depth_result = {
                'scenarios': len(depth.scenarios),
                'flip_thresholds': len(depth.flip_thresholds),
                'yoy_changes': len(depth.yoy_changes),
                'insight_score': depth.overall_insight_score,
            }

            # 注入深度优化结果到第7章
            depth_report = format_depth_for_report(depth)
            if depth_report and 7 in chapters:
                chapters[7] = chapters[7] + "\n\n" + depth_report
                logger.info("[Quality] 深度优化结果已注入第7章")

        except Exception as e:
            logger.error(f"Stage 5 失败: {e}")
            result.warnings.append(f"深度优化失败: {e}")

    logger.info(
        f"[Quality] 完成: 修复={result.total_fixes}处, "
        f"辩论增强={result.chapters_enhanced}章, "
        f"警告={len(result.warnings)}个"
    )

    return chapters, result


def _merge_debate_result(original: str, debate) -> str:
    """合并原始章节和辩论结果

    策略：
    1. 保留原始的结论要点和证据出处
    2. 看多/看空论点完整保留（折叠标签）
    3. PM 综合判断完整保留（折叠标签）
    4. 催化剂和触发条件内联展示
    """
    merged = original

    # 分隔线
    merged += "\n\n---\n\n"
    merged += f"> **辩论增强** (确信度: {debate.conviction_score:.0%})\n\n"

    # 看多论点：折叠标签（完整保留，无截断）
    merged += f"<details><summary>看多论点</summary>\n\n{debate.bull_argument}\n\n</details>\n\n"

    # 看空质疑：折叠标签（完整保留，无截断）
    merged += f"<details><summary>看空质疑</summary>\n\n{debate.bear_argument}\n\n</details>\n\n"

    # 催化剂和触发条件（全部保留）
    if debate.catalysts:
        merged += f"> **催化剂**: {', '.join(debate.catalysts)}\n"
    if debate.triggers:
        merged += f"> **触发条件**: {', '.join(debate.triggers)}\n"

    # PM 综合判断：折叠标签（完整保留）
    if debate.pm_synthesis:
        merged += f"\n<details><summary>PM 综合判断</summary>\n\n{debate.pm_synthesis}\n\n</details>"

    return merged
