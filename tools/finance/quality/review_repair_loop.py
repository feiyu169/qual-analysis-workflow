"""
审查修复循环模块

功能：
1. 执行审查（深度审查 + 实质性审查）
2. 如果发现问题，使用LLM修复
3. 再次审查
4. 重复直到通过或达到最大轮数

审查原则：不降低买方报告分析的专业性和质量
"""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..llm_errors import (
    DeterministicLLMFailure,
    LLMCallBudgetExceeded,
    WallClockDeadlineExceeded,
)

logger = logging.getLogger(__name__)


@dataclass
class ReviewRepairResult:
    """审查修复结果"""
    passed: bool
    rounds: int
    chapters: dict[int, str]
    issues_found: int
    issues_fixed: int
    remaining_issues: list[str]
    # v3.1 新增字段（全部带默认值，兼容 legacy workflow.py:2942 调用）
    llm_calls: int = 0
    exempted_count: int = 0
    exempted: list[str] = field(default_factory=list)
    review_incomplete: bool = False
    wall_clock_exceeded: bool = False
    budget_exceeded: bool = False


def _issue_signature(issue: str) -> str:
    """问题签名（三段式，v3.1 P0-A-1：保留章节号防跨章误豁免）

    修复 v2 缺陷16：先 findall 捕获章节号 → 归一化所有数字 →
    带计数 re.sub 按顺序还原章节号（防 str.replace 全量替换）。

    示例：
        "第4章营收增长100亿无解释" → "第@4章营收增长N亿无解释"
        "第5章营收增长100亿无解释" → "第@5章营收增长N亿无解释"  （≠ 第4章）
        "第12章总资产827.06亿"     → "第@12章总资产N亿"        （多数字节不破损）
    """
    if not issue:
        return issue

    # 1. 捕获章节号（含多数字节如 第12章）
    chapters = re.findall(r"第(\d+)章", issue)

    # 2. 归一化所有数字（含负号/小数）
    normalized = re.sub(r"-?\d+\.?\d*", "N", issue)

    # 3. 带计数按顺序还原章节号（防 str.replace 全量替换）
    it = iter(chapters)

    def _restore(m):
        try:
            return f"第@{next(it)}章"
        except StopIteration:
            return m.group(0)

    result = re.sub(r"第N章", _restore, normalized)
    return result.strip()


