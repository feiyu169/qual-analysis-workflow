# Qual 版本架构全景：V2-V7 单体 vs V8 的关系与版本治理

> 回答三个问题：
> 1. V2-V7 单体和 V8 是什么关系？作用有何区别？
> 2. 它们是同一个项目吗？
> 3. 整体版本如何划分控制（现状 + 建议）？

---

## 一、结论速览

**是同一个项目**——`tools/finance/` 是单个 Python 包（`__version__ = "5.0.0"`），V2-V7 单体与 V8 引擎是**同一个包里两个不同代次的架构**，共享同一批底层组件。它们不是两个项目，也不是简单的"旧版 vs 新版"，而是：

| | V2-V7 单体 | V8 引擎 |
|---|---|---|
| **本质** | 过程式单体工作流 | 状态机驱动的 Gate 门禁引擎 |
| **代码位置** | `workflow.py`（2935 行单体 `run_analysis()`） | `qual_v8/`（Gate0-8 九文件 + core 状态机/熔断/审计） |
| **作用** | **生成器**：类型推断→数据收集→11章写作→审计修复→组装 | **编排+门禁**：数据源验证→…→最终验证，把关每个阶段 |
| **当前运行关系** | R5 实际执行者（shadow 模式挂 v8 只记录） | 默认旁观；本轮已改造为可运行（Gate 灌入 v2-v7 真实组件） |
| **依赖方向** | v2-v7 调用 v8 的 workflow_context（记录型） | v8 的 Gate3/4/5/6 调用 v2-v7 的生成函数（本轮改造） |

**一句话**：V2-V7 是"会写的引擎"（生成报告），V8 是"会管的引擎"（把关质量）——两者是**同一项目的两个架构代次，当前以"V8 编排监督 + V2-V7 提供生成能力"的方式共存**。

---

## 二、为什么版本号显得混乱：四个维度被混用

项目里的版本号其实来自 **4 个不同维度**，全部叫"vX"，导致"版本如何划分"说不清：

| 维度 | 含义 | 证据 | 当前值 |
|---|---|---|---|
| **包版本** | 整个 finance 包的语义化版本 | `finance/__init__.py:29` `__version__ = "5.0.0"` | 5.0.0（但**无人消费**，无 changelog 对应） |
| **工作流代次** | 架构演进代次（单体→Gate 化） | `workflow.py:2` 头注释 "v2.0"；`qual_v8` 技能 "v8.4"；`qual-analysis/SKILL.md` "10+1章 v8" | **v2 到 v8.4 之间**（但 v3-v7 只是历史记录，代码只剩 v2 单体和 v8 引擎两代） |
| **组件代次** | 质量组件的独立代次 | `quality/v3/`（ContentValidator/InsightAuditor/ReviewIntegrator 等大量 v3） | v3（独立于工作流代次演进） |
| **实现细节版本** | 单文件/单模块迭代 | `fact_extractor.py` "方案C v2.0"；`mineru_parser.py` "v4.0.0"；`parsers` 各自 `PARSER_VERSION` | 各自独立 |

**混乱根源**：`finance.__version__=5.0.0`（包）与"qual v8"（工作流代次）与"quality v3"（组件代次）**不是同一个刻度**——5.0.0 ≠ v8 ≠ v3，它们描述的是不同层面的演进。`workflow.py` 内部同时混用 v1/v2/v3/v4 注释（"v3 新组件"、"v4.0新增 ANCH"、"v2 整改"），实际是**把组件/功能迭代写进了工作流代次的注释里**。

---

## 三、版本演进时间线（从代码痕迹还原）

```
v1 (2026-06-30 前)  单体雏形：类型推断→数据收集→11章写作→审计→组装
   ↓ 重写集成层（filing_downloader.py 头注释 "v1 修复3个阻断bug"）
v2 (2026-06-30)     单体工作流（workflow.py 头注释 "v2.0"）+ stage_manager 乐观锁
   ↓ 新增 v3 质量组件（ModuleLoader/ContentValidator/DataMappingRegistry...）
v3 (质量组件层)      quality/v3 全套（DCF/CAPM/YearAnchor/ReviewIntegrator...）
   ↓ 新增 ANCH、综合结论章
v4 (功能增量)        workflow.py 内 "v4.0新增"（ANCH、综合结论章、决策聚合）
   ↓ Gate 化尝试
v8 (2026-08-08)     qual_v8 Gate0-8 状态机引擎（qual-workflow-pitfalls 记录 "v8.2/v8.4"）
                    但实现是"脚手架"：Gate 全是"这里应该实现"占位
   ↓ 2026-08-18 本次
v8 可运行化           Gate 灌入 v2-v7 真实组件 + DataAnchor + 红队审查
```

