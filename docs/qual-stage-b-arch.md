# Qual 流水线阶段 B（数据真实性改进）架构设计分册

日期：2026-08-19
性质：阶段 B（B1-B5 工作包）的架构设计分册——分层架构、数据流、规则与验收的**实现级设计**
依据：`docs/qual-expert-suggestions-adjudication.md`（综合审议意见，本次修订唯一依据）+ `docs/qual-implementation-roadmap.md` v1.1（B 阶段工作包）
前置：`docs/qual-loop-fix-design-v3.md`（v3.1 死循环修复，阶段 A 交付基础）
对照源码：`tools/finance/workflow.py`、`tools/finance/fact_extractor.py`、`tools/finance/canonical.py`、`tools/finance/quality/numeric_guard.py`、`tools/finance/qual_v8/`（data_anchor/gate8/mode_manager/gate6/gate0/gate2）、`tools/finance/quality/peer_comparison.py`、`tools/finance/quality_enhancer.py`、`tools/finance/data_repair.py`、`tools/finance/data_context.py`

---

## 0. 设计总则（与综合审议一一对应的锚）

1. **防死循环复发（最高风险）**：B 阶段新增的一切阻断判据必须与 v3.1 单调守卫兼容——"修复验证通过即不再回滚"；合法历史引用场景进回归单测。B1-1 不删 any-fy，只在其上叠加当期锚断言。
2. **跑得完 vs 可信张力**：B1-2 分级阻断默认翻转以 A4（小鹏 ≤60 分钟有界终止）验收通过为前提；翻转后重跑不劣化。
3. **宁可缺失不可杜撰**：页码、无源财务字段、亏损公司 DCF、不可比数据，一律显式标注，禁止 LLM 补值、启发式回填与猜测。
4. **程序化优先**：一切可机器计算的值（目标价、ROIC、FCF、净负债、CAGR）由代码产出并注入，LLM 只做解读与标注。
5. 三处"必须修改"（B1-1 章节级财年语义、B1-2 分级阻断、B4-6 可比重写+数据源化）、两项"转验收"（B4-4、B4-5 后验部分）、B5 两个小包（B5-1 缺失字段处置表、B5-2 数值转写归一预处理器）在本册逐项落实，编号与路线图 v1.1 完全一致。

---

## 1. 阶段 B 分层架构图（B1-B5 位置）

```
┌────────────────────────────────────────────────────────────────────────┐
│ L0  Gate 编排层（qual_v8 状态机，阶段 A 交付，B 只做配置与接线）          │
│   Gate0 数据源验证 → Gate1 类型推断 → Gate2 数据收集 → Gate3 章节写作      │
│   → Gate4 审计修复 → Gate5 质量增强 → Gate6 结论 → Gate7 问题转化          │
│   → Gate8 最终验证 → 记忆存储                                              │
│   A 不变量：fail-closed / deadline / 熔断 threshold=2 / 单调守卫          │
├────────────────────────────────────────────────────────────────────────┤
│ L1  B1 语义与阻断层（B1-1/B1-2/B1-3）                                     │
│   check_fiscal_v2（合并扩展 numeric_guard.check_fiscal，不删 any-fy）      │
│   + CrossChapterValidator（any-fy 保底）→ 接线 Gate8（enforce）            │
│   + mode_manager 分级阻断（per-gate/per-error 级别，A4 后翻转默认）        │
│   + _CHAPTER_WRITE_ORDER 扩至 11 章（ch0/ch10 纳入审计，B1-3）             │
├────────────────────────────────────────────────────────────────────────┤
│ L2  B2 数据真源层（B2a 估值程序化 / B2b 财务 100% Wind）                  │
│   canonical.canonicalize（唯一真源）+ CANONICAL_FIELDS 扩展（B5-1 输入）   │
│   wind_stock_quote → current_price/shares/currency（删硬编码，B2a-1/2）    │
│   extract_dcf_params 专业化 + 亏损降级链 full_dcf→comparable→PE（B2a-3）   │
│   valuation_engine 程序输出 → 注入 ch7/ch10（B2a-4）                       │
│   fact_extractor 移除 financial 提取（B2b-1）+ _reconcile_facts_with_wind  │
│   仲裁扩至全部 canonical（B2b-2）+ data_repair canonicalize（B2b-3）        │
├────────────────────────────────────────────────────────────────────────┤
│ L3  B3 事实表层（多财年化 + 可复核）                                       │
│   3 份年报分组提取（每份独立 fiscal_year）→ MinerU 页码前置验证（B3-2）     │
│   → 程序化合并 3 张单年表（B3-1）→ 批次一致性仲裁（B3-3）                   │
│   → 字段增补：页码/原文片段/置信度/仲裁状态/对比期（B3-2）                  │
├────────────────────────────────────────────────────────────────────────┤
│ L4  B4 验证链层（运营验证 + 行业/结论修正）                                │
│   运营验证链四段：原文正则复核 → 多批次一致 → 交叉披露 → 派生钩稽（B4-1）   │
│   normalize_units 只标不改 + B5-2 预处理器（B4-2/B5-2）                    │
│   行业判定动态化（B4-3）；锚点注入转验收 + 补漏（B4-4）                    │
│   ch10 锚点注入 + 否决项联动，与 Gate6 合并（B4-5）                        │
│   可比矩阵数据源化重写 + 控股股东排除（B4-6）；ROIC/FCF 程序化（B4-7）      │
├────────────────────────────────────────────────────────────────────────┤
│ L5  B5 横切小包（插入 L2/L3/L4 前置）                                      │
│   B5-1 Wind 缺失字段处置表（canonical 字段 × Wind 可用性，B2b 输入）        │
│   B5-2 数值转写归一预处理器（B4-1 复核链配对）                             │
└────────────────────────────────────────────────────────────────────────┘

数据流向（左→右）：Wind/年报 原始数据 → L5 归一 → L2 真源化/程序化
→ L3 事实表 → L4 验证链 → L1 语义与阻断 → L0 Gate 编排 → 报告
```