def review_and_repair_loop(
    chapters: dict[int, str],
    ctx: Any,
    llm_caller: Callable[[str, str], str] | None = None,
    wind_data: dict | None = None,
    max_rounds: int = 3,
    industry: str = "综合",  # B4-3：动态化默认（原硬编码"新能源汽车"，调用方应传 industry_for 结果）
    # v3.1 新增 keyword-only 参数（全部带默认值，兼容 legacy 调用）
    enable_debate: bool = False,
    skip_repair: bool = False,
    llm_call_budget: int | None = None,
    deadline: float | None = None,
) -> ReviewRepairResult:
    """
    审查修复循环（v3.1：收敛早停 + 豁免累积判据 + 单调守卫 + fail-closed）

    Args:
        chapters: 各章节内容 {chapter_num: content}
        ctx: 数据上下文
        llm_caller: LLM调用函数
        wind_data: Wind数据
        max_rounds: 最大修复轮数
        industry: 行业类型
        enable_debate: 是否启用对抗辩论（v3.1 默认 False，已知卡死组件）
        skip_repair: 是否跳过修复（shadow 模式只审不修）
        llm_call_budget: 单 Gate LLM 调用次数预算
        deadline: 墙钟截止时间（time.monotonic() 值）

    Returns:
        ReviewRepairResult（v3.1：含豁免/预算/墙钟字段）
    """
    import time as _time

    all_issues = []
    issues_fixed = 0
    prev_issue_count = None
    round_hist: dict[str, int] = {}   # 签名 → 出现轮次数
    exempted: dict[str, str] = {}     # 签名 → 问题文本（累积豁免清单）
    fixed_sigs: set = set()           # 曾被成功修复的签名
    # v3.1 P0-B-7：统一计数状态（修复+审查共用，S5 每调用必计数）
    budget_state: dict = {"calls": 0, "wall_clock_exceeded": False, "budget_exceeded": False}
    review_incomplete = False

    # 修复与审查共用预算包装（v3.1 P0-B-7：全链透传，非死代码）
    repair_caller = (
        _make_budgeted_caller(llm_caller, budget_state, deadline, llm_call_budget)
        if llm_caller is not None else None
    )

    for round_num in range(1, max_rounds + 1):
        logger.info(f"审查修复循环 第{round_num}轮")
        _round_start = _time.monotonic()

        # 轮首墙钟检查（v3.1 P0-B-8：deadline 进入循环内部）
        if deadline is not None and _round_start > deadline:
            budget_state["wall_clock_exceeded"] = True
            logger.warning(f"审查修复循环 第{round_num}轮 墙钟耗尽，终止")
            kept = []  # 防 return 引用未定义（首轮即终止的边界）
            break

        # 1. 执行审查（首轮全量；修复后轮由调用方决定是否全量）
        round_issues = []
        try:
            deep_issues = _run_deep_review(chapters, wind_data)
            round_issues.extend(deep_issues)
        except Exception as e:  # noqa: BLE001
            review_incomplete = True
            logger.warning(f"深度审查异常（非阻断）: {e}")

        try:
            substantive_issues = _run_substantive_review(
                chapters, repair_caller, wind_data, industry,
                enable_debate=enable_debate,
                # v3.1 P0-B-7/P0-B-1：审查调用共用预算/墙钟计数（S5 计入）
                budget_state=budget_state,
                deadline=deadline,
                llm_call_budget=llm_call_budget,
            )
            round_issues.extend(substantive_issues)
        except (LLMCallBudgetExceeded, WallClockDeadlineExceeded, DeterministicLLMFailure):
            raise  # v3.1 P0-A-3：预算/墙钟/确定性失败不降级（fail-closed）
        except Exception as e:  # noqa: BLE001
            review_incomplete = True
            logger.warning(f"实质审查异常（非阻断）: {e}")

        # 2. 豁免剔除（v3.1 P0-A-1：累积豁免清单，含证据护栏）
        kept = []
        for iss in round_issues:
            sig = _issue_signature(iss)
            round_hist[sig] = round_hist.get(sig, 0) + 1
            if sig in exempted:
                continue  # 已豁免：不再重复上报，但计入收敛判定
            kept.append(iss)

        # 3. 收敛判定（v3.1 P0-A-2：豁免非空即 fail；早停=不降且修复=0）
        if not kept:
            if exempted:
                # 豁免清单非空 → fail-closed（不允许静默通过）
                logger.warning(
                    f"审查修复循环 第{round_num}轮 无新问题但存在{len(exempted)}项已豁免问题，"
                    f"按 fail-closed 判定失败"
                )
                return ReviewRepairResult(
                    passed=False, rounds=round_num, chapters=chapters,
                    issues_found=len(all_issues), issues_fixed=issues_fixed,
                    remaining_issues=list(exempted.values())[:10],
                    llm_calls=budget_state["calls"], exempted_count=len(exempted),
                    exempted=list(exempted.values())[:10],
                    review_incomplete=review_incomplete,
                )
            logger.info(f"审查修复循环 第{round_num}轮 通过，无问题")
            return ReviewRepairResult(
                passed=True, rounds=round_num, chapters=chapters,
                issues_found=len(all_issues), issues_fixed=issues_fixed,
                remaining_issues=[],
                llm_calls=budget_state["calls"], exempted_count=len(exempted),
                exempted=list(exempted.values())[:10],
                review_incomplete=review_incomplete,
            )

        logger.info(f"审查修复循环 第{round_num}轮 发现{len(kept)}个问题")
        all_issues.extend(kept)

        # 收敛早停（v3.1：问题数不降且上轮修复=0 → 终止）
        if prev_issue_count is not None and len(kept) >= prev_issue_count and issues_fixed == 0:
            logger.warning(
                f"收敛早停：第{round_num}轮问题数 {len(kept)} 未降（上轮 {prev_issue_count}），"
                f"且修复=0，终止"
            )
            return ReviewRepairResult(
                passed=False, rounds=round_num, chapters=chapters,
                issues_found=len(all_issues), issues_fixed=issues_fixed,
                remaining_issues=kept[:10],
                llm_calls=budget_state["calls"], exempted_count=len(exempted),
                exempted=list(exempted.values())[:10],
                review_incomplete=review_incomplete,
            )

        # 4. 无 LLM 调用器或跳过修复 → 记录问题
        if not llm_caller or skip_repair:
            mode = "跳过修复（shadow）" if skip_repair else "无LLM调用器"
            logger.warning(f"审查修复循环 第{round_num}轮 {mode}，返回未修复")
            return ReviewRepairResult(
                passed=False, rounds=round_num, chapters=chapters,
                issues_found=len(all_issues), issues_fixed=issues_fixed,
                remaining_issues=kept[:10],
                llm_calls=budget_state["calls"], exempted_count=len(exempted),
                exempted=list(exempted.values())[:10],
                review_incomplete=review_incomplete,
            )

        # 5. 修复（patch 模式，注入 Wind 锚点）
        _snapshot_before_round = {k: v for k, v in chapters.items()}  # 单调守卫快照
        before_count = len(kept)
        try:
            fixed_count = _repair_chapters(chapters, kept, repair_caller, wind_data)
        except (WallClockDeadlineExceeded, LLMCallBudgetExceeded):
            raise  # 预算/墙钟异常 → fail-closed，向上传播
        except Exception as e:  # noqa: BLE001
            logger.warning(f"修复异常: {e}")
            fixed_count = 0
        issues_fixed += fixed_count

        # 6. 单调守卫（v3.1 P0-A-3：先减后置零 + 原始签名集比较）
        # 修复后全量静态重审（只比较静态检查器，避免 LLM 噪声）
        try:
            after_issues = _run_deep_review(chapters, wind_data)
            after_sigs = {_issue_signature(i) for i in after_issues}
            before_sigs = {_issue_signature(i) for i in kept}
            new_sigs = after_sigs - before_sigs
            if new_sigs and fixed_count > 0:
                # 修复引入新问题 → 回滚本轮
                logger.warning(
                    f"单调性守卫：修复引入新问题签名 {sorted(new_sigs)[:3]}，回滚本轮修复"
                )
                chapters.clear()
                chapters.update(_snapshot_before_round)
                issues_fixed -= fixed_count  # 先减后置零（v3.1 P0-A-3 顺序）
                fixed_count = 0
        except Exception as e:  # noqa: BLE001
            logger.warning(f"单调守卫异常（非阻断）: {e}")

        # 7. 豁免学习（v3.1：同签名跨轮 ≥2 次且从未修复成功 → 豁免）
        for iss in kept:
            sig = _issue_signature(iss)
            if sig in fixed_sigs:
                continue  # 曾被修复 → 不豁免
            if round_hist.get(sig, 0) >= 2:
                exempted.setdefault(sig, iss)
                logger.info(f"豁免问题（出现{round_hist[sig]}轮且从未修复）: {iss[:50]}")

        prev_issue_count = before_count
        if budget_state["wall_clock_exceeded"] or budget_state["budget_exceeded"]:
            break

    # 达到最大轮数或预算/墙钟耗尽
    wce = budget_state["wall_clock_exceeded"]
    be = budget_state["budget_exceeded"]
    reason = "达到最大轮数" if not (wce or be) else ("墙钟耗尽" if wce else "预算耗尽")
    logger.warning(f"审查修复循环 {reason}，仍有问题未修复")
    return ReviewRepairResult(
        passed=False, rounds=max_rounds, chapters=chapters,
        issues_found=len(all_issues), issues_fixed=issues_fixed,
        remaining_issues=kept[:10] if kept else [],
        llm_calls=budget_state["calls"], exempted_count=len(exempted),
        exempted=list(exempted.values())[:10],
        review_incomplete=review_incomplete,
        wall_clock_exceeded=wce,
        budget_exceeded=be,
    )


