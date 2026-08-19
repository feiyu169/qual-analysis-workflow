# Qual 项目全面评审：数据矛盾源头分析 + 事实提取表评估

> 评审范围：`tools/finance/` 全链路（run_qual_full → filing_downloader(MinerU) → fact_extractor →
> workflow(_collect_data/_build_chapter_prompt/_write_chapters/_audit_and_fix/_assemble_report) →
> quality 链（v3/DataAnchor/ReviewIntegrator）→ qual_v8 Gate0-8）。
> 目标：从**数据源头**回答"R5 报告为什么出现 83.6/80.0/81.2 三套收入、+11.4 vs -7.76 归母、18.5/15.2/28.0/25.0 四套现金流"，
> 并提出**源头级**解决措施，评估**事实提取表**能否有效解决。

---

## 一、数据流全景（含每一跳的"数据形态"）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ ① Wind CLI 原始响应                                                          │
│    wind-fin.json: 列名 "近3年每年营业总收入" / "近3年每年归母净利润"...        │
│    （Wind 原始列名：带"近3年每年"前缀，值为 3 年数组）                        │
└──────────────┬──────────────────────────────────────────────────────────────┘
               │ assemble_wind_data.py FIELD_MAP（第 4 套映射）
               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ ② canonical Wind 数据（实际链路形态）                                        │
│    income = {"营业收入": [70.12, 81.21, 73.66], "归母净利润": [8.05, -2.09, -7.76], ...}
│    _year_labels = {"财年": [2023, 2024, 2025]}                                │
└──────────────┬──────────────────────────────────────────────────────────────┘
               │ run_qual_full.py → workflow._collect_data
               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ ③ DataContext.wind (WindData) + ctx.facts (ExtractedFacts)                  │
│    wind: canonical 键（② 原样）                                              │
│    facts: fact_extractor 从年报原文提取（fiscal_year=0！无财年概念）           │
└──────────────┬──────────────────────────────────────────────────────────────┘
               │ _build_chapter_prompt
               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ ④ LLM prompt：data_anchor（Wind 锚点 FY2025）+ format_facts_as_context（FY0 事实表）
│    ⚠️ 两套"权威"并存且财年矛盾 → LLM 各章自选 → 三套收入/四套现金流           │
└──────────────┬──────────────────────────────────────────────────────────────┘
               │ _generate_chapter × 11 → _audit_and_fix → _assemble_report
               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ ⑤ 报告（R5）：83.6/80.0/81.2 收入并存；+11.4 vs -7.76 归母并存               │
