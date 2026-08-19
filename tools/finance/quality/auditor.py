"""
Gate 4.2: 审计子代理 (Semantic Auditor)

使用 LLM-as-Judge 模式进行语义级别的质量审计。
读取 audit-prompt.md 作为审计指令，检查:
- must_answer 覆盖度
- must_not_cover 违反
- 行业视角应用
- 条件项满足度
- 数据质量
- 逻辑质量
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional

from .structural_check import AuditResult

logger = logging.getLogger(__name__)


# --------------------------------------------------
# Prompt 加载
# --------------------------------------------------

_PROMPTS_DIR = Path.home() / ".hermes" / "skills" / "finance" / "qual-analysis" / "prompts"


def _load_audit_prompt() -> str:
    """加载审计 prompt 模板"""
    prompt_path = _PROMPTS_DIR / "audit-prompt.md"
    if not prompt_path.exists():
        logger.warning(f"审计 prompt 不存在: {prompt_path}，使用内置模板")
        return _BUILTIN_AUDIT_PROMPT
    return prompt_path.read_text(encoding="utf-8")


# 内置备用模板（当文件不存在时使用）
_BUILTIN_AUDIT_PROMPT = """你是投资分析报告的质量审计员。请检查章节内容是否符合契约要求。

## 审计维度
1. 契约覆盖度 (30%): must_answer 问题是否都被回答
2. 边界遵守度 (20%): must_not_cover 内容是否被涉及
3. 视角应用度 (15%): 是否正确应用行业视角
4. 条件项满足度 (15%): ITEM_RULE 是否满足
5. 数据质量 (10%): 数据来源、准确性
6. 逻辑质量 (10%): 论述逻辑、结论支撑