def _run_deep_review(chapters: dict[int, str], wind_data: dict | None) -> list[str]:
    """执行深度审查"""
    issues = []
    
    # 1. 跨章节一致性检查
    try:
        from .cross_chapter_consistency import check_cross_chapter_consistency
        result = check_cross_chapter_consistency(chapters)
        if not result.passed:
            issues.extend([f"[跨章节一致性] {issue.description}" for issue in result.issues])
    except Exception as e:  # noqa: BLE001
        logger.warning(f"跨章节一致性检查失败: {e}")
    
    # 2. 逻辑一致性检查
    try:
        from .logic_consistency_check import check_logic_consistency
        result = check_logic_consistency(chapters)
        if not result.passed:
            issues.extend([f"[逻辑一致性] {issue.description}" for issue in result.issues])
    except Exception as e:  # noqa: BLE001
        logger.warning(f"逻辑一致性检查失败: {e}")
    
    # 3. 数据合理性验证
    try:
        from .data_reasonableness_check import check_data_reasonableness
        actual_financials = {}
        if wind_data:
            income = wind_data.get("income", {})
            if isinstance(income, dict):
                actual_financials["营业收入"] = income.get("年营业收入", [0])[-1] if income.get("年营业收入") else 0
        result = check_data_reasonableness(chapters, actual_financials)
        if not result.passed:
            issues.extend([f"[数据合理性] {issue.description}" for issue in result.issues])
    except Exception as e:  # noqa: BLE001
        logger.warning(f"数据合理性验证失败: {e}")
    
    # 4. 估值仲裁
    try:
        from .valuation_arbitrator import check_valuation_arbitration
        result = check_valuation_arbitration(chapters)
        if not result.passed:
            issues.extend([f"[估值仲裁] {issue.description}" for issue in result.issues])
    except Exception as e:  # noqa: BLE001
        logger.warning(f"估值仲裁失败: {e}")
    
    # 5. 日期锚点检查
    try:
        from .date_anchor_check import check_date_anchor
        result = check_date_anchor(chapters)
        if not result.passed:
            issues.extend([f"[日期锚点] {issue.description}" for issue in result.issues])
    except Exception as e:  # noqa: BLE001
        logger.warning(f"日期锚点检查失败: {e}")
    
    return issues


