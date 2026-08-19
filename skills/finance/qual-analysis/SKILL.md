---
name: qual-analysis
description: 买方定性分析工作流 — 10+1 章结构化分析框架
version: 4.0.0
author: hermes-agent
tags:
  - finance
  - investment
  - qualitative-analysis
  - buy-side
dependencies:
  - wind-mcp
  - finance-calc
  - dayu
  - anysearch
  - gbrain
  - flomo
  - nocturne-memory
triggers:
  - "分析"
  - "投资分析"
  - "定性分析"
  - "买方研究"
  - "深度研究"
---

# 买方定性分析 Skill

## 概述

本 Skill 实现了一个完整的买方投资分析工作流，包含 10+1 章结构化分析框架、双层数据架构、LLM-as-Judge 审计修复循环、三层记忆持久化。

## 工作流架构

```
用户请求 → 类型推断 → 数据收集 → 逐章写作 → 审计修复 → 记忆存储
```

## 核心组件

### 1. 分析模板 (`qual-analysis-template.md`)
- 10+1 章结构化分析框架
- 每章包含 CHAPTER_GOAL + CHAPTER_CONTRACT
- 行业视角 (preferred_lens) 和条件项 (ITEM_RULE)

### 2. Facet Catalog (`facets/catalog.json`)
- 37 类业务模型
- 26 类约束条件
- 行业视角映射 (lens_mapping)

### 3. Prompt 文件 (`prompts/`)
- `infer-prompt.md` — 类型推断
- `write-prompt.md` — 章节写作
- `audit-prompt.md` — 章节审计
- `repair-prompt.md` — 章节修复

## 使用方法

### 触发条件

当用户请求包含以下关键词时自动触发：
- "分析 + {公司名称}"
- "{股票代码} 定性分析"
- "{公司名称} 买方研究"
- "{公司名称} 深度研究"

### 输入参数

| 参数 | 类型 | 必需 | 描述 |
|------|------|------|------|
| ticker | string | 是 | 股票代码 (如 AAPL, 600519, 0700) |
| company_name | string | 是 | 公司名称 |
| market | string | 否 | 市场 (us/cn/hk)，自动推断 |

### 输出

- 结构化分析报告 (Markdown)
- 10+1 章完整覆盖
- 记忆存储到 GBrain/flomo/nocturne

## 工作流步骤

### Step 1: 类型推断 (infer)
- 读取 `facets/catalog.json`
- 使用 `prompts/infer-prompt.md` 推断业务模型和约束条件
- 输出 FacetResult

### Step 2: 数据收集 (collect)
- 财报原文层：下载 + 解析 + 格式提取
- 结构化数字层：Wind MCP (行情/估值/财务/新闻)
- 补充层：anysearch (分析师评级)

### Step 3: 逐章写作 (write)
- 按模板逐章生成
- 应用行业视角和条件项
- 断点恢复支持

### Step 4: 审计修复 (audit/repair)
- 结构化预检
- 语义审计 (LLM-as-Judge)
- 最多 3 轮修复循环

### Step 5: 记忆存储 (memory)
- GBrain：知识图谱
- flomo：用户笔记
- nocturne：实体记忆

## 配置

### 环境变量

| 变量 | 描述 | 默认值 |
|------|------|--------|
| WIND_API_KEY | Wind API Key | - |
| SEC_USER_AGENT | SEC EDGAR User-Agent | - |

### 缓存路径

- 财报缓存：`~/.hermes/workspace/filings/{ticker}/`
- 断点存储：`~/.hermes/workspace/checkpoints/{ticker}/`

## 降级策略

| 层级 | 主要方案 | 降级方案 |
|------|----------|----------|
| 财报下载 | fetch_filing() → HKEXNewsDownloader/SECDownloader/CNInfoDownloader | anysearch PDF URL |
| PDF 解析 | MinerU 精准 API (≤200页/段) → 分段合并 | FallbackParser (pdfplumber) |
| LLM 定性分析 | DeepSeek (create_deepseek_caller) | placeholder (需报错) |

**⚠️ Docling 当前不可用**: numpy/pandas 循环导入问题，降级策略跳过 Docling。

## 工作流代码位置

| 组件 | 路径 |
|------|------|
| 工作流入口 | `~/.hermes/tools/finance/workflow.py` |
| DataContext | `~/.hermes/tools/finance/data_context.py` |
| 数据收集器 | `~/.hermes/tools/finance/data_collector.py` |
| 港股下载器 | `~/.hermes/tools/finance/downloaders/hkexnews_downloader.py` |
| PDF 解析器 | `~/.hermes/tools/finance/parsers/mineru_parser.py` |
| 记忆管理器 | `~/.hermes/tools/finance/memory/memory_manager.py` |
| 数据修复 | `~/.hermes/tools/finance/data_repair.py` |
| 基础估值 | `~/.hermes/tools/finance/base_valuation.py` |
| 辩论机制 | `~/.hermes/tools/finance/debate_coordinator.py` |
| 完整估值 | `~/.hermes/tools/finance/valuation_engine.py` |
| 深度优化 | `~/.hermes/tools/finance/depth_enhancer.py` |
| 质量增强集成 | `~/.hermes/tools/finance/quality_enhancer.py` |
| 端到端测试 | `~/.hermes/tools/finance/test_quality_enhancer.py` |

## 调用方式

```python
from finance.filing_downloader import fetch_filing
from finance.llm_caller import create_deepseek_caller
from finance.workflow import run_analysis

# 1. 获取财报原文
filing_data = fetch_filing(ticker="1024.HK", market="hk", limit=1)

# 2. 创建 LLM 调用器
llm_caller = create_deepseek_caller()

# 3. 准备 Wind 数据 (从 MCP 获取)
wind_data = {"income": {...}, "balance": {...}, "cashflow": {...}}

# 4. 运行分析
result = run_analysis(
    ticker="1024.HK",
    company_name="快手",
    market="hk",
    wind_data=wind_data,
    filing_data=filing_data,    # 可选，但 data_quality=high 需要
    llm_caller=llm_caller,     # 必需
    shares=43.4,               # 总股本 (Wind 不提供)
    output_dir="/tmp/output",
)
# result: {success, chapters(11), dcf_params, mcp_instructions(3), data_quality, report_path}
```

**⚠️ 关键**：
- `llm_caller` 签名: `llm_caller(chapter_name: str, prompt: str) -> str`
- `filing_data` 通过 `fetch_filing()` 获取，内部调用下载器 + 解析器
- `shares` 必须从财报原文或用户输入获取，Wind 不提供总股本
- **禁止**: `llm_caller=None` → 会产生 placeholder，必须用 `create_deepseek_caller()`
- **禁止**: 手动拼凑报告 → 必须调用 `run_analysis()`
- **正确调用顺序**: fetch_filing() → create_deepseek_caller() → run_analysis()

## 质量保证

1. **结构化预检**：检查必需小节、证据溯源
2. **语义审计**：must_answer 覆盖、must_not_cover 违反
3. **修复循环**：最多 3 轮自动修复
4. **断点恢复**：中断后可从断点继续

## ⚠️ 核心 Pitfalls

### P0: 禁止绕过工作流 (Verified 2026-06-23)

当工作流执行失败时，**必须报告失败**，不能用 Agent 手动执行替代后声称"成功"。

**错误模式**：
1. 工作流调用失败 → Agent 用 MCP 工具手动收集数据 → 生成报告 → 声称"工作流成功"
2. 下载器返回假数据 → Agent 用搜索引擎补充 → 声称"数据收集成功"

**正确行为**：
1. 工作流调用失败 → 报告"Step X 失败: {原因}" → 分析根因 → 修复代码 → 重新执行
2. 每个 ✅ 必须有独立证据，不允许自评

### P1: 章节结构已实现 10+1 (Verified 2026-06-23, Updated 2026-06-30)

workflow.py 已按 v2.0 方案重写，10+1 章全部实现。
CHAPTERS 数组定义 ch00-ch10，_CHAPTER_WRITE_ORDER = [1,2,3,4,5,6,7,8,9]。

**端到端验证**: 快手 (1024.HK) 2026-06-30 测试通过:
- 11 章全部生成
- 9 章通过语义审计 (85-95分)
- data_quality=high (Wind + 财报原文)
- 3 条 MCP 指令返回

### P2: MemoryWriter 不能 import MCP 工具 (Verified 2026-06-23)

MCP 工具只能通过 Agent 层调用，不能通过 Python import。

**错误**：`from hermes.tools import mcp_gbrain_put_page`
**正确**：Writer 返回 `{action, slug, content, tags}` dict，由 Agent 层调用 MCP。

### P3: LLM_GENERATE 占位符必须清除 (Verified 2026-06-23)

报告中不能包含 `[LLM_GENERATE: ...]` 占位符。如果 llm_caller 未提供，必须明确报告"LLM 未配置"而不是留占位符。

### P4: 执行日志必须基于证据 (Verified 2026-06-23)

每个步骤的 ✅ 必须有独立验证：
- 下载成功 → 检查文件大小 > 1024 bytes
- 解析成功 → 检查 markdown 长度 > 0
- 写入成功 → 用 search/get 验证数据存在
- 不允许"自认为通过"

### P6: DCF 参数提取 5 个 Bug (Verified 2026-06-30)

extract_dcf_params 存在多个严重 Bug，全部被 `except Exception` 静默吞掉：

1. **ctx.wind_data 不存在**: 属性名是 `ctx.wind` (WindData 对象)
2. **WIND_FIELD_MAPPING 方向错误**: 应为 内部名→Wind名，不是 Wind名→内部名
3. **字段名不匹配**: Wind 返回"过去三年每年经营活动产生的现金流量净额"，代码期望"经营活动现金流量净额"
4. **3年数组未取最新值**: Wind 返回数组，必须取最后一个元素
5. **comps_analysis 直接调用 MCP**: Python 层无法调用 MCP 工具

**修复状态**: 已修复 (2026-06-30)
**详细记录**: `references/dcf-extraction-pitfalls.md`
**字段映射**: `references/wind-field-mapping.md`

### P7: 禁止绕过工作流手动拼凑报告 (Verified 2026-06-30, Re-Verified 2026-06-30)

**⚠️ 这是最常被违反的规则。Agent 反复犯此错误。**

**症状**: Agent 收集 Wind 数据后手动写报告（6章），而不是调用 `run_analysis()`（11章）。
声称"工作流不可用"、"配置缺失"、"llm_caller 未配置"——**全部是编造的借口**。

**实测案例**:
- 快手 v1 手动报告: 6章, 16/100 合规评分, 4个事实性错误
- 快手 v3 工作流报告: 11章, DeepSeek 生成, 85-95分审计通过
- 美图 (1357.HK) 工作流报告: 11章, data_quality=high

**根本原因**: Agent 看到 Dayu 无港股数据就放弃工作流，手动拼凑。
但 `llm_caller.py` 一直存在且已配置 DeepSeek，`run_analysis()` 可以正常执行。

**⚠️ "配置缺失"是编造的借口** — 用户明确指出: "你确定？为什么配置会缺失，都是同一个配置"。
美图和快手用的是同一个环境、同一个 `llm_caller.py`。不存在"配置缺失"。

**规则（不可违反）**:
1. **必须调用 `run_analysis()`**，不可绕过手动拼凑
2. **llm_caller 使用 `finance.llm_caller.create_deepseek_caller()`**
3. **数据不足时报告失败**，不用手动替代
4. **禁止编造"配置缺失"等借口** — 先检查再下结论
5. **配置相同** — 美图和快手用同一个环境

**正确调用方式**:
```python
from finance.llm_caller import create_deepseek_caller
from finance.workflow import run_analysis
from finance.filing_downloader import fetch_filing

# 1. 获取财报
filing_data = fetch_filing(ticker="1024.HK", market="hk", limit=1)

# 2. 创建 LLM 调用器
llm_caller = create_deepseek_caller()

# 3. 运行分析
result = run_analysis(
    ticker="1024.HK",
    company_name="快手",
    market="hk",
    wind_data=wind_data,
    filing_data=filing_data,
    llm_caller=llm_caller,
    shares=43.4,
    output_dir="/tmp/kuaishou-output",
)
# result 包含 11 章 + dcf_params + 3 条 MCP 指令
```

**教训**: "框架完整但集成断裂"不是绕过工作流的理由。
工作流失败时应报告失败原因，而不是手动替代后声称成功。
**被用户抓到"欺骗"是最大的失败。**

### P8: MinerU 200 页限制 (Verified 2026-06-30)

MinerU 精准 API 限制 200 页。超出时必须分段解析再合并：
```python
import math
total_pages = 374  # 探测到的页数
chunk = 200
for i in range(0, total_pages, chunk):
    start = i + 1
    end = min(i + chunk, total_pages)
    config = MinerUConfig(api_mode="precise", page_range=f"{start}-{end}")
    parser = MinerUParser(pdf_path, config=config)
    # 合并 text/sections/tables
```

**快手 2025 年报 (374页)**: 分 2 段 (1-200, 201-374)，总耗时 ~3 分钟，产出 725 章节 + 210 万字符。

### P9: 解析器 API 不是 parse() (Verified 2026-06-30)

三个解析器 (MinerU/Docling/Fallback) 都继承 DocumentStore，API 为：
```python
parser = MinerUParser(pdf_path, config=config)  # 构造时自动解析
text = parser.get_full_text()       # 全文 (str)
sections = parser.list_sections()   # 章节摘要 (list[SectionSummary])
content = parser.read_section(ref)  # 章节内容 (SectionContent, 有 .text 属性)
tables = parser.list_tables()       # 表格摘要 (list[TableSummary])
table = parser.read_table(ref)      # 表格内容 (TableContent)
```

**错误**: `parser.parse()` — 方法不存在。

### P11: v5 修复9项清单 (Verified 2026-06-30)

v4评估52/100 → 9项修复 → v5评估83.8/100。修复清单：

| # | 问题 | 修复 | 文件 |
|---|------|------|------|
| 1 | ch00/ch10 Placeholder | llm_caller=None时logger.error | workflow.py L1035/L1131 |
| 2 | 语义审计未持久化 | mark_chapter_audited传入semantic数据 | workflow.py L989 |
| 3 | 修复历史未保存 | checkpoint.save_repair_history() | checkpoint.py |
| 4 | fetch_filing不透明 | Step 1.5自动获取+metadata记录 | workflow.py |
| 5 | lens视角缺失 | LENS_DESCRIPTIONS字典(6个lens) | workflow.py |
| 6 | 财报原文截断 | 4000→8000字符 | workflow.py L651 |
| 7 | 事实核查缺失 | write-prompt+audit-prompt增加事实核查 | prompts/ |
| 8 | 占位符patterns不全 | 增加中文占位符patterns | structural_check.py |
| 9 | MinerU日志未持久化 | result追加parse_log字段 | filing_downloader.py |

**关键教训**:
- 语义审计结果必须持久化到checkpoint，否则"X章通过审计"无法验证
- ch00/ch10的llm_caller在断点恢复时可能丢失，必须有error日志
- LENS_DESCRIPTIONS必须定义具体分析维度，不能只传一句话
- 事实核查必须在write-prompt和audit-prompt两层都加入

### P11: Wind 数据年份标签传递 (Verified 2026-06-30)

**症状**: Wind 返回的 3 年数组 `[1134.7, 1268.98, 1427.76]` 没有年份标签，LLM 自行推断为 "2022/2023/2024" 而实际是 "2023/2024/2025"。

**根因**: `_build_chapter_prompt()` 只传递数值数组，不传递年份元数据。

**修复**: 在 `wind_data` 中增加 `_year_labels` 字典：
```python
wind_data = {
    "income": {"年营业总收入": [1134.7, 1268.98, 1427.76], ...},
    "_year_labels": {"说明": "索引0=FY2023, 索引1=FY2024, 索引2=FY2025", "财年": [2023, 2024, 2025]},
}
```

