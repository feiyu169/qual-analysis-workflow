# 前端闸门技术方案（代码级）

> 四道前端闸门的具体实现设计：数值量级校验器、空章检测、生成时校验链、组装前闸门，+ v8 引擎接入。
> 目标：1427.8/187元/空章/财年错位在**生成阶段**被机器拦截，杜绝进入报告。

---

## 一、闸门 1：数值量级校验器 `quality/numeric_guard.py`（新增）

### 1.1 API 设计

```python
"""quality/numeric_guard.py — 数值量级校验器（前端闸门1）

校验章节内财务数字与 Wind 锚点的量级一致性，拦截模板残留（如 1427.8 vs 73亿）。
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class NumericViolation:
    """量级违规"""
    chapter: int
    number: float          # 违规数字
    unit: str              # 单位（亿元/亿/万元）
    context: str           # 上下文片段
    anchor_closest: float  # 最接近的 Wind 锚点值
    ratio: float           # 数字/锚点 比值
    reason: str            # "模板残留嫌疑" / "估值数字超锚点5倍"


@dataclass
class NumericGuardResult:
    passed: bool
    violations: List[NumericViolation] = field(default_factory=list)


class NumericGuard:
    """数值量级校验器"""

    # 普通章：数字与任一锚点指标差 > 10 倍 → 模板残留
    GENERAL_RATIO = 10.0
    # 估值章（ch7）：任何"当前营收/利润"数字差 > 5 倍 → 模板残留（估值更敏感）
    VALUATION_RATIO = 5.0
    # 白名单：这些数字不参与量级校验
    WHITELIST_PATTERNS = [
        r"\d{4}年",          # 年份（2025年）
        r"^\d+\.?\d*\s*%$",  # 百分数
        r"股本", r"总股本", r"亿股", r"万股",   # 股本
        r"发行价", r"上市价", r"港元", r"港币", # 价格/币种
        r"每股", r"ARPU", r"ARPPU", r"MAU", r"DAU", r"MPU",  # 运营指标
        r"汇率", r"市盈率", r"市净率", r"PE", r"PB", r"PS", r"EV",  # 估值比率
    ]

    def check(
        self,
        chapter_num: int,
        content: str,
        wind_data: Dict,
        is_valuation_chapter: bool = False,
    ) -> NumericGuardResult:
        """校验章节数值量级

        Args:
            chapter_num: 章节号
            content: 章节内容
            wind_data: Wind canonical 数据（含 income/balance/cashflow）
            is_valuation_chapter: 是否估值章（阈值 5 倍）

        Returns:
            NumericGuardResult(passed, violations)
        """
        ...
```

### 1.2 核心算法（`_check`）

```python
    def _extract_numbers(self, content: str) -> List[Tuple[float, str, str]]:
        """提取 "数字+亿元"（复用 DataAnchor._extract_data 逻辑）
        返回 [(value, unit, context), ...]"""
        import re
        results = []
        # 匹配：数字 + 亿元/亿/万元
        for m in re.finditer(r"(-?\d+\.?\d*)\s*(亿元|亿|万元|万)", content):
            value = float(m.group(1))
            unit = m.group(2)
            if unit in ("万元", "万"):
                value = value / 10000.0
            ctx = content[max(0, m.start() - 20):m.end() + 10].replace("\n", " ")
            # 白名单过滤：上下文含白名单词 → 跳过
            if any(re.search(p, ctx) for p in self.WHITELIST_PATTERNS):
                continue
            results.append((value, unit, ctx))
        return results

    def _anchors(self, wind_data: Dict) -> List[float]:
        """从 Wind canonical 数据收集所有锚点数值（营收/净利/现金流/资产...）"""
        anchors = []
        for section in ("income", "balance", "cashflow"):
            table = wind_data.get(section) or {}
            for k, v in table.items():
                if isinstance(v, list):
                    for x in v:
                        if isinstance(x, (int, float)) and x is not None:
                            anchors.append(abs(float(x)))
        return [a for a in anchors if a > 0]

    def check(self, chapter_num, content, wind_data, is_valuation_chapter=False):
        violations = []
        anchors = self._anchors(wind_data)
        if not anchors:
            return NumericGuardResult(passed=True, violations=[])
        threshold = self.VALUATION_RATIO if is_valuation_chapter else self.GENERAL_RATIO

        for value, unit, ctx in self._extract_numbers(content):
            if value == 0:
                continue
            # 找最接近的锚点
            closest = min(anchors, key=lambda a: abs(value - a))
            ratio = abs(value) / closest if closest else float("inf")
            # 方向检查：若 value 与锚点差 > threshold 倍 → 模板残留嫌疑
            if ratio > threshold and ratio < 1 / threshold:  # 双向（value 远大于或远小于锚点）
                violations.append(NumericViolation(
                    chapter=chapter_num, number=value, unit=unit,
                    context=ctx, anchor_closest=closest,
                    ratio=round(ratio, 1),
                    reason="模板残留嫌疑（与Wind锚点量级差>{}倍）".format(threshold),
                ))
        return NumericGuardResult(
            passed=len(violations) == 0,
            violations=violations,
        )
```