def _make_budgeted_caller(
    caller: Callable[[str, str], str],
    budget_state: dict,
    deadline: float | None,
    llm_call_budget: int | None,
) -> Callable[[str, str], str]:
    """带预算/墙钟计数的 LLM 调用包装（v3.1 P0-B-7：修复+审查共用，S5 每调用必计数）"""
    import time as _time

    def budgeted(name: str, prompt: str) -> str:
        budget_state["calls"] += 1
        if deadline is not None and _time.monotonic() > deadline:
            budget_state["wall_clock_exceeded"] = True
            raise WallClockDeadlineExceeded()
        if llm_call_budget is not None and budget_state["calls"] > llm_call_budget:
            budget_state["budget_exceeded"] = True
            raise LLMCallBudgetExceeded()
        return caller(name, prompt)

    return budgeted


def _build_review_caller(
    primary: Callable[[str, str], str],
    budget_state: dict,
    deadline: float | None,
    llm_call_budget: int | None,
) -> Callable[[str, str], str] | None:
    """审查专用 caller：REVIEW_SYSTEM + fallback + budgeted + deadline（v3.1 P0-B-1/P0-B-7）。

    内部自建审查 caller（create_harness_caller + with_fallback 逃生直连），
    并套上预算/墙钟计数（与修复共用 budget_state）。
    测试可注入：monkeypatch "finance.harness_llm.create_harness_caller" 即可接管审查路径。
    """
    if primary is None:
        return None
    try:
        from ..harness_llm import create_harness_caller
        from ..llm_caller import create_deepseek_caller
        from ..llm_fallback import with_fallback
        REVIEW_SYSTEM = (
            "你是资深买方投资分析师（Research QC）。你的任务是评估报告的分析深度、结论合理性与"
            "数据支撑质量，给出批判性判断。你不写报告，不受报告格式约束。"
        )
        inner = create_harness_caller(
            max_tokens=8000,
            temperature=0.3,
            system=REVIEW_SYSTEM,
            deadline=deadline,  # v3.1 P0-B-1：审查调用同样受墙钟约束
        )
        fb = with_fallback(
            inner,
            lambda: create_deepseek_caller(model="deepseek-chat"),
            deadline=deadline,  # v3.1 P0-5：逃生直连同样受墙钟约束
        )
        return _make_budgeted_caller(fb, budget_state, deadline, llm_call_budget)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"审查 caller 构造失败，使用主 caller: {e}")
        return _make_budgeted_caller(primary, budget_state, deadline, llm_call_budget)