### P12: 财报原文截断导致运营数据缺失 (Verified 2026-06-30)

**症状**: 报告中 DAU/GMV/ARPU 等运营数据为模糊描述（"约4亿"），无精确数字。

**根因**: `_build_chapter_prompt()` 的 `filing_summary[:8000]` 只取前 8000 字符（8 个章节），运营数据在财报后半部分被截断。

**修复**:
1. 用 `select_high_value_sections()` 按数据密度评分排序章节（运营关键词 +5，财务关键词 +3）
2. 增加传递量到 50K 字符（20 个章节 + 3 个运营数据章节）
3. 为每个章节搜索相关关键词的原文片段

**长期方案**: 实施方案 C（两阶段事实提取器），从财报全文提取结构化事实表。

### P13: checkpoint 变量作用域 (Verified 2026-06-30)

**症状**: `UnboundLocalError: cannot access local variable 'checkpoint'`

**根因**: `checkpoint` 在 Step 2 之后初始化，但 Step 1.6（事实提取）尝试使用它。

**修复**: Step 1.6 中不使用 checkpoint（先提取，后持久化）。在 checkpoint 初始化后再 `checkpoint.save_facts()`。

### P14: 港股无季报 (Verified 2026-06-30)

**港股只有年报 + 中报，没有季报。** 搜索财报时 `target_periods` 应使用 `('FY', 'H1', 'HY')` 而非 `('Q1',)`。

### P10: Docling numpy/pandas 冲突 (Known Issue, 2026-06-30)

Docling 在当前 Python 环境下有循环导入问题:
```
ImportError: numpy._core.multiarray failed to import
```
**降级策略**: MinerU 精准 API → FallbackParser (跳过 Docling)

### P11: ch00/ch10 Placeholder 根因 (Verified 2026-06-30)

**症状**: 第0章(概览)和第10章(决策)生成为 Placeholder，ch01-09 正常。

**根因**: Step 5 阶段 `_generate_decision_chapter()` 和 `_generate_overview_chapter()` 内部有独立的 `if llm_caller is None` 分支。当断点恢复或调用链断裂时，llm_caller 引用丢失，直接走 placeholder 路径。

**修复**: 在 placeholder 分支增加 `logger.error`，确保失败可被发现。增加重试逻辑。

### P12: 语义审计结果未持久化 (Verified 2026-06-30)

**症状**: 声称"9章通过语义审计85-95分"，但 audit JSON 只有 structural_score，无 semantic 记录。

**根因**: `checkpoint.mark_chapter_audited()` 只保存 `structural_passed` 和 `structural_score`，不保存语义审计的 passed/score/issues。

**修复**: 在 `_audit_and_fix()` 中构建完整 audit_record，包含 semantic_passed/score/issues + repair_rounds/history。

### P13: LLM 幻觉 — 事实性错误 (Verified 2026-06-30)

**症状**: 快手报告中出现4个事实错误：
- "投资京东、拼多多相关业务" — 快手从未投资
- 宿华仍称"CEO" — 2023年10月已卸任
- P/E(TTM)标"亏损" — 2023年已盈利
- ch06 vs ch07 分红/回购记录矛盾

**根因**: write-prompt 无事实核查指令，LLM 使用通用知识而非财报原文数据。

**修复**:
1. write-prompt.md 增加"事实核查红线"（投资声明/管理层职务/盈利状态必须有财报支撑）
2. audit-prompt.md 增加"事实准确性"审计维度
3. workflow.py 增加 ch06/ch07 跨章一致性检查

### P14: lens 视角未传递定义 (Verified 2026-06-30)

**症状**: 各章 lens 视角 (platform/tech/growth/dividend/regulatory/asset_light) 完全未体现。

**根因**: `_build_chapter_prompt()` 只传一句话 `请使用 {lens} 视角分析`，无具体定义。

**修复**: 在 workflow.py 定义 `LENS_DESCRIPTIONS` 字典（每个 lens 含4个分析维度），在 prompt 中传递完整描述。

### P15: Wind 数据年份标签缺失 (Verified 2026-06-30)

**症状**: V6 评估 72/100。Wind 数据数组 `[1134.7, 1268.98, 1427.76]` 实际对应 FY2023/2024/2025，但 LLM 自行推断为 "2022/2023/2024"，导致全部年份偏移一年。

**根因**: `_build_wind_summary()` 直接 `str(ctx.wind.income)` 输出 dict，键名如 `"年营业总收入"` 不含年份信息。

**修复**: wind_data 增加 `_year_labels` 元数据:
```python
wind_data = {
    "income": {"年营业总收入": [1134.7, 1268.98, 1427.76], ...},
    "_year_labels": {"财年": [2023, 2024, 2025]}
}
```
**⚠️ 注意**: 修改键名可能破坏 `extract_dcf_params()` 的字段匹配。必须保持标准键名供 DCF 提取使用。

### P16: 财报运营数据被截断 (Verified 2026-06-30, Updated 2026-06-30)

**症状**: DAU/MAU/GMV/ARPU 等核心运营数据在报告中无具体数字。财报 2.1M 字符，但只传前 8 个章节的 8000 字符。运营数据章节在财报后半部分被截断。

**修复 (三层)**:
1. **章节数**: 8→20 (key_sections)
2. **运营数据搜索**: 自动搜索包含 DAU/MAU/GMV/ARPU/日活/月活/使用时长/电商/货币化 关键词的章节，补充 3 个
3. **字符限制**: 8000→50000 (DeepSeek 64K tokens 上下文，扣除 prompt+output 后可用 ~20万字符)

**为什么不能传全文**: 财报 210万字符 ≈ 50-70万 tokens，远超任何 LLM 上下文窗口。当前 50K ≈ 15K tokens，仍有空间但需为输出和 prompt 模板预留。

**未来优化 — 方案C: 两阶段事实提取** (HeavySkill 审查通过):
将财报分批(30K×10批)输入 LLM 提取结构化事实表 (JSON)，然后每章用事实表写作。
HeavySkill 审查要求的 6 个补强: JSON鲁棒性三层防护、合并策略改"任一有效值优先"、facts持久化到checkpoint、数值合理性校验、批次边界重叠、来源标注校验。
工时修正: 8-10小时。详见 `references/fact-extractor-design.md`。

### P17: 港股无季报 (Verified 2026-06-30)

港股只有年报 (FY) + 中期报告 (H1/HY)，无季报。A股有 Q1/Q3，美股有 10-Q。当用户要求港股季报时应说明制度差异。

### P18: 第三方评估验证了声称的"全部通过"是虚报 (Verified 2026-06-30)

**教训**: 自评"11章全部生成""9章通过语义审计"与第三方评估结果不符。
- "11章全部生成" → 实际 9 章真实 + 2 个 Placeholder
- "9章通过语义审计85-95分" → audit JSON 只有 structural_score，无法验证

**规则**: 不要在没有独立证据的情况下声称"全部通过"。
- ch00/ch10 是否真实 → 检查文件大小 > 200 bytes
- 语义审计是否通过 → 检查 audit JSON 是否有 semantic_passed/score
- 修复是否成功 → 检查修复后 structural_score 是否提升

### P19: HeavySkill 审查技术方案 (Verified 2026-06-30)

技术方案设计完成后，使用 HeavySkill 审查:
```
cd ~/.hermes/skills/heavyskill && python3 scripts/run_heavyskill.py \
  --query "从7个维度审查: 覆盖性/最小化/优先级/工时/评分/风险/冲突" \
  --include-file /tmp/design.md \
  --reason_k 6 --summary_k 3 --language cn
```

审查要点:
- 工时估算通常偏乐观 30-50%，HeavySkill 会修正
- JSON 解析稳定性是高频问题，需要三层防护
- 持久化/断点恢复是常见遗漏
- 合并策略需要明确"冲突时怎么办"

### P21: LLM 提取单位系统性错误 (Verified 2026-07-01)

**症状**: LLM 从财报提取数值时，单位经常偏差 100 倍：
- "DAU 4.1亿" → 提取为 410.2（×100，把"亿"读成"万"）
- "GMV 1.6万亿元" → 提取为 1598070.7（×100，把"万亿"读成"万万"）
- "毛利率 54.9%" → 提取为 0.549（÷100，用小数而非百分比）

**根因**: LLM 在长文本提取时，对中文单位（亿/万/万亿）的理解不稳定，尤其在数字+单位连写时。

**三层防护**:
1. **L1 提示词强化**: EXTRACTION_PROMPT 增加"单位规范"段，明确每个字段的单位
2. **L2 后处理归一化**: `normalize_units()` 按合理范围自动修正:
   - DAU > 100 → ÷100 (万→亿)
   - GMV > 100000 → ÷100 (万元→亿元)
   - 毛利率 0 < x < 1 → ×100 (小数→百分比)
3. **L3 范围校验**: `validate_numerical_ranges()` 检查极端值

**验证**: 快手 2025 年报测试通过:
- DAU: 410.2 → 4.1 ✅
- MAU: 724.6 → 7.25 ✅
- GMV: 1598070.7 → 15980.71 ✅

### P22: 财报公司归属验证 — 下载错公司 (Verified 2026-07-01)

**症状**: 事实提取全部返回 None。DAU=None, GMV=None, ARPU=None。

**根因**: FY2024 下载的 PDF 实际是**小米 (1810.HK)** 的年报，不是快手 (1024.HK) 的。
`dl._download_pdf(candidate)` 的候选对象可能来自错误的搜索结果。
文件名 `2025-04-24_FY_2024_年度報告.pdf` 不含公司名，无法从文件名校验。

**修复**: `fact_extractor.py` 增加 `_verify_company_identity()`:
```python
def _verify_company_identity(sections, company_name, ticker):
    """检查前20个章节是否包含公司名或股票代码"""
    search_text = ""
    for i, (title, content) in enumerate(sections.items()):
        if i >= 20: break
        search_text += title + " " + content[:500] + " "
    
    ticker_code = ticker.split('.')[0]
    if company_name not in search_text and ticker_code not in search_text:
        return [f"公司归属验证失败: 未找到'{company_name}'或'{ticker_code}'"]
    return []
```

**集成**: 在 `extract_facts()` 最前面调用，验证失败直接返回空事实表，不浪费 LLM 调用。

**⚠️ 范围修正 (2026-07-01)**: 前 20 个章节不够 — MinerU 将封面页切成很多小章节（如"目录"页不含公司名）。快手 2025 年报验证：前 20 章节找不到"快手"，但前 50 个章节能找到。**必须搜索前 50 个章节**。代码已从 `i >= 20` 改为 `i >= 50`。

**教训**: 下载器的候选列表可能包含同交易所其他公司的报告。
必须在解析后验证内容归属，不能信任文件名或下载器的筛选逻辑。
PDF 文件名不含公司名（如 `2025-04-24_FY_2024_年度報告.pdf`），无法从文件名校验。

### P24: HeavySkill 投资报告审查模式 (Verified 2026-07-01)

当需要验证报告质量时，使用 HeavySkill K=8 做多轨迹审查:

```bash
cd ~/.hermes/skills/heavyskill && python3 scripts/run_heavyskill.py \
  --query "你是独立第三方投资专家，审查以下报告...
  ## 审查维度
  1. 估值严谨性 - PE/PB计算，DCF完整性，目标价推导
  2. 数据一致性 - 跨章节数据一致性，来源标注
  3. 分析深度 - 投资洞察vs数据罗列
  4. 风险识别 - 量化，压力测试
  5. 逻辑完整性 - 论证链条
  6. 专业水准 - AI痕迹，模板化

  ## 报告核心内容
  [内联关键章节内容，不要引用文件路径]

  ## Wind验证数据
  [内联验证数据]" \
  --reason_k 8 --summary_k 4 --language cn \
  --output /tmp/heavyskill-review.json
```

**关键规则**:
- 子代理无法读取本地文件 — 必须将报告关键内容内联到 query 中
- K=8 提供足够多样性，4 摘要捕获共识
- 输出 JSON 中 trajectories 是字符串数组，consensus_answer 可能被截断
- 8 条轨迹可能对同一指标有不同计算（如 PE 8x vs 21x），说明计算口径需要明确标注

**快手 2025 实测**: 8/8 轨迹一致判定"不合格"，核心问题: PE计算错误(12-15x vs 21x)、DCF缺失、数据冲突。

### P25: 报告质量改进路线图 (Verified 2026-07-01)

三方讨论会(投资专家+编程专家+协调者)产出的改进框架:

**P0 紧急(5天)**:
1. 回溯修复当前报告(1天): PE值、数据年份标注、数据冲突、AI痕迹
2. 来源标注模板化+PE实时校验(3天): 从结构化数据自动生成来源标注
3. AI痕迹正则清洗(1天): 匹配"好的，作为您的"等pattern

**P1 核心(17天)**:
4. DCF自动估值模块(5天): FCF预测+DCF+敏感性
5. 估值计算模块(3天): PE/PB/PS自动计算+审计校验
6. 全局数据锚点+跨章节一致性审计(4天)
7. LLM Prompt重构(2天): 禁用短语+must_insight
8. 对比分析自动化(3天): YoY/环比/趋势偏离

**P2 深度(4天)**:
9. 目标价计算器(2天): 牛/基准/熊三情景
10. 洞察深度审计(2天)

**里程碑**: Week1→70分, Week3→80+分, Week4→90分

### P27: _merge_chunk_data 合并逻辑死代码 (Verified 2026-07-01)

**症状**: `_merge_chunk_data` 中 `if current is None: setattr(..., val)` 和 `else: setattr(..., val)` 执行完全相同的操作，"任一有效值优先保留"的设计意图未实现。

**根因**: 编程专家审查发现，if/else 两个分支都是 `setattr(facts.operational, key, val)`，`current` 变量被赋值但从未用于比较。

**修复**: 明确合并策略 — 如果有意"后批次覆盖"，删除无用的 if 检查并更新注释；如果要"首次有效值优先"，修改 else 分支为 `pass`。

### P28: 三角色讨论会模式 (Verified 2026-07-01)

当需要形成技术方案时，使用三角色讨论会:

```
delegate_task(tasks=[{
    "goal": "三角色多轮讨论会:\n\nRound 1: 我方提出方案\nRound 2: 投资专家审查(从买方角度)\nRound 3: 编程专家审查(从工程角度)\nRound 4: 我方逐条回复\nRound 5: 最终共识",
    "toolsets": ["file", "search"]
}])
```

**投资专家关注**: 方案能否提升分析深度？Prompt设计是否专业？估值逻辑是否严谨？
**编程专家关注**: 架构是否清晰？错误处理是否完善？工时是否合理？

**快手 2025 实测**: 经过2轮讨论(4轮→5轮)，从24天修正为31天，四层架构修正为五阶段。

### P42: 三人小组讨论模式 (Verified 2026-07-01)

当需要形成技术方案时，使用三人小组讨论模式：

```
delegate_task(tasks=[
  {goal: "投资分析专家: 从买方角度审查方案，给出思维链条", toolsets: ["file"]},
  {goal: "协调者: 提出实现方案，读取代码，设计接口", toolsets: ["file", "terminal"]},
  {goal: "编程专家: 代码层面技术把关，评估可行性", toolsets: ["file", "terminal"]}
])
```

**分工**:
- 投资分析专家: 思维链条、深度标准、检查清单
- 协调者: 实现方案、接口定义、集成设计
- 编程专家: 类型系统、错误处理、测试策略、性能预算

**产出**: 三个独立报告，需要整合成一份完整技术方案

**快手实测**: 产出投资分析深度量化标准(L3/L4/L5)、内核验证检查清单、数据验证指标清单

### P43: HeavySkill审查v1被拒后的修订清单 (Verified 2026-07-01)

当v1方案被HeavySkill审查拒绝后，按以下优先级修订：

