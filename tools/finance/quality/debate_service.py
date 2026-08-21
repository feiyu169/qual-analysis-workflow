"""
debate_service.py — 辩论服务（统一入口）

架构（docs/qual-debate-unified.md + docs/qual-debate-timeout-redesign.md）：
- 单一引擎（debate_coordinator.run_debate）+ 双消费模式（enhance/review）
- 锚点注入唯一化：Wind canonical 锚点表（一处构建，全链路共用）
- 超时分层：角色 240s（默认，可配）+ 总预算防挂死
- 部分成功降级：Bull 可独立利用；Bear 缺失标记；PM 超时自动裁决（引擎层已实现）

用法：
    from .debate_service import DebateService

    svc = DebateService(llm_caller, wind_data=wind_data, timeout=240)
    # 增强模式：append 辩论洞察到章节
    enhanced = svc.run(ch_num, title, content, contract=contract, mode="enhance")
    # 审查模式：提取 Bear 反驳为审查 issues
    issues = svc.run(ch_num, title, content, contract=contract, mode="review")
"""

import logging
import re
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

# 审查模式默认跑的关键章节（决策/经营/变化）
REVIEW_DEBATE_CHAPTERS = [10, 5, 4]
# 增强模式默认章节（成本控制：9 章全跑偏长，默认关键 5 章）
ENHANCE_DEBATE_CHAPTERS = [1, 4, 5, 7, 10]