**关键事实**：v3-v7 的"代次"大多**没有独立代码**——它们是 `workflow.py` 单体内部的功能迭代里程碑（用注释记录），真正的架构分叉只有 **v2 单体 vs v8 引擎**。`qual_v8` 直接标 "v8.4" 跳过了 v3-v7 是因为**工作流代次**与**组件代次**被合并计数。

---

## 四、版本治理建议（统一刻度，单一事实源）

### 4.1 三刻度分离（立即做，纯文档）

把混用的"vX"拆成三个独立刻度，各管各的：

| 刻度 | 命名 | 管理者 | 变化时机 |
|---|---|---|---|
| **包版本** | `__version__`（semver，如 5.1.0） | finance 包 | 任何对外接口变更 |
| **架构代次** | `ARCH_GEN = "v8"`（仅 v1→v2→…→v8） | 架构文档 | 只有发生架构级重写才递增 |
| **组件代次** | `COMPONENT_GEN = "v3"`（质量组件层） | quality/ | 质量组件整体换代 |

### 4.2 收敛为单一入口（架构级，下一步）

**目标状态**：V8 引擎成为**唯一对外入口**，V2-V7 单体降级为"内部实现库"（其函数被 Gate 调用，不再直接 `run_analysis()` 暴露）。

```
用户请求
   → qual_v8.QualWorkflow.execute(context)     ← 唯一入口（编排 + 门禁）
       Gate0-2  数据层（DataAnchor canonical 锚点）
       Gate3    调用 workflow._write_chapters（v2-v7 生成能力下沉为服务）
       Gate4-5  调用 quality 链（v3 组件）
       Gate6-7  决策/记忆
       Gate8    DataAnchor 校验 + 红队审查（buy_side_report_review）
   → 报告（已过全部 Gate）
```

- `workflow.run_analysis` 保留为**兼容回退**（`QUAL_MODE=legacy` 时用），新调用一律走 v8
- 版本标注：`qual_v8/__init__.py` 声明 `ARCH_GEN="v8"` + 依赖的包版本；`workflow.py` 头注释改为"legacy 单体（ARCH_GEN v2，被 v8 Gate3 调用）"

### 4.3 CHANGELOG 与版本锚定

- 新建 `tools/finance/CHANGELOG.md`，按**包版本**记录（当前基线 5.0.0 = 本次 v8 可运行化 + 红队审查接入）
- `__version__` 提升到 `5.1.0`（新增 review_report_text/DataAnchor canonical 化/红队审查）——但要等方案 A/B（单源契约+财年锚定）落地后一起打 tag，避免版本号空转
- 每个 Gate 文件头注释带 `since_arch_gen`（如 Gate8 `since v8.2`，DataAnchor `since v8.4`），组件带 `since_component_gen v3`——**不再用裸 "vX" 混在代码注释里**

---

## 五、当前状态的诚实评估

1. **不是两个项目**：单包双架构，共享 fact_extractor/quality/DCF 等组件——这是**过渡期常态**（从单体演进到 Gate 引擎的中间态），不是缺陷
2. **代码里没有真 v3-v7**：那些是 workflow.py 单体内的功能迭代注释，不是独立版本——"v8" 是**架构代次**（第 8 次架构演进），与包版本 5.0.0 无关
3. **本轮改造让关系从"v8 旁观"变成"v8 编排 + v2-v7 供能"**——方向正确，但 v2-v7 的 `run_analysis` 仍是"另一个入口"，存在双入口漂移风险（改了一处漏另一处）
4. **版本治理的第一步是文档**（三刻度分离），第二步是入口收敛（v8 唯一），第三步才是包版本号维护（semver + changelog）