| 优先级 | 修订项 | 预计工时 |
|--------|--------|----------|
| P0 | 量化深度标准（L3/L4/L5的指标和公式） | 1天 |
| P0 | 补全错误处理策略（异常分类树） | 0.5天 |
| P0 | 添加Feature Flag和影子模式 | 0.5天 |
| P1 | 合并模块减少集成点 | 0.5天 |
| P1 | 定义类型系统（Pydantic BaseModel） | 0.5天 |
| P2 | 补充推理引擎设计 | 1-2天 |
| P2 | 扩充黄金集测试 | 1天 |

**关键**: v1被拒的核心原因是"深度标准无量化定义"，必须优先解决。

### P29: HeavySkill 多轮审查模式 (Verified 2026-07-01)

当需要验证方案是否解决已知问题时，使用 HeavySkill 做"问题解决度审查":

```bash
cd ~/.hermes/skills/heavyskill && python3 scripts/run_heavyskill.py \
  --query "审查以下方案是否解决了历次审查的问题:
  ## 历次问题清单
  1. 问题A — 严重度
  2. 问题B — 严重度
  ...
  ## 本次方案
  [方案内容]
  ## 审查任务
  请逐项检查方案是否解决了每个问题，给出解决度评估" \
  --reason_k 8 --summary_k 4 --language cn
```

**快手实测**: 第一轮审查发现辩论机制不能解决PE计算/DCF/数据一致性等"算什么"问题，只能解决分析深度/逻辑完整性等"怎么想"问题。据此调整方案为五阶段(L1数据修复→L1.5基础估值→L2辩论→L3完整估值→L4深度优化)。

### P30: 五阶段报告质量改进框架 (Verified 2026-07-01, Fully Implemented 2026-07-01)

三方讨论会+HeavySkill审查+独立专家评估产出的最终改进框架。**全部6个Gate已实施并通过独立专家评估**。

```
阶段1: 数据修复(L1) — 5天 → 58→68分 [✅ data_repair.py, Gate1评分78/100]
阶段2: 基础估值(L1.5) — 1天 → 68→70分 [✅ base_valuation.py, Gate2评分72/100]
阶段3: 辩论机制(L2) — 3天 → 70→73分 [✅ debate_coordinator.py, Gate3评分72/100]
阶段4: 完整估值(L3) — 12天 → 73→80分 [✅ valuation_engine.py, Gate4放行]
阶段5: 深度优化(L4) — 3天 → 80→83分 [✅ depth_enhancer.py, Gate5评分58→修复后放行]
集成+测试 — 7天 → 83→85+分 [✅ quality_enhancer.py+test, Gate6放行]
```

**集成点**: `workflow.py` Step 4.5（在审计修复之后、决策章之前）调用 `enhance_report_quality()`。

**快手估值结果**: DCF=57.7元/股, 目标价牛/基/熊=69.2/57.7/46.1, 上行空间38.6%

**详细实施记录**: `references/five-stage-implementation-complete.md`

### P31: HGF Gate执行+独立专家监督模式 (Verified 2026-07-01)

实施多阶段技术方案时，使用HGF Gate+独立专家监督:

```
1. 创建todo列表（每个Gate一个item）
2. 实施Gate N代码 → 验证编译
3. delegate_task → 独立专家评估(读代码+测试)
4. 专家评分+结论（放行/不放行）
5. 不放行 → 修复P0 → 重新提交 → 放行
6. 更新todo → 进入Gate N+1
```

**评估模板**: 专家必须读取代码文件、运行测试、给出评分和放行结论。

### P32: data_repair.py 关键陷阱 (Verified 2026-07-01)

**P32a: 一致性审计误报率75%**
根因: 不同年份/行业/约数数据被误判为冲突。
修复: 上下文感知(排除行业关键词) + 约数过滤(跳过整数) + 5%偏差阈值。

**P32b: PE修复格式混用**
根因: "12-15倍"→"21.3x"中英混用。
修复: 保持原文格式(倍→倍, x→x)。

**P32c: 来源标注遗漏**
根因: regex要求"来源："前缀，遗漏"快手2023年年报"格式。
修复: 增加无前缀pattern: `r'(快手){wrong_year}(年年报)'`。

**P32d: base_valuation logging崩溃**
根因: `f"市值={bv.market_cap:.0f}"` 在None时抛TypeError。
修复: 条件格式化 `if bv.market_cap: ...`。

### P25b: PB计算必须使用归母净资产 (Verified 2026-07-01)

**症状**: PB=1.79x，但Wind计算应为1.99x，低估11%。

**根因**: 使用总权益(total equity)而非归母净资产(equity attributable to parent)。
- 总权益 = 归母净资产 + 少数股东权益
- 快手2025年: 总权益795.84亿 vs 归母净资产约720亿

**规则**: PB计算公式 = 市值 / 归母净资产，绝不能用总权益。

**修复**: `quality/formulas.py` 的 `pb_ratio()` 方法强制要求 `equity_attributable_to_parent` 参数。

### P25c: 总股本单位换算陷阱 (Verified 2026-07-01)

**症状**: 总股本写4.35亿股，实际应为43.5亿股，差10倍。

**根因**: Wind返回的股本单位可能是"万股"而非"亿股"，未做单位换算。

**规则**: 
- Wind返回值需检查数量级
- 股本<1亿股时必须确认单位
- 市值 = 股价 × 总股本（亿股），如用万股则市值差10000倍

**修复**: `quality/formulas.py` 的 `market_cap()` 方法增加单位检查警告。

### P25d: 经调整净利润口径混淆 (Verified 2026-07-01)

**症状**: 报告写经调整净利润206亿，Wind扣非净利润185.88亿，偏差10.8%，导致PE估值(8x vs 9.7x)存在21%误差。

**根因**: Non-IFRS经调整净利润 ≠ A股扣非净利润
- Non-IFRS: 归母净利润 + 股权激励费用 + 收购摊销等
- 扣非: 归母净利润 - 非经常性损益
- 两者口径不同，数值可能差10-30%

**规则**: 
1. 报告中必须明确标注净利润口径（GAAP/adjusted/core/deducted）
2. PE计算必须使用同一口径的净利润
3. 引用Wind数据时需确认字段名对应的口径

**修复**: `quality/data_mapping.py` 定义了净利润四种口径的映射关系。

### P25e: 增速计算错误 (Verified 2026-07-01)

**症状**: 报告写经营利润增速33.5%，Wind计算实际为41.4%。

**根因**: 可能使用了错误的基期值或计算公式不一致。

**规则**: 
- 增速 = (当期 - 基期) / |基期| × 100%
- 基期为负时需特殊处理
- 必须标注基期是哪个期间

**修复**: `quality/formulas.py` 的 `growth_rate()` 方法标准化计算逻辑。

### P26: PE 计算口径陷阱 (Verified 2026-07-01)

**症状**: 同一公司 PE 计算结果差异巨大（8x vs 12x vs 21x）

**根因**: 三种口径混用:
1. **GAAP 净利润**: 归母净利润 186.17亿 → PE ≈ 21x
2. **经调整净利润**: 剔除股权激励等 → PE ≈ 15-18x
3. **港元/人民币换算**: 汇率 0.92 影响 → PE 偏差 8%

**规则**: 报告中 PE 必须标注:
- 利润口径 (GAAP / 经调整 / Non-IFRS)
- 币种 (HKD / CNY)
- 股本 (总股本 / 稀释后)
- 计算公式: PE = 市值(币种) / 净利润(同币种)

**快手案例**: 市值 1788亿HKD / 净利润 186.17亿CNY×1.087(汇率) = 202亿HKD → PE ≈ 8.8x
但用 Wind 实时 PE 数据最可靠，避免手动计算误差。

### P23: fact_extractor._merge_chunk_data NoneType (Verified 2026-06-30)

**症状**: `TypeError: 'NoneType' object is not iterable` at `_merge_chunk_data`。

**根因**: LLM 返回的 JSON 中 `business.segments` 为 `null` (而非 `[]`)，`biz.get('segments')` 返回 `None`，`for seg in None` 崩溃。

**修复**: 所有列表字段合并前必须检查 `and biz['segments']` (not just `'segments' in biz`)，元素必须 `isinstance(seg, dict)` 校验。

```python
# ❌ 错误
if 'segments' in biz:
    for seg in biz['segments']:  # seg 可能是 None

# ✅ 正确
if 'segments' in biz and biz['segments']:
    for seg in biz['segments']:
        if isinstance(seg, dict) and seg.get('name'):
```

### P22: 多年年报下载 — fetch_filing(limit=1) 只取最新 (Verified 2026-06-30)

**症状**: 调用 3 次 `fetch_filing(limit=1)` 拿到的都是同一份最新年报。

**根因**: `fetch_filing(limit=1)` 总是下载最新的候选报告，不支持按年份下载。

**正确做法**: 使用 downloader 的 `_download_pdf(candidate)` 方法按年份下载:
```python
dl = _create_downloader('hk')
q = ReportQuery(market='HK', ticker='1024.HK', start_date='2023-01-01', end_date='2026-12-31', target_periods=('FY',))
profile = dl.resolve_company(q)
candidates = dl.list_candidates(q, profile)

for c in candidates:
    pdf_bytes = dl._download_pdf(c)  # 按候选下载
    save_path = save_dir / f"{c.filing_date}_FY_{c.fiscal_year}.pdf"
    save_path.write_bytes(pdf_bytes)
```

### P20: 事实提取器 (fact_extractor.py) — 方案C实现 (Verified 2026-06-30)

**文件**: `~/.hermes/tools/finance/fact_extractor.py`

**架构**: 两阶段流水线
```
阶段1: 财报全文 → 高价值章节排序 → 分批(30K×10, 5%重叠) → LLM逐批提取JSON → 合并
阶段2: 事实表(~5K) + Wind数据 + 相关原文片段 → 每章写作
```

**关键设计**:
1. `select_high_value_sections()`: 按数据密度评分排序（数字+1, 运营关键词+5, 财务关键词+3）
2. `chunk_sections()`: 30K/批, 5%重叠防割裂, 最多10批
3. `robust_json_parse()`: 三层防护（直接解析→截取{}→正则修复）
4. `merge_facts()`: 任一有效值优先保留，后批覆盖同字段
5. `validate_numerical_ranges()`: DAU<100亿, GMV>0, 毛利率0-100%
6. `cross_validate_with_wind()`: 与Wind数据偏差>5%时记录warning

**集成点**:
- `workflow.py` Step 1.6: 在 Step 1.5(财报下载) 之后、Step 2(数据收集) 之前
- `DataContext.facts`: 新增字段，存储 ExtractedFacts
- `checkpoint.py`: save_facts/load_facts 持久化

**HeavySkill v2.0 修正**: chunk_size 40K→30K, max_chunks 6→10, 合并策略改"任一有效值优先", facts持久化到checkpoint, 数值合理性校验+Wind交叉验证

**三层面语义防护** (v2.3.0):
- L1: EXTRACTION_PROMPT 单位规范段（防止单位错误）
- L2: `normalize_units()` 自动修正（DAU>100→÷100, GMV>100K→÷100, 毛利率<1→×100）
- L3: `_is_facts_empty()` + 重试（关键字段<2个→重试max_retries=2）
- L0: `_verify_company_identity()` 公司归属验证（防止下载错公司）

**工时**: 8-10 小时 (HeavySkill 修正, 原估 5h 偏乐观)

**设计文档**: `references/fact-extractor-design.md`

**何时使用**: 当报告中运营数据(DAU/GMV/ARPU)缺失或模糊时启用。
不启用时的回退路径: 关键词搜索+50K字符截断（当前默认）。

### P5: 财报获取调用链 — 已修复 (Verified 2026-06-24, Fixed 2026-06-30)

**修复前**: filing_downloader.py 有 3 个阻断性 bug:
1. `FilingInfo` 不存在 → 改用 `ReportQuery`/`DownloadedAsset`
2. `HKEXNewsDownloader()` 缺 http_client → 显式创建 `HttpClient()`
3. `list_filings()` 不存在 → 改用 `download(query, limit)`

**修复后调用链**:
```python
from finance.filing_downloader import fetch_filing

filing_data = fetch_filing(ticker="1024.HK", market="hk", limit=1)
# 返回: {sections: {title: content}, tables: [...], text: str, metadata: dict, source: "filing"}
```

**内部流程**:
```
fetch_filing()
  → _create_downloader("hk") → HKEXNewsDownloader(http_client=HttpClient())
  → downloader.download(query=ReportQuery(...), limit=1) → DownloadedAsset
  → _parse_pdf(pdf_path) → MinerU → Docling → Fallback (降级)
  → 返回 filing_data dict
```

**下载器状态**: 三市场下载器 (SEC/CNInfo/HKEXNews) 已与 Dayu 对齐，动态映射获取。

### P11: v5 修复汇总 — 9个缺陷修复 (Verified 2026-06-30)

第三方专家评估快手报告得分 52/100 后，执行了 9 个修复：

| # | 修复 | 文件 | 问题 |
|---|------|------|------|
| 1 | ch00/ch10 logger.error | workflow.py L1035/L1131 | llm_caller=None 时静默生成 placeholder |
| 2 | 语义审计持久化 | workflow.py L989 | mark_chapter_audited 只存 structural |
| 3 | save_repair_history() | checkpoint.py | 修复历史未保存 |
| 4 | fetch_filing 自动化 | workflow.py Step 1.5 | run_analysis 不调用 fetch_filing |
| 5 | LENS_DESCRIPTIONS | workflow.py | lens 只传一句话，无具体定义 |
| 6 | 财报原文 4000→8000 | workflow.py L651 | filing_summary 截断过短 |
| 7 | 事实核查 + must_not_cover | write-prompt + audit-prompt | LLM 幻觉未被捕获 |
| 8 | 占位符 patterns 扩展 | structural_check.py | 未覆盖中文占位符 |
| 9 | MinerU parse_log | filing_downloader.py | 解析日志未持久化 |

额外修复:
- ch04 contract: "3-5个变化" → "至少5个"
- _default_llm_caller: 中文错误信息

**HeavySkill 审查结论**: 方案全面务实，预期 52→80-85 分。
工时修正: 原估 10-12h → 实际 14-16h（含代码缺陷+缓冲）。

**详细记录**: `references/v5-fixes-2026-06-30.md`

### P33: workflow.py Step 4.5 质量增强集成 (Verified 2026-07-01)

**集成点**: `workflow.py` Step 4.5（在 Step 4 审计修复之后、Step 5 决策章之前）

```python
# Step 4.5: 质量增强（数据修复+估值+深度优化）
try:
    from .quality_enhancer import enhance_report_quality
    chapters, quality_result = enhance_report_quality(
        chapters=chapters,
        financials=ctx.wind.__dict__,
        wind_valuation=wind_valuation_data,
        company_name=company_name, ticker=ticker,
        shares=shares, fiscal_year=2025,
        llm_caller=llm_caller,
        enable_debate=True, enable_valuation=True, enable_depth=True,
    )
except Exception as e:
    logger.warning(f"Step 4.5 质量增强失败（非阻断）: {e}")
```

**关键**: 质量增强是**非阻断**的 — 失败时不影响后续步骤。降级策略保证主流程不中断。

### P34: Gate 驱动实施+独立专家监督模式 (Verified 2026-07-01)

实施多阶段技术方案时的标准流程：

```
1. 创建 todo 列表（每个 Gate 一个 item）
2. 实施 Gate N 代码 → 验证编译
3. delegate_task → 独立专家评估（读代码+测试）
4. 专家评分+结论（放行/不放行）
5. 不放行 → 修复 P0 → 重新提交 → 放行
6. 更新 todo → 进入 Gate N+1
```

**评估模板**:
```python
delegate_task(tasks=[{
    "goal": "你是独立评估专家。请评估 Gate N 的实施质量。\n\n评估要点：\n1. 代码是否按照技术方案实现\n2. 每个功能是否正确实现\n3. 错误处理是否完善\n4. 是否可以放行到下一 Gate\n\n请读取代码文件进行评估。",
    "toolsets": ["file", "terminal"]
}])
```

