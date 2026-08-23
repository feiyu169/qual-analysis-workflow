"""
Qual v9 Prompting 模块（参照 dayu-agent prompting/）。

从 workflow.py _build_chapter_prompt 提取，加入：
- 条件渲染：<when_tool> 根据运行时工具集自动裁剪 prompt 段落
- context_slots：声明允许注入的动态片段，防止 prompt 膨胀
- 模板变量替换：统一的 {{variable}} 替换机制

Note: E501 行过长豁免——prompt 模板中的长行是 LLM 需要完整阅读的指令文本，
拆行会破坏 prompt 语义。
"""
# ruff: noqa: E501
from __future__ import annotations

import re
from typing import Any

# ============================================================
# 条件渲染引擎
# ============================================================

_CONDITION_RE = re.compile(
    r"<when_(\w+)\s+([^>]*)>(.*?)</when_\1>",
    re.DOTALL,
)


def render_conditional(prompt: str, active_slots: set[str]) -> str:
    """条件渲染：根据活跃 slot 集合裁剪 prompt 段落。

    语法：
        <when_tool wind>Wind 相关指令...</when_tool>
        <when_tool search>搜索相关指令...</when_tool>

    规则：
    - slot 名在 active_slots 中 → 保留内容
    - slot 名不在 active_slots 中 → 删除整个标签及内容

    Args:
        prompt: 含条件标签的 prompt。
        active_slots: 当前活跃的 slot 名集合。

    Returns:
        裁剪后的 prompt。
    """
    def _replacer(match: re.Match) -> str:
        slot_name = match.group(2).strip()
        content = match.group(3)
        if slot_name in active_slots:
            return content
        return ""

    return _CONDITION_RE.sub(_replacer, prompt)


# ============================================================
# 模板变量替换
# ============================================================

_VARIABLE_RE = re.compile(r"\{\{(\w+)\}\}")


def render_variables(prompt: str, variables: dict[str, str]) -> str:
    """模板变量替换：{{variable}} → 值。

    Args:
        prompt: 含 {{variable}} 的 prompt。
        variables: 变量名→值映射。

    Returns:
        替换后的 prompt。未匹配的变量保留原样。
    """
    def _replacer(match: re.Match) -> str:
        var_name = match.group(1)
        return variables.get(var_name, match.group(0))

    return _VARIABLE_RE.sub(_replacer, prompt)


# ============================================================
# Context Slots（参照 dayu prompting/prompt_contribution_slots.py）
# ============================================================

class ContextSlots:
    """上下文插槽管理器：声明允许注入 prompt 的动态片段。

    用法：
        slots = ContextSlots()
        slots.declare("company_info", required=True)
        slots.declare("wind_anchor", required=True)
        slots.declare("filing_summary", required=False)
        slots.fill("company_info", "小鹏汽车 (9868.HK)")
        slots.fill("wind_anchor", "营业收入: FY2025=767.20亿...")

        prompt = slots.inject(base_prompt)
    """

    def __init__(self) -> None:
        self._slots: dict[str, dict[str, Any]] = {}

    def declare(self, name: str, *, required: bool = False, default: str = "") -> None:
        """声明一个 slot。"""
        self._slots[name] = {"required": required, "value": None, "default": default}

    def fill(self, name: str, value: str) -> None:
        """填充 slot 值。"""
        if name in self._slots:
            self._slots[name]["value"] = value

    def get(self, name: str) -> str:
        """获取 slot 值（未填充返回 default 或空串）。"""
        slot = self._slots.get(name)
        if slot is None:
            return ""
        return slot["value"] or slot.get("default", "")

    def get_variables(self) -> dict[str, str]:
        """获取所有 slot 值（用于模板变量替换）。"""
        return {name: self.get(name) for name in self._slots}

    def check_required(self) -> list[str]:
        """检查必填 slot 是否已填充。返回未填充的 slot 名列表。"""
        return [
            name for name, slot in self._slots.items()
            if slot["required"] and not slot["value"]
        ]

    def inject(self, prompt: str) -> str:
        """将 slot 值注入 prompt（模板变量替换）。"""
        return render_variables(prompt, self.get_variables())


# ============================================================
# Chapter Prompt Builder（从 workflow.py _build_chapter_prompt 提取）
# ============================================================