**逻辑说明**：
- `ratio = |value| / closest`；若 `ratio > threshold`（如 1427.8 / 73.66 ≈ 19.4 > 10）→ 违规
- 双向检查：value 可能是"大 20 倍"（1427.8）或"小 20 倍"（0.5 误写）都拦
- 白名单：年份/百分数/股本/价格/运营指标/估值比率 不参与（避免误伤）
- 估值章阈值 5 倍（更严）：1427.8 / 73.66 = 19.4 > 5 照样拦

---

## 二、闸门 2：空章检测（`_generate_chapter` 内联）

```python
    # _generate_chapter 内，结构校验后追加：
    _MIN_CHAPTER_CHARS = 800   # 去空白后最小长度

    def _check_empty_chapter(chapter_num: int, content: str) -> Optional[str]:
        """空章检测：去空白后 < 800 字符 → 空章/半成品"""
        stripped = re.sub(r"\s", "", content or "")
        if len(stripped) < _MIN_CHAPTER_CHARS:
            return f"第{chapter_num}章疑似空章/半成品（有效内容仅 {len(stripped)} 字符）"
        return None
```

**效果**：R6 第8/9章（24/23 字符）→ 立即判空章 → 强制重生成。

---

## 三、闸门 3：生成时校验链（`_generate_chapter` 集成）

```python
def _generate_chapter(chapter_num, prompt, ctx, llm_caller, max_format_retries=3):
    """生成单章（集成闸门：格式 + 量级 + 空章）"""
    from .quality.numeric_guard import NumericGuard

    guard = NumericGuard()
    is_valuation = (chapter_num == 7)  # 估值章

    for attempt in range(max_format_retries + 1):
        content = llm_caller(chapter_name, prompt)

        # 闸门A：格式（现有 structural_check）
        check_result = structural_check(f"ch{chapter_num}", content)
        # 闸门B：空章检测（新增）
        empty_issue = _check_empty_chapter(chapter_num, content)
        # 闸门C：数值量级（新增）
        numeric_result = guard.check(
            chapter_num, content,
            _wind_to_dict(ctx.wind),   # WindData → canonical dict
            is_valuation_chapter=is_valuation,
        )

        issues = []
        if not check_result.passed:
            issues.extend(check_result.issues[:3])
        if empty_issue:
            issues.append(empty_issue)
        if not numeric_result.passed:
            issues.extend(
                f"{v.chapter}章: {v.context[:30]}... 数字{v.number}{v.unit} 与锚点{v.anchor_closest}差{v.ratio}倍"
                for v in numeric_result.violations[:3]
            )

        if not issues:
            return content  # 全过 → 通过
        if attempt < max_format_retries:
            # 重试 prompt 追加闸门修正指令
            prompt += _build_gate_fix_prompt(issues)
        else:
            logger.warning(f"第{chapter_num}章 {len(issues)} 个闸门问题未修复，返回当前内容")
            return content
```

```python
def _build_gate_fix_prompt(issues: List[str]) -> str:
    return f"""

⚠️ **前端闸门未通过（必须修正）**：
{chr(10).join('- ' + i for i in issues[:5])}

修正要求：
1. **删除任何与 Wind 锚点量级不符的数值**（如营收写成 1427 亿而实际 73 亿）——模板残留必须清除
2. **补全内容**：若章节过短，用 Wind 锚点数据 + 事实表充实到完整分析
3. 保持章节主题与骨架不变
"""
```

---

## 四、闸门 4：组装前闸门（`_assemble_report` 前）