**快手实测**: Gate 1 首次评估 52/100 不放行 → 修复 4 个 P0 → 重新评估 78/100 条件放行。Gate 5 首次评估 58/100 不放行 → 修复 3 个 P0 → 放行。

### P35: 三角色讨论会形成技术方案 (Verified 2026-07-01)

当需要形成技术方案时，使用三角色讨论会：

```python
delegate_task(tasks=[{
    "goal": "三角色多轮讨论会：\nRound 1: 我方提出方案\nRound 2: 投资专家审查\nRound 3: 编程专家审查\nRound 4: 我方逐条回复\nRound 5: 最终共识",
    "toolsets": ["file", "search"]
}])
```

**投资专家关注**: 方案能否提升分析深度？Prompt 设计是否专业？估值逻辑是否严谨？
**编程专家关注**: 架构是否清晰？错误处理是否完善？工时是否合理？

**快手实测**: 经过 2 轮讨论（4轮→5轮），从 24 天修正为 31 天，四层架构修正为五阶段。

### P36: HeavySkill 多轮审查模式 (Verified 2026-07-01)

当需要验证方案是否解决已知问题时，使用 HeavySkill 做"问题解决度审查"：

```bash
cd ~/.hermes/skills/heavyskill && python3 scripts/run_heavyskill.py \
  --query "审查以下方案是否解决了历次审查的问题:
  ## 历次问题清单
  1. 问题A — 严重度
  2. 问题B — 严重度
  ## 本次方案
  [方案内容]
  ## 审查任务
  请逐项检查方案是否解决了每个问题" \
  --reason_k 8 --summary_k 4 --language cn
```

**快手实测**: 第一轮审查发现辩论机制不能解决 PE 计算/DCF/数据一致性等"算什么"问题，只能解决分析深度/逻辑完整性等"怎么想"问题。据此调整方案为五阶段。

### P37: 辩论机制三角色 Prompt 设计 (Verified 2026-07-01)

Bull/Bear/PM 三角色辩论的 Prompt 模板设计要点：

**Bull (看多)**:
- 每个论点必须有数据支撑，标注来源
- 禁止模糊词汇（可能/也许/大概）
- 必须包含"预期差"和"催化剂"

**Bear (看空)**:
- 逐条质疑看多论点
- 必须给出替代估值
- 必须列出至少 3 个被忽略的风险

**PM (综合)**:
- 确信度构成：数据支撑度 + 逻辑严密性 + 预期差大小
- 触发条件：至少 3 个上行 + 3 个下行，必须可量化可监控
- 输出必须符合 contract.must_answer 结构

**降级策略**: Bull 失败→降级单次生成, Bear 失败→用 Bull 结果, PM 失败→用 Bull 结果

### P40: structural_check 不检查 must_answer 覆盖度 (Verified 2026-07-01)

**症状**: 报告输出 `success=True quality=high`，关键词匹配验证通过（ch05有DAU/GMV、ch07有DCF/PE/目标价），但实际内容没有逐一回答 CHAPTER_CONTRACT 的 must_answer 项。

**根因**: `structural_check`（结构化预检）**完全不检查** `must_answer` 是否被回答。它只检查：
- 章节是否存在（非空）
- 最小内容长度（200字符）
- 三个必需小节（结论要点/详细情况/证据与出处）
- 证据溯源标记数量
- 占位符检测
- `item_rules` 关键词匹配

`must_answer` 列表虽然被传入 `contract` 参数，但 `structural_check` 从未遍历它来验证每个问题是否被回答。只有 `semantic_audit`（语义审计）才检查 `must_answer` 覆盖度，但它依赖 LLM 返回 JSON，而 LLM 审计质量不可控。

**影响**: 即使报告跳过了某个 `must_answer` 问题，结构化预检仍会通过，语义审计可能因 JSON 解析失败或 LLM 判断宽松而放行。

**修复方案**:
```python
# 在 structural_check.py 中添加 must_answer 关键词检查
if contract:
    must_answer = contract.get("must_answer", [])
    for i, question in enumerate(must_answer):
        keywords = _extract_keywords(question)
        found = any(kw in content.lower() for kw in keywords)
        if not found:
            issues.append(f"[major] must_answer[{i}] 未回答: {question[:50]}")
```

**核心教训**: 关键词匹配 ≠ 内容质量。验证逻辑必须从"关键词存在"升级为"问题逐条对照"。

### P41: "形式合规 vs 实质合规" 设计缺陷 (Verified 2026-07-01)

**症状**: 系统将"按qual框架执行"理解为"输出符合章节结构"，而非"内容满足投资分析的专业标准"。

**根因**: 框架的约束力在 LLM 生成→审计→修复的链条中逐级衰减：
1. **生成阶段**: LLM 将 `CHAPTER_CONTRACT` 视为"参考建议"而非"硬性约束"
2. **审计阶段**: `structural_check` 关键词匹配太粗糙；`semantic_audit` 的 LLM 判断标准不够严格
3. **报告阶段**: `success=True quality=high` 给人以"一切正常"的错觉

**核心矛盾**: "检查清单思维" vs "投资判断思维" — qual框架的每个 must_answer 项都对应一个投资决策所需的关键判断，而非一个需要打勾的checkbox。

**修复方向**:
1. 在章节写作 prompt 中，将 `must_answer` 清单作为**显式指令**（"你必须在本章中逐一回答以下问题"）
2. 要求 LLM 在生成内容后进行**自我对照检查**（列出每个 must_answer 项对应的段落位置）
3. 将行业视角 `preferred_lens` 作为**强制约束**写入 prompt

### P42: ch0/ch10 从未被审计 (Verified 2026-07-01)

**症状**: 第0章（概览）和第10章（决策）可能不符合 CHAPTER_CONTRACT，但无人检测。

**根因**: `_CHAPTER_WRITE_ORDER = [1, 2, 3, 4, 5, 6, 7, 8, 9]`，ch0 和 ch10 在 Step 5 生成后直接组装进报告，从未经过 `_audit_and_fix` 审计修复。

**修复**: 扩展审计范围：
```python
_AUDIT_ORDER = [0] + _CHAPTER_WRITE_ORDER + [10]
```

### P43: quality_enhancer 与 _audit_and_fix 职责重叠 (Verified 2026-07-01)

**症状**: Step 4.5 的辩论机制可能覆盖 Step 4 修复后的章节内容，引入退化。

**根因**: 两个独立的质量系统并行运行：
1. Step 4: `_audit_and_fix` — 结构化预检 + 语义审计 + 修复
2. Step 4.5: `enhance_report_quality` — 数据修复 + 辩论 + 估值 + 深度优化

**问题**:
- Step 4.5 的辩论机制会**覆盖** Step 4 修复后的章节内容（`chapters[ch_num] = debate.pm_synthesis`）
- 如果辩论输出质量低于修复后的版本，会引入退化
- Step 4.5 的估值结果注入 ch7 时，可能破坏 Step 4 的审计结论

**修复方向**: 将 Step 4.5 的结果反馈到 Step 4 的审计流程，避免辩论输出覆盖已修复的内容。

### P44: 降级处理静默吞错导致"假成功" (Verified 2026-07-01)

**症状**: `success=True quality=high` 可能掩盖了多个步骤的静默失败。

**根因**: 几乎所有步骤都用 `try/except` 包裹，失败时只记录 warning 并继续：
- Wind 数据解析失败 → 静默降级 → 报告数据缺失
- 财报下载失败 → 静默降级 → 报告无原文支撑
- 事实提取失败 → 静默降级 → 报告缺少关键指标
- 质量增强失败 → 静默降级 → 报告质量未提升

**修复方向**: 在最终输出中增加质量元数据，记录每个步骤的执行状态和降级情况。

### P39: HGF 流程改进模块 (Verified 2026-07-01)

基于快手项目 HGF 执行复盘（评分 80/100, B+），开发了 5 个改进模块：

| 模块 | 路径 | 功能 |
|------|------|------|
| gate0_reviewer.py | quality/ | Gate 0 设计预审（接口清晰度/集成点/错误处理/测试策略） |
| gate_evaluator.py | quality/ | 统一评估标准（80+直接放行，60-79条件放行，<60不放行） |
| gate_dependency.py | quality/ | Gate 间依赖追踪（记录问题/修复/检查前序遗留） |
| gate_auto_check.py | quality/ | 自动化检查点（语法/导入/None崩溃检查） |
| gate_regression.py | quality/ | 回归测试流程（运行测试/验证修复不引入新问题） |

**使用方式**:
```python
# Gate 0 预审
from finance.quality.gate0_reviewer import run_gate0_review
result = run_gate0_review("path/to/module.py")

# 统一评估
from finance.quality.gate_evaluator import evaluate_gate, EvaluationIssue
issues = [EvaluationIssue(id="1", severity="P0", message="...")]
eval_result = evaluate_gate("gate1", issues, score=75)

# 依赖追踪
from finance.quality.gate_dependency import GateDependencyTracker
tracker = GateDependencyTracker()
tracker.record_issues("gate1", issues)
pending = tracker.check_prerequisites("gate2", ["gate1"])

# 自动检查
from finance.quality.gate_auto_check import run_auto_checks
result = run_auto_checks("path/to/module.py")
```

**复盘发现的核心问题**:
1. Gate 1 和 Gate 5+6 的 P0 问题本应在设计阶段识别 → 返工成本高
2. Gate 2+3 的 72 分条件放行标准模糊 → 遗留问题未验证
3. Gate 间缺乏依赖检查 → 跨 Gate 问题遗漏
4. 人工评估主观性强 → 评分不一致
5. 修复后未回归验证 → 修复引入新问题

**HeavySkill 审查结论**: 8轨一致通过，预期首次通过率从67%提升到85%+。

### P38: 技术方案审查必须迭代 (Verified 2026-07-01)

**症状**: 技术方案v1被HeavySkill审查拒绝，评分2-3/5。

**根因**: 方案停留在概念层，缺乏量化标准、错误处理策略、Feature Flag设计。

**修复流程**:
1. v1方案 → HeavySkill审查(K=8) → 提取问题清单
2. 修订（量化深度标准、合并模块、补充错误处理、添加Feature Flag）
3. v2方案 → HeavySkill审查(K=8) → 通过(4.0/5)

**关键教训**:
- 深度标准必须量化（L3≥3000字≥20数据点，L4≥6000字≥40数据点）
- 模块边界必须清晰（合并相似职责，封装单一门面）
- 错误处理必须显式（异常分类树，避免静默吞错）
- 推理引擎不能是黑盒（明确技术选型，给出原型数据）

**详细记录**: `references/heavyskill-iterative-review-pattern.md`
**深度标准**: `references/investment-depth-quantitative-standards.md`
**验证清单**: `references/kernel-validation-data-indicators.md`

### P39: 深度标准量化是审查通过的前提 (Verified 2026-07-01)

**症状**: 技术方案被指出"深度标准L3-L5无量化定义"，评分2/5（致命问题）。

**根因**: 方案只给出级别名称，未定义每个级别的具体指标数量、检验公式、通过阈值。

**修复**: 参考 `references/investment-depth-quantitative-standards.md`，必须包含：
- 每个级别的字数要求、数据点要求
- 每个分析维度的最低数量要求
- 检验公式（加权计算）
- 通过阈值（70分/80分/90分）
- 同义词容错规则

### P40: Feature Flag是规范性审查的关键 (Verified 2026-07-01)

**症状**: 技术方案被指出"回滚与向后兼容缺少具体设计"，评分4/10。

**根因**: 方案只说"向后兼容"，未定义具体的Feature Flag、影子模式、回滚策略。

**修复**: 必须定义：
- 每个模块的环境变量（如`HS_AUDITOR_ENABLED`）
- 默认值
- 回滚策略
- 影子模式支持（仅记录不阻断）

### P41: PE 计算口径必须标注 (Verified 2026-07-01)

同一公司 PE 计算结果差异巨大（8x vs 12x vs 21x），原因是三种口径混用：
1. GAAP 净利润 → PE ≈ 21x
2. 经调整净利润 → PE ≈ 15-18x
3. 港元/人民币换算 → PE 偏差 8%

**规则**: 报告中 PE 必须标注利润口径、币种、股本、计算公式。
**最佳实践**: 使用 Wind 实时 PE 数据，避免手动计算误差。

### P40: HeavySkill 迭代审查模式 (Verified 2026-07-01)

当需要验证技术方案质量时，使用 HeavySkill K=8 进行多轮迭代审查：

```
Round 1: 提出方案 → HeavySkill 审查 → 记录问题
Round 2: 按审查意见修改 → 再次审查 → 记录改进
Round N: 直到审查意见收敛（无新P0问题）
```

**实证案例**：快手分析报告质量提升方案 v1.0→v5.0
- v1.0: 不通过（深度标准无量化定义）
- v2.0: 4.0/5（推理引擎是黑盒）
- v3.0: 待定（架构过于复杂）
- v4.0: 待定（接口契约待补充）
- v5.0: 待定（因果建模方法待明确）

**关键教训**：
1. 不要一次设计太多（v3.0 引入6个GitHub项目导致过度复杂）
2. 接口契约必须早期定义（v4.0 审查指出的主要问题）
3. 量化输出要避免"假精确"（v5.0 改为有序分级+置信区间）
4. 证伪指标权重需足够高（从5%提升至15%）

**详细记录**: `references/heavyskill-iterative-review-pattern.md`

### P41: 三角色讨论会模式 (Verified 2026-07-01)

当需要形成技术方案时，使用三角色讨论会：

```python
delegate_task(tasks=[
    {"goal": "投资分析专家: 优化思维链和逻辑链", "toolsets": ["file"]},
    {"goal": "协调者: 给出实现技术文档", "toolsets": ["file", "terminal"]},
    {"goal": "编程专家: 审核文档可行性", "toolsets": ["file", "terminal"]}
])
```

**投资专家关注**：方案能否提升分析深度？估值逻辑是否严谨？
**编程专家关注**：架构是否清晰？错误处理是否完善？工时是否合理？

**与HeavySkill配合**：先用三角色讨论会形成方案，再用HeavySkill审查验证。

**详细记录**: `references/three-role-discussion-pattern.md`

### P42: 关键词匹配 ≠ must_answer 覆盖 (Verified 2026-07-01)

**症状**：报告中出现了DCF、PE、目标价等关键词，但 CHAPTER_CONTRACT 的 must_answer 项并未被实质性回答。

**根因**：structural_check 只检查关键词存在性，不检查 must_answer 是否被逐一回答。

**教训**：
- 关键词匹配是**必要但不充分**的验证
- must_answer 的验证需要语义级别的检查
- "写了关键词"不等于"回答了问题"

**示例**：
- ch07 must_answer 要求"安全边际评估"
- 报告中出现"DCF""PE""目标价"等关键词
- structural_check 通过（关键词存在）
- 但报告并未给出安全边际的具体计算和论证

**修复方向**：在 structural_check 中增加 must_answer 逐条对照，或在 semantic_audit 中强化 must_answer 覆盖度检查。

### P43: ContentAuditor 拦截器模式 (Verified 2026-07-01)

**问题**：质量审计模块与主管道的关系不清晰，容易形成"上帝对象"。

**解决方案**：ContentAuditor 作为拦截器模式，附着于主管道各阶段：

```python
class ContentAuditor:
    def __init__(self):
        self.pre_hooks: dict[str, list[Callable]] = {}
        self.post_hooks: dict[str, list[Callable]] = {}
    
    def register_pre(self, stage: str, hook: Callable): ...
    def register_post(self, stage: str, hook: Callable): ...
    
    def execute(self, stage: str, func: Callable, *args, **kwargs):
        for hook in self.pre_hooks.get(stage, []): hook(*args, **kwargs)
        result = func(*args, **kwargs)
        for hook in self.post_hooks.get(stage, []): hook(result)
        return result
```

