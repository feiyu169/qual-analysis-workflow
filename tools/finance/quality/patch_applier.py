"""
patch_applier.py — 修复最小侵入（Patch 模式）+ 校验闭环

规范审查五条铁律的载体（docs/qual-review-discipline.md）：
- 铁律1：修复最小侵入——LLM 只输出 patch（target+replacement），程序应用，不整章重写
- 铁律2：修复携带锚点（调用方在 prompt 注入 Wind 锚点/事实表/权威契约）
- 铁律3：修复后重跑全量校验（structural/cross-chapter/DataAnchor/模板指纹），失败回滚
- 铁律4：修复预算（最多 N patch）+ 单调性守卫
- 铁律5：修复审计日志

用法：
    from .patch_applier import apply_patches, PatchIssue

    patches = [{"target": "2024年收入80亿元", "replacement": "2025年收入73.66亿元"}]
    ok, result = apply_patches(original, patches, validators=[...])
"""

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

MAX_PATCHES = 5  # 铁律4：每轮修复最多 5 个 patch


@dataclass
class PatchResult:
    """Patch 应用结果"""
    ok: bool
    content: str
    applied: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    validation: dict[str, Any] = field(default_factory=dict)
    rollback: bool = False  # 校验失败是否回滚


def parse_patch_json(llm_output: str) -> list[dict[str, Any]]:
    """解析 LLM 输出的 patch JSON（容忍代码块/前后噪音）"""
    text = llm_output.strip()
    # 去 ```json ... ``` 包裹
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        text = m.group(1)
    # 找到第一个 { 和最后一个 }
    first = text.find("{")
    last = text.rfind("}")
    if first == -1 or last == -1 or last <= first:
        return []
    try:
        data = json.loads(text[first:last + 1])
    except json.JSONDecodeError:
        return []
    patches = data.get("patches", []) if isinstance(data, dict) else data
    if not isinstance(patches, list):
        return []
    cleaned = []
    for p in patches:
        if isinstance(p, dict) and isinstance(p.get("target"), str) and isinstance(p.get("replacement"), str):
            cleaned.append({"target": p["target"], "replacement": p["replacement"]})
    return cleaned


def apply_patches(
    original: str,
    patches: list[dict[str, Any]],
    validators: list[Callable[[str], list[str]]] | None = None,
    max_patches: int = MAX_PATCHES,
) -> PatchResult:
    """应用 patches（唯一匹配 + 预算 + 校验闭环）

    Args:
        original: 原文
        patches: [{"target": 唯一锚串, "replacement": 替换文本}]
        validators: 校验函数列表，每个接收 content 返回问题列表（空=通过）
        max_patches: 每轮最多应用 patch 数（铁律4）

    Returns:
        PatchResult(ok, content, applied, rejected, validation, rollback)
    """
    result = PatchResult(ok=True, content=original)

    # 预算检查（铁律4）
    if len(patches) > max_patches:
        result.rejected.append({
            "reason": f"patch 数超预算（{len(patches)} > {max_patches}）",
            "patches_overflow": len(patches) - max_patches,
        })
        patches = patches[:max_patches]

    content = original
    for i, p in enumerate(patches):
        target = p.get("target", "")
        replacement = p.get("replacement", "")
        if not target:
            result.rejected.append({"index": i, "reason": "target 为空"})
            continue
        # 唯一匹配（铁律1：target 必须唯一，防止误替换）
        count = content.count(target)
        if count == 0:
            result.rejected.append({"index": i, "reason": f"target 未找到: {target[:40]}", "target": target})
            continue
        if count > 1:
            result.rejected.append({"index": i, "reason": f"target 不唯一（{count} 处匹配）: {target[:40]}", "target": target})
            continue
        content = content.replace(target, replacement, 1)
        result.applied.append({"index": i, "target": target[:40], "replacement": replacement[:40]})

    # 校验闭环（铁律3）
    if validators:
        all_issues: list[str] = []
        for v in validators:
            try:
                issues = v(content)
                all_issues.extend(issues or [])
            except Exception as e:
                all_issues.append(f"校验器异常: {e}")
        result.validation = {"passed": len(all_issues) == 0, "issues": all_issues[:10]}
        if all_issues:
            result.ok = False
            result.rollback = True
            # 回滚：恢复原内容（铁律3：校验失败不作废修复）
            result.content = original
            logger.warning(f"修复校验失败，回滚: {all_issues[:5]}")
            return result

    result.content = content
    result.ok = True
    return result


def build_repair_instruction() -> str:
    """修复输出格式指令（注入修复 prompt，铁律1/2）"""
    return """
## 修复输出格式（必须严格遵守）

只输出修复点（patch），不要输出整个章节/报告。格式为 JSON：

```json
{
  "patches": [
    {"target": "原文中唯一的原句", "replacement": "替换后的句子"},
    {"target": "另一处原文", "replacement": "另一处替换"}
  ]
}
```

约束：
1. **target 必须是原文中的唯一子串**（原样复制，不能省略/改动），否则该 patch 会被拒绝
2. **只修复审查点名的位置**，未点名的内容一个字节都不要动
3. **修复后的财务数字必须与 Wind 锚点表一致**；禁止引入锚点外的新数字/新事实/新观点
4. **最多 5 个 patch**；超过则本轮修复失败
5. 只输出 JSON，不要其他文字
"""