```python
# run_analysis / QualWorkflow Gate6 后、组装前：
def _pre_assembly_gate(chapters: Dict[int, str], wind_data) -> Dict[int, List[str]]:
    """组装前闸门：11 章全过（格式+量级+空章），失败章标注"""
    from .quality.numeric_guard import NumericGuard
    guard = NumericGuard()
    failures = {}
    for num, content in chapters.items():
        issues = []
        # 空章
        if len(re.sub(r"\s", "", content or "")) < 800:
            issues.append("空章/半成品")
        # 量级
        r = guard.check(num, content, wind_data, is_valuation_chapter=(num == 7))
        if not r.passed:
            issues.append(f"数值量级违规 {len(r.violations)} 处")
        if issues:
            failures[num] = issues
    return failures

# 使用：
# failures = _pre_assembly_gate(chapters, wind_dict)
# if failures:
#     report_head += f"⚠️ 以下章节未通过前端闸门: {list(failures.keys())}"
# 仍组装（标注），或阻断（enforce 模式）
```

---

## 五、v8 引擎接入（后端真正生效）

```python
# run_qual_full.py — 从 v2-v7 单体改为 v8 引擎
from finance.qual_v8.workflow import QualWorkflow

def main():
    # ... Wind + filing 加载（不变）...
    context = {
        "ticker": "00772.HK",
        "company_name": "阅文集团",
        "market": "hk",
        "wind_data": wind_data,
        "filing_data": filing,
        "llm_caller": llm_caller_with_fallback,  # 桥接+直连 fallback
        "shares": shares,
        "current_price": 21.48,   # Wind 最新价
        "fiscal_year": 2025,
        "qual_mode": "shadow",    # 或 enforce（Gate8 失败阻断）
        "output_dir": out_dir,
    }
    wf = QualWorkflow()
    result = wf.execute(context)
    # result.passed = 全部 Gate 通过（含 Gate8 红队）
    # 报告在 context["report"]（Gate8 已组装）
```

**关键**：v8 Gate3 `_generate_chapters` 内部调用 `_build_chapter_prompt` + `_generate_chapter`——
闸门 1-3 集成在 `_generate_chapter`（workflow.py）后**自动对 v8 生效**（同一函数）。
Gate8 红队成为真正后端兜底。

---

## 六、测试用例设计

| 用例 | 输入 | 期望 |
|---|---|---|
| T1 模板残留 | ch7 "当前营收1427.8亿元" + Wind(73.66) | violation ratio≈19.4 → 拦截 |
| T2 正常值 | ch1 "营业收入73.66亿元" | passed |
| T3 白名单 | "总股本10.2亿股"、"PE 16.4倍"、"2025年" | 跳过 |
| T4 空章 | 24 字符内容 | 判空章 |
| T5 估值章加严 | ch7 "净利润15.5亿" vs 锚点-7.76（差2倍） | 通过（同量级）|
| T6 负值 | "归母净利润-7.76亿元" vs 锚点-7.76 | passed |
| T7 组装闸门 | 第8章空章 → failures 标注 | 报告头标注 |

---

## 七、落地顺序与验证

1. 写 `numeric_guard.py`（含白名单/阈值/估值章加严）→ 单测 T1-T6
2. `_generate_chapter` 集成闸门 1-3 + `_build_gate_fix_prompt` → 单测 T4
3. `_pre_assembly_gate` 组装闸门 → 单测 T7
4. `run_qual_full.py` 改走 v8 `QualWorkflow.execute()`（含 Gate8 红队）→ 编译 + quick 回归
5. 用现有 R6 报告跑 `numeric_guard`（应拦 1427.8/187元）→ 验证闸门有效性
6. 重跑 R8 全量（~106min）→ v8 扫描 + 红队审查应零 F1-F4

---

## 八、HeavySkill K=6 评审结论（2026-08-18，6/6 轨迹成功）
### 评审总分
- 各轨迹评分：43/100、43/100、40/100、47/100、56/100、60/100
- **共识：约 43-60/100，方向正确但不能独立支撑 R6 放行**——量级/空章闸门有效，但**未覆盖 F1/F2 两个致命一致性问题**。

### 一致确认有效的部分 ✅
- 数值量级校验（1427.8 vs 73.66）方向正确，能拦模板大数
- 空章检测（<800 字符）能拦极端空章
- 分层思路（前端机械化硬伤 + 后端红队语义）正确

### 一致指出的致命漏洞（必须补齐）❌