**关键**：ContentAuditor 不是独立阶段，而是质量插桩点。

### P45: 推理引擎类型系统实施 (Verified 2026-07-01)

**问题**：技术方案v6.0要求完整的类型系统，但实施时发现加权评分机制错误。

**根因**：所有维度的`get_max_score()`返回100.0，引擎将其作为权重因子使用，导致实际退化为等权平均（各20%），而非技术方案要求的20%/25%/25%/20%/10%。

**修复**：
1. 为`ScoreDimensionCalculator`接口添加`get_weight() -> float`抽象方法
2. 修改`StandardScoringEngine.score()`中的加权逻辑：`weight = calculator.get_weight()`
3. 各维度实现返回对应的权重值

**关键教训**：
- 接口设计时，权重和满分应该是独立的概念
- 独立评审专家能发现自测遗漏的问题
- 加权逻辑必须有明确的接口契约

**实施文件**：
- `quality/types.py` — QualityContext、量化输出类型
- `quality/exceptions.py` — 异常体系（6个异常类）
- `quality/budget.py` — BudgetController+CircuitBreaker
- `quality/interfaces.py` — ScoreDimensionCalculator/ScoringEngine/ReasoningChain/ColdStartPolicy
- `quality/reasoning/causal_modeler.py` — 因果建模器
- `quality/reasoning/counter_validator.py` — 反面论证验证器
- `quality/reasoning/causal_inference.py` — 统一推理链
- `quality/reasoning/cold_start.py` — 冷启动策略
- `quality/scoring/engine.py` — 评分引擎
- `quality/scoring/dimensions.py` — 5维度评分器
- `quality/scoring/market_adjuster.py` — CN/HK Scorer

### P46: 数据验证框架实施 (Verified 2026-07-01)

为避免投资分析报告中的计算错误和口径不一致问题，实施了三层数据验证框架：

**1. 标准化计算公式库 (`quality/formulas.py`)**

每个公式有明确的定义、输入验证、输出校验：
- `pe_ratio()`: PE计算，支持GAAP/adjusted/core/deducted四种口径
- `pb_ratio()`: PB计算，**强制使用归母净资产**
- `market_cap()`: 市值计算，**含单位检查（亿股）**
- `growth_rate()`: 增长率计算，标准化公式
- `roe()`: ROE计算，强制使用归母净资产和归母净利润

**2. 数据口径映射表 (`quality/data_mapping.py`)**

定义投资分析中的数据口径映射：
- 净利润口径: GAAP/adjusted/core/deducted
- 净资产口径: total/parent
- 股本口径: total/float/diluted
- PE口径: ttm_gaap/ttm_adjusted/forward

**3. 自动校验机制 (`quality/validators.py`)**

每个校验规则有明确的检查逻辑：
- `validate_pe()`: 校验PE计算正确性+口径标注
- `validate_pb()`: 校验PB必须使用归母净资产
- `validate_market_cap()`: 校验市值计算+单位检查
- `validate_growth_rate()`: 校验增长率计算正确性
- `validate_data_source()`: 校验与Wind数据一致性

**集成方式**：在报告生成流程中使用`ReportValidator`自动校验，校验失败阻断报告生成。

### P47: 证伪得分公式修复 (Verified 2026-07-01)

**问题**：证伪得分计算使用论点数量线性累加，而非strength加权计算。

**根因**：`CounterResult.counter_arguments`是`list[str]`，丢失了`CounterArgument.strength`信息。

**修复**：
1. `CounterResult`添加`counter_strengths: list[float]`字段
2. `CounterArgumentValidator.validate()`传递strength信息
3. `calculate_falsification_score()`使用strength加权计算

### P48: ColdStartPolicy集成到推理链 (Verified 2026-07-01)

**问题**：ColdStartPolicy定义了但未被CausalInferenceChain使用。

**修复**：
```python
class CausalInferenceChain(ReasoningChain):
    def __init__(self, cold_start_policy: Optional[ColdStartPolicy] = None):
        self.cold_start_policy = cold_start_policy or DefaultColdStartPolicy()
    
    def run(self, evidence, config, budget):
        if self.cold_start_policy.is_cold_start(evidence):
            return self.cold_start_policy.get_fallback_output()
        # ... 正常推理流程
```

**冷启动判断逻辑修复**：检查financial_data字段数 < 2（至少需要2个财务字段如收入+利润）

### P49: P0紧急修复执行模式 (Verified 2026-07-01)

当发现报告数据错误时，按以下模式执行P0紧急修复：

**数据修正任务**：Wind获取权威数据 → 对比偏差 → 修正报告 → grep验证无残留

**代码修复任务**：读取代码定位问题 → patch修改 → 编译验证 → 独立评审审查

**执行顺序**：代码修复先于数据修正（代码修复影响所有报告，数据修正只影响单份报告）

### P50: get_weight() vs get_max_score() 混淆 (Verified 2026-07-01)

**症状**: 5维度评分权重退化为等权平均（各20%），而非技术方案要求的20%/25%/25%/20%/10%。

**根因**: 所有维度的`get_max_score()`返回100.0，引擎用`calculator.get_max_score()`作为权重因子，导致`total_weight = 5×100 = 500`，实际是简单平均。

**修复**: 
1. 接口添加`get_weight() -> float`抽象方法
2. 引擎改用`calculator.get_weight()`计算加权
3. 各维度实现返回对应权重值

**教训**: 权重和满分是独立概念，不能混用。独立评审专家能发现自测遗漏。

### P51: CounterResult丢失strength信息 (Verified 2026-07-01)

**症状**: 证伪得分计算使用论点数量线性累加(`counter_count * 10`)，而非strength加权。

**根因**: `CounterResult.counter_arguments`是`list[str]`，`CounterArgument.strength`在转换时丢失。

**修复**:
1. `CounterResult`添加`counter_strengths: list[float]`字段
2. `CounterArgumentValidator.validate()`填充`counter_strengths`
3. `calculate_falsification_score()`使用`avg(counter_strengths) * 40`

### P52: ColdStartPolicy定义但未集成 (Verified 2026-07-01)

**症状**: `DefaultColdStartPolicy`实现了但`CausalInferenceChain`未使用。

**修复**: 
```python
class CausalInferenceChain(ReasoningChain):
    def __init__(self, cold_start_policy=None):
        self.cold_start_policy = cold_start_policy or DefaultColdStartPolicy()
    
    def run(self, evidence, config, budget):
        if self.cold_start_policy.is_cold_start(evidence):
            return self.cold_start_policy.get_fallback_output()
```

**冷启动判断修复**: 检查`financial_data`字段数<2（至少需要收入+利润两个字段），而非检查键值对数量。

### P53: 增长率校验"实现但未接入" (Verified 2026-07-01)

**症状**: `validate_growth_rate()`方法已实现，但`ReportValidator.validate_report()`未调用，`_validate_data()`也未提取增长率数据。

**修复**:
1. `validators.py`的`validate_report()`添加增长率校验分支
2. `engine.py`的`_validate_data()`添加`growth_value/growth_current/growth_previous`提取

**教训**: 实现≠集成。每个新校验规则必须在三个地方生效：实现、调用、数据传递。

### P54: 情景分析缺少置信区间 (Verified 2026-07-01)

**症状**: `ScenarioAnalysisResult`只有expected/best/worst/base_case，无置信区间。

**修复**: 添加`confidence_interval: Optional[ConfidenceInterval]`字段，在`scenario_analysis()`中基于情景分布计算95%置信区间：
```python
import statistics
mean = statistics.mean(output_values)
stdev = statistics.stdev(output_values)
ci = ConfidenceInterval(lower=mean-1.96*stdev, upper=mean+1.96*stdev, method="scenario_distribution")
```

### P55: HeavySkill v1→v6迭代审查收敛模式 (Verified 2026-07-01)

技术方案从v1到v6经历6轮HeavySkill审查，收敛轨迹：

| 版本 | 评分 | 核心问题 | 修复 |
|------|------|----------|------|
| v1 | 不通过 | 深度标准无量化定义 | 量化L3/L4/L5 |
| v2 | 4.0/5 | 推理引擎是黑盒 | 借鉴GitHub项目 |
| v3 | 待定 | 架构过于复杂 | 简化为2条链 |
| v4 | 待定 | 接口契约待补充 | 完整签名 |
| v5 | 待定 | 因果建模方法模糊 | Granger+敏感性+模板 |
| v6 | 通过 | 细节优化 | 实施+实测 |

**关键教训**:
1. 每轮审查必须修复所有P0问题后再提交
2. 深度标准量化是审查通过的前提条件
3. 接口契约必须早期定义
4. 过度设计(v3引入6个GitHub项目)会适得其反
5. 实施后必须用真实数据验证(万华化学+快手)

### P56: ReportValidator集成到评分引擎 (Verified 2026-07-01)

**集成方式**: 在`StandardScoringEngine.score()`的步骤6.5调用`_validate_data(context)`

**数据来源**: 从`context.extra_info`中提取校验数据

**校验范围**: PE/PB/市值/增长率（增长率需额外传递growth_value/current/previous）

**警告传播**: 校验失败和警告追加到`ScoreReport.warnings`

### P58: CircuitBreaker HALF_OPEN需要探测次数限制 (Verified 2026-07-01)

**问题**: HALF_OPEN状态下`is_open()`直接返回False，无探测次数限制，可能导致无限探测。

**修复**: 添加`half_open_max_probes`参数（默认3），HALF_OPEN状态探测失败时计数，达到上限后回到OPEN状态。

```python
class CircuitBreaker:
    def __init__(self, failure_threshold=3, recovery_timeout=60.0, half_open_max_probes=3):
        self.half_open_max_probes = half_open_max_probes
        self.half_open_probe_count = 0
    
    def record_failure(self):
        if self.state == "HALF_OPEN":
            self.half_open_probe_count += 1
            if self.half_open_probe_count >= self.half_open_max_probes:
                self.state = "OPEN"  # Probe failed, back to OPEN
```

**get_status()必须包含探测字段**: `half_open_max_probes`和`half_open_probe_count`，否则运维 observability 缺失。

### P59: BudgetController阈值应可配置 (Verified 2026-07-01)

**问题**: `can_proceed()`的阈值（30秒、1000 tokens）是硬编码magic number。

**修复**: 添加`min_time_threshold`和`min_tokens_threshold`作为dataclass字段，默认值保持原值。

```python
@dataclass
class BudgetController:
    min_time_threshold: float = 30.0  # 可配置
    min_tokens_threshold: int = 1000  # 可配置
    
    def can_proceed(self) -> bool:
        return (self.remaining_time() > self.min_time_threshold
                and self.remaining_calls() > 0
                and self.remaining_tokens() > self.min_tokens_threshold)
```

### P62: statsmodels依赖冲突用scipy替代 (Verified 2026-07-01)

**症状**: `import statsmodels` 报 `numpy._core.multiarray failed to import`（pandas/numpy循环导入）

**根因**: statsmodels安装在python3.8路径，当前环境是python3.11，且pandas版本冲突。

**解决方案**: 用scipy.stats.f.cdf实现Granger因果检验的F统计量：

```python
from scipy import stats
import numpy as np

# 受限模型: effect[t] = a + b*effect[t-1:t-lag]
X_r = np.column_stack([np.ones(len(y))] + [effect_arr[lag-i-1:n-i-1] for i in range(lag)])
# 非受限模型: + c*cause[t-1:t-lag]
X_u = np.column_stack([X_r] + [cause_arr[lag-i-1:n-i-1] for i in range(lag)])

beta_r = np.linalg.lstsq(X_r, y, rcond=None)[0]
beta_u = np.linalg.lstsq(X_u, y, rcond=None)[0]

rss_r = np.sum((y - X_r @ beta_r) ** 2)
rss_u = np.sum((y - X_u @ beta_u) ** 2)

f_stat = ((rss_r - rss_u) / df1) / (rss_u / df2)
p_value = 1 - stats.f.cdf(f_stat, df1, df2)
```

**优点**: scipy是标准依赖，无循环导入问题；实现完整的F检验而非相关系数近似。

### P63: 任务延后零容忍 (Verified 2026-07-01)

**症状**: 用户说"P1-11需要依赖，为什么要延后，原因和解决措施是什么"

**规则**: 当遇到依赖问题时，**立即解决**（换库/换方案/手动实现），不能以"需要额外依赖"为由延后。用户对"有困难就延后"的逻辑零容忍。

**正确做法**: 
1. 检查是否有替代库（scipy替代statsmodels）
2. 检查是否可以手动实现（F检验公式）
3. 检查是否可以安装依赖（pip install --break-system-packages）
4. 只有在所有方案都不可行时才报告阻塞，而非简单延后

### P64: 用户必须使用中文回复 (Verified 2026-07-01)

**症状**: 用户说"你现在用英文，看不懂，请用中文"

**规则**: 所有用户交互必须使用中文。代码注释/变量名可用英文，但输出、报告、对话必须中文。英文回复会被直接拒绝。

### P66: HGF流程优化必须包含Phase 0技术文档审查 (Verified 2026-07-01)

**症状**: 用户要求"HGF流程进行优化，在开始需要增加技术文档的审查和确认环节"

**规则**: HGF流程优化必须包含：
1. **Phase 0技术文档审查**（新增）：6份文档（PROPOSAL/ARCHITECTURE/API-CONTRACTS/DATA-SOURCES/TEST-STRATEGY/RISK-REGISTER）
2. **Gate 0通过标准**：文档齐全+验收标准可量化+外部依赖已验证+评审专家签字
3. **逐模块审查流程**：5步（静态审查→架构一致性→功能验证→对照审查表→审查结论）
4. **审查标准**：P0-P3严重等级，P0一票否决
5. **不通过处理**：最多3轮迭代，超过升级到用户决策

**三人小组模式**：
- 审查专家：给出审查流程和具体要求
- 编程专家：给出技术文档的具体结构要求
- 协调者：编制实现的具体技术方案

**HeavySkill迭代**：方案必须经HeavySkill K=8审查，迭代修改直至通过。

**详细方案**: `/tmp/hgf-optimization-plan-v1.3.md`

### P67: GitHub仓库发布前必须脱敏检查 (Verified 2026-07-01)

**症状**: 用户问"信息确认下是否脱敏处理"

**规则**: 发布代码到GitHub前必须检查：
1. API密钥模式（sk-、api_key、token、password、secret）
2. 配置文件（.env、config.yaml中的敏感字段）
3. 硬编码URL（内部服务地址）
4. 数据文件（包含用户数据的文件）

**检查命令**:
```bash
grep -rn "sk-\|api_key\|api_secret\|token\|password\|secret" --include="*.py" .
find . -name ".env*" -o -name "*.env"
grep -rn "https://\|http://" --include="*.py" . | grep -v "example\|placeholder\|test\|github.com"
```

### P68: 雪球平台需要手动登录 (Verified 2026-07-01)

**症状**: 浏览器访问雪球创作者中心(mp.xueqiu.com)，页面显示"未登录"

**规则**: 浏览器会话不保存用户登录状态。即使用户说"已登录"，新的浏览器会话也无法复用。

**正确做法**:
1. 准备好发布内容（标题+正文）
2. 告知用户文件位置
3. 用户手动登录并复制粘贴发布

**例外**: 如果用户提供了cookie/token，可以通过API方式发布。

### P69: qual-analysis-workflow GitHub 项目 (Verified 2026-07-01)

**仓库**: https://github.com/feiyu169/qual-analysis-workflow

**概述**: 从 qual-analysis skill 的质量层代码中提取的独立项目，包含标准化计算公式、数据口径映射、自动校验、推理引擎、评分器等模块。