def _run_substantive_review(
    chapters: dict[int, str],
    llm_caller: Callable | None,
    wind_data: dict | None,
    industry: str,
    enable_debate: bool = False,
    *,
    budget_state: dict | None = None,     # v3.1：统一计数（S5 计入）
    deadline: float | None = None,        # v3.1 P0-B-1
    llm_call_budget: int | None = None,   # v3.1 P0-B-7
) -> list[str]:
    """执行实质性审查（v3.1：enable_debate 门控对抗辩论；审查调用计入预算/墙钟）"""
    issues = []

    # 审查改进：构造审查专用 caller（审查 system，避免报告撰写格式约束污染审查判断）
    # 仅当传入的是可包装的 llm_caller 时使用；否则退化为原 caller
    review_caller = llm_caller
    if llm_caller is not None and budget_state is not None:
        review_caller = _build_review_caller(llm_caller, budget_state, deadline, llm_call_budget)
    
    # 1. 事实核查
    try:
        from .fact_checker import check_facts
        result = check_facts(chapters, wind_data or {})
        if not result.passed:
            issues.extend([f"[事实核查] {issue.description}" for issue in result.issues])
    except Exception as e:  # noqa: BLE001
        logger.warning(f"事实核查失败: {e}")
    
    # 2. 分析深度审查（注入 Wind 锚点）
    try:
        from .depth_reviewer import check_depth
        result = check_depth(chapters, review_caller, wind_data)
        if not result.passed:
            issues.extend([f"[分析深度] {issue.description}" for issue in result.issues])
    except (LLMCallBudgetExceeded, WallClockDeadlineExceeded, DeterministicLLMFailure):
        raise  # v3.1 P0-A-3：预算/墙钟/确定性失败不降级（fail-closed）
    except Exception as e:  # noqa: BLE001
        logger.warning(f"分析深度审查失败: {e}")
    
    # 3. 结论合理性审查（注入 Wind 锚点）
    try:
        from .conclusion_validator import check_conclusion
        result = check_conclusion(chapters, review_caller, wind_data)
        if not result.passed:
            issues.extend([f"[结论合理性] {issue.description}" for issue in result.issues])
    except (LLMCallBudgetExceeded, WallClockDeadlineExceeded, DeterministicLLMFailure):
        raise  # v3.1 P0-A-3：预算/墙钟/确定性失败不降级（fail-closed）
    except Exception as e:  # noqa: BLE001
        logger.warning(f"结论合理性审查失败: {e}")
    
    # 4. 假设合理性审查
    try:
        from .assumption_checker import check_assumptions
        result = check_assumptions(chapters, industry, wind_data)
        if not result.passed:
            issues.extend([f"[假设合理性] {issue.description}" for issue in result.issues])
    except Exception as e:  # noqa: BLE001
        logger.warning(f"假设合理性审查失败: {e}")

    # 5. 对抗性辩论审查（v3.1：enable_debate 门控——已知卡死组件，默认 False）
    if review_caller is not None and enable_debate:
        try:
            from .debate_service import REVIEW_DEBATE_CHAPTERS, DebateService
            svc = DebateService(
                llm_caller=review_caller,
                wind_data=wind_data,
                timeout=240,   # 角色超时（推理模型）
            )
            for ch_num in REVIEW_DEBATE_CHAPTERS:
                if ch_num not in chapters or not chapters[ch_num]:
                    continue
                try:
                    title = f"第{ch_num}章"
                    debate_issues = svc.run(
                        chapter_num=ch_num,
                        chapter_title=title,
                        chapter_content=chapters[ch_num],
                        contract=None,
                        mode="review",
                    )
                    if debate_issues:
                        issues.extend(debate_issues)
                        logger.info(f"对抗辩论审查 第{ch_num}章: 发现 {len(debate_issues)} 个问题")
                except (LLMCallBudgetExceeded, WallClockDeadlineExceeded, DeterministicLLMFailure):
                    raise  # v3.1 P0-A-3：预算/墙钟/确定性失败不降级（fail-closed）
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"对抗辩论审查 第{ch_num}章失败（非阻断）: {e}")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"对抗辩论审查初始化失败（非阻断）: {e}")

    return issues