└─────────────────────────────────────────────────────────────────────────────┘
```

**矛盾的本质**：数据在 ①② 是**结构化且财年明确**的（canonical + _year_labels）；
到了 ④ prompt 时，LLM 同时收到"Wind FY2025 锚点"与"FY0 事实表（实际是 FY2024 年报对比列）"，
**没有仲裁机制决定谁覆盖谁** → LLM 的统计性漂移被放大成系统性矛盾。

---

## 二、源头定位：三层六处

### 层 1 — 数据契约层（最源头）

| 编号 | 问题 | 证据 |
|---|---|---|
| S1 | **字段映射 4 套并存，方向/覆盖不一致** | `data_context.WIND_FIELD_MAPPING`（内部名→Wind原始名 `营业收入→年营业总收入`）、`wind_field_mapper.FIELD_MAPPINGS`（英文→三市场Wind代码 `revenue→S_FA_REVENUE_TTM`）、`data_mapping.DataMappingRegistry`（口径知识：GAAP/adjusted/归母/扣非）、`assemble_wind_data.FIELD_MAP`（列名→canonical，**实际产出的形态**）。前三套从未被实际数据流消费，第四套是唯一真实输出——**canonical 键从未被统一声明为唯一真源** |
| S2 | **检查器期望键 ≠ canonical 键 → 校验静默失效** | `fact_checker` 期望 `年营业收入`；`fact_extractor.cross_validate_with_wind` 期望 `年净利润`；`data_repair._build_correct_values` 期望 `['年净利润','净利润','归母净利润']`——都与 canonical（`营业收入`/`归母净利润`）不一致 → 取 None → 检查跳过（R-D1 实锤） |

### 层 2 — 提取层

| 编号 | 问题 | 证据 |
|---|---|---|
| S3 | **事实提取器无财年概念** | `ExtractedFacts.fiscal_year=0` 默认；`_merge_chunk_data` 从不设置；`EXTRACTION_PROMPT` 不要求 LLM 标注财年；`select_high_value_sections` 按"数据密度"选章（不区分当期/对比列）→ FY0 事实表，实际混入 FY2024 对比列 |
| S4 | **事实表与 Wind 无仲裁** | `_build_chapter_prompt` 同时注入 FY0 事实表 + FY2025 数据铁律，无"谁覆盖谁"的代码逻辑（R-C4 实锤） |

### 层 3 — 生成与校验层

| 编号 | 问题 | 证据 |
|---|---|---|
| S5 | **数据铁律只进 prompt 不进代码** | 锚点是提示文本；报告生成后无程序化数字校验器（R-D4）——v8 Gate8 的 DataAnchor 校验是本轮新补，v2-v7 单体无 |
| S6 | **审查修复循环不带锚点** | `_repair_chapters` 修复 prompt 只有问题+内容前3000字，无 Wind 锚点/事实表 → 修复即污染源（R-C3） |

---

## 三、源头解决方案（按"数据进 LLM 前"与"报告生成后"两阶段）

### 方案 A：单源数据契约层（解决 S1/S2）—— 最高优先级

**统一 canonical 键为唯一真源**，让所有检查器/提取器/审查器走同一映射：

```
新增 tools/finance/canonical.py（唯一映射真源）：
  CANONICAL = {
    "营业收入", "营业利润", "归母净利润", "净利润", "总资产",
    "归母净资产", "年负债合计", "年所有者权益合计", "经营活动现金流量净额",
    "购建固定资产、无形资产和其他长期资产支付的现金",
  }
  ALIASES: Dict[str, str] = {  # 所有历史键名 → canonical（单向）
    "年营业总收入"→"营业收入", "近3年每年营业总收入"→"营业收入",
    "年净利润"→"归母净利润", "年归属母公司股东的净利润"→"归母净利润",
    "经营活动产生的现金流量净额"→"经营活动现金流量净额", ...
  }
  def canonicalize(d: dict) -> dict:  # 任意字典 → canonical 形态