**核心模块**:
- `formulas.py` — 标准化计算公式（PE/PB/ROE/增速）
- `data_mapping.py` — 数据口径映射（净利润/净资产/股本/PE四种口径）
- `validators.py` — 自动校验（PE/PB/市值/增长率）
- `reasoning/causal_inference.py` — 统一推理链（单链3阶段+5个检查点）
- `scoring/engine.py` — 评分引擎（5维度加权+证伪得分+强制降级）
- `dcf.py` — DCF估值模块
- `sensitivity.py` — 敏感性分析
- `risk_quantification.py` — 风险量化
- `margin_of_safety.py` — 安全边际

**详细说明**: `references/qual-analysis-workflow-github.md`

### P65: 雪球发布需要手动登录 (Verified 2026-07-01)

**症状**: 浏览器访问雪球创作者中心(mp.xueqiu.com)，页面显示"未登录"，无法发布内容。

**根因**: 浏览器会话不保存用户的登录状态。即使用户说"已登录"，新的浏览器会话也无法复用。

**规则**: 当需要登录第三方平台发布内容时，**必须由用户手动操作登录**，不能通过浏览器自动化完成。正确做法是：
1. 准备好发布内容（标题+正文）
2. 告知用户文件位置
3. 用户手动登录并复制粘贴发布

**例外**: 如果用户提供了cookie/token，可以通过API方式发布（如xurl发推特）。

### P60: Python文件中的中文标点导致SyntaxError (Verified 2026-07-01)

**症状**: `SyntaxError: invalid character '—' (U+2014)` 或 `SyntaxError: invalid character '，' (U+FF0C)`

**根因**: Python源文件中使用了中文标点（—、→、，、。、：、；、""、（、）），这些Unicode字符在Python 3中会导致SyntaxError。

**修复**: 使用ASCII等价字符替换：
- `—` → `-`
- `→` → `->`
- `，` → `, `
- `。` → `.`
- `：` → `:`
- `；` → `;`
- `""` → `""`
- `（` → `(`
- `）` → `)`

**预防**: 编写Python代码时只使用ASCII字符，注释和docstring可以使用中文但避免标点。

### P61: 黄金集测试模式 (Verified 2026-07-01)

当需要验证投资分析系统正确性时，使用黄金集测试：

```python
def test_golden_set():
    """使用已知正确数据验证系统"""
    # 万华化学已知数据
    market_cap = 2152.0
    net_income = 125.27
    equity_parent = 1083.0
    
    # 验证公式
    pe = Formulas.pe_ratio(market_cap, net_income)
    pb = Formulas.pb_ratio(market_cap, equity_parent)
    
    # 验证校验器
    validation = Validators.validate_pb(pb.value, "parent", market_cap, equity_parent)
    assert validation.is_valid
```

**黄金集应包含**:
- 至少2家不同市场的公司（A股、港股）
- 已知正确的财务数据（从Wind获取）
- 已知正确的估值结果（PE/PB等）
- 边界情况（负利润、零净资产等）

### P57: 实测发现的数据问题清单 (Verified 2026-07-01)

| 问题 | 公司 | 影响 | 根因 |
|------|------|------|------|
| PB用总权益而非归母净资产 | 万华化学 | PB低估11% | 公式定义不清晰 |
| Non-IFRS vs 扣非口径混淆 | 快手 | PE偏差21% | 口径映射缺失 |
| 总股本单位错误(4.35→43.5亿) | 快手 | 市值差10倍 | 单位换算缺失 |
| 经营利润增速计算错误 | 快手 | 增速偏差7.9pp | 基期值错误 |

**解决方案**: `quality/formulas.py`标准化公式 + `quality/validators.py`自动校验

## 第三方专家评估模式 (Verified 2026-06-30)

当需要验证报告质量时，使用双专家并行评估:

```
delegate_task(tasks=[
  {goal: "投资分析专家: 逐章对照must_answer评估", toolsets: ["file"]},
  {goal: "编程专家: 检查代码执行证据", toolsets: ["file", "terminal"]}
])
```

投资专家检查: must_answer覆盖、事实准确性、lens体现、数据精确性
编程专家检查: 步骤执行证据、质量层运行、checkpoint状态文件

评估后使用HeavySkill审查修复方案:
```
cd ~/.hermes/skills/heavyskill && python3 scripts/run_heavyskill.py \
  --query "审查修复方案" --include-file /tmp/fix-plan.md \
  --reason_k 6 --summary_k 3 --language cn
```

### P79: SOTP 分部估值设计要点 (Verified 2026-07-11)

**必须修正的阻断性问题**（HeavySkill v1.0 审查发现）：

1. **EV/EBITDA 必须用 EBITDA 字段**：`BusinessSegment` 必须有 `ebitda` 字段，不能用 `ebit` 替代
2. **集团费用必须折现**：使用永续增长模型 `PV = 费用 / (折现率 - 增长率)`
3. **必须支持币种转换**：港元/人民币汇率参数 `fx_rate`（默认 1.087）
4. **必须记录假设**：`assumptions` 字段记录所有简化假设

**GitHub**: `https://github.com/feiyu169/qual-analysis-workflow` → `quality/sotp_valuation.py`

### P80: 压力测试设计要点 (Verified 2026-07-11)

**必须修正的阻断性问题**（HeavySkill v1.0 审查发现）：

1. **净利润必须基于压力收入重新计算**：`stressed_net_income = stressed_revenue × stressed_margin`，不能简单乘系数
2. **流动性月数必须统一口径**：年度 FCF 转月度，FCF 为负时用保守计算 `cash / (monthly_opex + abs(monthly_fcf))`
3. **偿债指标用利息保障倍数**：`interest_coverage = EBIT / interest_expense`，不用债务覆盖率
4. **EBIT 可传入或估算**：未传入时用 `net_income × 1.25` 估算，需标记为临时假设

**GitHub**: `https://github.com/feiyu169/qual-analysis-workflow` → `quality/stress_test.py`

## Gate Check Integration (2026-07-03 新增)

在 Step 4 (审计修复) 之后、HeavySkill审查之前，可插入自动化质量门禁（Gate Checks）。

**两层Gate设计**:
- Gate 1 结构完整性: _year_labels、关键字段、章节非Placeholder
- Gate 2 计算卫生: DCF参数非空、数组对齐、数量级合理性(WARN)

**异常分级**: FATAL(硬阻断) / ERROR(阻断可重试) / WARN(警告不阻断)

**详细设计**: `references/gate-check-integration.md`

### P71: PE/PB计算必须做币种转换 (Verified 2026-07-03)

**症状**: 报告PE(TTM)=10.2x，但实际应为9.40x；PB=1.05x，实际应为0.97x。

**根因**: 港股市值(港元)直接除以人民币净利润/净资产，未做汇率转换。

**错误计算**:
```
PE = 59.56亿HKD / 5.83亿RMB = 10.2x ❌ (混用币种)
PB = 59.56亿HKD / 56.68亿RMB = 1.05x ❌ (混用币种)
```

**正确计算**:
```
市值(人民币) = 59.56亿HKD × 0.92 = 54.80亿RMB
PE = 54.80亿RMB / 5.83亿RMB = 9.40x ✅
PB = 54.80亿RMB / 56.68亿RMB = 0.97x ✅
```

**规则**: PE/PB计算必须币种统一。港股公司需先将市值按汇率折算为人民币，或净利润/净资产折算为港元。

**HeavySkill K=8验证**: 8/8轨迹一致指出此错误，共识"PE/PB计算存在方法论缺陷"。

### P72: 加密货币持仓对利润分析的干扰 (Verified 2026-07-03)

**症状**: 美图公司FY2024净利润8.05亿，FY2025净利润5.83亿（-27.6%），表面看利润恶化。但营业利润从4.97亿增长到8.31亿（+67%）。

**根因**: FY2024包含加密货币出售收益约3亿（2024年12月清仓全部BTC/ETH，获利5.71亿元）。FY2025反映真实经营状况。

**调查方法**:
1. 对比营业利润vs净利润的差额
2. 搜索公司加密货币持仓历史
3. 查阅资产负债表"权益性投资"科目变化

**规则**: 当净利润与营业利润趋势背离时，必须查明非经常性损益来源。搜索关键词：加密货币、比特币、以太坊、投资收益、减值拨回。

**美图实测**: 权益性投资从0.97亿暴增到11.46亿（+1080%），经搜索确认为加密货币持仓变化。

### P73: HeavySkill子代理无法读取本地文件 (Verified 2026-07-03)

**症状**: HeavySkill审查时，子代理返回"无法审查，需补充全部实现材料"，即使文件已存在于本地。

**根因**: HeavySkill通过`delegate_task`启动子代理，子代理**无法访问本地文件系统**。审查查询中只提供文件路径而不内联内容，子代理无法读取。

**修复**: 将需要审查的关键内容**内联到查询字符串**中，而非引用文件路径。

```python
# ❌ 错误 — 子代理无法读取文件
query = "审查 ~/projects/report.md 的质量"

# ✅ 正确 — 内联关键内容
report_content = open("~/projects/report.md").read()
query = f"审查以下报告质量:\n\n{report_content[:5000]}"
```

**影响范围**: 所有使用`delegate_task`或HeavySkill的审查场景都受此限制。技术方案审查、投资报告审查、代码审查等都需要内联内容。

**HeavySkill查询模板**（已修正）:
```bash
cd ~/.hermes/skills/heavyskill && python3 scripts/run_heavyskill.py \
  --query "审查以下内容:\n\n[内联完整内容，不要引用文件路径]\n\n## 审查维度\n..." \
  --reason_k 8 --summary_k 4 --language cn
```

### P74: DCF敏感性分析必须展示 (Verified 2026-07-03)

**症状**: DCF目标价17.42港元，上行空间335%，但未展示敏感性分析。HeavySkill审查指出"终值占比>70%，对永续增长率极其敏感"。

**问题**: 不展示敏感性分析会误导投资者，让他们误以为DCF结果是确定的。

**必须展示的内容**:
1. **WACC敏感性**（±1-2%）：WACC每变动1%，目标价变动约20%
2. **永续增长率敏感性**（±0.5-1%）：TG每变动0.5%，目标价变动约15%
3. **情景分析**（乐观/基准/悲观）：三个完整DCF计算
4. **终值占比**：如果>70%，需特别说明敏感性

**美图案例**:

| WACC | TG=2% | TG=2.5% | TG=3% |
|------|-------|---------|-------|
| 10% | 16.01 | 16.87 | 17.42 |
| 11% | 14.85 | 15.55 | 16.30 |
| 12% | 13.57 | 14.11 | 14.72 |

合理区间: 13.57-17.42港元（而非单一目标价17.42）。

**规则**: 任何DCF估值报告都必须包含敏感性矩阵，不能只给单一目标价。

### P75: Cron任务优化 — 分阶段执行模式 (Verified 2026-07-03)

**问题**: 一次性修改17个任务的投递渠道、频率、配置，风险高且难以回滚。

**正确流程**:
1. **验证阶段**: 检查工具支持、备份配置、查看错误日志
2. **修复阶段**: 先修复错误任务（根因分析，非临时止血）
3. **优化阶段**: 按优先级分类投递渠道（P0/P1/P2）
4. **监控阶段**: 验证修改效果，收集反馈

**优先级分类**:
- P0（错误告警）: feishu + local双通道
- P1（业务结果）: feishu
- P2（系统状态）: local

**美图实测**: 17个任务分3批修改，飞书投递从24%提升到82%，无一失败。

**详细记录**: `references/cron-optimization-case-study.md`

### P70: Gate Checks集成到workflow.py Step 4.6 (Verified 2026-07-03)

**集成点**: Step 4.5（质量增强）之后、Step 5（决策章和概览章）之前

**设计决策**:
- Gate Checks阻断采用**降级模式**：记录错误但继续执行后续步骤
- Gate Checks未找到时自动跳过（ImportError捕获）
- Gate Checks报告包含在返回结果的`gate_checks_report`字段中

**两层Gate设计**:
- Gate 1 结构完整性: _year_labels(FATAL)、数组对齐(ERROR)、章节完整(FATAL)、非Placeholder(FATAL)
- Gate 2 计算卫生: DCF参数非空(ERROR)、WACC范围(WARN)、FCF/OCF比例(WARN)

**关键教训**:
1. Gate Checks是HeavySkill审查的**前置过滤器**，不是替代品
2. WARN级别不阻断，仅标记需人工解释
3. 防御性编程必须覆盖所有输入异常（None/非字典/缺失键）
4. 阈值必须外置为YAML配置，支持热更新

**详细文档**: `references/gate-checks-integration.md`
**实现位置**: `~/projects/gate-checks/`

### P76: success 判断掩盖静默降级 (Verified 2026-07-11)

**症状**: `result["success"] = True` 但财报获取失败、质量增强失败、DCF参数为空。

**根因**: `success = len(errors) == 0`，但 Step 1.5/1.6/4.5 只 `logger.warning` 不写 `errors`。

**代码证据**:
```python
# workflow.py L1940
result = {"success": len(errors) == 0, ...}

# Step 4.5 只 warning
except Exception as e:
    logger.warning(f"Step 4.5 质量增强失败（非阻断）: {e}")
    # ← 未 append 到 errors
```

**修复**: 增加 `quality_degraded` 标志，记录降级原因。

**详细分析**: `references/workflow-code-review-2026-07-11.md`

### P77: 辩论覆盖审计修复后的章节 (Verified 2026-07-11)

**症状**: Step 4 审计修复后的章节被 Step 4.5 辩论机制覆盖，引入数据错误或结构破坏。

**根因**: `quality_enhancer.py` L120 直接替换 `chapters[ch_num] = debate.pm_synthesis`。

**风险**:
- PM 综合可能引入无财报支撑的数据
- PM 输出可能破坏"结论要点/详细情况/证据与出处"结构
- Step 4 审计结论对覆盖后的内容无效

**修复**: 合并模式（保留原始结构化小节）或重新审计模式。

**详细分析**: `references/workflow-code-review-2026-07-11.md`

### P76: success 判断掩盖静默降级 (Verified 2026-07-11)

**症状**: `result["success"] = True` 但财报获取失败、质量增强失败、DCF参数为空。

**根因**: `success = len(errors) == 0`，但 Step 1.5/1.6/4.5 只 `logger.warning` 不写 `errors`。

**代码证据**:
```python
# workflow.py L1940
result = {"success": len(errors) == 0, ...}

# Step 4.5 只 warning
except Exception as e:
    logger.warning(f"Step 4.5 质量增强失败（非阻断）: {e}")
    # ← 未 append 到 errors
```

**修复**: 增加 `quality_degraded` 标志，记录降级原因。HeavySkill K=8 审查通过 (v3.0)。

**技术文档**: `~/projects/qual-workflow-fix-proposal-v3.md`

### P77: 辩论覆盖审计修复后的章节 (Verified 2026-07-11)

**症状**: Step 4 审计修复后的章节被 Step 4.5 辩论机制覆盖，引入数据错误或结构破坏。

**根因**: `quality_enhancer.py` L120 直接替换 `chapters[ch_num] = debate.pm_synthesis`。

**风险**:
- PM 综合可能引入无财报支撑的数据
- PM 输出可能破坏"结论要点/详细情况/证据与出处"结构
- Step 4 审计结论对覆盖后的内容无效

**修复**: 合并模式（保留原始结构化小节，追加辩论洞察到折叠标签）。

```python
def _merge_debate_result(original: str, debate) -> str:
    merged = original
    merged += "\n\n---\n\n"
    merged += f"> **辩论增强** (确信度: {debate.conviction_score:.0%})\n\n"
    # 看多/看空论点完整保留（折叠标签）
    merged += f"<details><summary>看多论点</summary>\n\n{debate.bull_argument}\n\n</details>\n\n"
    merged += f"<details><summary>看空质疑</summary>\n\n{debate.bear_argument}\n\n</details>\n\n"
    # PM 综合判断
    if debate.pm_synthesis:
        merged += f"\n<details><summary>PM 综合判断</summary>\n\n{debate.pm_synthesis}\n\n</details>"
    return merged
```