**分层责任划分**

| 层 | 责任 | 禁止 |
|---|---|---|
| L0 Gate 编排 | 状态机推进、超时/熔断/重试、人工确认 | 禁止改动 A 的 fail-closed/deadline/熔断机制本身 |
| L1 语义阻断 | 财年语义判定、错误分级、阻断/放行决策 | 禁止自行改数（只判不改）；禁止引入不可满足的阻断判据 |
| L2 数据真源 | 字段归一、权威仲裁、程序计算 | 禁止 LLM 产出财务数值、禁止硬编码股价/参数、禁止启发式回填 |
| L3 事实表 | 提取、页码验证、合并、可复核 | 禁止 LLM 编造页码/原文、禁止前批值补当前批、禁止静默覆盖 |
| L4 验证链 | 复核、钩稽、可比、结论联动 | 禁止自动修正单位（只标不改）、禁止自选可比公司 |
| L5 横切 | 单位/数值确定性归一、无源字段处置 | 禁止改变数值语义（只归一、不推断） |

---

## 2. 章节-数据源-校验矩阵（11 章）

数据源缩写：**W**=Wind（canonical 真源）、**WQ**=Wind quote（行情）、**FY**=年报原文（MinerU 解析）、**FAC**=事实表（B3 多财年化后）、**PEER**=可比矩阵（B4-6 数据源化后）、**VE**=估值引擎程序输出。

