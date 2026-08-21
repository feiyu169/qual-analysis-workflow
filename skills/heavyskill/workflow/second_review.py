"""P54-增强-路径2：异质模型独立二审（SecondReviewer）。

deepseek 一审结论 C1 → mimo 独立二审 C2（**不注入 C1**，只喂轨迹+请求，打破单模型
自洽盲点）→ 确定性仲裁（不引入第三次 LLM）：
- 任一 FAIL/P0 → 取 FAIL（安全优先）
- C1 == C2（裁决词一致）→ 采用，置信度提升
- 分歧 → conflict 标记 + PASS_WITH_WARNING，输出人工复核提示

mimo 失败/超时 → fail-open：返回 conflict=False、采用一审，附 warning。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agent.openai_compatible import OpenAICompatibleClient
from configuration import HeavySkillConfig
from .validator import _detect_verdict

logger = logging.getLogger(__name__)

_SECOND_REVIEW_SYSTEM = (
    "你是独立二审员（与生成/审议模型不同源，独立判断，不参考其他模型的结论）。"
    "基于以下 K 条独立推理轨迹，独立给出你的审查结论："
    "逐条找错、交叉验证、综合判定。"
    "结论必须包含明确的裁决词：通过 / 不通过 / 有条件通过 / PASS / FAIL。"
)


@dataclass
class SecondReviewResult:
    """二审结果。"""

    second_conclusion: str = ""
    second_model: str = ""
    second_verdict: Optional[str] = None  # 二审裁决词（PASS/PASS_WITH_WARNING/FAIL）
    conflict: bool = False  # 一审二审裁决分歧
    final_verdict: str = ""  # 仲裁后最终裁决
    confidence: float = 0.8
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "second_conclusion": self.second_conclusion,
            "second_model": self.second_model,
            "second_verdict": self.second_verdict,
            "conflict": self.conflict,
            "final_verdict": self.final_verdict,
            "confidence": self.confidence,
            "warnings": self.warnings,
        }


class SecondReviewer:
    """异质二审：mimo 独立判断 + 确定性仲裁。"""

    def __init__(self, config: HeavySkillConfig):
        self.config = config

    async def review(
        self,
        trajectories: List[str],
        query: str,
        first_verdict: Optional[str] = None,
        first_conclusion: str = "",
    ) -> SecondReviewResult:
        """执行二审。

        Args:
            trajectories: 一审使用的轨迹（same set，保证对比公平）。
            query: 原始审查请求。
            first_verdict: 一审裁决词（仲裁用，不注入二审 prompt）。
            first_conclusion: 一审结论（仅用于仲裁对比，不注入 prompt）。

        Returns:
            SecondReviewResult。
        """
        result = SecondReviewResult(
            second_model=self.config.validator_model,
            final_verdict=first_verdict or "PASS",
        )
        if not self.config.validator_api_key:
            result.warnings.append("validator_api_key 未配置，二审跳过（fail-open）")
            return result

        traj_text = "\n\n".join(
            f"--- 轨迹 {i + 1} ---\n{t[:1200]}" for i, t in enumerate(trajectories[:4])
        )
        user = f"审查请求：\n{query[:2000]}\n\n推理轨迹：\n{traj_text}"
        try:
            client = OpenAICompatibleClient(
                api_base=self.config.validator_api_base,
                api_key=self.config.validator_api_key,
                model=self.config.validator_model,
                timeout=60.0,
                max_retries=1,
            )
            try:
                resp = await client.chat_completion(
                    messages=[
                        {"role": "system", "content": _SECOND_REVIEW_SYSTEM},
                        {"role": "user", "content": user},
                    ],
                    model=self.config.validator_model,
                    temperature=0.3,
                    max_tokens=self.config.summary_max_tokens,
                )
            finally:
                await client.close()

            result.second_conclusion = resp.content
            if resp.truncated:
                result.warnings.append("二审响应被截断，裁决可靠性下降")
            result.second_verdict = _detect_verdict(resp.content)

            # 确定性仲裁
            fv, sv = first_verdict, result.second_verdict
            if sv == "FAIL" or fv == "FAIL":
                result.final_verdict = "FAIL"
                result.conflict = bool(fv != sv)
            elif sv is None:
                result.final_verdict = fv or "PASS_WITH_WARNING"
                result.warnings.append("二审未给出可识别裁决，采用一审")
            elif sv == fv:
                result.final_verdict = sv
                result.conflict = False
                result.confidence = min(0.95, (result.confidence or 0.8) * 1.2)
            else:
                result.final_verdict = "PASS_WITH_WARNING"
                result.conflict = True
                result.confidence = 0.6
                result.warnings.append(
                    f"一审({fv})与二审({sv})裁决分歧，按 P0 安全优先取 "
                    f"{result.final_verdict}，建议人工复核"
                )
        except Exception as e:  # noqa: BLE001 - fail-open
            logger.warning(f"二审失败，采用一审: {e}")
            result.warnings.append(f"二审失败（{type(e).__name__}），采用一审")
        return result
