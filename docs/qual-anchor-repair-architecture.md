# 架构方案：锚点驱动的确定性数值修复层（ADVC）

> 针对 qual v8 买方定性分析工作流中"LLM 数值转写错位（如 1031.63→31.63）→ Gate4 拦截 → LLM patch 反复产错 → 回滚死循环 → 报告无法产出"的根本性解决方案。
> 原则：**值类问题（数字 vs 锚点）从 LLM 职责中整体移出**——它是"字符串变换 + 锚点验证"的确定性任务，正确性由程序保证，LLM 只保留结构/表述/逻辑类修复。

---

## 0. 问题本质诊断（基于源码核实）

| 环节 | 现状 | 缺口 |
|---|---|---|
| Gate3 `numeric_guard.check_numeric` | 类别锚点 + 10x/5x 量级粗筛，只判不修 | 31.63 对最近锚点 841.63 ratio≈26.6 会被拦，但拦截后走 LLM 重试修复 |
| `_generate_chapter` 重试 | `_build_gate_fix_prompt` 把数值修复交给 LLM | LLM 对数值不可靠，重试 3 次仍可能产错 |
| Gate4 `validate_chapter_any_fy` | 1% 容差、多财年，fail-closed，只判不修 | `_extract_data` **last-wins**（`data[k]=value` 覆盖）：同指标多处出现时前面错值被后面合法值掩盖 → 漏检 |
| `fix_chapter`/`_find_number_context` | 已存在但脆弱：latest-FY-only + `str.replace(str(value))`，无签名/无唯一性/无 span | 不可用于生产修复，应废弃 |
| `review_repair_loop._repair_chapters` | LLM patch + validators，值类问题也进 LLM prompt | LLM 反复产错 → `_numeric` 校验回滚 → 收敛早停 → Gate4 失败；T3 类问题（无签名幻觉）也被喂给 LLM 空耗 |
| `normalize_values.py`（B5-2） | parse_number_with_unit / unit_error_detect / verify_value_against_source 已建 + 有测试 | **未接线**：workflow 全链路无 import |

核心不对称：**checker 强（确定性拦截）、fixer 弱（唯一手段是 LLM）**。修复正确性必须从"LLM 自觉"迁移到"程序可证"。

---

## 1. 核心架构（三层）

### 层 0 — 错位签名检测原语（增强 `normalize_values.py`，纯函数、无 DataAnchor 依赖）

把"值 vs 锚点集"的关系判定做成纯函数，可独立单测：

```python
@dataclass
class AnchorDeviation:
    pattern: str          # "exact" | "x10" | "x100" | "x1000" | "x10000"
                          # | "/10" | "/100" | "/1000" | "/10000"
                          # | "prefix_drop" | "digit_typo"
    anchor_value: float
    fiscal_year: int | None
    strength: str         # "high"（×10^n、prefix_drop≥2位）| "medium" | "low"（单字 typo）

def anchor_deviation(value: float,
                     anchors: list[tuple[float, int | None]],
                     tolerance: float = 0.02) -> list[AnchorDeviation]:
    """纯函数：错位签名检测。返回 0..n 个候选（>1 = 歧义）。"""
```

检测算法（见 Q3 签名设计）。所有判定在**单位归一（万元/亿/万亿→亿）后**进行，复用 `parse_number_with_unit`。

### 层 1 — 确定性修复引擎（新模块 `tools/finance/qual_v8/anchor_repair.py`）

唯一的新组件；无任何 LLM 调用。职责：提取 → 分类 → 三档处置 → 全章 re-validation → 审计日志。