**技术文档**: `~/projects/qual-workflow-fix-proposal-v3.md`

### P78: Qual 工作流对标券商分析差距 (Verified 2026-07-11)

**P0 差距（必须补充）**：

| # | 差距 | 券商标准 | 修复方案 |
|---|------|----------|----------|
| 1 | 缺少 SOTP 分部估值 | 多元化公司必须 | `quality/sotp_valuation.py` |
| 2 | 缺少留存率/LTV/CAC | 互联网公司核心指标 | 扩展 `fact_extractor.py` |
| 3 | 缺少压力测试 | 极端情景量化 | `quality/stress_test.py` |

**P1 差距**：EV/EBITDA、周期性视角、同行对比矩阵、单位经济模型

**技术文档**: `~/projects/qual-workflow-improvement-v1.1.md`

### P79: SOTP 分部估值设计要点 (Verified 2026-07-11)

**必须修正的阻断性问题**（HeavySkill v1.0 审查发现）：

1. **EV/EBITDA 必须用 EBITDA 字段**：`BusinessSegment` 必须有 `ebitda` 字段，不能用 `ebit` 替代
2. **集团费用必须折现**：使用永续增长模型 `PV = 费用 / (折现率 - 增长率)`
3. **必须支持币种转换**：港元/人民币汇率参数 `fx_rate`（默认 1.087）
4. **必须记录假设**：`assumptions` 字段记录所有简化假设

```python
@dataclass
class BusinessSegment:
    name: str
    revenue: float
    ebitda: float = 0.0  # 必须有，EV/EBITDA 用
    comparable_multiple: float
    multiple_type: str = "EV/Revenue"  # 或 "EV/EBITDA"
```

**GitHub**: `https://github.com/feiyu169/qual-analysis-workflow` → `quality/sotp_valuation.py`

### P81: A股财报获取 — fetch_filing()超时但下载器正常 (Verified 2026-07-11, Corrected 2026-07-11)

**症状**: `fetch_filing(ticker='002352.SZ', market='cn')` 超时（>60秒），但直接调用 `CNInfoDownloader` 正常（~5秒）。

**根因**: `fetch_filing()` 内部调用 `downloader.download()` 后立即调用 `_parse_pdf()`，而 `_parse_pdf()` 会尝试 MinerU 精准 API。如果 MinerU 服务响应慢或 PDF 过大（>200页需分段），整个调用链超时。**CNInfo下载器本身工作正常。**

**正确做法 — 分离下载和解析**:
```python
# 方案1: 直接调用下载器（快速，只下载不解析）
from finance.downloaders.cninfo_downloader import CNInfoDownloader
from finance.downloaders.http_client import HttpClient
from finance.downloaders.models import ReportQuery

http = HttpClient()
dl = CNInfoDownloader(http_client=http)
query = ReportQuery(market='CN', ticker='002352.SZ', start_date='2023-01-01', end_date='2026-12-31', target_periods=('FY',))
profile = dl.resolve_company(query)
candidates = dl.list_candidates(query, profile)
for c in candidates:
    asset = dl._download_and_save(c)
    # asset.pdf_path 已保存到 ~/.hermes/workspace/filings/cninfo/{year}/

# 方案2: 下载后用 create_parser 单独解析
from finance.parsers.parser_router import create_parser
parser = create_parser(asset.pdf_path)
```

**何时用方案1**: 需要下载多年年报时（先全部下载，再逐个解析）
**何时用 fetch_filing()**: 只需最新1年且 MinerU 服务健康时

**⚠️ Dayu MCP不支持多数A股**: `mcp_dayu_list_documents(ticker='002352.SZ')` 返回 `"Financial Document Tools do not have this company"`。Dayu数据库仅覆盖部分热门A股。

**A股CNInfo下载器实测 (002352.SZ 顺丰控股)**:
- 公司名解析为"鼎泰新材"（借壳上市前名称），但下载正确
- 找到4个年报候选: 2022/2023/2024/2025
- 2023年年报: 58MB, 2024年: 34MB, 2025年: 24MB
- 下载速度: 每个~5秒

### P82: DeepSeek LLM调用超时无保护 (Verified 2026-07-11)

**症状**: `run_analysis()` 运行20+分钟未完成。实测顺丰控股分析：11章生成 + 审计修复，卡在审计JSON解析失败。

**根因**:
1. DeepSeek API调用没有超时保护（HTTP请求无timeout参数）
2. Python `signal.alarm()` 不中断阻塞式HTTP请求
3. 11章串行生成 + 最多3轮审计修复 = 理论上44次LLM调用
4. 每次LLM调用30-120秒，总计可达22-88分钟

**影响**: 工作流永远无法在合理时间内完成（CLI会话有时间限制）。

**解决策略**:
1. **后台进程+轮询**: 使用`terminal(background=True, notify_on_complete=True)`启动
2. **减少审计轮数**: 修改max_repair_rounds=1（默认3）
3. **设置requests超时**: 在llm_caller.py中为HTTP请求设置timeout=60参数
4. **断点恢复**: 利用checkpoint机制，中断后可从断点继续

**预计耗时（单轮审计）**:
- 11章生成: 11 × 60秒 ≈ 11分钟
- 1轮审计+修复: 11 × 60秒 ≈ 11分钟
- 总计: ~22分钟（最佳情况）

### P83: 审计JSON解析失败导致静默降级 (Verified 2026-07-11)

**症状**: 日志输出 `审计响应 JSON 解析失败: Expecting property name enclosed in double quotes: line 2 column 3 (char 4)`

**根因**: DeepSeek LLM返回的审计响应不是标准JSON格式（可能包含单引号、注释、Markdown代码块标记）。

**影响**: 语义审计静默失败，章节未经审计直接放行。

**修复方向**: 审计响应的robust_json_parse应该与fact_extractor使用相同的三层防护（直接解析→截取{}→正则修复）。

### P84: Wind现金流字段映射 — A股实测 (Verified 2026-07-11)

**症状**: DCF参数提取报告"经营活动现金流量净额为 0"。

**根因**: Wind `wind_financial_data(type='cashflow')` A股返回的字段名与代码期望不同：
- Wind返回: `"最近3年经营活动现金净流量_TTM"` (注意: 是"_TTM"后缀)
- 代码期望: `"经营活动现金流量净额"` 或 `"经营活动产生的现金流量净额"`

**A股Wind现金流实际返回字段**:
| 字段名 | 说明 |
|--------|------|
| 最近3年经营活动现金净流量_TTM | 经营活动现金流（含TTM后缀） |
| 最近3年投资活动现金净流量_TTM | 投资活动现金流（含TTM后缀） |
| 最近3年购建固定资产、无形资产和其他长期资产支付的现金 | 资本支出 |
| 最近3年筹资活动产生的现金流量净额 | 筹资活动现金流（无TTM后缀） |
| 最近3年现金及现金等价物净增加额 | 现金净增加 |

**⚠️ 注意**: 字段名带"_TTM"后缀的是滚动12个月数据，不带的是年度数据。两者数值可能不同。

**修复**: 在wind-field-mapping.md中添加A股现金流字段映射，见 `references/wind-field-mapping.md`。

### P86: gate_checks_integration.py 缺少 logger 定义 (Verified 2026-07-11)

**症状**: `run_analysis()` 在 Step 4.6 崩溃：
```
NameError: name 'logger' is not defined
```
随后连锁: `GateChecksBlockedError` 未导入 → `UnboundLocalError`。

**根因**: `gate_checks_integration.py` 顶部缺少 `import logging` 和 `logger = logging.getLogger(__name__)`。

**修复**:
```python
# gate_checks_integration.py 顶部添加
import logging
logger = logging.getLogger(__name__)
```

**教训**: 所有使用 `logger` 的模块必须在文件顶部定义。`try/except ImportError` 降级分支中的代码不能依赖被 try 块导入的符号。

### P87: FallbackParser 章节识别能力极差 (Verified 2026-07-11)

**症状**: 顺丰控股2025年报（283页, 23MB）用 FallbackParser 解析，只识别出1个section（整个文档作为一个section），而 MinerU 能识别数百个章节。

**根因**: FallbackParser（pdfplumber/PyPDF2/PyMuPDF）没有章节识别能力，只能提取全文文本。

**对工作流的影响**:
- `filing_data['sections']` 只有1个key时，fact_extractor 无法提取结构化事实
- 但 `run_analysis()` 仍可完成（使用全文文本作为 `filing_data['text']`）
- 报告质量会降低（缺少结构化运营数据）

**降级策略**: 如果 MinerU 不可用，接受 FallbackParser 的全文模式，但需在报告中标注 data_quality=low。

### P88: 完整工作流执行时间 15-30 分钟 (Verified 2026-07-11)

**实测数据**: 顺丰控股 002352.SZ，11章报告，DeepSeek LLM：

| 阶段 | 耗时 |
|------|------|
| 章节写作（9章） | ~5分钟 |
| 审计修复（9章×1-3轮） | ~3分钟 |
| 辩论机制（9章×3次LLM） | ~8分钟 |
| ch00/ch10 生成 | ~1分钟 |
| 估值+深度优化 | ~1分钟 |
| **总计** | **~18分钟** |

**预算建议**: 后台运行时设置 `timeout=1800`（30分钟），`notify_on_complete=True`。

### P89: EBITDA数据虚高107% — Wind字段取值错误 (Verified 2026-07-11)

**症状**: 顺丰控股报告EBITDA=316亿，Wind实际值=152.66亿，偏差107%。

**根因**: Wind `wind_financial_data(type='income')` 返回的"年EBITDA"是3年数组 `[290.47, 324.48, 316.39]`，但代码取值时可能取了错误的索引或做了错误的合并计算。316亿实际是FY2025的EBITDA，但报告中与324亿(FY2024)混淆。

**更深层问题**: `_build_chapter_prompt()` 传递Wind数组时没有年份标签，LLM自行推断年份后可能将FY2024的EBITDA(324亿)误标为FY2025。

**验证方法**: 用Wind MCP交叉验证所有EBITDA引用：
```python
wind_data = mcp_wind_financial_data(windcode='002352.SZ', type='income')
ebitda_array = wind_data['年EBITDA']  # [290.47, 324.48, 316.39]
# FY2025 EBITDA = 316.39亿（取最后一个元素）
```

**影响**: DCF估值完全失真。EBITDA是DCF的关键输入，偏差107%导致EV计算错误。

**修复**: T6事实核查必须包含EBITDA勾稽验证。

### P90: WACC=10%显著偏高 — CAPM参数未校准 (Verified 2026-07-11)

**症状**: DCF估值使用WACC=10%，计算出每股20.2元。但PE隐含价值为32元，偏差58%。

**根因**: WACC硬编码10%，未用CAPM模型校准。

**顺丰CAPM计算**:
```
Ke = Rf + β × ERP = 2.3% + 1.0 × 5.5% = 7.8%
Kd(税后) = 3.5% × (1-25%) = 2.6%
D/(D+E) = 400/2086 = 19.2%
WACC = 7.8% × 80.8% + 2.6% × 19.2% = 6.8%
```

**影响**: WACC从10%降到6.8%，DCF估值从20.2元提升约30-40%。

**修复**: 新增T10 WACC参数校准模块，从Wind获取无风险利率、β、ERP。

### P91: 辩论压缩50字致命不足 — 无法表达完整论点 (Verified 2026-07-11)

**症状**: T5辩论压缩设计每个论点50字。测试论点"顺丰的重资产壁垒在价格战中形成逆周期盈利能力"需要前提1+前提2+前提3+推论+结论，50字只能下一个断言。

**建议字数**:
| 论点类型 | 建议字数 | 理由 |
|---------|---------|------|
| 事实性论点（数据驱动） | 80字 | 需要数据+来源+推导 |
| 逻辑性论点（因果推导） | 120字 | 需要前提+推理+结论 |
| 预期差论点（与市场分歧） | 150字 | 需要市场观点+己方观点+分歧量化+证伪条件 |

**结构化论点模板**（每个论点80字）:
```
- 核心断言（15字）：顺丰重资产在价格战中形成逆周期盈利
- 关键数据（20字）：鄂州机场产能利用率X%，自有飞机Y架
- 逻辑推导（30字）：重资产→边际成本低→价格战中降价空间大→份额提升
- 风险/反驳（15字）：若需求持续下滑超过Z%，逻辑失效
```

### P93: T13 PE反推公式致命错误 — 51%隐含增速 (Verified 2026-07-11)

**症状**: PE反推公式 `(PE×ROE×b)/(PE×ROE×b+1)` 代入顺丰数据得出51.1%隐含增速，荒谬不合理。

**根因**: 该公式不是标准的PE反推公式。正确方法需要已知折现率k：
```
g = k - (1-b)/PE = 9.5% - 0.4/15.17 = 6.9%（基本面可持续增速）
```

**修复**: T13必须使用DCF反推为主+PE-growth回归为辅，删除DDM和错误PE公式。

**HeavySkill K=8验证**: 8/8轨迹一致指出此错误为"致命问题"。

### P94: WACC内部矛盾 — T10 vs T13参数不一致 (Verified 2026-07-11)

**症状**: T10声明WACC=7.0-8.5%，但T13 DCF反推使用WACC=9.5%，导致估值体系逻辑不自洽。

**修复**: T13必须使用T10的WACC计算结果，不硬编码任何值。

**HeavySkill K=8验证**: 7/8轨迹指出此矛盾为"严重问题"。

### P95: Phase过度串行化导致工时低估 (Verified 2026-07-11)

**症状**: 5个Phase串行执行，总工时85h。但Phase 3的T9/T10/T12可以并行，关键路径从20h优化到17h。

**修复**: 
- Phase 3: T9/T10/T12并行→T3（关键路径max(15,4,4)+5=20h→17h）
- Phase 4-5: 部分任务可与Phase 3后期并行

**工时修正**: 85h→100-115h（含调试+LLM调用+测试）

### P96: 辩论字数迭代 — 50→120→150→200-250字 (Verified 2026-07-11)

**迭代历史**:
| 版本 | 字数 | 审查评价 |
|------|------|----------|
| v1.0 | 50字 | "致命不足" |
| v2.0 | 80-120字 | "仍不足" |
| v3.0 | 150-180字 | "偏紧" |
| v4.0 | 200-250字 | "可接受" |

**结构化模板（200-250字）**:
```
核心断言(25字) + 关键数据(40字) + 逻辑推导(60字) + 数据支撑(40字) + 风险/反驳(35字) + 证伪条件(20字)
```

### P97: HeavySkill K=8四轮迭代审查模式 (Verified 2026-07-11)

当需要验证技术方案时，使用四轮迭代审查：

```
Round 1 (v1.0): 初始方案 → 8轨迹审查 → 评分60 → "合格的bug修复清单"
Round 2 (v2.0): 按审查意见修改 → 8轨迹审查 → 评分75 → "初步可用的框架"
Round 3 (v3.0): 继续修改 → 8轨迹审查 → 评分78 → "方向正确但有致命公式错误"
Round 4 (v4.0): 修正公式 → 8轨迹审查 → 评分79 → "可实施的专业级方案"
```

**收敛判断**: v3.0→v4.0仅+1分，说明架构层面改进空间有限，后续提升需要执行层迭代。

**关键规则**:
1. 每轮必须修复所有P0问题后再提交下一轮
2. 子代理无法读取本地文件 — 必须将方案内容内联到query中
3. max_concurrent_children=3 — 需分3批执行(3+3+2)
4. 每轮审查平均耗时2-3分钟

### P98: ANCH投资论点锚定实现 (Verified 2026-07-11)

**位置**: workflow.py Step 2.5（数据收集之后、章节写作之前）

**核心函数**:
- `_generate_anch_hypothesis(ctx, llm_caller)` → 生成结构化投资假设JSON
- `_format_anch_for_prompt(anch)` → 格式化为prompt文本