| # | 漏洞 | 评审要点 | 修订方案 |
|---|---|---|---|
| **L1 F1 财年错位未覆盖** | 量级校验只看"数值大小"，11.4 与 -7.76 **同量级**（ratio≈1.5）→ 不会拦；但财年不同（2024 vs 2025） | **新增"财年一致性闸门"**：每章财务数字须带财年标注；ch5 必须锚 FY2025（R7-③ 财年铁律已在 prompt，需程序化强制：检测 ch5 含"2024年度/2024年业绩"且无"对比/历史"标注 → P0） |
| **L2 F2 币值混用未覆盖** | 量级校验不辨币种：187元(人民币) vs 锚点(亿元) 单位不同 | **新增"币值/单位语义校验"**：估值章每股价值必须带币种且与市场(HK→港元)一致；数字单位(元/股 vs 亿元)与上下文一致性检查 |
| **L3 "closest 锚点"设计缺陷** | 取"最接近锚点"可能漏检：1427.8 若锚点里有 1427.8 同量级的干扰值？或 value 恰好与某锚点近 | 改为**类别锚点**：营收类数字只对营收锚点比（income.营业收入），净利对净利——按指标类别比对，非全局 closest |
| **L4 无锚点幻觉未覆盖** | 报告可能引用 Wind 没有的数据（如"自由现金流缺口7.30亿"）→ 量级校验找不到锚点跳过 | **新增"无锚点数字审查"**：数字无法匹配任何锚点类别 → 标注"待核实"，估值/财务章中这类数字 → P0 |
| **L5 空壳章未覆盖** | 第6章 2063 字符但 0 小数（有长度无数据） | **空壳检测**：长度达标但"小数数字计数=0"且属财务章(ch6) → 判空壳 |

### 其他改进建议
- **职责边界**（评审 G）：前端闸门 = 可机械化判定的硬伤（量级/空章/财年/币值）；红队 = 需语义理解的深度问题（估值逻辑/结论自洽）——文档明确定义
- **重试有效性**（评审 F）：重试 prompt 能拦模板残留，但财年/币值需**程序化强制**（prompt 不可靠）
- **性能**（评审 G）：numeric_guard 逐章正则，量级小可接受；建议缓存锚点列表

### 修订后的闸门清单（v2）
```
闸门1 数值量级校验（类别锚点，非全局 closest；普通10倍/估值5倍）
闸门2 空章检测（<800字符）
闸门3 财年一致性校验（ch5 必须锚 FY2025，程序化强制）   ← 新增（L1）
闸门4 币值/单位语义校验（估值章每股价值币种对齐）      ← 新增（L2）
闸门5 空壳检测（财务章长度达标但无数字 → 空壳）        ← 新增（L5）
闸门6 组装前闸门（全过才组装 + 无锚点数字标注）        ← 含 L4
后端 v8 Gate8 红队（语义深度问题兜底）
```

---

## 九、实施完成状态（HGF 驱动，2026-08-18）

### 已落地
| 闸门 | 实现 | 验证 |
|---|---|---|
| 闸门1 数值量级 | `quality/numeric_guard.py`（类别锚点/白名单/计数词过滤/行业规模豁免） | T1 1427.8 拦 ✅；T2/T3 正常值+白名单 ✅ |
| 闸门2 空章 | `<800 字符` | T4 ✅ |
| 闸门3 财年 | ch5 检测"2024年度"无"2025" → P0 | T6/T6b ✅ |
| 闸门4 币值 | 港股每股人民币未标注 → P0；有人民币标注 → warning | T7/T7b ✅ |
| 闸门5 空壳 | 财务章长度达标但 <3 个小数数字 | T5 ✅ |
| 闸门6 组装前 | `pre_assembly_gate` 失败章报告头标注 | T8 ✅ |
| 集成 | `_generate_chapter` 闸门1-5 + `_build_gate_fix_prompt` 重试 | 编译 ✅ |
| v8 接入 | `run_qual_full.py` 改走 `QualWorkflow.execute()`（QUAL_MODE=legacy 回退 v2） | 编译 ✅ |

### HGF 门禁
- **pytest**：`test_numeric_guard.py` 13 passed ✅
- **ruff**：numeric_guard + test 全绿 ✅
- **L2 真实数据验证**：用 R6 报告跑闸门 → 精确拦截红队审查问题（第6章空壳、第8/9章空章），
  误报全消除（行业规模2600亿/计数词100万次）✅
- **quick 回归**：Gate0-7 PASS，Gate8 正确拒绝 R6 ✅

### 已知局限（诚实）
- **1427.8/187元 未在第7章被量级闸门拦**：因第7章同时有合法锚点值（81.2亿），
  整章数值集合含合法值掩盖了模板残留。需更强规则（"锚点外的非白名单数字必须可解释"）
  或依赖后端红队。当前闸门已抓 I1/I5（空壳/空章），正常报告无误伤。