```python
@dataclass
class RepairFix:
    metric: str          # canonical key
    old_value: float
    new_value: float
    pattern: str         # 错位签名
    fiscal_year: int | None
    span: tuple[int, int]      # 精确 span（start, end）
    strength: str
    sentence: str              # 审计上下文

@dataclass
class UnresolvedValue:         # T3 证据清单
    metric: str
    value: float
    reason: str                # "no_signature" | "ambiguous" | "cross_metric_hint" | "fy_conflict"
    detail: str

@dataclass
class ChapterRepairResult:
    content: str
    fixes: list[RepairFix]
    unresolved: list[UnresolvedValue]
    changed: bool

def repair_chapter_values(chapter_num: int, content: str, anchor: DataAnchor,
                          *, low_confidence: bool = False) -> ChapterRepairResult:
    """单章确定性清洗：提取 → 分类 → T1/T2 替换 → 全章 re-validation → 审计。"""

def sweep_all_chapters(chapters: dict[int, str], anchor: DataAnchor) -> SweepResult:
    """全局清洗（所有章节一次过）。关键：跨章一致性问题在同一次 sweep 内消解，
    避免 ch6 修好后 ch0 还挂着旧值 → 被单调守卫误回滚。"""
```

### 层 2 — 接线点（两处既有代码增强）

1. `workflow.py::_generate_chapter`：生成后插入**强制清洗层**（clean-then-check，见 Q2）。
2. `review_repair_loop.py::_repair_chapters`：**确定性优先、LLM 降级**（见 Q4）。

---

## 2. 分问题设计

### Q1 程序化数值修复（何时安全替换 vs 只标注；优先级）

**触发条件（T1 高置信自动替换，全部满足才动手）：**

1. **指标绑定**：数字被提取为 canonical 指标（总资产/营收/净利润…），非比率（毛利率）、非百分比、非运营指标（用户数/ARPU——无锚点自然跳过）。
2. **单位归一后比较**：万元/亿/万亿 经 `parse_number_with_unit` 归一为亿（覆盖 亿↔万 = ×10^4、万亿↔亿 = ×10^4 错位）。
3. **唯一强签名**：`anchor_deviation` 返回恰 1 个 high-strength 候选（×10^n / ÷10^n 或 prefix_drop 丢 ≥2 位）。>1 候选 → 用 `attribute_value` 的 FY 归因消歧；仍歧义 → T3。
4. **上下文无矛盾**：句中显式 FY 标注不指向其他锚点（例：句标 FY2024、错位候选是 FY2025 锚点 → 降档 T3 或按 FY 重选）。
5. **不在排斥语境**：复用 `_extract_data` 的 R7-①（变化量/成分量："下降2.5亿元"、"含减值约5.4亿元"）+ `numeric_guard.WHITELIST_CONTEXT`（倍/比率/每股/市场规模…）。
6. **span 精确定位**：只替换数字 token 本身（保留原小数位/千分位格式），绝不用 `str.replace(str(value))`。

**自证机制（防误替换的杀手锏）**：替换后对**整章**重跑 `validate_chapter_any_fy`，必须通过。原值错（fail）→ 替换值对（pass）→ 修复与全部锚点一致，正确性可证。替换后仍 fail 的其它问题进下一轮 sweep 或 T3。

**何时只标注（T3）**：无签名（幻觉值 999.99，与任何锚点无变换关系）、多候选歧义、跨指标暗示（"总资产31.63亿"恰等于货币资金锚点 → 疑似指标名写错，给 reviewer 提示，不自动修）、FY 冲突。T3 产出 `UnresolvedValue` 证据清单，**绝不喂给 LLM**（见 Q4）。

**优先级（同一轮内固定顺序）**：
1. 生成时清洗（`_generate_chapter` 内，T1/T2）
2. 修复循环轮首全局 sweep（T1/T2）
3. LLM patch（仅非值类问题）
4. 数值 validator 后置兜底（`_numeric`，保持 fail-closed）
5. 组装闸门救援 sweep（可选，幂等）
6. fail-closed（Gate4）

### Q2 生成后数值清洗（强制清洗层，clean-then-check）

**是——必须接线**。位置：`_generate_chapter` 中 `clean_ai_artifacts` 之后、`structural_check` 之前：

```
content = caller(...)
content, _ = clean_ai_artifacts(content)
content, repair = repair_chapter_values(chapter_num, content, anchor)   # 新：强制清洗层
check_result = structural_check(...)   # 之后照旧：结构 + 闸门 + 财年校验
```

**清洗 vs 重试的决策表：**

