"""
Gate 4.3: 修复子代理 (Chapter Repairer)

根据审计结果修复章节内容。使用 repair-prompt.md 模板，
支持最多 3 轮审计-修复循环，直到通过或达到最大轮数。

修复策略:
- 针对性修复：只修复审计指出的问题
- 保持原意：不改变核心观点
- 最小改动：尽量保持原文结构
"""

import logging
from pathlib import Path
from typing import Any, Optional

from .auditor import semantic_audit
from .structural_check import AuditResult, structural_check

logger = logging.getLogger(__name__)


# --------------------------------------------------
# Prompt 加载
# --------------------------------------------------

_PROMPTS_DIR = Path.home() / ".hermes" / "skills" / "finance" / "qual-analysis" / "prompts"

_MAX_REPAIR_ROUNDS = 3


def _load_repair_prompt() -> str:
    """加载修复 prompt 模板"""
    prompt_path = _PROMPTS_DIR / "repair-prompt.md"
    if not prompt_path.exists():
        logger.warning(f"修复 prompt 不存在: {prompt_path}，使用内置模板")
        return _BUILTIN_REPAIR_PROMPT
    return prompt_path.read_text(encoding="utf-8")


_BUILTIN_REPAIR_PROMPT = """你是投资报告编辑，根据审计反馈修复章节。

## 修复原则
1. 只修复审计指出的问题
2. 保持原有核心观点
3. 尽量保持原文结构
4. 修复后质量应有提升

## 修复对象
公司: {{company_name}} ({{ticker}})
章节: {{chapter_id}} - {{chapter_title}}

## 契约要求
必须回答: {{must_answer}}
不得涉及: {{must_not_cover}}

## 原始内容
{{original_content}}

## 审计结果
评分: {{audit_score}}
总结: {{audit_summary}}

### 问题列表
{{audit_issues}}

### 改进建议
{{audit_suggestions}}

## 输出要求
输出修复后的完整章节 Markdown 内容，不要只输出片段。
"""


# --------------------------------------------------
# 主函数
# --------------------------------------------------

def repair_chapter(
    chapter_id: str,
    content: str,
    issues: list[str],
    *,
    contract: Optional[dict] = None,
    llm_caller: Optional[Any] = None,
    max_rounds: int = _MAX_REPAIR_ROUNDS,
) -> dict:
    """修复章节：审计-修复循环

    执行最多 max_rounds 轮循环:
    1. 结构化预检
    2. 语义审计
    3. 如果不通过，使用 LLM 修复
    4. 重复直到通过或达到最大轮数

    Args:
        chapter_id: 章节标识
        content: 章节 Markdown 内容
        issues: 初始问题列表（来自先前审计）
        contract: 章节契约
        llm_caller: LLM 调用函数 (prompt: str) -> str
        max_rounds: 最大修复轮数（默认 3）

    Returns:
        {
            "content": str,           # 修复后的内容
            "passed": bool,           # 最终是否通过
            "rounds": int,            # 实际执行轮数
            "final_audit": AuditResult,  # 最终审计结果
            "history": list[dict],    # 每轮历史记录
        }
    """
    if contract is None:
        contract = {}

    current_content = content
    history: list[dict] = []
    max_rounds = min(max_rounds, _MAX_REPAIR_ROUNDS)

    logger.info(
        f"修复开始: {chapter_id}, "
        f"初始问题数={len(issues)}, 最大轮数={max_rounds}"
    )

    for round_num in range(1, max_rounds + 1):
        logger.info(f"修复轮次 {round_num}/{max_rounds}: {chapter_id}")

        round_record: dict = {
            "round": round_num,
            "input_length": len(current_content),
        }

        # ---- Step 1: 结构化预检 ----
        struct_result = structural_check(chapter_id, current_content, contract)
        round_record["structural_check"] = {
            "passed": struct_result.passed,
            "score": struct_result.score,
            "issues": struct_result.issues,
        }

        # 如果连结构化预检都过不了且有 critical 问题，需要修复
        needs_repair = not struct_result.passed
        repair_issues = struct_result.issues.copy()

        # ---- Step 2: 语义审计 ----
        if not needs_repair:
            # 结构化预检通过，继续语义审计
            audit_result = semantic_audit(
                chapter_id, current_content, contract,
                llm_caller=llm_caller,
            )
            round_record["semantic_audit"] = {
                "passed": audit_result.passed,
                "score": audit_result.score,
                "issues": audit_result.issues,
                "details": audit_result.details,
            }

            if audit_result.passed:
                # 通过！
                round_record["outcome"] = "passed"
                history.append(round_record)
                logger.info(
                    f"修复完成: {chapter_id} 在第 {round_num} 轮通过"
                )
                return {
                    "content": current_content,
                    "passed": True,
                    "rounds": round_num,
                    "final_audit": audit_result,
                    "history": history,
                }
            else:
                needs_repair = True
                repair_issues.extend(audit_result.issues)
        else:
            # 结构化预检未通过，创建一个模拟的语义审计结果
            audit_result = AuditResult(
                passed=False,
                issues=struct_result.issues,
                score=struct_result.score,
            )
            round_record["semantic_audit"] = {
                "passed": False,
                "score": struct_result.score,
                "issues": struct_result.issues,
            }

        # ---- Step 3: 修复 ----
        if needs_repair:
            round_record["repair_issues"] = repair_issues

            if llm_caller is None:
                # 无 LLM，返回原内容 + 问题注释
                logger.warning(
                    f"修复 {chapter_id}: 无 LLM 调用器，"
                    f"附加问题注释后返回"
                )
                issue_comment = (
                    "<!-- 审计问题 (需 LLM 修复):\n"
                    + "\n".join(f"- {i}" for i in repair_issues)
                    + "\n-->\n\n"
                )
                current_content = issue_comment + current_content
                round_record["outcome"] = "no_llm"
            else:
                # 调用 LLM 修复
                repaired = _call_llm_repair(
                    chapter_id=chapter_id,
                    content=current_content,
                    issues=repair_issues,
                    audit_result=audit_result,
                    contract=contract,
                    llm_caller=llm_caller,
                )
                if repaired and len(repaired.strip()) > len(current_content) * 0.5:
                    current_content = repaired
                    round_record["outcome"] = "repaired"
                    round_record["output_length"] = len(current_content)
                    logger.info(
                        f"修复 {chapter_id} 第 {round_num} 轮: "
                        f"{round_record['input_length']} → "
                        f"{round_record['output_length']} 字符"
                    )
                else:
                    round_record["outcome"] = "repair_failed"
                    logger.warning(
                        f"修复 {chapter_id} 第 {round_num} 轮: "
                        f"LLM 返回内容异常，保留原内容"
                    )

        history.append(round_record)

    # 最终审计
    final_struct = structural_check(chapter_id, current_content, contract)
    final_audit = semantic_audit(
        chapter_id, current_content, contract,
        llm_caller=llm_caller,
    )

    final_passed = final_struct.passed and final_audit.passed

    logger.warning(
        f"修复结束: {chapter_id}, "
        f"轮数={max_rounds}, 最终 passed={final_passed}"
    )

    return {
        "content": current_content,
        "passed": final_passed,
        "rounds": max_rounds,
        "final_audit": final_audit,
        "history": history,
    }


