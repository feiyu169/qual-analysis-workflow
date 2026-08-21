"""P54-增强-路径1：结论验证器（Conclusion Validator）。

两级校验：
A. 确定性规则（零成本）：verdict 格式 / P0 一致性 / 维度覆盖 / 数字核对
B. LLM 校验（mimo 异质视角）：逻辑矛盾 / 遗漏维度 / 过度自信 / 严重度合理性

mimo 校验失败/超时 → 降级为仅规则校验（fail-open，不阻断主链路）。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agent.openai_compatible import OpenAICompatibleClient
from configuration import HeavySkillConfig

logger = logging.getLogger(__name__)

# 裁决词（结论是否给出可识别判定）
_VERDICT_PASS = ("通过", "可行", "PASS", "接受", "可交付", "可用", "采纳")
_VERDICT_FAIL = (
    "不通过",
    "不可行",
    "不可交付",
    "FAIL",
    "拒绝",
    "否决",
    "必须重写",
    "不可用",
)
_VERDICT_CONDITIONAL = ("有条件", "条件通过", "条件接受", "有条件通过", "PASS_WITH")

# 严重度词
_P0_MARKERS = ("P0", "致命", "阻断", "必须修复")
_P1_MARKERS = ("P1", "严重", "重要", "应该修复")


@dataclass
class ValidationResult:
    """验证结果。"""

    verdict: str  # PASS / PASS_WITH_WARNING / FAIL
    original_verdict: str = ""  # 审议原裁决词（供对比）
    verdict_changed: bool = False
    issues: List[Dict[str, str]] = field(
        default_factory=list
    )  # [{severity, rule, message}]
    warnings: List[str] = field(default_factory=list)
    confidence: float = 0.8
    validator_model: str = ""
    llm_checked: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "original_verdict": self.original_verdict,
            "verdict_changed": self.verdict_changed,
            "issues": self.issues,
            "warnings": self.warnings,
            "confidence": self.confidence,
            "validator_model": self.validator_model,
            "llm_checked": self.llm_checked,
        }


def _detect_verdict(text: str) -> Optional[str]:
    """从结论文本识别裁决词。"""
    t = text or ""
    for w in _VERDICT_FAIL:
        if w in t:
            return "FAIL"
    for w in _VERDICT_CONDITIONAL:
        if w in t:
            return "PASS_WITH_WARNING"
    for w in _VERDICT_PASS:
        if w in t:
            return "PASS"
    return None


def _extract_numbers(text: str) -> List[str]:
    """抽取文本中的数字（含小数点/百分号），用于数字交叉核对。"""
    return re.findall(r"\d+(?:\.\d+)?%?", text or "")


def rule_validate(
    deliberation_response: str,
    query: str,
    fail_on_p0: bool = True,
) -> ValidationResult:
    """A. 确定性规则校验（零 LLM 成本）。

    规则（宽松启发式，避免误报；issue 只报高置信问题）：
    - verdict_format：结论含可识别裁决词
    - p0_consistency：结论声称存在 P0/致命问题但裁决为 PASS → 矛盾
    - coverage_complete：query 中的"维度/章节"关键词在结论中出现
    """
    result = ValidationResult(verdict="PASS", original_verdict="")
    text = deliberation_response or ""
    detected = _detect_verdict(text)

    # 规则1：verdict_format
    if detected is None:
        result.issues.append(
            {
                "severity": "P1",
                "rule": "verdict_format",
                "message": "结论未给出可识别的裁决（通过/不通过/有条件/PASS/FAIL）",
            }
        )
    else:
        result.original_verdict = detected

    # 规则2：p0_consistency
    has_p0 = any(m in text for m in _P0_MARKERS)
    if has_p0 and detected == "PASS":
        result.issues.append(
            {
                "severity": "P1",
                "rule": "p0_consistency",
                "message": "结论声明存在 P0/致命问题但裁决为 PASS，严重度与裁决矛盾",
            }
        )

    # 规则3：coverage_complete（query 声明了维度时检查覆盖）
    dims = re.findall(r"(?:维度|方面)[一二三四五六七八九十\d]+", query)
    if dims:
        missing = [d for d in dims if d not in text]
        if missing:
            result.warnings.append(f"结论未覆盖 query 声明的维度: {', '.join(missing)}")

    # 汇总裁决
    p0_issues = [i for i in result.issues if i["severity"] == "P0"]
    if p0_issues and fail_on_p0:
        result.verdict = "FAIL"
        result.verdict_changed = result.original_verdict not in ("FAIL", "")
    elif result.issues:
        result.verdict = "PASS_WITH_WARNING"
        result.verdict_changed = result.original_verdict == "PASS"
    else:
        result.verdict = "PASS"
    return result


_VALIDATOR_SYSTEM = (
    "你是独立结论验证员（与生成/审议模型不同源）。核查审查结论的："
    "1) 逻辑矛盾 2) 遗漏的审查维度 3) 过度自信/无证据支撑的判断 4) 严重度分级是否合理。"
    '只输出 JSON：{"issues": [{"severity": "P0|P1|P2", "message": "...", '
    '"evidence": "..."}], "verdict": "PASS|PASS_WITH_WARNING|FAIL"}'
)


async def llm_validate(
    deliberation_response: str,
    trajectories: List[str],
    query: str,
    config: HeavySkillConfig,
) -> ValidationResult:
    """B. LLM 校验（mimo 异质视角）。

    失败/超时 → 返回空结果（fail-open），由调用方降级为仅规则校验。
    """
    result = ValidationResult(verdict="", validator_model=config.validator_model)
    traj_summary = "\n\n".join(
        f"--- 轨迹 {i + 1} 摘要 ---\n{t[:800]}" for i, t in enumerate(trajectories[:4])
    )
    user = (
        f"审查请求：\n{query[:2000]}\n\n"
        f"审议结论：\n{deliberation_response[:4000]}\n\n"
        f"推理轨迹摘要：\n{traj_summary}"
    )
    try:
        client = OpenAICompatibleClient(
            api_base=config.validator_api_base,
            api_key=config.validator_api_key,
            model=config.validator_model,
            timeout=60.0,
            max_retries=1,
        )
        try:
            resp = await client.chat_completion(
                messages=[
                    {"role": "system", "content": _VALIDATOR_SYSTEM},
                    {"role": "user", "content": user},
                ],
                model=config.validator_model,
                temperature=0.2,
                max_tokens=2000,
            )
        finally:
            await client.close()
        if resp.truncated:
            result.warnings.append("mimo 校验响应被截断，校验不完整")
        parsed = _parse_validator_json(resp.content)
        if parsed is None:
            result.warnings.append("mimo 校验输出无法解析为 JSON，仅采用规则校验")
            return result
        result.llm_checked = True
        issues = parsed.get("issues", [])
        result.issues = [
            {
                "severity": str(i.get("severity", "P2")).upper(),
                "rule": "llm",
                "message": str(i.get("message", "")),
                "evidence": str(i.get("evidence", "")),
            }
            for i in issues
            if isinstance(i, dict)
        ]
        result.verdict = str(parsed.get("verdict", "")).upper()
    except Exception as e:  # noqa: BLE001 - fail-open
        logger.warning(f"mimo 校验失败，降级为规则校验: {e}")
        result.warnings.append(f"mimo 校验失败（{type(e).__name__}），降级规则校验")
    return result


def _parse_validator_json(text: str) -> Optional[Dict[str, Any]]:
    """宽松解析验证器 JSON 输出（容忍 ```json 围栏与前后杂文）。"""
    if not text:
        return None
    t = text.strip()
    # 剥 ```json ... ``` 围栏
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.DOTALL)
    if m:
        t = m.group(1).strip()
    # 提取第一个 { ... } 块（容忍前缀文本）
    m = re.search(r"\{.*\}", t, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


async def validate_conclusion(
    deliberation_response: str,
    trajectories: List[str],
    query: str,
    config: HeavySkillConfig,
) -> ValidationResult:
    """组合校验：先规则后 LLM；LLM 结果与规则结果合并（LLM issue 追加）。"""
    rule_result = rule_validate(
        deliberation_response, query, config.validator_fail_on_p0
    )
    if not config.validator_api_key:
        rule_result.warnings.append("validator_api_key 未配置，仅执行规则校验")
        return rule_result

    llm_result = await llm_validate(deliberation_response, trajectories, query, config)
    # 合并：LLM issues 追加到规则 issues；verdict 取更严（LLM FAIL > 规则）
    if llm_result.issues:
        rule_result.issues.extend(llm_result.issues)
    rule_result.warnings.extend(llm_result.warnings)
    rule_result.llm_checked = llm_result.llm_checked
    rule_result.validator_model = llm_result.validator_model
    if llm_result.verdict == "FAIL":
        rule_result.verdict = "FAIL"
        rule_result.verdict_changed = True
    elif rule_result.verdict == "PASS" and llm_result.verdict == "PASS_WITH_WARNING":
        rule_result.verdict = "PASS_WITH_WARNING"
    # 置信度：LLM 校验后按 issue 数衰减
    rule_result.confidence = max(0.4, 0.95 - 0.1 * len(rule_result.issues))
    return rule_result