| 清洗结果 | 闸门结果 | 决策 |
|---|---|---|
| 有 fixes（T1/T2） | 通过 | **接受，不重试**（值已与锚点一致，重试只会再引入风险；审计记录） |
| 有 fixes | 仍失败（非值类） | 按现有逻辑重试（值类已解决，问题只剩结构/表述） |
| 有 unresolved（T3） | — | 重试时在 prompt 注入 **omit 指令**："上版存在无法自动校正的数值 X（锚点 Y），请**省略该数值或改写为'规模达百亿级'等定性表述**，不得再猜测具体数字" |
| 无 fixes、无 unresolved | 通过 | 接受 |
| 无 fixes、无 unresolved | 失败（非值类） | 现有重试逻辑不变 |

要点：**T3 的重试指令是"省略"，不是"修对"**——LLM 对数值的猜测已证明不可靠，用 omit 打破"写错→回滚→再写错"循环；若重试后仍 T3，保持 fail-closed（Gate4 出精确证据），或按策略开关降级为"内容标注【数据待核】+ 审计"。

### Q3 错位模式检测（签名设计）

在 `anchor_deviation(value, anchors)` 中按优先级判定（数字串 = 去符号/千分位/小数点/尾零后的纯数字串）：

1. **×10^n / ÷10^n（n=1..4）**：`value ≈ anchor × 10^n`（容差 2%，n 取满足的最小数）。覆盖：小数点错位（1031.63→103.163）、单位错位（亿↔万 ×10^4、亿↔万亿 ÷10^4）、零补漏（1031.63→10316.3）。
2. **prefix_drop（前缀丢位）**：value 的数字串是 anchor 数字串的**后缀**且丢失前缀 ≥2 位。覆盖本次事故 1031.63→31.63（"103163" ⊃ 后缀 "3163"，丢 "10"）。丢 1 位视为 digit_typo（弱签名，仅 T3 提示）。
3. **decimal_shift** ≡ ×10^n（无需独立模式，由 1 覆盖）。
4. **digit_typo（弱，仅提示）**：编辑距离 ≤2 且无 1/2 命中 → T3，"疑似笔误，最近锚点 FY2025=1031.63"。

**歧义消解**：恰 1 候选 → 用；多候选 → 句中 FY 标注（`attribute_value` 归因）选锚；仍歧义 → T3。

**示例签名（测试夹具）**：`anchor_deviation(31.63, [(841.63,2023),(827.06,2024),(1031.63,2025)])`
→ `[AnchorDeviation("prefix_drop", 1031.63, 2025, "high")]`；`anchor_deviation(827.06, ...)` → `[("exact", ...)]` 或空（合法值，走 EXACT 分支不动）。

### Q4 防回滚死循环（确定性优先、LLM 降级）

`_repair_chapters` 改造为**分层修复**：

```
_repair_chapters(chapters, issues, llm_caller, wind_data):
    anchor = get_data_anchor(wind_data)
    # 阶段0：确定性清洗（全局 sweep，先于快照——修复不被单调守卫回滚）
    sweep_all_chapters(chapters, anchor)          # T1/T2 修正；T3 收集
    # 阶段1：问题分类
    value_issues, other_issues = _triage_issues(issues)   # 按问题前缀/签名判类
    #   value_issues 已由 sweep 处理；sweep 未消解的（T3）→ 直接进豁免清单（fail-closed 证据），不进 LLM
    # 阶段2：LLM patch 只接收 other_issues（结构/表述/逻辑）
    #   prompt 明示："数值类问题已由系统处理，你只修复结构/表述；禁止输出任何财务数字"
    # 阶段3：apply_patches(validators=[_structural, _consistency, _numeric]) 保持 fail-closed 兜底
```

配套三处调整：

1. **值类问题不进 LLM prompt**：`_triage_issues` 按前缀（`数字锚点`/`[数据合理性]`/`[事实核查]` 中的数值类）分类。LLM 从此不再被要求产数字 → 从根上消除"反复产错"。
2. **T3 立即豁免（带证据）**：现有"同签名 ≥2 轮才豁免"对值类问题太慢且白白耗 2 轮；sweep 判定为 T3 的值类问题第 1 轮即入 `exempted`（附 `UnresolvedValue.reason/detail`），fail-closed 消息从"不匹配任一财年锚点"升级为"无法自动校正 + 原因 + 锚点行 + 建议"。
3. **单调守卫兼容**：sweep 在 `_snapshot_before_round` 快照**之前**执行（或 `_repair_chapters` 内部先 sweep 再自行快照），保证守卫回滚只作用于 LLM 修复、不撤销确定性修复；且 sweep 是全章一次过，跨章连锁（ch6 修好、ch0 仍旧）在同一 sweep 内消解，不会产生"新问题签名"触发误回滚。