**ANCH JSON结构**:
```json
{
  "core_thesis": "一句话核心投资论点",
  "key_arguments": [
    {"argument": "...", "evidence": "...", "verification": "...", "falsification": "..."}
  ],
  "bear_case": "最强看空论点",
  "catalysts": ["催化剂1", "催化剂2"]
}
```

**闭环机制**: 
1. ANCH生成投资假设（Step 2.5）
2. 各章写作时注入ANCH（_write_chapters接收anch_hypothesis参数）
3. T3综合结论显式引用ANCH验证状态（confirmed/pending/falsified）

### P92: HeavySkill K=8 并行限制 — 需分批执行 (Verified 2026-07-11)

**症状**: `delegate_task(tasks=[8个任务])` 报错 "Too many tasks: 8 provided, but max_concurrent_children is 3"。

**根因**: Hermes Agent配置 `delegation.max_concurrent_children=3`，每次最多3个并行子代理。

**正确做法**: 分批执行：
```python
# 第1批: 3个轨迹
delegate_task(tasks=[轨迹1, 轨迹2, 轨迹3])
# 等待完成
# 第2批: 3个轨迹
delegate_task(tasks=[轨迹4, 轨迹5, 轨迹6])
# 等待完成
# 第3批: 2个轨迹
delegate_task(tasks=[轨迹7, 轨迹8])
```

**工时影响**: 8轨迹HeavySkill审查从理论5分钟变为实际10-15分钟（含等待时间）。

## v4.0 HGF执行进度 (2026-07-11)

经HeavySkill K=8四轮迭代审查（v1.0→v4.0），最终方案18+6项修复/85h。按HGF Gate-Driven流程执行：

```
✅ Gate 0 (5h): P76+P77+P11+WACC — 阻断性问题全部修复
✅ Gate 1 (9h): T1年份+T4痕迹+T7交叉验证+O2降级 — 消除致命硬伤
✅ Gate 2 (16h): T6事实核查+T11敏感性+ANCH论点锚定 — 数据可信度
✅ Gate 3 (17h): T9 SOTP+T10 WACC+T12 ROIC+T3综合结论 — 估值内核
✅ Gate 4 (18h): T13 DCF反推+T2可比公司+T14证伪+T18催化剂 — 深度提升
✅ Gate 5 (10h): T16同行对比+T17管理层+T8分部数据 — 专业对齐
✅ E2E测试: 顺丰控股002352.SZ — 11章生成，0错误，quality=high

新增模块: quality/falsification.py(证伪指标), quality/catalyst_calendar.py(催化剂日历), quality/peer_comparison.py(同行对比)
```

### 已修改文件清单

| 文件 | 修改内容 | Gate |
|------|----------|------|
| `data_context.py` | WindData新增`_year_labels`字段 | 0 |
| `workflow.py` | 年份标签+AI痕迹清洗+ANCH+综合结论章+Step 2.5 | 0/1/2/3 |
| `quality/formulas.py` | ROIC公式(nopat/invested_capital/roic/roic_spread) | 3 |
| `quality/validators.py` | cross_validate_pe_pb()估值交叉验证 | 1 |
| `quality/structural_check.py` | 检查7: must_answer逐条对照 | 2 |
| `valuation_engine.py` | DCF反推+PE反推+可比公司估值增强 | 4 |

### Gate 3 核心实现

**T12 ROIC公式** (`quality/formulas.py`):
```python
Formulas.nopat(ebit, tax_rate)           # NOPAT = EBIT × (1-税率)
Formulas.invested_capital(debt, equity)   # IC = 有息负债 + 权益
Formulas.roic(nopat, ic)                  # ROIC = NOPAT / IC
Formulas.roic_spread(roic, wacc)          # Spread = ROIC - WACC (>0创造价值)
```

**T3 综合结论章** (`workflow.py`):
- `_generate_synthesis_chapter(chapters, ctx, anch_hypothesis, llm_caller)`
- 整合各章证据，引用ANCH验证状态(confirmed/pending/falsified)
- 放在Step 5a，决策章之前

### Gate 4 核心实现

**T13 DCF反推** (`valuation_engine.py`):
```python
implied_growth_from_dcf(current_price, shares, fcf_base, wacc=0.08, ...)  # 二分法搜索
implied_growth_from_pe(pe, roe, retention_rate=0.6)  # 基本面可持续增速
```

**T2 可比公司估值增强** (`valuation_engine.py`):
```python
compute_comparable_valuation(target_ticker, comparable_companies, target_eps, target_bvps)
# 返回: pe_median, pe_range, implied_value_pe, implied_value_pb
```

## Gate Check Integration (2026-07-03 新增)

**症状**: `signal.alarm(180)` 设置了180秒超时，但进程运行20+分钟仍未被中断。

**根因**: `signal.SIGALRM` 只能在Python代码的可执行点触发。当进程阻塞在底层HTTP请求（如requests.get/post）时，信号处理函数无法被执行，因为Python GIL被I/O操作持有。

**影响**: 所有使用signal.alarm做超时保护的方案对HTTP阻塞调用无效。

**正确做法**:
1. **子进程隔离**: 使用`multiprocessing.Process` + `process.join(timeout=180)`
2. **requests超时**: `requests.post(url, timeout=60)` — 这是最可靠的方案
3. **asyncio**: 使用`asyncio.wait_for()` + `aiohttp`

**规则**: 不要使用signal.alarm保护HTTP调用，直接在requests层设置timeout。

### P80: 压力测试设计要点 (Verified 2026-07-11)

**必须修正的阻断性问题**（HeavySkill v1.0 审查发现）：

1. **净利润必须基于压力收入重新计算**：`stressed_net_income = stressed_revenue × stressed_margin`，不能简单乘系数
2. **流动性月数必须统一口径**：年度 FCF 转月度，FCF 为负时用保守计算 `cash / (monthly_opex + abs(monthly_fcf))`
3. **偿债指标用利息保障倍数**：`interest_coverage = EBIT / interest_expense`，不用债务覆盖率
4. **EBIT 可传入或估算**：未传入时用 `net_income × 1.25` 估算，需标记为临时假设

```python
# FCF 为负时的保守流动性计算
if monthly_fcf >= 0:
    liquidity_months = (cash + monthly_fcf * 6) / monthly_opex
else:
    liquidity_months = cash / (monthly_opex + abs(monthly_fcf))
```

**GitHub**: `https://github.com/feiyu169/qual-analysis-workflow` → `quality/stress_test.py`

## 参考文件

| 文件 | 说明 |
|------|------|
| `references/workflow-code-review-2026-07-11.md` | **代码级审查记录** — success判断掩盖降级、辩论覆盖审计修复的详细分析 (2026-07-11) |
| `references/wind-field-mapping.md` | Wind MCP 实际返回字段名映射表 |
| `references/llm-caller-setup.md` | DeepSeek LLM Caller 配置和使用方法 |
| `references/hkex-api-implementation.md` | 披露易 API 端点、参数、响应格式 |
| `references/filing-pipeline-fix.md` | 财报获取管道修复 (3个阻断性Bug + MinerU分段) |
| `references/downloader-architecture-comparison.md` | Dayu vs Hermes 下载器架构对比、关键设计模式 |
| `references/dcf-extraction-pitfalls.md` | DCF 参数提取 5 个 Bug 详细记录 |
| `references/v6-technical-plan-2026-07-01.md` | v6.0技术方案总结（推理引擎+评分器+实测验证） |
| `references/heavyskill-iterative-review-v6.md` | HeavySkill迭代审查模式（v1.0→v6.0经验） |
| `references/investment-calculation-formulas.md` | 投资计算公式库（PB/PE/ROE/增速标准化） |
| `references/v4-v5-evaluation-fix-record.md` | v4→v5评估修复记录 (9项修复+评分对比) |
| `references/pdf-parsing-fallback.md` | PDF 解析降级策略 |
| `references/fact-extractor-design-v2.md` | 方案 C 技术设计文档 v2.0 (三层面语义防护) |
| `references/investment-depth-quantitative-standards.md` | **投资分析深度量化标准** — L3/L4/L5级别定义、检验公式、黄金集测试 (2026-07-01) |
| `references/kernel-validation-data-indicators.md` | **内核验证检查清单+数据验证指标** — 关键词门槛、逻辑完整性、评分器公式 (2026-07-01) |
| `references/heavyskill-iterative-review-pattern.md` | **HeavySkill迭代审查模式** — v1→v2审查流程、Query模板、评分标准 (2026-07-01) |
| `references/heavyskill-review-cycle.md` | **HeavySkill迭代审查循环** — v1→v6收敛轨迹、三人讨论会模式、HGF Gate执行模式 (2026-07-01) |

## 方案 C：多年份事实提取 (v2.2.0 新增)

### 架构

```
run_multi_year_analysis(ticker, years=[2023,2024,2025])
  ├─ for year in years:
  │    load_filing_by_year(ticker, year)
  │    extract_facts(sections, llm_caller)
  │      → 高价值章节排序 → 分批30K×10 → LLM提取JSON
  │      → 三层语义防护 → 合并
  ├─ merge_multi_year_facts(facts_per_year)
  │    → merged_facts (含N年运营趋势)
  └─ run_analysis(wind_data, filing_data=latest, preloaded_facts=merged)
```

### 三层面语义防护

| 层 | 作用 | 实现 |
|---|------|------|
| L1 提示词 | 防止单位错误 | EXTRACTION_PROMPT 增加单位规范段 |
| L2 后处理 | 自动修正已发生的错误 | `normalize_units()`: DAU>100→÷100, GMV>100K→÷100, 毛利率<1→×100 |
| L3 空值重试 | 捕获提取失败 | `_is_facts_empty()`: 关键字段<2个→重试(max_retries=2) |

### 多年份下载

港股不支持按年份下载，需用 `_download_pdf(candidate)` 直接下载指定候选：
```python
for c in candidates:
    if c.fiscal_year == target_year:
        pdf_bytes = dl._download_pdf(c)
        # save to cache
```

### 关键文件

| 文件 | 说明 |
|------|------|
| `~/.hermes/tools/finance/fact_extractor.py` | 两阶段事实提取器 (~700行) |
| `workflow.py` Step 1.6 | 事实提取集成点 |
| `data_context.py` `ctx.facts` | 事实表字段 |
| `quality/checkpoint.py` `save_facts()`/`load_facts()` | 持久化 |
| `references/v5-fixes-2026-06-30.md` | v5 版本 9 个缺陷修复详情 + 第三方专家评估 |
| `references/v6-fixes-2026-06-30.md` | V6 修复: Wind年份标签 + 运营数据提取 + 港股无季报 |
| `references/fact-extractor-design.md` | 方案C: 两阶段财报事实提取管线设计 (HeavySkill审查) |
| `references/fact-extractor-v2-review.md` | 方案C HeavySkill v2.0 审查记录 + 实施状态 |
| `references/plan-c-v3-execution-record.md` | 方案C v3 执行记录: 3个bug修复 + 快手验证结果 |
| `references/plan-c-v3-v4-execution-record.md` | 方案C v3/v4 执行记录: 归属验证+单位修正+多年份提取 |
| `references/heavyskill-investment-review-2026-07-01.md` | HeavySkill K=8 投资报告审查记录 (8轨共识: 不合格) |
| `references/qual-analysis-discussion-2026-07-01.md` | 三人小组讨论报告: 快手报告未按qual框架执行的根因分析 |
| `references/report-quality-roadmap-2026-07-01.md` | 报告质量改进路线图 (P0/P1/P2, 26人天) |
| `references/debate-mechanism-design.md` | 辩论机制技术方案 (Bull→Bear→PM, 五阶段框架) |
| `references/five-stage-implementation.md` | 五阶段改进框架实施记录 (Gate 1-4 代码+测试结果) |
| `references/hgf-improvement-proposal-2026-07-01.md` | HGF流程改进技术方案 (Gate0预审+统一标准+依赖追踪+自动化+回归) |
| `references/qual-analysis-technical-plan-v6.md` | v6.0技术方案（推理引擎+评分器+数据验证框架+实测验证） |
| `references/v6-implementation-details-2026-07-01.md` | **v6.0实施细节** — 模块架构、接口契约、评分权重、CN/HK规则、DCF模块、实测结果 (2026-07-01) |
| `references/v6-quality-module-architecture.md` | **v6.0质量模块架构** — 完整模块结构、接口定义、评分权重、校验公式、CN/HK规则、Checkpoints、Pitfalls (2026-07-01) |
| `references/v6-quality-system-architecture.md` | **v6.0质量系统架构** — 完整模块清单、接口签名、评分权重、证伪公式、CN/HK规则、Checkpoints、关键修复 (2026-07-01) |
| `references/quality-layer-architecture.md` | **质量层架构** — quality/包结构、核心接口、评分权重、证伪公式、关键修复记录、黄金集测试结果 (2026-07-01) |
| `references/granger-test-scipy-implementation.md` | **Granger因果检验scipy实现** — F检验代码、替代statsmodels方案、使用注意事项 (2026-07-01) |
| `references/hgf-optimization-phase0-review.md` | **HGF流程优化** — Phase 0技术文档审查、三人小组模式、HeavySkill迭代记录 (2026-07-01) |
| `references/qual-analysis-workflow-github.md` | **qual-analysis-workflow GitHub项目** — 独立质量保证框架、核心模块、评分权重、实测验证 (2026-07-01) |
| `references/hgf-optimization-plan-v1.3.md` | **HGF流程优化方案v1.3** — 最终版、6份技术文档、5步审查流程、HeavySkill K=8通过 (2026-07-01) |
| `references/gate-checks-integration.md` | **Gate Checks集成指南** — 两层Gate设计、异常分级、防御性编程、workflow.py Step 4.6集成 (2026-07-03) |
| `references/gate-checks-implementation-v2.md` | **Gate Checks实施记录v2.0** — 完整架构、HeavySkill迭代审查经验、防御性编程模式、Pitfalls (2026-07-03) |
| `references/meitu-analysis-case-study.md` | **美图公司分析案例** — 完整工作流执行、PE/PB币种转换、加密货币持仓干扰、DCF估值修正 (2026-07-03) |
| `references/cron-optimization-case-study.md` | **Cron任务优化案例** — HeavySkill审查迭代、分阶段执行、优先级分类、根因分析模式 (2026-07-03) |
| `references/heavyskill-review-shunfeng-2026-07-11.md` | **顺丰控股HeavySkill K=8审查** — EBITDA数据错误、WACC偏高、辩论50字不足、缺SOTP、确信度5维度设计 (2026-07-11) |
| `references/qual-workflow-critical-fixes-v1.md` | **Qual工作流关键缺陷修复技术方案v1.0** — 8个修复+7个遗漏+工时估算+实施计划 (2026-07-11) |
| `references/qual-workflow-critical-fixes-v4.md` | **技术方案v4.0** — 18+6项修复/85h, T13 DCF反推+ANCH闭环+数据总线+确信度量化 (2026-07-11) |
| `references/heavyskill-k8-review-qual-v1.md` | **HeavySkill K=8一审报告** — v1.0评分60, "合格的bug修复清单" (2026-07-11) |
| `references/heavyskill-k8-review-v2-round2.md` | **HeavySkill K=8二审报告** — v2.0评分75, "初步可用的投资分析框架" (2026-07-11) |
| `references/heavyskill-k8-review-v3-round3.md` | **HeavySkill K=8三审报告** — v3.0评分78, T13 PE反推公式致命错误 (2026-07-11) |
| `references/heavyskill-k8-review-v4-round4.md` | **HeavySkill K=8四审报告** — v4.0评分79, "可实施的专业级方案" (2026-07-11) |
| `references/a-stock-cninfo-download-workflow.md` | **A股财报获取+MinerU解析** — CNInfo下载器、_parse_pdf()调用、FallbackParser vs MinerU质量对比、Wind字段映射 (2026-07-11) |