def _call_llm_repair(
    chapter_id: str,
    content: str,
    issues: list[str],
    audit_result: AuditResult,
    contract: dict,
    llm_caller: Any,
) -> Optional[str]:
    """调用 LLM 执行修复

    Args:
        chapter_id: 章节标识
        content: 当前章节内容
        issues: 问题列表
        audit_result: 审计结果
        contract: 章节契约
        llm_caller: LLM 调用函数

    Returns:
        修复后的内容，或 None 表示失败
    """
    repair_template = _load_repair_prompt()

    # 格式化问题列表
    issues_text = "\n".join(f"- {i}" for i in issues)
    suggestions = audit_result.details.get("suggestions", [])
    suggestions_text = "\n".join(f"- {s}" for s in suggestions)

    # 填充模板
    replacements = {
        "{{company_name}}": contract.get("company_name", "未知公司"),
        "{{ticker}}": contract.get("ticker", "N/A"),
        "{{chapter_id}}": chapter_id,
        "{{chapter_title}}": contract.get("chapter_title", chapter_id),
        "{{must_answer}}": "\n".join(
            f"- {a}" for a in contract.get("must_answer", [])
        ) or "（未指定）",
        "{{must_not_cover}}": "\n".join(
            f"- {n}" for n in contract.get("must_not_cover", [])
        ) or "（未指定）",
        "{{original_content}}": content,
        "{{audit_score}}": str(audit_result.score or "N/A"),
        "{{audit_summary}}": audit_result.details.get("summary", ""),
        "{{audit_issues}}": issues_text,
        "{{audit_suggestions}}": suggestions_text or "（无）",
    }

    prompt = repair_template
    for key, value in replacements.items():
        prompt = prompt.replace(key, value)

    try:
        response = llm_caller(prompt)

        # 尝试提取 Markdown 内容
        repaired = _extract_markdown(response)
        return repaired if repaired else response

    except Exception as e:
        logger.error(f"LLM 修复调用失败: {e}")
        return None


def _extract_markdown(text: str) -> Optional[str]:
    """从 LLM 响应中提取 Markdown 内容

    处理以下格式:
    1. ```markdown ... ```
    2. ```md ... ```
    3. 纯 Markdown
    """
    import re

    # 尝试提取代码块中的内容
    patterns = [
        r"```(?:markdown|md)?\s*\n(.*?)\n\s*```",
        r"```\s*\n(.*?)\n\s*```",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()

    # 如果没有代码块，检查是否看起来像 Markdown
    if text.strip().startswith("#"):
        return text.strip()

    return None