**本轮修复轮次数不变**（max_rounds 预算保留），但值类问题通常第 1 轮 sweep 即清零，LLM 调用数显著下降。

### Q5 可验证性（单测 + 回归）

沿用 `test_normalize_values.py` / `test_numeric_guard.py` 的 pytest 约定（ROOT 注入 + 纯函数断言）：

**层0 签名单测**（`test_anchor_deviation.py`）：
- 1031.63→31.63 检出 `prefix_drop`、锚点 1031.63、high；827.06（合法值）→ 无候选/EXACT；
- ×10/÷10/×100/÷100/×1000/×10000 全谱系；999.99（幻觉）→ 无候选；
- 歧义夹具（1.234 vs [12.34, 123.4]）→ 2 候选 → ambiguous；
- 单位归一（"1.03万亿"、"410.2百万"）→ 归一后判定正确；
- 负值（-7.76 vs -77.6）符号归一。

**层1 修复引擎单测**（`test_anchor_repair.py`）：
- 单章：`"小鹏集团总资产31.63亿元，负债合计500亿元"`（500 与负债锚点一致）→ 仅 31.63→1031.63，500 不动；
- **同值不同语境**：`"总资产31.63亿元，货币资金31.63亿元"`（货币资金锚点=31.63）→ 只修总资产绑定处（span + 指标绑定）；
- 历史引用：`"FY2024 总资产 27.06 亿元"` → 修成 827.06 且保留 FY 标注；
- 近似语境：`"约31.63亿"` → 强度降档/按策略处置；
- 幂等：`repair(repair(x)) == repair(x)`；
- **自证**：修复后整章过 `validate_chapter_any_fy`；修复前整章 fail；
- **逐出现值校验**：`"总资产31.63亿元…总资产1031.63亿元"`（last-wins 漏洞）→ 两处均检出、前面错值被修。

**层2 接线集成测试**（`test_generate_clean.py` / `test_repair_loop_no_llm_values.py`）：
- mock LLM 恒输出错值 31.63 的 patch → 断言：确定性修复生效、`fixed_count>0`、循环以 passed 收敛（或 T3 带证据 fail），**LLM prompt 中不含任何值类问题**；
- mock LLM 生成含错位章节 → 清洗层修正 → 闸门通过 → **LLM 只调用 1 次（不触发重试）**；
- 回归金样：全对章节 → 清洗引擎逐字节不变（"合法值不被误替换"的硬保证）；
- 真实 Wind 夹具（小鹏 9868.HK 三财年）埋入各类错位 → 全量修复 + 全量 re-validation 通过。

---

## 3. 文件/函数级改动清单

| 文件 | 改动 | 类型 |
|---|---|---|
| `tools/finance/normalize_values.py` | 新增 `anchor_deviation` + `AnchorDeviation`（纯函数） | 增强 |
| `tools/finance/qual_v8/data_anchor.py` | 新增 `extract_data_spans`（位置保留提取，`_extract_data` 保留为薄封装）；`validate_chapter_any_fy` 内部改用逐出现值（堵 last-wins 漏检）；新增 `repair_transpositions`（调用 anchor_repair）；`fix_chapter`/`fix_all_chapters` 标注 deprecated | 增强 |
| `tools/finance/qual_v8/anchor_repair.py` | 新模块：`repair_chapter_values` / `sweep_all_chapters` / T1/T2/T3 分类 / span 替换 / 全章 re-validation / 审计日志 | **新增** |
| `tools/finance/workflow.py` | `_generate_chapter` 插入清洗层（Q2 决策表）；`_build_gate_fix_prompt` 增加 T3 omit 指令段 | 增强 |
| `tools/finance/quality/review_repair_loop.py` | `_repair_chapters` 分层改造（sweep→triage→LLM-only-non-value→validators）；T3 立即豁免；单调守卫兼容 | 增强 |
| `tools/finance/quality/numeric_guard.py` | 不改语义（仍为前端粗闸门）；`WHITELIST_CONTEXT` 可复用为修复引擎排斥语境 | 复用 |
| 测试 | `test_anchor_deviation.py` / `test_anchor_repair.py` / `test_generate_clean.py` / `test_repair_loop_no_llm_values.py` | **新增** |