class DebateService:
    """辩论服务：统一入口，注入锚点 + 超时 + enhance/review 双消费模式"""

    def __init__(
        self,
        llm_caller: Callable[[str, str], str],
        wind_data: dict | None = None,
        timeout: int = 240,               # 角色超时（原 60 → 240，见 redesign 文档）
        retries: int = 1,                 # 每角色失败重试（受 timeout 约束）
        chapters: list[int] | None = None,  # 章节白名单（None=调用方指定）
    ):
        self.llm_caller = llm_caller
        self.wind_data = wind_data
        self.timeout = timeout
        self.retries = retries
        self.chapters = chapters
        self.wind_anchor = self._build_wind_anchor_table(wind_data)

    # ------------------------------------------------------------
    # 锚点构建（唯一化：此处实现，全链路共用）
    # ------------------------------------------------------------
    @staticmethod
    def _build_wind_anchor_table(wind_data: dict | None) -> str:
        """从 wind_data 构建 canonical 锚点表（与 review_integrator 同逻辑，收敛于此）"""
        if not wind_data:
            return ""
        try:
            from ..qual_v8.data_anchor import get_data_anchor
            anchor = get_data_anchor(wind_data)
            all_a = anchor.get_all_anchors()
            if not all_a:
                return ""
            fys = sorted({dp.fiscal_year for pts in all_a.values()
                          for dp in pts if dp.fiscal_year is not None})
            if not fys:
                return ""
            rows = []
            for k, pts in all_a.items():
                row = {dp.fiscal_year: f"{dp.value:.2f}" for dp in pts if dp.fiscal_year is not None}
                rows.append(f"| {k} | " + " | ".join(row.get(fy, "—") for fy in fys) + " |")
            return ("| 指标 | " + " | ".join(f"FY{fy}" for fy in fys) + " |\n|------|"
                    + "--------|" * len(fys) + "\n" + "\n".join(rows))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"辩论锚点构建失败: {e}")
            return ""

    # ------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------
    def run(
        self,
        chapter_num: int,
        chapter_title: str,
        chapter_content: str,
        contract: dict | None = None,
        mode: str = "enhance",   # "enhance" | "review" | "raw"
    ) -> Any:
        """跑一次辩论（注入锚点 + 超时），按模式消费

        Returns:
            enhance: 增强后的章节内容（str）
            review: 审查问题列表（list[str]）
            raw: DebateResult 对象
        """
        if self.llm_caller is None:
            return chapter_content if mode == "enhance" else []

        from ..debate_coordinator import run_debate

        # 锚点注入：作为 base_valuation_summary 传给三角色（估值上下文 = Wind 锚点）
        anchor_context = self.wind_anchor or "（未提供 Wind 锚点）"

        # 带重试的调用（部分成功降级由引擎层处理）
        debate = None
        for attempt in range(self.retries + 1):
            try:
                debate = run_debate(
                    chapter_num=chapter_num,
                    chapter_title=chapter_title,
                    chapter_content=chapter_content,
                    base_valuation_summary=anchor_context,
                    llm_caller=self.llm_caller,
                    contract=contract,
                    llm_timeout_seconds=self.timeout,
                )
                # 全部失败（Bull 缺失）则重试一次
                if debate.stages.get("bull") == "ok":
                    break
                logger.warning(f"辩论第{chapter_num}章第{attempt+1}次尝试 Bull 缺失，重试")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"辩论第{chapter_num}章第{attempt+1}次尝试失败: {e}")
                debate = None
        if debate is None:
            return chapter_content if mode == "enhance" else []

        # 双消费模式
        if mode == "enhance":
            return self._consume_enhance(chapter_content, debate)
        if mode == "review":
            return self._consume_review(debate)
        return debate

    # ------------------------------------------------------------
    # 消费者 A：增强（append 辩论洞察到章节）
    # ------------------------------------------------------------
    def _consume_enhance(self, original: str, debate: Any) -> str:
        """增强模式：保留原文，追加辩论洞察（Bull/Bear/PM）"""
        parts = [original.rstrip()]
        parts.append("\n\n---\n\n")
        parts.append(f"> **辩论增强** (确信度: {debate.conviction_score:.0%}")

        if debate.stages.get("bull") == "ok":
            parts.append(f", 看多论点: {'完整' if debate.stages.get('bear') == 'ok' else '部分（Bear 缺失）'}")
        parts.append(")\n\n")

        if debate.bull_argument:
            parts.append(f"<details><summary>看多论点</summary>\n\n{debate.bull_argument}\n\n</details>\n\n")
        if debate.bear_argument:
            parts.append(f"<details><summary>看空质疑</summary>\n\n{debate.bear_argument}\n\n</details>\n\n")
        if debate.pm_synthesis:
            parts.append(f"<details><summary>PM 综合判断</summary>\n\n{debate.pm_synthesis}\n\n</details>")
        return "\n".join(parts)

    # ------------------------------------------------------------
    # 消费者 B：审查（提取 Bear 反驳为审查 issues）
    # ------------------------------------------------------------
    def _consume_review(self, debate: Any) -> list[str]:
        """审查模式：从 Bear 反驳/PM 裁决提取审查问题"""
        issues: list[str] = []

        if debate.stages.get("bear") != "ok":
            # Bear 缺失：明确"该章无对抗审查"而非报错
            logger.info(f"辩论审查: 第{debate.chapter_num if hasattr(debate, 'chapter_num') else '?'}章 Bear 缺失，无对抗审查")
            return issues

        bear = debate.bear_argument or ""
        # Bear 的"被忽略风险"→ 审查问题
        risk_m = re.search(r"被忽略的关键风险.*?(?:\n|$)((?:- .+\n?)+)", bear, re.DOTALL)
        if risk_m:
            for line in risk_m.group(1).strip().splitlines():
                line = line.strip("- ").strip()
                if line:
                    issues.append(f"[辩论-Bear] 被忽略风险: {line[:100]}")
        # Bear 的"数据质疑/替代解释"→ 审查问题
        for marker in ("数据质疑", "替代解释", "逻辑检验"):
            for m in re.finditer(rf"{marker}[：:]\s*(.+?)(?:\n|$)", bear):
                text = m.group(1).strip()
                if text:
                    issues.append(f"[辩论-Bear] {marker}: {text[:100]}")
        # PM 裁决倾向看空 → 审查问题（首尾矛盾信号）
        if debate.pm_synthesis and ("看空" in debate.pm_synthesis or "中性" in debate.pm_synthesis) \
                and "自动裁决" not in debate.pm_synthesis:
            issues.append(f"[辩论-PM] 裁决含看空/中性信号（与章节可能矛盾）: {debate.pm_synthesis[:100]}")

        return issues[:10]  # 每章最多 10 条


# ------------------------------------------------------------
# 便捷入口
# ------------------------------------------------------------

def run_chapter_debate(
    llm_caller: Callable[[str, str], str],
    chapter_num: int,
    chapter_title: str,
    chapter_content: str,
    wind_data: dict | None = None,
    contract: dict | None = None,
    mode: str = "review",
    timeout: int = 240,
) -> Any:
    """单章辩论便捷函数（审查/增强）"""
    svc = DebateService(llm_caller, wind_data=wind_data, timeout=timeout)
    return svc.run(chapter_num, chapter_title, chapter_content,
                   contract=contract, mode=mode)