| 章 | 标题 | 主数据源 | 辅助源 | 财年策略（B1-1） | 数值闸门（numeric_guard） | 特殊校验 |
|---|---|---|---|---|---|---|
| 0 | 概览 | W + 全章节综合 | VE | default | numeric/empty | 首尾一致性断言（与 ch10 评级/目标价一致）；纳入审计（B1-3） |
| 1 | 公司业务 | FY（业务分部） | FAC、W 收入构成 | default | numeric/empty | 分部收入之和≈Wind 营业收入（钩稽 warning） |
| 2 | 行业 | W（行业/宏观）、PEER | FY | default | numeric/empty | 行业判定动态化（B4-3）；可比表数据源化（B4-6）；数据年份标注 |
| 3 | 商业模式 | FY（定性） | FAC | default | numeric/empty | 运营指标只引 FAC（带页码/置信度） |
| 4 | 最近变化 | FY（重大变化） | W 同比 | **lenient（放行历史引用）** | numeric/empty/fiscal(lenient) | YoY 对比引用须 FY 标注（缺失→warning 可升级） |
| 5 | 经营表现 | **W（100%）** | FAC 运营辅助 | **strict（当期=latest 阻断）** | numeric/empty/shell/fiscal(strict) | 当期锚断言：写 prior 财年当期→Critical；无 FY 标注当期数字须命中 latest 锚点 |
| 6 | 财务健康 | **W（100%）**（BS/CF） | B5-1 缺失处置 | **lenient（放行历史引用）** | numeric/empty/shell/fiscal(lenient) | 三财年表合法；无源字段（有息负债等）显式标注"未披露" |
| 7 | 估值 | **WQ + VE（100% 程序）** | PEER、W 财务 | **strict（当期=latest 阻断）** | numeric(5倍)/empty/fiscal(strict)/**currency** | 目标价=程序输出（含降级链）；每股价值币种对齐市场；当前价/股本动态取 |
| 8 | 管理层 | FY（管理层/治理） | W 股权 | default | numeric/empty | 回购/股息等数字须带财年标注 |
| 9 | 风险 | FY（风险） | FAC | default | numeric/empty | 否决项清单→Gate6 联动输入（B4-5）；监控指标引 FAC |
| 10 | 决策 | VE + W 锚点表 + RATING_VALUATION_MAPPING | 全章节 | default | numeric/empty | 评级=规则输出+override 留痕；否决项未消除不得买入/增持（B4-5）；目标价偏差 ≤20%（Gate6）；纳入审计（B1-3） |

**矩阵实现要点**
- 财年策略表落为常量 `FISCAL_CHAPTER_POLICY = {5: "strict", 7: "strict", 4: "lenient", 6: "lenient"}`，其余章节默认 "default"（当期锚断言阻断 + 历史引用强制标注）。
- 校验接线：单章写作后调 `check_chapter_gates`（闸门 1-5，ch0/ch10 补入）；组装前 `pre_assembly_gate` 全 11 章；Gate8 追加"财年语义校验（enforce）"步骤（见 §3）。
- ch5/ch6 数据源从"FY 提取"切换为"W 100%"后，numeric_guard 的 Wind 锚点天然可全覆盖——这是 B2b 对 B1 校验的增益，非矛盾。

---

## 3. 当期财年语义校验两级规则设计（B1-1）

### 3.1 设计目标与约束（综合审议裁决落实）

- 当期锚断言全章节阻断（修复专家 Top1 的"Gate8 无当期语义"）；
- 历史引用上下文豁免（不误杀 ch6/ch7 合法历史引用 → **不删 any-fy**，其保护场景进回归单测）；
- 章节调参：ch5/7 从严、ch6/4 放行；
- **合并扩展** `numeric_guard.check_fiscal`（吸收其 ch4/ch5 现有启发式），不另起炉灶；
- 接线 Gate8，且与 v3.1 单调守卫兼容（阻断判据"修复后可满足"）。

### 3.2 两级规则定义

```
规则 0（元规则：当期锚来源）
  当期锚 latest_fy = wind_data["_year_labels"]["财年"][-1]        # 单一来源，禁硬编码年份
  prior_fy        = latest_fy - 1
  当期语境 = 数字所在句无显式 FY 标注，或标注 == latest_fy
  历史引用 = 数字带显式 FY 标注且 FY < latest_fy

规则 1（章节级调参，FISCAL_CHAPTER_POLICY）
  strict  = {5, 7}   ch5 经营表现 / ch7 估值：当期语境数字必须命中 latest 锚点（±1%），
                     历史引用必须同时满足规则 2 全部豁免条件，否则 Critical（enforce）
  lenient = {4, 6}   ch4 最近变化 / ch6 财务健康：当期语境数字必须命中 latest 锚点；
                     历史引用仅要求 FY 标注 + 对比/趋势语境（豁免条件 a+b），
                     数字命中该 FY 锚点（豁免条件 c）缺失 → warning（可升级 Critical）
  default = {0,1,2,3,8,9,10}：当期语境阻断；历史引用强制 FY 标注（豁免条件 a+b），
                     命中锚点（条件 c）缺失 → warning

规则 2（历史引用上下文豁免三元组，三者缺一降级）
  a) 显式 FY 标注：数字紧跟 "FY20XX / 20XX年 / 20XX年度 / （20XX）" 等
  b) 对比/趋势语境：句中含 同比/环比/上年/历史/对比/较 FYx/过去三年/趋势/累计 等词
  c) 数字命中该 FY 锚点：|value − anchor(FY标注) | / anchor ≤ 1%
  缺失级别：strict → Critical；lenient/default → warning（warning 可在多章累计后升级）

规则 3（快捷失败路径，保留 check_fiscal 现有启发式）
  prior_refs 计数 > 0 且 latest_refs 计数 == 0（全章只有 prior 无 latest）→ 直接 fail，
  语义="本章把历史财年当当期"。strict 章节必 fail；lenient 章节降为 warning（三财年表合法）。
```

### 3.3 实现设计：合并扩展 check_fiscal

```python
# numeric_guard.py（合并扩展，非新增模块）
FISCAL_CHAPTER_POLICY = {5: "strict", 7: "strict", 4: "lenient", 6: "lenient"}

def check_fiscal_v2(self, chapter_num: int, content: str, wind_data: dict,
                    policy: str | None = None, mode: QualMode | str = "enforce") -> GateResult:
    """B1-1 当期财年语义校验（两级规则）。
    保留原 check_fiscal 的 prior/latest 启发式（规则3）→ 新增规则1/规则2。
    policy 缺省取 FISCAL_CHAPTER_POLICY.get(chapter_num, "default")。
    返回 violations 时按 policy 标注 severity（strict=critical / lenient=warning 可升级）。"""
```

- **any-fy 的保留方式**：`data_anchor.validate_chapter_any_fy` 原样保留，作为 Gate8 `CrossChapterValidator` 的"幻觉数字过滤"底层（命中任一财年锚点即非幻觉）；**在其输出之上叠加 check_fiscal_v2 的当期锚断言**。即最终判定 = any-fy 过滤（不匹配任何财年 → 幻觉，阻断）∧ 当期锚断言（财年错位 → 按规则 1/2 处理）。两者职责正交：any-fy 拦幻觉、check_fiscal_v2 拦错位。
- **接线 Gate8**：`gate8.execute` 在 `_check_critical_issues` 之后新增步骤 `_check_fiscal_semantics`：对 chapters 全 11 章（0-10）调 `check_fiscal_v2`，strict 违规并入 errors（enforce），lenient/default 违规入 warnings；报告附财年校验摘要。
- **单调守卫兼容**：check_fiscal_v2 只产出"修复后可满足"的判据（补 FY 标注 / 改引 latest / 补对比语境）；修复验证通过后不再回滚（沿用阶段 A 的"豁免 PASS 累积清单"判据，缺陷 1 修复）。
- **回归单测（B1-1 验收）**：① ch5 写 "FY2024 当期经营表现"（latest=2025）→ fail（Critical）；② ch6 写 "总资产 827.06 亿元（2024 年，对比 2025 年 841.63 亿元）" → 通过（历史引用豁免）；③ ch6 写 "总资产 827.06 亿元"（无 FY 标注、无对比语境）→ warning；④ 模板残留数字不匹配任何财年 → 仍被 any-fy 拦截；⑤ 修复后（补标注）验证通过 → 不再回滚。

---

## 4. 分级阻断策略矩阵（错误类型 × 阻断级别，B1-2）

### 4.1 矩阵

| 错误类型 | 判定入口 | 阻断级别 | 说明 / 依据 |
|---|---|---|---|
| 当期财年错位（strict 章节） | Gate8 check_fiscal_v2 | **enforce** | B1-1 裁决：财年语义 enforce |
| 数字不匹配任何财年锚点（幻觉/模板残留） | Gate8 CrossChapterValidator（any-fy） | **enforce** | 现状已阻断，保持 |
| 数值量级超锚（numeric 闸门，估值章 5 倍/普通 10 倍） | numeric_guard.check_numeric | **enforce** | 确定性违规，机器可判 |
| 币种混用（HK 每股价值人民币无标注/未换算） | numeric_guard.check_currency | **enforce** | Gate8 汇总 |
| 空章 / 空壳章 | check_empty / check_shell | **enforce** | 现状保持 |
| 结构性运营铁律违反（MAU < DAU、付费 > MAU 等） | B4-1 钩稽 | **enforce** | 仅结构性铁律用阻断（综合审议裁决） |
| Wind 数据源整体不可用 | Gate0 | **enforce 或人工确认** | Critical 类缺失（数据源整体缺失 → 阻断/人工，按 Gate0 现逻辑） |
| Gate0 coverage 小缺（单字段缺失致 <0.95） | Gate0 | **soft + 降级标注** | 裁决：不因小缺整线停摆；降级路径仍产出带标注报告 |
| Gate2 数据字段缺失 | Gate2 | **soft（按 B5-1 处置）** | 有源→canonical；可派生→公式+标注；无源→显式"未披露"，禁补值 |
| 历史引用缺 FY 标注（lenient/default 章节） | Gate8 check_fiscal_v2 | **warning（可升级）** | 规则 2 豁免降级 |
| 派生钩稽口径例外（non-IFRS/一次性/含税口径） | B4-1 | **warning + 白名单** | 口径例外白名单命中 → 不报 |
| 事实表批次冲突（同字段不同值） | B3-3 | **warning（保留高 confidence + 记录）** | 禁静默覆盖 |
| 页码不可得 | B3-2 | **warning + page=null+unverified** | 宁可缺失不可杜撰 |
| 可比数据不可用 / 验证不过 | B4-6 | **降级"标注不可比"（不阻断）** | 禁 LLM 自选填充 |
| 亏损公司 DCF 不可用 | B2a-3 | **降级链（不阻断）** | full_dcf→comparable→PE；全不可用→目标价 null+标注 |

### 4.2 mode_manager 分级实现

```python
# mode_manager.py 扩展
# 保留 QualMode.SHADOW/SOFT/ENFORCE 三档（显式覆盖用）
# 新增"分级默认档"：per-error-type 级别表（上表），按错误类型选择阻断级别
# 翻转时机：A4（小鹏 ≤60min 有界终止）验收通过后，将默认档从"全 shadow"切为"分级档"；
#          翻转后重跑 A 验收不劣化（数据源降级路径仍产出带标注报告）
DEFAULT_BLOCKING_PROFILE = {
    "fiscal": QualMode.ENFORCE,        # Gate8 财年语义
    "numeric": QualMode.ENFORCE,       # 锚点量级/幻觉
    "currency": QualMode.ENFORCE,
    "structural_ops": QualMode.ENFORCE, # B4-1 结构性铁律
    "gate0_availability": QualMode.SOFT,  # 数据源可用性：Critical 整体缺失→enforce/人工，小缺→soft
    "gate2_fields": QualMode.SOFT,
    "cross_disclosure": QualMode.SOFT,
    "page": QualMode.SOFT,             # 页码缺失→warning
}
# QUAL_MODE 环境变量语义不变；新增 QUAL_BLOCKING_PROFILE 覆盖（默认 "default"）
```

- **勘误固守**：专家清单中 enforce 为 **Top2**（非 Top8）；实施以 Top2/B1-2 为准。
- 与熔断的关系：soft 类错误不计入熔断失败计数；enforce 类失败仍走 v3.1 熔断 threshold=2 语义。

---

## 5. 估值程序化数据流（B2a：quote → DCF 降级链 → 目标价注入）

```
wind_stock_quote(ticker)                          # B2a-1：删 21.48/46.52/41.6 硬编码
   │  {current_price, total_shares, currency, quote_time}
   ▼
[B2a-2 币种断言] currency == market 基准币种？
   ├─ hk → 要求 HKD；若返回 CNY → 显式 fx 标注并换算（禁混用）
   ├─ cn → CNY；us → USD
   └─ 不一致 → 阻断（enforce），写入报告"币种口径"备注
   ▼
context["current_price"] / context["shares"]       # 注入 Gate2/5/6 context（gate5 已要求显式传入）
   ▼
[B2a-3 DCF 参数专业化] extract_dcf_params_v2(wind_data, shares)
   ├─ β 动态取：Wind 提供 β → 用之；缺 → 行业 β 表 + warning（禁无标注硬编码 1.2）
   ├─ 净有息负债：有息负债 − 现金及等价物（B5-1 字段处置）；
   │             有息负债无源 → 显式标注，删 extract_dcf_params 的 net_debt=负债×0.3 启发式
   ├─ FCF = 经营活动现金流 − CapEx ± ΔWC（B4-7/B5-1 派生公式口径）
   ├─ shares fail-fast：shares ≤ 0 → 拒绝输出每股价值（禁默认 1）
   └─ growth/wacc 沿用程序计算（CAGR clamp、CAPM），但参数来源显式化
   ▼
[盈利判定] fcf_base > 0 ?
   ├─ 是 → full_dcf（valuation_engine：FCF 折现 + 终值 + 净负债 → 每股价值）
   └─ 否 → 降级链（小鹏即样本）：
         ① comparable（B4-6 数据源化可比矩阵：EV/Revenue、PS 锚点）
         ② PE（EPS > 0 时）
         ③ 全不可用 → 目标价 = null + 报告标注"DCF 不可用（亏损期），无可比锚点"
            （禁止 LLM 编造目标价）
   ▼
[B2a-4 目标价程序注入]
   ├─ valuation_engine 输出 target_price + upside + 三法结果（DCF/comparable/PE）
   ├─ 注入 ch7（当前估值/未来回报路径/安全边际）与 ch10（决策章）
   ├─ 三数自洽：目标价 = 三法结果的程序化综合（含 DCF 不可用分支），
   │            注入前校验 target_price 与 current_price 同币种同量级
   └─ Gate6 后验：_check_rating_valuation_consistency（评级-估值一致性）对程序目标价校验
```

**硬编码删除清单（B2a-1/B2a-2 验收依据）**

| 位置 | 现状 | B 后 |
|---|---|---|
| `run_qual_full.py:133` / `run_xpev_full.py:217` / `run_qual_v8.py:75` | context 写死 current_price 21.48/46.52 | 从 wind_stock_quote 动态取 |
| `quality_enhancer.py:51-52` | 默认 shares=43.0、current_price=41.6 | 删除默认值，改为必传参数 |
| `workflow.py:2803/2817`（单体验证路径） | `set_snapshot("latest", price=41.6)`、`shares=10.12` | 改 quote 动态取 |
| `extract_dcf_params` rf=0.023/beta=1.2/erp=0.055 | 硬编码 CAPM 参数 | β 动态取；rf/erp 显式配置+标注来源 |
| `extract_dcf_params` net_debt=总负债×0.3 | 启发式 | 按 B5-1：有息负债−现金，无源→显式标注 |
| shares 默认 1 | 静默兜底 | fail-fast（≤0 拒绝） |

---

## 6. 财务 100% Wind 数据流（B2b：canonical 扩展 + 缺失处置 + 仲裁）

### 6.1 总数据流

```
B5-1 Wind 缺失字段处置表（先行，L5）
   │  canonical 字段 × Wind 可用性盘点 → 每字段三态处置
   ▼
canonical.py 扩展
   │  CANONICAL_FIELDS 扩至事实表财务字段全集（FinancialFacts 12 字段对齐）
   │  新增派生字段定义（净负债/ΔWC/ROIC/FCF 公式口径，标注"派生"）
   ▼
fact_extractor 移除 financial 提取（B2b-1）
   │  EXTRACTION_PROMPT 删除 financial 块；FinancialFacts 不再由 LLM 产出
   │  事实表 financial 部分 = Wind canonical 引用指针 + 仲裁状态
   ▼
_reconcile_facts_with_wind 仲裁扩至全部 canonical（B2b-2）
   │  field_map 5 字段 → 全部 canonical 字段
   │  容差双阈值：偏差 ≤1% 保留 / >1% 覆盖（Wind 权威）/ 异财年降级
   │  统一 cross_validate_with_wind(5%) 与 reconcile(1%) 口径
   ▼
data_repair 走 canonicalize + 负号正则统一（B2b-3）
   │  删 wrong_years=[2023,2024,2026] 硬编码（改从 _year_labels 动态生成）
   │  删 "快手XXXX年年报" 公司名 pattern（改通用公司名参数）
   │  负号统一：-7.76 / (7.76) / 亏损 7.76 → 单一规范形态
   ▼
Wind 锚点表 / 事实表（financial 部分）→ 章节 prompt + numeric_guard 锚点
```

### 6.2 B5-1 缺失字段处置表（先行交付物，B2b 输入清单）

| canonical / 需求字段 | Wind 可用性 | 三态处置 | 口径说明 |
|---|---|---|---|
| 营业收入/营业利润/归母净利润/净利润 | ✅ 直取 | Wind 直取 | canonical 现 12 键 |
| 总资产/归母净资产/负债合计/所有者权益 | ✅ 直取 | Wind 直取 | |
| 经营活动现金流量净额 / CapEx | ✅ 直取 | Wind 直取 | |
| **有息负债**（interest_bearing_debt） | ⚠️ 疑似无源 | **显式标缺失**（报告"未披露"）或派生 | 禁启发式 0.3；派生口径=有息负债−现金（两子项均可得时） |
| **净负债** | 派生 | 派生计算（公式+标注） | = 有息负债 − 现金及等价物；缺任一子项→显式标缺失 |
| **ΔWC（营运资本变动）** | ⚠️ 疑似无源 | 显式标缺失 或 派生（流动资产−流动负债变动） | 用于 FCF 含 ΔWC（B4-7） |
| 现金及等价物 | ✅ 直取 | Wind 直取 | |
| 汇率（外币折算） | ✅ 直取 | Wind 直取 + fx 标注 | B2a-2 币种断言输入 |
| 每股股息 | ⚠️ 部分无源 | 派生（股息总额/股本）或标缺失 | |
| β | ⚠️ 部分无源 | 有源→直取；无源→行业 β 表+warning | 禁无标注硬编码 |

**处置表铁律**：每个字段落入且仅落入一态（直取/派生/标缺失）；**禁止 LLM 补值与启发式默认**（删 0.3 启发式即本项验收）；无源字段在报告中显式标注"未披露"，不得静默消失。

### 6.3 仲裁扩展细节（B2b-2）

- `_reconcile_facts_with_wind` 的 `field_map` 从 5 字段扩至全部 canonical 字段（含派生字段走公式比对）。
- **容差统一**：`fact_extractor.cross_validate_with_wind`（现 5% 偏差 → warning）与 `workflow._reconcile_facts_with_wind`（现 1% → 覆盖）统一为双阈值：**≤1% 保留（交叉验证通过）/ >1% 覆盖（Wind 权威，记仲裁 note）/ 异财年降级**；5% 阈值仅作为"预警"（不触发覆盖）保留在提示层。
- 仲裁输出标准化：`【事实表↔Wind 仲裁】<字段>: 提取 X vs Wind Y，偏差 D%，已以 Wind 为准 / 保留`，注入章节 prompt（复用现有 reconcile_note 通道）。
- 与 B3 多财年化衔接：每张单年表独立仲裁（该年 vs Wind 该年锚点）；多财年表只有 latest 年进入当期断言，历史年仅作对比。

---

## 7. 事实表多财年化数据流（B3）

```
fetch 3 份年报（成本计入预算 200，v3.1 约束）           # B3-1
   │  年报1(FYn-2) / 年报2(FYn-1) / 年报3(FYn)
   ▼
MinerU 页码结构前置验证（B3-2）
   ├─ sections 带 page 元数据 → 页码字段可用
   └─ sections 不带 page → page = null + unverified（禁 LLM 猜测页码）
   ▼
按年报分组提取（每份独立 fiscal_year，来自年报报告期）   # B3-1 + B3-4
   │  EXTRACTION_PROMPT 增补：
   │   - "宁可缺失不可杜撰"：无明确数据 → null，禁猜测/推断
   │   - 禁止用前批/他年值补当前批/当年（"本年度/报告期"严格指向本批 fiscal_year）
   │   字段增补（B3-2）：页码(null+unverified) / 原文片段(≤80字) / confidence /
   │                    arbitration_status / comparison_period(对比期)
   ▼
批次一致性仲裁（_merge_chunk_data 改造，B3-3）
   │  同字段不同值（冲突）→ 保留 confidence 高者 + 写入 warnings（禁静默覆盖）
   │  现逻辑"后批次覆盖"→ 删除
   ▼
3 张单年表程序化合并（不走 LLM）                       # B3-1
   │  按 fiscal_year 对齐为多财年列：| 指标 | FYn-2 | FYn-1 | FYn | 单位 | 页码 | 置信度 | 仲裁状态 |
   │  同指标跨年值冲突 → 按 B3-3 仲裁 + 记录
   ▼
format_facts_as_context 多财年化输出
   │  财务列引用 Wind（B2b 后事实表无财务提取，financial 块为 Wind 指针）
   │  运营/业务/管理层列 = 多财年表（带页码可复核）
   ▼
章节 prompt（ch5/ch6 用 Wind；ch1/3/8/9 引多财年事实表，每行可翻原文）
```

**B3 与 B2b 的衔接（路线图依赖 B3-1 ← B2b-1）**：财务移出事实表后，多财年表聚焦运营/定性指标，3 份年报的成本集中在运营指标覆盖率上，避免与 Wind 财务双源口径冲突。

---

## 8. 运营验证链判定流程（B4-1/B4-2/B4-3/B4-4/B4-5/B4-6/B4-7）

### 8.1 运营验证链四段（B4-1）

```
运营指标候选值（B5-2 归一后）
   │
   ▼ ① 原文正则复核（配对 B5-2 预处理器）
   用归一化正则从年报原文提取同指标数值（单位/千分位/约/区间归一后比对）
   ├─ 命中原文 → 保留，confidence=high
   ├─ 未命中 → confidence=low（标注"未能复核到原文"），不自动修正
   └─ 单位级错误（4.102亿→410.2亿）→ 在转写阶段被 B5-2 拦截（标注不修正）
   │
   ▼ ② 多批次一致性（复用 B3-3 仲裁）
   同指标多批值 → 冲突保留高 confidence + warnings
   │
   ▼ ③ 交叉披露
   年报 vs Wind/披露材料 同指标 → 偏差 ≤5% 通过；>5% → warning + 仲裁
   │
   ▼ ④ 派生钩稽（warning 级 + 口径例外白名单）
   钩稽规则集：MAU×ARPU≈收入、付费率=付费/MAU、DAU/MAU 比值、GMV×货币化率≈收入、
               LTV/CAC、留存率单调性…
   ├─ 命中口径例外白名单（non-IFRS 调整 / 一次性项目 / 含税口径 / 披露口径差异）→ 豁免
   ├─ 违反结构性铁律（MAU ≥ DAU ≥ 付费用户）→ enforce（Critical）
   └─ 其余钩稽偏差 → warning（写入报告"数据校验"附注，不阻断）
```

### 8.2 各子项落地

| 项 | 设计要点 | 对应裁决 |
|---|---|---|
| **B4-2** | 删 `_calculate_unit_economics` 毛利率 50% 默认填充；`normalize_units` 改"只标不改"（超范围→标注+confidence=low，不自动 ÷100/×100）；配对 B5-2 预处理器在转写阶段拦截单位错误 | 综合审议 Top8 "只标不改"配 B5-2 |
| **B4-3** | `industry_for` 动态化：Wind 行业字段优先 + 公司名关键词权重，删"新能源汽车"类硬编码误判；ch2 数据年份标注（不可确定性 → 强制降级"标注或年份未知"） | 采纳原样 |
| **B4-4（转验收）** | 验收 review_repair_loop:299-319 Wind 锚点注入已在 v8 gate4 生效；补两处收尾：①修复 prompt 增事实表注入（多财年表+页码）；②legacy 路径覆盖（quality/v3/review_repair_loop.py、tools/finance/workflow.py 审计链） | 转验收 + 补漏 |
| **B4-5（与 Gate6 合并）** | ①前置注入：Wind 锚点表 + RATING_VALUATION_MAPPING 注入 `_build_decision_prompt`（ch10 prompt）；②后验阻断：gate6 `_check_rating_valuation_consistency`（已存在，验收）；③新开发：否决项联动（ch9 否决项未消除 → 评级不得为买入/增持，enforce）；④评级=规则输出+人工 override 留痕（非绝对禁止） | 后验转验收 + 前置/否决项开发 |
| **B4-6（可比重写+数据源化）** | ①前置 Wind 可比可用性验证（港股/美股可比 quote/财务覆盖面；验证不过 → 降级"标注不可比"，禁 LLM 自选填充）；②删 `create_sf_express_peers` 顺丰硬编码与错误 ticker（中通 002024.SZ 实为分众传媒）；③**控股股东排除硬规则**（腾讯 70.05% 持阅文 → 腾讯不可作可比）；④数据驱动重写 peer_comparison（可比表=Wind 数据动态生成）；⑤接线 ch2（竞争格局）/ch7（可比估值锚） | 三处必须修改之一 |
| **B4-7** | ROIC vs WACC、FCF 含 ΔWC 程序化支撑：roic_wacc_checker / fcf_calculator 全部从 Wind canonical 数值计算（ΔWC 按 B5-1 处置），禁 LLM 估算 | 路线图 B4-7 |

---

## 9. B 与 A 阶段边界

### 9.1 交付物与验收边界

| 维度 | 阶段 A（v3.1，已完成） | 阶段 B（本册） |
|---|---|---|
| 目标 | 跑得完：有界终止、无死循环 | 可信：数据真实、可复核、结论可决策 |
| 交付物 | A1-A4 提交（fail-closed/deadline/熔断/单调守卫/预算 200）+ 20 测试绿 + 小鹏 ≤60min | B1-B5 工作包 + 重跑验收（财年错位 0/目标价程序化/事实表可复核） |
| 机制改动 | 状态机、超时、重试、预算（**机制层**） | 校验规则、数据流、阻断策略（**规则层**，不动机制） |
| 新增判据 | 修复可满足、单调、有界 | 财年语义/钩稽/页码/币种——**必须与 A 的单调守卫兼容** |

### 9.2 数据与依赖边界（路线图 §四 依赖矩阵固守）

```
B1-1（Gate8 接线）   ← A2（fail-closed/deadline）
B2b-1/2（仲裁基础）  ← A1（P0-A canonical/仲裁）
B3-1                ← B2b-1（财务移出后事实表才专注运营）
B4-2                ← B3（删除默认值依赖提取重构）
B4-5                ← B2a-4（结论锚依赖估值程序化）
B2b-1                ← B5-1（Wind 缺失字段处置表先行）
```

### 9.3 防回归边界（不得跨越的红线）

1. **B 不删 A 机制**：deadline/fail-closed/熔断 threshold=2/单调守卫/预算 200 保持原样；B 只在其上叠加"分级阻断配置"（§4.2 profile）。
2. **B 不新增不可满足判据**：任何新阻断必须能通过"修复动作"满足，且"修复验证通过即不再回滚"（defect 1 豁免 PASS 累积清单判据继续适用）；any-fy 保护场景（ch6/ch7 合法历史引用）进回归单测。
3. **翻转时序**：B1-2 默认档翻转只能在 A4 验收通过后；翻转后重跑 A 验收（小鹏 ≤60min、无死循环）不劣化。
4. **A 的验收口径是 B 的基线**：B 每完成一个工作包，跑 A 验收回归（20 测试绿 + 小鹏有界）作为准入门禁。
5. **B 内子包顺序**（综合审议优先级修订版）：B1 → B2a → B5-1 → B2b → B3 → B5-2 → B4 → B5 收口；横切小包（B5-1/B5-2）分别插在 B2b/B4-2 前置。

---

## 10. B 阶段验收标准

### 10.1 里程碑验收（路线图 §五 对齐）

| 里程碑 | 验收标准 |
|---|---|
| M2（B1 完成） | 章节级财年校验拦截 ch5 写 FY2024 当期（fail）；ch6 合法历史引用（带"对比"标注）通过（回归单测 ①-⑤）；Gate8 财年语义 enforce 接线生效；Critical 阻断出厂默认；数据源降级路径仍产出带标注报告 |
| M3（B2 完成） | 全仓无硬编码股价（21.48/46.52/41.6 删除）；目标价=程序输出（亏损公司走降级链，小鹏样本产出 comparable/PE 锚或"不可比"标注，无无意义 DCF 目标价）；币种断言生效（无港元/人民币混用）；事实表无 financial 提取行；B5-1 无源字段显式标注"未披露"（删 0.3 启发式）；仲裁覆盖全部 canonical；data_repair 无 wrong_years/快手 硬编码 |
| M4（B3 完成） | 事实表多财年列（FYn-2/FYn-1/FYn）；每行可翻原文复核（页码 null+unverified 而非编造）；批次冲突保留高 confidence+warning（无静默覆盖） |
| M5（B4/B5 完成） | 运营验证链通过（钩稽 warning 级+白名单；结构性铁律 enforce）；行业判定正确（阅文不落"新能源汽车"）；结论可复现（评级=规则输出+override 留痕；否决项联动生效）；可比表数据动态（无可比硬编码；控股股东被排除）；B5-2 拦截"4.102亿→410.2亿"类单位错误 |

### 10.2 端到端验收（综合审议 + 路线图 B 阶段验收汇总）

重跑小鹏 9868.HK：
1. 财年错位 Critical = 0；
2. 目标价为程序输出（含 DCF 不可用分支，三数自洽）；
3. 事实表每行可翻原文复核（页码真实或 null+unverified）；
4. 运营数据验证链通过（无杜撰数据源、无默认值填充）；
5. 无硬编码股价/行业/可比数据；
6. 回归测试全绿（新增：any-fy 保护场景、财年语义 ①-⑤、分级阻断 profile、B5-2 归一、B3 仲裁）。

### 10.3 风险护栏复核（综合审议 §⑤ 逐条）

| 风险 | 本册落实的护栏 |
|---|---|
| 死循环复发 | §3.3 单调守卫兼容设计 + 回归单测；any-fy 保留为幻觉过滤层 |
| 跑得完 vs 可信 | §4.2 分级默认 + 翻转时序；soft 不计熔断 |
| 页码幻觉 | §7 B3-2 前置 MinerU 验证 + null+unverified |
| 事实表膨胀挤预算 | 3 份年报成本计入预算 200；超限转惰性分财年提取 |
| 可比虚假精确 | §8.2 B4-6 前置验证 + 降级"标注不可比" + 控股股东排除硬规则 |
| 亏损公司 DCF 无意义 | §5 降级链 + 目标价三数自洽含 DCF 不可用分支 |
| 派生钩稽口径误报 | §8.1 口径例外白名单 + warning 级 |
| Wind 化后字段空洞 | §6.2 B5-1 三态处置 + 显式"未披露" |

---

## 附：与综合审议/路线图的一一对应追溯

| 综合审议/路线图条目 | 本册落点 |
|---|---|
| 裁决①-1 B1-1 章节级财年语义（合并扩展 check_fiscal、不删 any-fy、接线 Gate8） | §3（两级规则 + 实现设计 + 回归单测） |
| 裁决①-2 B1-2 分级阻断（Gate8/财年 enforce；Gate0/2 soft；A4 后翻转；三档保留） | §4（矩阵 + mode_manager 扩展 + 勘误固守） |
| 裁决①-3 B4-6 可比重写+数据源化（前置验证+控股股东排除+删硬编码+降级） | §8.2 B4-6 |
| 裁决② B4-4 转验收（补事实表注入+legacy 覆盖） | §8.2 B4-4 |
| 裁决② B4-5 与 Gate6 合并（前置注入+后验+否决项联动+override 留痕） | §8.2 B4-5 |
| 裁决③ 优先级修订（B1→B2a→B5-1→B2b→B3→B5-2→B4） | §9.3-5、§1 分层 |
| 裁决④ B5-1 缺失字段处置表 / B5-2 数值转写归一预处理器 | §6.2 / §8.1（B5-2 并入四段验证链①） |
| 裁决⑤ 风险护栏 | §10.3 |
| 路线图 B1-3（ch0/ch10 纳入审计） | §2 矩阵 + §1 L1 |
| 路线图 B2a-1..4 | §5 |
| 路线图 B2b-1..3 | §6 |
| 路线图 B3-1..4 | §7 |
| 路线图 B4-1..7 | §8 |
| 路线图 §四 依赖矩阵 | §9.2 |
| 路线图 §五 验收总纲 M2-M5 | §10.1 |