## 输出格式
严格输出 JSON:
{
  "passed": true/false,
  "score": 0-100,
  "summary": "审计总结",
  "issues": [{"severity": "critical/major/medium/minor", "dimension": "...", "description": "...", "suggestion": "..."}],
  "suggestions": ["改进建议1", "改进建议2"]
}
"""


# --------------------------------------------------
# 主函数
# --------------------------------------------------

def semantic_audit(
    chapter_id: str,
    content: str,
    contract: dict,
    *,
    llm_caller: Optional[Any] = None,
) -> AuditResult:
    """语义审计：使用 LLM-as-Judge 检查章节质量

    Args:
        chapter_id: 章节标识
        content: 章节 Markdown 内容
        contract: 章节契约，包含:
            - chapter_title: 章节标题
            - must_answer: 必须回答的问题列表
            - must_not_cover: 不得涉及的内容列表
            - preferred_lens: 行业视角描述
            - item_rules: 条件项列表
            - company_name: 公司名称（可选）
            - ticker: 股票代码（可选）
        llm_caller: LLM 调用函数 (prompt: str) -> str
            如果为 None，返回一个需要 LLM 调用的占位结果

    Returns:
        AuditResult(passed, issues, score, details)
    """
    # 加载审计 prompt 模板
    audit_template = _load_audit_prompt()

    # 填充模板变量
    must_answer_text = "\n".join(
        f"- {item}" for item in contract.get("must_answer", [])
    )
    must_not_cover_text = "\n".join(
        f"- {item}" for item in contract.get("must_not_cover", [])
    )
    item_rules_text = "\n".join(
        f"- {rule.get('name', '')}: {rule.get('description', '')}"
        for rule in contract.get("item_rules", [])
    )

    filled_prompt = audit_template
    replacements = {
        "{{company_name}}": contract.get("company_name", "未知公司"),
        "{{ticker}}": contract.get("ticker", "N/A"),
        "{{chapter_id}}": chapter_id,
        "{{chapter_title}}": contract.get("chapter_title", chapter_id),
        "{{must_answer}}": must_answer_text or "（未指定）",
        "{{must_not_cover}}": must_not_cover_text or "（未指定）",
        "{{lens_description}}": contract.get("preferred_lens", "（未指定视角）"),
        "{{item_rules}}": item_rules_text or "（无条件项）",
        "{{chapter_content}}": content,
    }

    for key, value in replacements.items():
        filled_prompt = filled_prompt.replace(key, value)

    # 如果没有 LLM 调用器，返回提示性结果
    if llm_caller is None:
        logger.info(
            f"语义审计 {chapter_id}: 无 LLM 调用器，"
            f"返回占位结果（需上层 Agent 处理）"
        )
        return AuditResult(
            passed=True,  # 默认通过，等待 LLM 审计
            issues=["[info] 语义审计需要 LLM 调用，当前返回占位结果"],
            score=None,
            details={
                "chapter_id": chapter_id,
                "audit_prompt": filled_prompt,
                "needs_llm": True,
                "must_answer_count": len(contract.get("must_answer", [])),
                "must_not_cover_count": len(contract.get("must_not_cover", [])),
            },
        )

    # 调用 LLM 执行审计
    logger.info(f"语义审计 {chapter_id}: 调用 LLM...")
    try:
        llm_response = llm_caller(filled_prompt)
    except Exception as e:
        logger.error(f"语义审计 LLM 调用失败: {e}")
        return AuditResult(
            passed=False,
            issues=[f"[critical] LLM 审计调用失败: {e}"],
            score=0.0,
            details={"chapter_id": chapter_id, "error": str(e)},
        )

    # 解析 LLM 返回的 JSON
    return _parse_audit_response(chapter_id, llm_response)


def _parse_audit_response(chapter_id: str, llm_response: str) -> AuditResult:
    """解析 LLM 审计响应

    Args:
        chapter_id: 章节标识
        llm_response: LLM 返回的 JSON 字符串

    Returns:
        AuditResult
    """
    try:
        # 尝试从响应中提取 JSON
        json_str = _extract_json(llm_response)
        result = json.loads(json_str)
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"审计响应 JSON 解析失败: {e}")
        return AuditResult(
            passed=False,
            issues=[f"[critical] 审计响应解析失败: {e}"],
            score=0.0,
            details={
                "chapter_id": chapter_id,
                "raw_response": llm_response[:500],
                "parse_error": str(e),
            },
        )

    # 提取字段
    passed = result.get("passed", False)
    score = result.get("score", 0)
    summary = result.get("summary", "")
    raw_issues = result.get("issues", [])
    suggestions = result.get("suggestions", [])
    dimensions = result.get("dimensions", {})

    # 规范化 issues 格式
    issues: list[str] = []
    for issue in raw_issues:
        if isinstance(issue, dict):
            severity = issue.get("severity", "medium")
            dimension = issue.get("dimension", "")
            desc = issue.get("description", "")
            suggestion = issue.get("suggestion", "")
            issue_str = f"[{severity}] [{dimension}] {desc}"
            if suggestion:
                issue_str += f" → 建议: {suggestion}"
            issues.append(issue_str)
        elif isinstance(issue, str):
            issues.append(issue)

    # 二次判定：根据硬性条件覆盖 passed
    # 条件 1: 有 critical 问题 → 不通过
    has_critical = any("[critical]" in i for i in issues)
    # 条件 2: score < 70 → 不通过
    score_fail = isinstance(score, (int, float)) and score < 70
    # 条件 3: must_answer 覆盖不足
    contract_cov = dimensions.get("contract_coverage", {})
    if isinstance(contract_cov, dict) and not contract_cov.get("passed", True):
        issues.append("[critical] must_answer 问题未全部回答")

    if has_critical or score_fail:
        passed = False

    logger.info(
        f"语义审计完成 {chapter_id}: passed={passed}, "
        f"score={score}, issues={len(issues)}"
    )

    return AuditResult(
        passed=passed,
        issues=issues,
        score=score if isinstance(score, (int, float)) else None,
        details={
            "chapter_id": chapter_id,
            "summary": summary,
            "dimensions": dimensions,
            "suggestions": suggestions,
        },
    )


def _extract_json(text: str) -> str:
    """从 LLM 响应中提取 JSON 字符串

    支持以下格式:
    1. 纯 JSON
    2. ```json ... ``` 代码块
    3. 包含 JSON 的文本（提取第一个 { ... } 块）
    """
    import re

    # 尝试 1: ```json ... ```
    code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if code_block:
        return code_block.group(1).strip()

    # 尝试 2: 直接是 JSON
    stripped = text.strip()
    if stripped.startswith("{"):
        # 找到匹配的闭合括号
        depth = 0
        for i, ch in enumerate(stripped):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return stripped[: i + 1]

    # 尝试 3: 第一个 { ... } 块
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return match.group(0)

    raise ValueError("无法从响应中提取 JSON")