def build_chapter_prompt(
    chapter_num: int,
    chapter_def: dict[str, Any],
    wind_anchor: str,
    filing_summary: str,
    search_summary: str,
    prev_summary: str,
    must_answer: list[str],
    must_not_cover: list[str],
    skeleton_lines: str,
    fiscal_chapter_rule: str,
    company_name: str = "",
    ticker: str = "",
    market: str = "",
    data_quality: str = "",
    constraints: list[str] | None = None,
    lens: str = "",
) -> str:
    """构建单章写作 prompt（从 workflow.py 提取，加入 context_slots）。

    Args:
        chapter_num: 章节编号。
        chapter_def: 章节定义（title/goal/contract/lens）。
        wind_anchor: Wind 锚点表文本。
        filing_summary: 财报摘要。
        search_summary: 搜索摘要。
        prev_summary: 前序章节摘要。
        must_answer: 必须回答的问题。
        must_not_cover: 不得涉及的内容。
        skeleton_lines: 章节骨架。
        fiscal_chapter_rule: 财年铁律。
        company_name/ticker/market/data_quality: 公司信息。
        constraints: 约束条件。
        lens: 行业视角。

    Returns:
        完整 prompt 文本。
    """
    chapter_title = chapter_def.get("title", "")
    chapter_goal = chapter_def.get("goal", "")
    must_answer_text = "\n".join(f"- {q}" for q in must_answer)
    must_not_cover_text = "\n".join(f"- {q}" for q in must_not_cover)

    # 条件渲染：Wind 锚点可用时注入相关指令
    active_slots: set[str] = set()
    if wind_anchor:
        active_slots.add("wind")
    if filing_summary:
        active_slots.add("filing")
    if search_summary:
        active_slots.add("search")

    prompt = f"""你是一位资深买方投资分析师。请撰写「第{chapter_num}章: {chapter_title}」。

## 章节目标
{chapter_goal}

## 公司信息
- Ticker: {ticker}
- 公司名: {company_name}
- 市场: {market.upper()}
- 数据质量: {data_quality}
- 约束条件: {', '.join(constraints) if constraints else '无'}

## ⚖️ 数据源权威契约（必须遵守）
- **财务数值**（收入/利润/现金流/资产）：以 **Wind 锚点表（数据铁律）为准**，禁止使用与锚点矛盾的数值；  # noqa: E501
  财报事实表的财务字段仅作交叉印证（同财年一致才可引用；不一致以 Wind 覆盖；异财年只能作历史参考，不得当当期值）
- **运营/定性事实**（产品/客户/MAU/付费/IP/治理/风险）：以**财报事实表**为准（一手披露）
- **行业/市场/外部信息**：以搜索补充为准，但**不参与财务数值计算**
- 冲突铁律：任何来源与 Wind 锚点矛盾 → **Wind 锚点优先**，其余作废或标注参考

## 必须回答的问题
{must_answer_text}

## 不得涉及的内容
{must_not_cover_text}

{"## 行业视角" + chr(10) + lens + chr(10) * 2 if lens else ""}## 财报原文摘要
{filing_summary[:50000] if filing_summary else "无财报原文数据"}

## ⚠️ 数据铁律（权威锚点，必须逐字使用，禁止改动任何数字、单位、正负号；与下表矛盾的自有知识一律作废）  # noqa: E501
{wind_anchor if wind_anchor else "（无 Wind 锚点数据）"}
**财年统一规则（通用）**：全报告财务引用必须以**最新财年（上表最后一个财年）**为当期基准；禁止把其他财年的数字当作当期值引用；同一指标全报告只允许一个数值；统一使用 **IFRS 归母口径**，禁止混用 Non-IFRS/经调整口径。  # noqa: E501
{fiscal_chapter_rule}

## 结构化数据
{wind_anchor[:3000] if wind_anchor else "无 Wind 数据"}

## 搜索补充
{search_summary[:2000] if search_summary else "无搜索结果"}

## 已完成章节
{prev_summary[:2000] if prev_summary else "（这是第一个章节）"}

## 输出要求
1. 使用 Markdown 格式
2. **必须包含以下三个小节（标题必须完全匹配）**：
   - `## 结论要点` — 本章核心结论，3-5条要点
   - `## 详细情况` — 详细分析内容，包含数据支撑
   - `## 证据与出处` — 数据来源表格，引用具体来源
3. ⚠️ **标题必须使用 H2（##），绝对禁止使用 H3（###）**
4. 引用具体数据和来源（如 [来源: Wind]、[来源: 10-K]）
5. 数据不足时明确标注「⚠️ 数据不足」
6. 保持客观中立，不做过度推测

## 🔢 PGNB 数字回填铁律（最重要——违反即重写）
**禁止直接写出任何财务数字**。需要引用 Wind 锚点表中的指标时，用**占位符**：
- 最新财年值：`[{{营业收入}}]`（系统自动回填为 FY2025 767.20 亿元）
- 指定财年：`[{{总资产:2023}}]`（系统回填为 FY2023 841.63 亿元）
- **派生指标（程序计算，禁止自算）**：`[{{净利率}}]`/`[{{营业利润率}}]`/`[{{ROE}}]`/
  `[{{资产负债率}}]`/`[{{营收同比}}]`/`[{{净利同比}}]`（系统按锚点计算百分比）
- 可用的指标名（Wind 锚点表键）：营业收入 / 营业利润 / 归母净利润 /
  经营活动现金流量净额 / 总资产 / 年负债合计 / 年所有者权益合计
- **正负号由系统按锚点保留**（如亏损 `[{{归母净利润}}]` 会回填为负值，你不得自行写正/负）
- 非锚点指标（运营数据等）无法用占位符 → 写 `[数据待核:指标名]` 或基于事实表定性描述，
  **不得编造具体数字**

## 📅 时间表述铁律（R7-⑤，违反即重写）
**禁止使用模糊时间词**：当前 / 目前 / 最近 / 近期 / 近年 / 本年度（单独使用）。
必须用**具体财年**：FY2025 / FY2024 / FY2023（或"2025财年"）。

## 🏗️ 章节骨架（必须逐字保留，禁止增删改）  # noqa: E501
- **本章固定标题**：`{chapter_title}`（不得自造其他标题，尤其**禁止输出 `# 第N章` 形式的 H1 标题**）
- **H1 铁律**：全文**只允许 0 个 H1（#）**——你输出的就是章节正文，章节标题由组装层统一添加
- **详细情况下的固定子节**（必须逐字使用，可在其后补充子节）：
{skeleton_lines}

## 格式示例
```
## 结论要点
1. **要点一**：xxx
2. **要点二**：xxx

## 详细情况
### 1. xxx
详细分析内容...

## 证据与出处
| 编号 | 核心事实 | 信息来源 | 说明 |
|:---:|---------|---------|------|
| 1 | xxx | [来源: Wind] | xxx |
```
"""
    return prompt