```

- `assemble_wind_data.py` 直接产出 canonical（已做，标注为唯一出口）
- `data_context.WIND_FIELD_MAPPING` 改为引用 canonical.py（删除独立副本）
- `fact_checker`/`cross_validate_with_wind`/`data_repair`/`DataAnchor` 全部改用 `canonicalize()` 预处理
- `data_mapping.DataMappingRegistry` 保留为"口径知识库"（GAAP/adjusted），校验时检查报告是否标注口径而非强制

### 方案 B：事实提取锚定财年 + 事实表↔Wind 仲裁（解决 S3/S4）—— 源头根治

**B1. 提取时锚定财年**（改 fact_extractor）：
- `extract_facts()` 增加 `fiscal_year` 参数，由调用方从**年报元数据**传入
  （`filing.metadata.fiscal_year`——filing_downloader 已能从 MinerU 解析报告期/封面页得到）
- `EXTRACTION_PROMPT` 注入："本批文本为 FY{year} 年报原文，其中出现的'本年度/报告期'指 FY{year}，
  '上年/对比期'指 FY{year-1}；提取的财务数字必须标注所属财年"
- `ExtractedFacts.fiscal_year` 在 `_merge_chunk_data` 时统一设置（不再默认 0）
- `format_facts_as_context` 输出的表格头从 `FY0` 变为真实财年，且**财务列只放当期（FY{year}）数据**

> ⚠️ **B1 落地的关键坑（已核实）**：`filing_downloader.py:294` 目前 `fiscal_year = int(filing.filing_date[:4])`
> 取的是**发布日期年份**——FY2025 年报若在 2026-04 发布，会错误标成 2026。
> 正确做法：从年报正文报告期推断（MinerU 解析封面页"截至2025年12月31日止年度"），
> 或用 Wind `_year_labels` 对齐（`labels[-1]` = 最新财年 = 应锚定的 FY）。
> 推荐：`fiscal_year = 报告期结束日所在年份`（如"截至2025-12-31"→2025），并**用 Wind labels[-1] 交叉验证**，
> 不一致时以 Wind 为准并告警。

**B2. 进入 prompt 前的仲裁**（改 workflow._build_chapter_prompt）：
- 新增 `_reconcile_facts_with_wind(ctx)`：在注入 prompt 前，把事实表**财务字段**与 Wind canonical 锚点比对：
  - 同财年且偏差≤1% → 保留事实表值（来源标"年报，Wind 验证一致"）
  - 同财年但偏差>1% → **以 Wind 为准覆盖**，并记 warning
  - 财年不同（事实表 FY2024 vs 锚点 FY2025）→ 事实表财务字段**降级为"参考"**并显式标注"FY2024 年报口径，非当期"，
    当期财务一律用 Wind
- 仲裁后的事实表才是 prompt 里的唯一事实源；Wind 锚点表仍注入（作为数据铁律的权威值）

### 方案 C：程序化数字校验器 + 审查锚点注入（解决 S5/S6）—— 兜底

- **C1. 报告后数字校验器**：`_assemble_report` 后跑 DataAnchor 全文校验（v8 Gate8 已实现，移植/复用进 v2-v7 单体的 Step 4.7 后）——报告内任一财务数字与 Wind canonical 锚点同财年偏差>1% 即 P0
- **C2. 审查修复注入锚点**：`_repair_chapters`/`review_and_repair_loop` 的修复 prompt 强制注入 Wind canonical 锚点表 + 仲裁后事实表（v8 Gate8 红队审查已用 `_build_wind_anchor_table` 做到，同步进 v2-v7）

---

## 四、事实提取表能否有效解决数据矛盾？—— 评估

### 结论：**事实提取表本身不能解决数据矛盾；但改造后（B1+B2）是必要且有效的组成部分**

**为什么"现状的事实表"不能解决（甚至制造矛盾）**：
1. **它是矛盾的一方**：FY0 事实表（实际混入 FY2024 对比列）与 Wind FY2025 锚点并存，正是 R5 三套收入的来源之一（83.6/16.2/11.4/18.5 来自年报原文提取）
2. **无财年锚定**（S3）：提取器把"上年对比列"当当期 → 事实表本身数据就错位
3. **无仲裁**（S4）：LLM 同时看到两套"权威" → 各章自选 → 矛盾放大
4. **键契约断裂**（S2）：事实表与 Wind 交叉验证静默失效 → 提取错误永不暴露

**为什么"改造后的事实表"是必要组成部分**：
1. 事实表提供 **Wind 没有的定性/运营数据**（产品、客户、MAU、付费用户、IP 授权、管理层、风险）——这些不能从 Wind 数值得到
2. 事实表的**财务字段**在仲裁后（B2）可作为 Wind 的交叉印证（同财年偏差≤1% 增强可信度）
3. 财年锚定后（B1），事实表成为"年报口径的 FY{year} 结构化摘要"，与 Wind 锚点**对齐**而非竞争

**分工建议（最终形态）**：
| 数据类别 | 唯一权威源 | 事实表角色 |
|---|---|---|
| 财务数值（收入/利润/现金流/资产） | **Wind canonical 锚点**（唯一真源） | 交叉印证（仲裁后一致才引用）；冲突时以 Wind 覆盖 |
| 运营/定性（产品/客户/MAU/付费/IP/治理） | **事实表**（年报提取，财年标注） | 唯一来源 |
| 行业/市场 | 搜索/事实表 | 补充 |

**一句话**：数据矛盾的根治 = **方案 A（单源契约）+ 方案 B（财年锚定 + 仲裁）**；事实提取表在 B1+B2 改造后是"运营数据的唯一源 + 财务数据的印证层"，单独存在（现状）则是矛盾的制造者。

---

## 五、实施顺序与工作量

| 优先级 | 方案 | 改动文件 | 工作量 |
|---|---|---|---|
| P0 | A 单源契约 | 新增 canonical.py；改 assemble_wind_data/data_context/fact_checker/cross_validate/data_repair/DataAnchor | 中（机械替换+测试） |
| P0 | B1 财年锚定 | fact_extractor.py（参数+prompt+merge+format） | 中（含 LLM 提取回归） |
| P0 | B2 事实表仲裁 | workflow.py `_reconcile_facts_with_wind` | 中 |
| P1 | C1 数字校验器移植 | v2-v7 单体 Step 4.7 后接 DataAnchor（v8 已实现，复用） | 小 |
| P1 | C2 修复锚点注入 | review_repair_loop/_repair_chapters | 小 |

> 已验证基础：v8 DataAnchor（canonical 键 + 财年 + 校验）与红队审查锚点表（`_build_wind_anchor_table`）
> 已实现方案 A/B/C 的核心机制，可作为移植蓝本。