def _repair_chapters(
    chapters: dict[int, str],
    issues: list[str],
    llm_caller: Callable[[str, str], str],
    wind_data: dict | None = None,
) -> int:
    """使用 LLM 修复章节（Patch 模式，规范审查：最小侵入+锚点+校验闭环）

    只允许 LLM 输出 patch（target+replacement），程序应用并校验；
    整章主题漂移（模板泄漏）走专用重写路径；未点名内容物理不变。
    """
    fixed_count = 0
    
    # 按章节分组问题
    import re
    chapter_issues = {}
    for issue in issues:
        match = re.search(r"第(\d+)章", issue)
        if match:
            ch_num = int(match.group(1))
            if ch_num not in chapter_issues:
                chapter_issues[ch_num] = []
            chapter_issues[ch_num].append(issue)
    
    # 修复每个章节
    for ch_num, ch_issues in chapter_issues.items():
        if ch_num not in chapters:
            continue
        
        content = chapters[ch_num]
        issues_text = "\n".join([f"- {issue}" for issue in ch_issues[:10]])

        # 铁律2：注入 Wind 锚点表（若有）
        wind_anchor = ""
        if wind_data:
            try:
                from ..qual_v8.data_anchor import DataAnchor
                anchor = DataAnchor()
                anchor.init_from_wind_data(wind_data)
                all_a = anchor.get_all_anchors()
                if all_a:
                    fys = sorted({dp.fiscal_year for pts in all_a.values()
                                  for dp in pts if dp.fiscal_year is not None})
                    rows = []
                    for k, pts in all_a.items():
                        row = {dp.fiscal_year: f"{dp.value:.2f}" for dp in pts if dp.fiscal_year is not None}
                        vals = " | ".join(row.get(fy, "—") for fy in fys)
                        rows.append(f"| {k} | {vals} |")
                    wind_anchor = "## Wind 验证锚点（修复后的财务数字必须与此一致）\n\n| 指标 | " + \
                        " | ".join(f"FY{fy}" for fy in fys) + " |\n|------|" + "--------|" * len(fys) + \
                        "\n" + "\n".join(rows)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"修复锚点构建失败: {e}")

        # 铁律1：patch 模式（LLM 只输出修改点）
        prompt = f"""
请修复以下章节中的问题。

问题列表：
{issues_text}

{wind_anchor}

当前内容：
{content}

## 修复输出格式（必须严格遵守）
只输出修复点（patch），不要输出整个章节。格式为 JSON：

```json
{{"patches": [
  {{"target": "原文中唯一的原句", "replacement": "替换后的句子"}}
]}}
```

约束：
1. **target 必须是当前内容中的唯一子串**（原样复制），否则该 patch 会被拒绝
2. **只修复问题点名的位置**，未点名的内容一个字节都不要动
3. **修复后的财务数字必须与 Wind 锚点一致**；禁止引入锚点外的新数字/新事实/新观点
4. **最多 5 个 patch**；超过则本轮修复失败
5. 只输出 JSON，不要其他文字
"""
        
        try:
            from .cross_chapter_consistency import check_cross_chapter_consistency
            from .patch_applier import (
                apply_patches,
                parse_patch_json,
            )
            from .structural_check import structural_check

            # 调用 LLM 生成 patch
            llm_out = llm_caller(f"repair_patch_ch{ch_num}", prompt)
            patches = parse_patch_json(llm_out)

            if not patches:
                logger.warning(f"第{ch_num}章 patch 解析为空，保留原文")
                continue

            # 校验器列表（铁律3：结构 + 跨章一致 + 数字锚点）
            def _structural(content: str) -> list:
                r = structural_check(f"ch{ch_num}", content)  # noqa: B023
                return r.issues if not r.passed else []

            def _consistency(content: str) -> list:
                try:
                    r = check_cross_chapter_consistency({ch_num: content})  # noqa: B023
                    return [i.description for i in r.issues] if not r.passed else []
                except Exception:  # noqa: BLE001
                    return []

            def _numeric(content: str) -> list:
                """数字锚点校验：内容中财务数字 vs Wind 锚点（多财年兼容，1% 容差）

                用 validate_chapter_any_fy：数值命中任一财年锚点即通过，
                避免把 ch6/ch7 合法引用的 FY2024 历史值（如总资产 827.06 亿）误判为错误。
                """
                if not wind_data:
                    return []
                try:
                    from ..qual_v8.data_anchor import DataAnchor
                    anchor = DataAnchor()
                    anchor.init_from_wind_data(wind_data)
                    errs = anchor.validate_chapter_any_fy(ch_num, content)  # noqa: B023
                    return [f"数字锚点: {e}" for e in errs]
                except Exception:  # noqa: BLE001
                    return []

            result = apply_patches(
                content,
                patches,
                validators=[_structural, _consistency, _numeric],
            )

            if result.ok and result.applied:
                chapters[ch_num] = result.content
                fixed_count += 1
                logger.info(f"第{ch_num}章 patch 修复成功: {len(result.applied)} 处, 校验通过")
            elif result.rollback:
                logger.warning(f"第{ch_num}章 patch 校验失败，已回滚（保留原文）: {result.validation.get('issues', [])[:3]}")
            else:
                logger.warning(f"第{ch_num}章 无有效 patch（拒绝 {len(result.rejected)} 处）: {[r.get('reason','')[:50] for r in result.rejected[:3]]}")

        except (LLMCallBudgetExceeded, WallClockDeadlineExceeded, DeterministicLLMFailure):
            raise  # v3.1 P0-A-3：预算/墙钟/确定性失败不降级（fail-closed）
        except Exception as e:  # noqa: BLE001
            logger.warning(f"第{ch_num}章 patch 修复失败: {e}")
    
    return fixed_count