---

## 4. 优先级排序

- **P0（本轮，核心闭环）**：层0 签名检测 + 单测 → `extract_data_spans` 重构（含 last-wins 漏洞修复）+ 回归 → `anchor_repair.py` T1/T3 + 自证 re-validation → 接线 `_generate_chapter` 清洗层 → 接线 `_repair_chapters`（sweep + triage + T3 立即豁免）→ P0 集成测试。
- **P1（下轮）**：T2 低置信替换（配置开关，默认关）；FY 上下文歧义消解强化；组装闸门救援 sweep（幂等 + 审计告警）。
- **P2（后续）**：digit_typo 弱签名提示；T3 案例回流为生成 prompt 的负样本（few-shot 反例）；跨指标暗示提示（"疑似指标名写错"）。

---

## 5. 风险与边界

1. **误替换**：T1 五重护栏（指标绑定 + 唯一强签名 + 语境排斥 + span 精确定位 + 全章 re-validation 自证）；默认关闭 T2；修复全程审计日志可回查。**硬保证：修复后的章节必须通过与修复前同一把 fail-closed 校验器**。
2. **多财年歧义**：单候选直用；多候选走 FY 标注归因（复用 `attribute_value`）；仍歧义 → T3，绝不猜测。
3. **字符串语境**：近似前缀（约/近/逾）→ 强度降档；变化量/成分量（R7-① 排除）、比率/百分比/白名单语境（WHITELIST_CONTEXT）一律不碰；同值不同指标靠 span + 指标绑定区分；千分位/小数位格式在替换时保留。
4. **last-wins 漏检**：`validate_chapter_any_fy` 改逐出现值校验后，漏检面消除（这是对既有防线的**增强**，非新机制）。
5. **单调守卫误回滚**：sweep 先于快照 + 全章一次过，确定性修复不参与守卫回滚。
6. **口径/单位漂移**：单位归一（万/亿/万亿）在比较前完成；锚点与内容单位不一致时以归一后为准。
7. **LLM 残余风险**：LLM 仍负责结构/表述修复，理论上 patch 可夹带新数字——由 `_numeric` validator 后置兜底 + sweep 每轮轮首重跑兜住；T3 用 omit 指令而非猜数，杜绝"再写错"。

---

## 6. 与现有防线的关系（复用/增强/新层）

| 现有防线 | 关系 |
|---|---|
| Gate3 `numeric_guard`（10x/5x 量级） | **复用不改**：仍是前端粗闸门；清洗层在其前，故其失败多为非值类或 T3 |
| Gate4 `validate_chapter_any_fy` | **增强**：逐出现值校验（堵 last-wins）；仍是 fail-closed 兜底校验器 |
| `fix_chapter` / `fix_all_chapters` | **废弃**（naive 替换，latest-FY-only，无签名无 span），由 ADVC 引擎取代 |
| FiscalSemantics（`attribute_value` / `validate_fiscal_references`） | **复用**：FY 归因用于歧义消解；财年标注防线不变 |
| `normalize_values`（B5-2） | **增强 + 接线**：新增 `anchor_deviation`；由 ADVC 引擎首次接入生成/修复路径 |
| 修复循环（review_repair_loop） | **增强**：确定性优先、LLM 降级、T3 立即豁免（fail-closed 证据化） |
| `_generate_chapter` 重试 | **增强**：clean-then-check 强制清洗层 + T3 omit 指令 |
| **ADVC 修复引擎（anchor_repair.py）** | **新层**：唯一新组件，纯确定性，值类问题唯一修复方 |
