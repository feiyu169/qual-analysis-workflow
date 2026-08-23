# Qual v9 最终重构方案

**日期**：2026-08-22  
**版本**：v1.0  
**目标**：基于 qual v8 代码审查 + dayu-agent 192,000 行全量对比，制定分层融合重构方案  
**原则**：保留 qual 可预测性 + 借鉴 dayu 数据控制范式 + 消除 Gate4 死循环

---

## 一、架构总览

### 1.1 四层分层架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Layer 4: 终局兜底（程序化修复）                    │
│  ┌───────────┐  ┌───────────┐  ┌──────────────────┐                 │
│  │   ADVC    │  │   PGNB    │  │  bind_fuzzy_dates │                 │
│  │ 锚点修复  │  │ 数字守卫  │  │   模糊日期绑定    │                 │
│  └───────────┘  └───────────┘  └──────────────────┘                 │
│  控制权：100% 程序化（确定性，不调 LLM）                               │
├─────────────────────────────────────────────────────────────────────┤
│                     Layer 3: 质量保障（3 个检查器）                    │
│  ┌─────────────────┐  ┌─────────────┐  ┌──────────────────┐         │
│  │ CrossChapter    │  │   Numeric   │  │  Placeholder     │         │
│  │ Consistency     │  │   Guard     │  │  Detector        │         │
│  │ 跨章一致性      │  │  数值守卫   │  │  占位符检测       │         │
│  └─────────────────┘  └─────────────┘  └──────────────────┘         │
│  控制权：100% 程序化（确定性检查，不调 LLM）                           │
├─────────────────────────────────────────────────────────────────────┤
│                     Layer 2: 章节生成（LLM 驱动，只读）                │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │  ChapterGenerator（按 prompt 生成章节，数字必须来自锚点）      │    │
│  │  - 11 章买方标准结构（CFA 框架）                               │    │
│  │  - 数字通过 DataAnchor API 注入（LLM 不编造）                 │    │
│  │  - 生成后立即触发 Layer 3 检查                                 │    │
│  └──────────────────────────────────────────────────────────────┘    │
│  控制权：LLM 负责分析逻辑和写作，数字由程序注入                        │
├─────────────────────────────────────────────────────────────────────┤
│                     Layer 1: 数据获取（程序化控制）                    │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────┐      │
│  │  Wind MCP    │  │ Filing Fetch │  │    DataAnchor         │      │
│  │  行情/估值   │  │ 财报下载     │  │  唯一数据源（锚点库）  │      │
│  │  财务数据    │  │ PDF 解析     │  │  多财年/canonical键    │      │
│  └──────────────┘  └──────────────┘  └───────────────────────┘      │
│  控制权：100% 程序化（LLM 不参与）                                    │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 核心设计原则

| # | 原则 | 说明 |
|---|------|------|
| P1 | **程序化优先** | 凡是能用程序确定性解决的，不用 LLM |
| P2 | **数据只读** | Layer 2（LLM）只能读取 Layer 1 的数据，不能修改 |
| P3 | **单轮修复** | 检查器发现问题 → 程序化修复 → 不再循环审查 |
| P4 | **锚点单源** | 所有数字来自 DataAnchor，章节通过 API 获取 |
| P5 | **确定性质量** | Layer 3 检查器必须是确定性的（非 LLM），结果可复现 |
| P6 | **增量感知** | 修复只影响当前章，不触发全量重查 |

### 1.3 与现有架构对比

| 维度 | Qual v8 | Qual v9 |
|------|---------|---------|
| 检查器数量 | 16 个（7 个 LLM + 9 个程序） | **3 个**（全部程序化） |
| 修复机制 | LLM 修复 LLM（多轮循环） | **程序化修复（单轮）** |
| 数据传递 | `dict[str, Any]` | **强类型 dataclass** |
| 典型耗时 | 40-60 分钟（7 轮失败） | **目标 < 15 分钟** |
| 代码行数 | 57,318 行 | **目标 < 15,000 行** |
| 死循环风险 | 高（16 检查器正反馈） | **零（无循环依赖）** |

---

## 二、模块清单

### 2.1 完整模块表

| 模块 | 路径 | 职责 | 行数估算 | 来源 |
|------|------|------|----------|------|
| **contracts** | `qual/contracts/` | 强类型契约层 | **1,200** | 新建（参照 dayu） |
| ├─ data_context.py | | DataContextContract（替代 dict） | 150 | 新建 |
| ├─ wind_data.py | | WindDataContract | 80 | 新建 |
| ├─ filing_data.py | | FilingDataContract | 60 | 新建 |
| ├─ facts.py | | FactsContract | 80 | 新建 |
| ├─ chapter.py | | ChapterContract | 60 | 新建 |
| ├─ gate_contract.py | | GateContract + GateResultContract | 200 | 新建 |
| ├─ review_result.py | | ReviewResultContract | 60 | 新建 |
| ├─ gate_state.py | | GateState 状态机 | 120 | 重构自 state_machine.py |
| ├─ events.py | | QualEvent + QualResult | 80 | 新建 |
| ├─ cancellation.py | | CancellationToken | 60 | 参照 dayu |
| └─ protocols.py | | CheckerProtocol + RepairerProtocol | 80 | 新建 |
| **host** | `qual/host/` | 托管执行层 | **12,000** | 新建（参照 dayu） |
| ├─ orchestrator.py | | 编排入口（调度 Gate0-8） | 400 | 重构自 workflow.py |
| ├─ session.py | | Session 生命周期管理 | 300 | 新建 |
| ├─ run.py | | Run 记录 + 状态管理 | 300 | 新建 |
| ├─ budget.py | | LLM 调用预算 + 墙钟 | 200 | 重构自 quality/budget.py |
| ├─ circuit_breaker.py | | 熔断器 | 150 | 保留 qual_v8 |
| ├─ audit_logger.py | | 审计日志 | 200 | 保留 qual_v8 |
| ├─ supervisor.py | | 第三方监督 | 200 | 保留 qual_v8 |
| └─ error_classifier.py | | 错误分类 | 150 | 保留 qual_v8 |
| **write_pipeline** | `qual/write_pipeline/` | 报告写作流水线 | **8,000** | 重构 |
| ├─ chapter_generator.py | | 单章生成（prompt + LLM） | 600 | 重构自 workflow.py |
| ├─ prompt_builder.py | | Prompt 模板构建 | 500 | 新建（参照 dayu prompting） |
| ├─ numeric_binder.py | | PGNB：数字注入绑定 | 400 | 保留 qual_v8 |
| ├─ anchor_repair.py | | ADVC：锚点修复 | 300 | 保留 qual_v8 |
| ├─ report_assembler.py | | 报告组装（11 章 → 完整报告） | 200 | 重构自 workflow.py |
| ├─ conclusion_generator.py | | 结论章（Gate6） | 300 | 重构自 gates/gate6.py |
| ├─ quality_enhancer.py | | 质量增强（Gate5） | 300 | 重构自 gates/gate5.py |
| └─ validators.py | | 章节级验证 | 400 | 重构自 quality/ |
| **storage** | `qual/storage/` | 数据存储协议 | **800** | 新建（参照 dayu） |
| ├─ report_store.py | | 报告存储 | 200 | 新建 |
| ├─ anchor_store.py | | 锚点持久化 | 200 | 新建 |
| └─ audit_store.py | | 审计日志存储 | 200 | 新建 |
| **prompting** | `qual/prompting/` | Prompt 渲染 | **500** | 新建（参照 dayu） |
| ├─ chapter_prompts.py | | 各章 prompt 模板 | 300 | 提取自 workflow.py |
| └─ review_prompts.py | | 审查 prompt 模板 | 200 | 提取自 quality/ |
| **checkers** | `qual/checkers/` | 确定性检查器（3 个） | **1,500** | 精简重构 |
| ├─ cross_chapter.py | | 跨章一致性 | 500 | 精简自 quality/ |
| ├─ numeric_guard.py | | 数值守卫 | 500 | 精简自 quality/ |
| └─ placeholder.py | | 占位符检测 | 200 | 精简自 quality/ |
| **fins** | `qual/fins/` | 数据层 | **4,600** | 保留 + 重构 |
| ├─ wind_adapter.py | | Wind MCP 适配 | 600 | 保留 |
| ├─ filing_service.py | | 财报下载/解析 | 800 | 保留 |
| ├─ fact_extractor.py | | 事实提取 | 500 | 保留 |
| ├─ data_anchor.py | | DataAnchor 核心 | 500 | 保留 qual_v8 |
| └─ wind_field_mapper.py | | Wind 字段映射 | 400 | 保留 quality/v3 |
| **gates** | `qual/gates/` | Gate 实现（精简版） | **2,000** | 重构 |
| ├─ gate0.py | | 数据源验证 | 200 | 精简 |
| ├─ gate1.py | | 类型推断 | 200 | 精简 |
| ├─ gate2.py | | 数据收集 | 300 | 精简 |
| ├─ gate3.py | | 章节写作 | 400 | 精简 |
| ├─ gate4.py | | 审查修复（精简版） | 300 | **核心重构** |
| ├─ gate6.py | | 结论 | 200 | 精简 |
| ├─ gate7.py | | 问题转化 | 100 | 精简 |
| └─ gate8.py | | 最终验证 | 200 | 精简 |
| **engine** | `qual/engine/` | 工具基础设施 | **5,200** | 参照 dayu |
| ├─ llm_caller.py | | LLM 调用封装 | 400 | 保留 |
| ├─ tool_registry.py | | 工具注册 | 300 | 新建 |
| ├─ trace_recorder.py | | 执行追踪 | 300 | 新建 |
| ├─ dcf_service.py | | DCF 估值计算 | 600 | 保留 quality/v3 |
| ├─ fcf_calculator.py | | FCF 计算 | 400 | 保留 quality/ |
| ├─ capm_calculator.py | | CAPM/Ke 计算 | 400 | 保留 quality/ |
| ├─ terminal_value.py | | 终值计算 | 400 | 保留 quality/ |
| ├─ roic_checker.py | | ROIC-WACC 检查 | 300 | 保留 quality/ |
| └─ sensitivity.py | | 敏感性分析 | 300 | 保留 quality/ |
| **monitoring** | `qual/monitoring/` | 监控告警 | **400** | 保留 qual_v8 |
| ├─ alerts.py | | 告警管理 | 200 | 保留 |
| └─ metrics.py | | 指标收集 | 200 | 保留 |
| **tests** | `qual/tests/` | 测试套件 | **2,000** | 新建 |
| ├─ test_contracts.py | | 契约层测试 | 300 | 新建 |
| ├─ test_checkers.py | | 检查器测试 | 400 | 新建 |
| ├─ test_gates.py | | Gate 集成测试 | 500 | 新建 |
| ├─ test_pipeline.py | | 流水线 E2E 测试 | 400 | 新建 |
| └─ test_golden.py | | 金标准回归测试 | 400 | 新建 |
| **合计** | | | **~30,000** | |

### 2.2 模块依赖图

```
contracts (1,200行)
    │
    ├──► host (12,000行)
    │        │
    │        ├──► gates (2,000行)
    │        │        │
    │        │        ├──► write_pipeline (8,000行)
    │        │        │        │
    │        │        │        ├──► prompting (500行)
    │        │        │        ├──► checkers (1,500行)
    │        │        │        └──► engine (5,200行)
    │        │        │
    │        │        └──► fins (4,600行)
    │        │
    │        ├──► storage (800行)
    │        └──► monitoring (400行)
    │
    └──► tests (2,000行)
```

---

## 三、数据流

### 3.1 完整数据流（从 Wind 数据到最终报告）

```
                        ┌─────────────────────────────────┐
                        │         用户请求                  │
                        │  ticker + company_name + market   │
                        └───────────────┬─────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Gate 0: 数据源验证（Layer 1，100% 程序化）                               │
│  ┌──────────┐    ┌──────────┐    ┌──────────────┐                       │
│  │ Wind MCP │───►│ 格式校验  │───►│ DataAnchor   │                       │
│  │ 数据获取  │    │ 字段覆盖  │    │ 初始化锚点库  │                       │
│  └──────────┘    └──────────┘    └──────────────┘                       │
│  输出: WindDataContract + DataAnchor（含 3 年 × 10 指标锚点）             │
│  控制权: ████ 100% 程序                                                  │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Gate 1: 类型推断（Layer 1，100% 程序化）                                 │
│  ┌──────────┐    ┌──────────┐    ┌──────────────┐                       │
│  │ 行业识别  │    │ 市场判断  │    │ FactsContract│                       │
│  │ 上下文提取│───►│ 港/A/美  │───►│ 事实表构建    │                       │
│  └──────────┘    └──────────┘    └──────────────┘                       │
│  输出: FactsContract（公司画像、行业、市场类型）                           │
│  控制权: ████ 100% 程序                                                  │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Gate 2: 数据收集 + 参数提取（Layer 1，100% 程序化）                      │
│  ┌──────────┐    ┌──────────┐    ┌──────────────┐                       │
│  │ 财报下载  │    │ DCF 参数  │    │ FilingData   │                       │
│  │ PDF 解析  │───►│ 提取校验  │───►│ Contract     │                       │
│  └──────────┘    └──────────┘    └──────────────┘                       │
│  输出: FilingDataContract + DCF 参数（WACC/FCF/g/tax）                   │
│  控制权: ████ 100% 程序                                                  │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Gate 3: 章节写作（Layer 2，LLM 驱动 + 程序约束）                         │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │  ChapterGenerator                                               │    │
│  │                                                                  │    │
│  │  输入: DataContextContract + 章节 prompt                         │    │
│  │  过程:                                                          │    │
│  │    1. PromptBuilder 构建 prompt（注入锚点数据，非原始 Wind）      │    │
│  │    2. LLM 生成章节（只读锚点，不编造数字）                        │    │
│  │    3. NumericBinder 绑定裸数字（PGNB）                           │    │
│  │    4. PlaceholderDetector 检测占位符（Layer 3）                   │    │
│  │    5. 若有占位符 → 单轮修复（不循环）                             │    │
│  │  输出: ChapterContract（章节内容 + 元数据）                       │    │
│  └──────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  控制权: █░░░ LLM 负责分析逻辑，数字由程序注入和校验                     │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Gate 4: 审查修复（Layer 3 + Layer 4，精简版）                            │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │  单轮审查（不循环！）                                             │    │
│  │                                                                  │    │
│  │  Step 1: CrossChapterChecker（程序化）                            │    │
│  │    - 跨章数据一致性（锚点比对）                                    │    │
│  │    - 逻辑矛盾检测（规则引擎，非 LLM）                             │    │
│  │                                                                  │    │
│  │  Step 2: NumericGuard（程序化）                                   │    │
│  │    - 数值范围校验（WACC/FCF/税率等）                              │    │
│  │    - 财年匹配校验                                                 │    │
│  │    - 币种一致性校验                                               │    │
│  │                                                                  │    │
│  │  Step 3: PlaceholderDetector（程序化）                            │    │
│  │    - 占位符模式匹配                                               │    │
│  │    - 模板残留检测                                                 │    │
│  │                                                                  │    │
│  │  Step 4: 程序化修复（Layer 4）                                    │    │
│  │    - ADVC: 锚点数据替换（确定性）                                 │    │
│  │    - PGNB: 裸数字绑定（确定性）                                   │    │
│  │    - bind_fuzzy_dates: 模糊日期绑定（确定性）                     │    │
│  │                                                                  │    │
│  │  Step 5: 修复后单次复验（非循环）                                  │    │
│  │    - 仅检查被修复的章节（增量）                                    │    │
│  │    - 若仍有问题 → 标注降级，不阻断                                │    │
│  └──────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  控制权: ████ 100% 程序化（零 LLM 调用）                                │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Gate 5: 质量增强（Layer 2，LLM 辅助）                                   │
│  ┌──────────┐    ┌──────────┐    ┌──────────────┐                       │
│  │ DCF 重算  │    │ 敏感性    │    │ 估值校验     │                       │
│  │ SOTP     │───►│ 分析     │───►│ 参数一致性    │                       │
│  └──────────┘    └──────────┘    └──────────────┘                       │
│  控制权: █░░░ 程序计算为主，LLM 辅助解读                                 │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Gate 6: 综合结论（Layer 2，LLM 驱动）                                   │
│  ┌──────────┐    ┌──────────┐    ┌──────────────┐                       │
│  │ 投资评级  │    │ 目标价    │    │ 决策章       │                       │
│  │ 推导     │───►│ 计算     │───►│ 生成         │                       │
│  └──────────┘    └──────────┘    └──────────────┘                       │
│  控制权: █░░░ LLM 负责分析推导，数字由锚点保障                           │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Gate 7: 问题转化 + 记忆存储（Layer 1，100% 程序化）                      │
│  输出: 跟踪问题清单 + 记忆存储                                           │
│  控制权: ████ 100% 程序                                                  │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Gate 8: 最终验证（Layer 3 + Layer 4，确定性）                            │
│  ┌──────────┐    ┌──────────┐    ┌──────────────┐                       │
│  │ 全章终验  │    │ 质量声明  │    │ 报告输出     │                       │
│  │ 3 检查器  │───►│ 降级标注  │───►│ + 审计日志   │                       │
│  └──────────┘    └──────────┘    └──────────────┘                       │
│  控制权: ████ 100% 程序                                                  │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.2 数据流中的控制权分配

| 步骤 | 控制权 | 说明 |
|------|--------|------|
| Wind 数据获取 | **程序** | 通过 MCP 调用，LLM 不参与 |
| 数据锚点初始化 | **程序** | DataAnchor 从 Wind 数据自动构建 |
| 类型推断 | **程序** | 规则引擎，不调 LLM |
| 财报下载/解析 | **程序** | PDF 解析 + 结构化提取 |
| 章节生成 | **LLM** | LLM 负责分析逻辑和写作 |
| 数字注入 | **程序** | PGNB/ADVC 将锚点数字注入章节 |
| 跨章检查 | **程序** | 锚点比对，确定性 |
| 逻辑矛盾检测 | **程序** | 规则引擎（LC01-LC11） |
| 数值范围校验 | **程序** | 配置化阈值 |
| 修复 | **程序** | ADVC/PGNB 确定性替换 |
| 估值计算 | **程序** | DCF/SOTP 数学计算 |
| 结论推导 | **LLM** | LLM 综合分析 |
| 最终验证 | **程序** | 3 个检查器 + 降级标注 |

---

## 四、Gate 设计（精简版）

### 4.1 Gate 职责表

| Gate | 名称 | 职责 | 控制权 | 输入 | 输出 | 超时 |
|------|------|------|--------|------|------|------|
| **Gate 0** | 数据源验证 | Wind 数据获取 + 字段覆盖校验 + DataAnchor 初始化 | 100% 程序 | ticker, market | WindDataContract, DataAnchor | 60s |
| **Gate 1** | 类型推断 | 行业识别 + 市场判断 + FactsContract 构建 | 100% 程序 | WindData, company_name | FactsContract | 30s |
| **Gate 2** | 数据收集 | 财报下载 + DCF 参数提取 + 校验 | 100% 程序 | ticker, market, WindData | FilingDataContract, DCFParams | 120s |
| **Gate 3** | 章节写作 | 11 章逐章生成 + PGNB 数字绑定 | LLM + 程序约束 | DataContext | Chapters | 600s |
| **Gate 4** | 审查修复 | 3 检查器 + 程序化修复 + 单次复验 | 100% 程序 | Chapters, DataAnchor | 修复后 Chapters | 120s |
| **Gate 5** | 质量增强 | DCF 重算 + 敏感性分析 + 估值校验 | 程序为主 | Chapters, DCFParams | 增强后 Chapters | 180s |
| **Gate 6** | 综合结论 | 投资评级推导 + 目标价计算 + 决策章生成 | LLM + 程序 | 全部章节 | 结论章 | 180s |
| **Gate 7** | 问题转化 | 跟踪问题提取 + 记忆存储 | 100% 程序 | 全部章节 | 问题清单 | 30s |
| **Gate 8** | 最终验证 | 全章终验 + 质量声明 + 报告输出 | 100% 程序 | 全部章节 | 最终报告 | 60s |

### 4.2 Gate 详细设计

#### Gate 0: 数据源验证

```python
class Gate0DataSource(GateBase):
    """数据源验证（Layer 1，100% 程序化）"""
    
    def execute(self, ctx: DataContextContract) -> GateResultContract:
        # 1. Wind 数据获取
        wind_raw = self.wind_client.fetch(ctx.ticker, ctx.market)
        
        # 2. 字段覆盖校验（≥95% 必填字段）
        coverage = self._check_field_coverage(wind_raw)
        if coverage < 0.95:
            return GateResultContract(gate_num=0, state=GateState.FAILED,
                errors=(f"Wind 字段覆盖率 {coverage:.1%} < 95%",))
        
        # 3. 构建 WindDataContract
        wind = WindDataContract.from_raw(wind_raw)
        
        # 4. 初始化 DataAnchor
        anchor = DataAnchor()
        anchor.init_from_wind(wind)
        
        # 5. 写回上下文
        ctx = ctx.with_wind(wind).with_anchor(anchor)
        return GateResultContract(gate_num=0, state=GateState.PASSED)
```

#### Gate 4: 审查修复（核心重构）

```python
class Gate4ReviewRepair(GateBase):
    """审查修复（Layer 3 + Layer 4，100% 程序化，零 LLM 调用）
    
    关键设计：
    1. 三个检查器串行执行（非并行，避免交叉误报）
    2. 每个检查器独立，不依赖其他检查器的输出
    3. 修复后单次复验（仅检查被修复的章节）
    4. 不循环——复验失败直接标注降级，不阻断
    """
    
    CHECKERS = [
        CrossChapterChecker(),      # 跨章一致性（锚点比对）
        NumericGuard(),             # 数值范围/财年/币种
        PlaceholderDetector(),      # 占位符/模板残留
    ]
    
    REPAIRERS = [
        ADVCRepairer(),             # 锚点数据替换
        PGNBRepairer(),             # 裸数字绑定
        FuzzyDateRepairer(),        # 模糊日期绑定
    ]
    
    def execute(self, ctx: DataContextContract) -> GateResultContract:
        chapters = ctx.chapters
        all_issues = []
        
        # Step 1: 串行检查（非并行，避免交叉误报）
        for checker in self.CHECKERS:
            issues = checker.check(chapters, ctx.anchor)
            all_issues.extend(issues)
        
        # Step 2: 程序化修复（单轮）
        if all_issues:
            for repairer in self.REPAIRERS:
                chapters = repairer.repair(chapters, all_issues, ctx.anchor)
        
        # Step 3: 修复后单次复验（仅检查被修复的章节）
        remaining = []
        for checker in self.CHECKERS:
            recheck = checker.check(chapters, ctx.anchor)
            remaining.extend(recheck)
        
        # Step 4: 判定（不循环！）
        if remaining:
            # 仍有问题 → 标注降级，不阻断
            logger.warning(f"Gate4 仍有 {len(remaining)} 个问题，标注降级")
            return GateResultContract(
                gate_num=4, state=GateState.PASSED,  # 不阻断！
                warnings=tuple(f"降级: {i}" for i in remaining[:5]),
            )
        
        return GateResultContract(gate_num=4, state=GateState.PASSED)
```

#### Gate 8: 最终验证

```python
class Gate8FinalValidation(GateBase):
    """最终验证（Layer 3，100% 程序化）"""
    
    def execute(self, ctx: DataContextContract) -> GateResultContract:
        chapters = ctx.chapters
        errors = []
        warnings = []
        
        # 1. 占位符终检（零容忍）
        placeholders = self.placeholder_detector.check_all(chapters)
        if placeholders:
            errors.extend(f"占位符: {p}" for p in placeholders)
        
        # 2. 锚点一致性终验
        anchor_errors = ctx.anchor.validate_all_chapters(chapters)
        if anchor_errors:
            warnings.extend(anchor_errors[:5])  # 降级标注，不阻断
        
        # 3. 风险提示覆盖
        risk_coverage = self._check_risk_coverage(chapters)
        if risk_coverage < 0.8:
            warnings.append(f"风险提示覆盖 {risk_coverage:.0%}")
        
        # 4. 判定
        if errors:
            return GateResultContract(
                gate_num=8, state=GateState.FAILED,
                errors=tuple(errors),
            )
        
        return GateResultContract(
            gate_num=8, state=GateState.PASSED,
            warnings=tuple(warnings),
        )
```

---

## 五、检查器设计

### 5.1 保留 3 个检查器

| # | 检查器 | 功能 | 类型 | 来源 | 行数 |
|---|--------|------|------|------|------|
| 1 | **CrossChapterChecker** | 跨章数据一致性 | 确定性（锚点比对） | 精简自 `cross_chapter_consistency.py` | 500 |
| 2 | **NumericGuard** | 数值范围/财年/币种校验 | 确定性（规则引擎） | 精简自 `numeric_guard.py` | 500 |
| 3 | **PlaceholderDetector** | 占位符/模板残留检测 | 确定性（正则匹配） | 精简自 `placeholder_rules.py` | 200 |

### 5.2 删除 13 个检查器

| # | 检查器 | 删除理由 |
|---|--------|----------|
| 1 | **DepthReviewer** | LLM 审查 LLM → 正反馈循环源。用程序化检查器替代 |
| 2 | **FactChecker** | 与 CrossChapterChecker 功能重叠（锚点比对）。合并 |
| 3 | **LogicConsistencyChecker** | 规则引擎过于复杂（LC01-LC11），精简到 CrossChapterChecker 内 |
| 4 | **DataReasonablenessChecker** | 与 NumericGuard 功能重叠（范围校验）。合并 |
| 5 | **DateAnchorChecker** | 日期问题通过 bind_fuzzy_dates 程序化修复，不需要独立检查器 |
| 6 | **ValuationArbitrator** | 估值问题在 Gate5（DCF 重算）中程序化解决 |
| 7 | **AssumptionChecker** | LLM 检查 LLM 的假设 → 不确定性来源。删除 |
| 8 | **CounterArgumentValidator** | LLM 对抗审查 → 正反馈循环源。删除 |
| 9 | **ConclusionValidator** | LLM 审查结论 → 不确定性来源。用规则引擎（评级-估值一致性）替代 |
| 10 | **AuditValidator** | 过度工程化（检查检查器的检查器）。删除 |
| 11 | **ROICWACCChecker** | 与 NumericGuard 功能重叠（ROIC-WACC 范围校验）。合并 |
| 12 | **ConfigValidator** | 配置校验在 Gate0/2 中已覆盖，不需要独立检查器 |
| 13 | **ReviewIntegrator** | 审查整合器本身是死循环的编排器。删除 |

### 5.3 CrossChapterChecker 详细设计

```python
class CrossChapterChecker:
    """跨章一致性检查器（确定性，锚点比对）
    
    合并了原：
    - cross_chapter_consistency.py（跨章数据一致性）
    - logic_consistency_check.py（逻辑矛盾检测，精简为规则引擎）
    - fact_checker.py（事实核查，锚点比对）
    """
    
    # 逻辑矛盾规则（精简版，只保留高频问题）
    CONTRADICTION_RULES = [
        ("营收增长但利润下降无解释", "revenue_growth > 0 and net_profit_growth < 0"),
        ("评级上调但目标价下调", "rating == 'up' and target_price_change < 0"),
        ("现金流为负但推荐买入", "ocf < 0 and rating == 'buy'"),
    ]
    
    def check(self, chapters: dict[int, str], anchor: DataAnchor) -> list[str]:
        issues = []
        
        # 1. 锚点比对（确定性）
        for ch_num, content in chapters.items():
            anchor_errors = anchor.validate_chapter_any_fy(ch_num, content)
            issues.extend(f"第{ch_num}章: {e}" for e in anchor_errors)
        
        # 2. 跨章数字一致性（同一指标在不同章节的值必须一致）
        issues.extend(self._cross_chapter_consistency(chapters, anchor))
        
        # 3. 逻辑矛盾（规则引擎，非 LLM）
        issues.extend(self._check_contradictions(chapters))
        
        return issues
    
    def _cross_chapter_consistency(self, chapters, anchor) -> list[str]:
        """检查同一指标在不同章节的值是否一致"""
        # 从各章提取数字，与锚点比对
        # 不一致 → 报错
        ...
    
    def _check_contradictions(self, chapters) -> list[str]:
        """规则引擎检测逻辑矛盾"""
        # 基于规则匹配，非 LLM
        ...
```

### 5.4 NumericGuard 详细设计

```python
class NumericGuard:
    """数值守卫（确定性，规则引擎）
    
    合并了原：
    - numeric_guard.py（数值范围/财年/币种）
    - data_reasonableness_check.py（数据合理性）
    - roic_wacc_checker.py（ROIC-WACC 校验）
    - config_validator.py（DCF 参数校验）
    """
    
    # 校验规则（配置化）
    RANGE_RULES = {
        "wacc": (0.05, 0.25),           # WACC 合理范围
        "terminal_growth": (0.01, 0.05), # 永续增长率
        "tax_rate": (0.10, 0.35),        # 税率范围
        "revenue_growth": (-0.50, 1.00), # 营收增长率
    }
    
    def check(self, chapters: dict[int, str], anchor: DataAnchor) -> list[str]:
        issues = []
        
        for ch_num, content in chapters.items():
            # 1. 数值范围校验
            issues.extend(self._check_ranges(ch_num, content))
            
            # 2. 财年匹配校验
            issues.extend(self._check_fiscal_years(ch_num, content, anchor))
            
            # 3. 币种一致性校验
            issues.extend(self._check_currency(ch_num, content))
        
        return issues
```

---

## 六、审查修复循环：消除死循环

### 6.1 死循环根因分析

```
v8 死循环机制：

Gate3 生成章节
    │
    ▼
Gate4 审查（16 个检查器）
    │
    ├── 检查器 A 发现问题 X → 修复 X
    │       │
    │       ▼
    │   修复 X 触发检查器 B 发现新问题 Y → 修复 Y
    │       │
    │       ▼
    │   修复 Y 触发检查器 C 发现新问题 Z → 修复 Z
    │       │
    │       ▼
    │   修复 Z 又触发检查器 A 发现问题 X'（修复副作用）
    │       │
    │       ▼
    │   ┌──────────────────────────────┐
    │   │  正反馈循环：X→Y→Z→X'→...   │
    │   │  40-60 分钟，7 轮全部失败     │
    │   └──────────────────────────────┘
    │
    ▼
Gate4 失败 → Gate5-8 全部跳过
```

### 6.2 v9 解决方案：单轮确定性修复 + 标注

```
v9 修复机制：

Gate3 生成章节
    │
    ▼
Gate4 审查（3 个检查器，串行）
    │
    ├── CrossChapterChecker → 发现问题列表
    ├── NumericGuard → 发现问题列表
    ├── PlaceholderDetector → 发现问题列表
    │
    ▼
合并问题列表（去重）
    │
    ▼
程序化修复（单轮，确定性）
    │
    ├── ADVC: 锚点数据替换（数字 → 锚点值）
    ├── PGNB: 裸数字绑定（数字 → 格式化）
    └── bind_fuzzy_dates: 日期绑定
    │
    ▼
修复后单次复验（仅检查被修复的章节）
    │
    ├── 通过 → Gate4 PASSED
    └── 仍有问题 → Gate4 PASSED（降级标注，不阻断）
                      │
                      ▼
                 报告头部添加：
                 "⚠️ 质量受限声明：第 X 章存在数据一致性问题，
                  投资结论需人工复核"
```

### 6.3 关键设计决策

| 决策 | 理由 |
|------|------|
| **检查器串行执行** | 避免并行检查器交叉误报 |
| **修复后单次复验** | 验证修复效果，但不循环 |
| **复验失败不阻断** | 标注降级，允许人工复核。买方需要报告，不是完美报告 |
| **增量复验** | 只检查被修复的章节，不全量重查 |
| **修复用程序不用 LLM** | 确定性修复，不会引入新问题 |

---

## 七、Contracts 层核心定义

### 7.1 文件结构

```
qual/contracts/
├── __init__.py              # lazy import + _EXPORT_MAP
├── data_context.py          # DataContextContract
├── wind_data.py             # WindDataContract
├── filing_data.py           # FilingDataContract
├── facts.py                 # FactsContract
├── chapter.py               # ChapterContract
├── gate_contract.py         # GateContract + GateResultContract
├── review_result.py         # ReviewResultContract
├── gate_state.py            # GateState 状态机
├── events.py                # QualEvent + QualResult
├── cancellation.py          # CancellationToken
└── protocols.py             # CheckerProtocol + RepairerProtocol
```

### 7.2 核心 dataclass 定义

```python
# qual/contracts/wind_data.py
from __future__ import annotations
from dataclasses import dataclass, field

@dataclass(frozen=True)
class WindDataContract:
    """Wind 数据强类型契约（替代 dict[str, Any]）"""
    income: dict[str, list[float | None]]
    balance: dict[str, list[float | None]]
    cashflow: dict[str, list[float | None]]
    quote: dict[str, float | str | None] = field(default_factory=dict)
    valuation: dict[str, float | None] = field(default_factory=dict)
    year_labels: tuple[int, ...] = (2023, 2024, 2025)
    
    @classmethod
    def from_raw(cls, raw: dict) -> WindDataContract:
        """从 Wind MCP 原始数据构建"""
        return cls(
            income=raw.get("income", {}),
            balance=raw.get("balance", {}),
            cashflow=raw.get("cashflow", {}),
            quote=raw.get("quote", {}),
            valuation=raw.get("valuation", {}),
            year_labels=tuple(raw.get("_year_labels", {}).get("财年", [2023, 2024, 2025])),
        )


# qual/contracts/data_context.py
from __future__ import annotations
from dataclasses import dataclass, field
from .wind_data import WindDataContract
from .filing_data import FilingDataContract
from .facts import FactsContract

@dataclass(frozen=True)
class DataContextContract:
    """Gate 间传递的完整数据上下文（替代 dict[str, Any]）"""
    ticker: str
    company_name: str
    market: str  # "hk" | "us" | "cn"
    data_quality: str = "unknown"
    wind: WindDataContract | None = None
    filing: FilingDataContract | None = None
    facts: FactsContract | None = None
    chapters: dict[int, str] = field(default_factory=dict)
    facets: dict[str, object] = field(default_factory=dict)
    anchor: DataAnchor | None = None  # 注：不 frozen，anchor 是可变的
    
    def with_wind(self, wind: WindDataContract) -> DataContextContract:
        """返回带有 Wind 数据的新上下文"""
        return DataContextContract(
            ticker=self.ticker, company_name=self.company_name,
            market=self.market, data_quality=self.data_quality,
            wind=wind, filing=self.filing, facts=self.facts,
            chapters=self.chapters, facets=self.facets, anchor=self.anchor,
        )


# qual/contracts/gate_contract.py
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum

class GateState(str, Enum):
    """Gate 状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"

# 合法状态转换表
_VALID_TRANSITIONS: dict[GateState, frozenset[GateState]] = {
    GateState.PENDING: frozenset({GateState.RUNNING, GateState.SKIPPED}),
    GateState.RUNNING: frozenset({GateState.PASSED, GateState.FAILED}),
    GateState.PASSED: frozenset(),
    GateState.FAILED: frozenset({GateState.RUNNING}),
    GateState.SKIPPED: frozenset(),
}

@dataclass(frozen=True)
class GateContract:
    """Gate 执行契约（Service → Gate 的输入）"""
    gate_num: int
    gate_name: str
    data_context: DataContextContract
    prerequisites: tuple[int, ...] = ()
    max_retries: int = 1
    deadline: float | None = None

@dataclass(frozen=True)
class GateResultContract:
    """Gate 执行结果契约（Gate → Service 的输出）"""
    gate_num: int
    state: GateState
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    issues_found: int = 0
    issues_fixed: int = 0
    remaining_issues: tuple[str, ...] = ()
    chapters: dict[int, str] | None = None
    execution_time: float = 0.0


# qual/contracts/protocols.py
from __future__ import annotations
from typing import Protocol, runtime_checkable

@runtime_checkable
class CheckerProtocol(Protocol):
    """检查器协议（所有检查器必须实现）"""
    @property
    def name(self) -> str: ...
    def check(self, chapters: dict[int, str], anchor: DataAnchor) -> list[str]: ...

@runtime_checkable
class RepairerProtocol(Protocol):
    """修复器协议（所有修复器必须实现）"""
    def repair(self, chapters: dict[int, str], issues: list[str], 
               anchor: DataAnchor) -> dict[int, str]: ...


# qual/contracts/events.py
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum

class QualEventType(str, Enum):
    """Qual 事件类型"""
    GATE_STARTED = "gate_started"
    GATE_PASSED = "gate_passed"
    GATE_FAILED = "gate_failed"
    CHAPTER_GENERATED = "chapter_generated"
    CHAPTER_REPAIRED = "chapter_repaired"
    CHECKER_WARNING = "checker_warning"
    DONE = "done"
    ERROR = "error"

@dataclass
class QualEvent:
    """Qual 标准事件"""
    type: QualEventType
    payload: dict[str, object] = field(default_factory=dict)
    gate_num: int | None = None
    chapter_num: int | None = None

@dataclass
class QualResult:
    """Qual 执行结果"""
    success: bool
    chapters: dict[int, str]
    report: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    degraded: bool = False
    gate_summary: dict[int, GateResultContract] = field(default_factory=dict)
```

---

## 八、实施路线图

### Phase 0: 准备（1 周）

**目标**：建立基础设施，不影响现有代码

| 任务 | 交付物 | 验证标准 |
|------|--------|----------|
| 创建 `qual/` 目录结构 | 目录骨架 + `__init__.py` | 目录存在，import 不报错 |
| 建立 contracts 层 | 12 个 dataclass 文件 | `pytest test_contracts.py` 通过 |
| 建立测试框架 | `test_contracts.py` + `conftest.py` | 测试可运行 |
| 建立 CI 钩子 | pre-commit + 格式化 | 提交自动检查 |

**验证标准**：`python -m pytest qual/tests/test_contracts.py -v` 全部通过

---

### Phase 1: Layer 1 数据层（2 周）

**目标**：实现程序化数据获取，LLM 不参与

| 任务 | 交付物 | 验证标准 |
|------|--------|----------|
| Gate 0 实现 | `gates/gate0.py` | Wind 数据获取 + 字段覆盖校验 |
| Gate 1 实现 | `gates/gate1.py` | 类型推断 + FactsContract 构建 |
| Gate 2 实现 | `gates/gate2.py` | 财报下载 + DCF 参数提取 |
| DataAnchor 重构 | `fins/data_anchor.py` | 锚点初始化 + 多财年支持 |
| Wind 适配器 | `fins/wind_adapter.py` | Wind MCP 调用封装 |
| 财报服务 | `fins/filing_service.py` | PDF 下载 + 解析 |

**验证标准**：
```python
# 端到端测试：从 ticker 到 DataAnchor
ctx = DataContextContract(ticker="00772.HK", company_name="阅文集团", market="hk")
ctx = gate0.execute(ctx)  # Wind 数据获取
ctx = gate1.execute(ctx)  # 类型推断
ctx = gate2.execute(ctx)  # 数据收集
assert ctx.anchor is not None
assert ctx.wind is not None
assert ctx.facts is not None
```

---

### Phase 2: Layer 3 检查器（2 周）

**目标**：实现 3 个确定性检查器

| 任务 | 交付物 | 验证标准 |
|------|--------|----------|
| CrossChapterChecker | `checkers/cross_chapter.py` | 跨章一致性检测 |
| NumericGuard | `checkers/numeric_guard.py` | 数值范围/财年/币种校验 |
| PlaceholderDetector | `checkers/placeholder.py` | 占位符/模板残留检测 |
| 检查器测试 | `test_checkers.py` | 100% 测试覆盖率 |

**验证标准**：
```python
# 测试检查器
checker = CrossChapterChecker()
issues = checker.check(chapters, anchor)
assert len(issues) == 0 or all("锚点" in i for i in issues)
```

---

### Phase 3: Layer 4 修复器（1 周）

**目标**：实现程序化修复

| 任务 | 交付物 | 验证标准 |
|------|--------|----------|
| ADVC 重构 | `write_pipeline/anchor_repair.py` | 锚点数据替换 |
| PGNB 重构 | `write_pipeline/numeric_binder.py` | 裸数字绑定 |
| FuzzyDateRepairer | `write_pipeline/fuzzy_date.py` | 模糊日期绑定 |
| 修复器测试 | `test_repairers.py` | 确定性修复验证 |

**验证标准**：
```python
# 测试修复器
repairer = ADVCRepairer()
fixed = repairer.repair(chapters, issues, anchor)
assert anchor.validate_all_chapters(fixed)["passed"]
```

---

### Phase 4: Layer 2 章节生成（3 周）

**目标**：实现 LLM 驱动的章节生成

| 任务 | 交付物 | 验证标准 |
|------|--------|----------|
| ChapterGenerator | `write_pipeline/chapter_generator.py` | 单章生成 |
| PromptBuilder | `prompting/chapter_prompts.py` | Prompt 模板构建 |
| ReportAssembler | `write_pipeline/report_assembler.py` | 11 章组装 |
| Gate 3 实现 | `gates/gate3.py` | 章节写作流程 |
| Gate 5 实现 | `gates/gate5.py` | 质量增强 |
| Gate 6 实现 | `gates/gate6.py` | 综合结论 |

**验证标准**：
```python
# 端到端测试：生成单章
chapter = chapter_generator.generate(1, ctx)
assert len(chapter) > 1000  # 非空
assert not any(p in chapter for p in PLACEHOLDER_PATTERNS)  # 无占位符
```

---

### Phase 5: Gate 4 核心重构（2 周）

**目标**：实现精简版审查修复（零死循环风险）

| 任务 | 交付物 | 验证标准 |
|------|--------|----------|
| Gate 4 实现 | `gates/gate4.py` | 单轮审查 + 程序化修复 |
| 集成测试 | `test_gate4.py` | 无死循环验证 |
| 性能测试 | `test_gate4_perf.py` | < 120s 完成 |

**验证标准**：
```python
# 死循环测试：Gate4 必须在 120s 内完成
import time
start = time.time()
result = gate4.execute(ctx)
assert time.time() - start < 120
assert result.state in (GateState.PASSED, GateState.FAILED)  # 不能是 RUNNING
```

---

### Phase 6: Host 编排层（2 周）

**目标**：实现完整的 Gate0-8 编排

| 任务 | 交付物 | 验证标准 |
|------|--------|----------|
| Orchestrator | `host/orchestrator.py` | Gate0-8 调度 |
| Session 管理 | `host/session.py` | 生命周期管理 |
| 预算管理 | `host/budget.py` | LLM 调用预算 + 墙钟 |
| 熔断器 | `host/circuit_breaker.py` | 故障熔断 |
| Gate 7/8 | `gates/gate7.py`, `gate8.py` | 问题转化 + 最终验证 |

**验证标准**：
```python
# 端到端测试：完整流程
result = orchestrator.run("00772.HK", "阅文集团", "hk")
assert result.success
assert len(result.chapters) == 11
assert result.execution_time < 900  # < 15 分钟
```

---

### Phase 7: 集成测试 + 金标准（2 周）

**目标**：端到端验证 + 回归保护

| 任务 | 交付物 | 验证标准 |
|------|--------|----------|
| E2E 测试 | `test_pipeline.py` | 完整流程通过 |
| 金标准测试 | `test_golden.py` | 已知 good case 回归 |
| 性能基准 | `test_benchmark.py` | < 15 分钟 |
| 文档 | `README.md` + API 文档 | 可读性 |

**验证标准**：
```bash
# 全量测试
python -m pytest qual/tests/ -v --tb=short
# 性能基准
python -m pytest qual/tests/test_benchmark.py -v
# 金标准回归
python -m pytest qual/tests/test_golden.py -v
```

---

### Phase 8: 迁移 + 切换（1 周）

**目标**：从 v8 平滑迁移到 v9

| 任务 | 交付物 | 验证标准 |
|------|--------|----------|
| 适配层 | `qual/legacy_adapters.py` | v8 接口兼容 |
| 迁移脚本 | `scripts/migrate_v8_to_v9.py` | 自动迁移 |
| A/B 测试 | 同时运行 v8/v9 | 结果对比 |
| 切换 | 更新 SKILL.md | v9 成为默认 |

**验证标准**：
```python
# A/B 测试：v9 结果不差于 v8
v8_result = run_v8(ticker)
v9_result = run_v9(ticker)
assert v9_result.success or not v8_result.success  # v9 至少不比 v8 差
assert v9_result.execution_time < v8_result.execution_time  # v9 更快
```

---

## 九、风险和缓解

### 9.1 风险矩阵

| # | 风险 | 概率 | 影响 | 缓解措施 |
|---|------|------|------|----------|
| R1 | **检查器精简后漏检** | 中 | 高 | 金标准测试覆盖；降级标注而非阻断 |
| R2 | **程序化修复不完整** | 中 | 中 | 修复后复验 + 降级标注；人工复核兜底 |
| R3 | **LLM 仍编造数字** | 低 | 高 | PGNB 强制绑定；锚点校验；降级标注 |
| R4 | **性能回退** | 低 | 中 | 性能基准测试；墙钟预算硬限 |
| R5 | **迁移期间功能缺失** | 中 | 中 | A/B 测试；v8 保留为回退方案 |
| R6 | **新 Gate4 仍有边缘死循环** | 低 | 高 | 墙钟硬限 120s；无循环依赖设计 |
| R7 | **锚点覆盖率不足** | 中 | 中 | 扩展 CANONICAL_ALIASES；降级标注 |
| R8 | **测试覆盖不足** | 中 | 高 | Phase 7 专项；金标准回归 |

### 9.2 关键缓解策略

#### R1: 检查器精简后漏检

**风险**：从 16 个检查器精简到 3 个，可能漏掉某些问题

**缓解**：
1. **金标准测试**：建立 10+ 已知 good case，每次改动都回归
2. **降级标注**：Gate4/8 复验失败不阻断，添加质量声明
3. **人工复核**：报告头部可见的质量声明，提示人工复核
4. **渐进式精简**：Phase 2 先实现 3 个检查器，验证后再删除旧检查器

#### R6: 新 Gate4 仍有边缘死循环

**风险**：即使设计为无循环，某些边缘 case 可能仍有问题

**缓解**：
1. **墙钟硬限**：Gate4 超时 120s 强制终止
2. **无循环依赖**：3 个检查器串行，不互相依赖
3. **单轮修复**：修复后单次复验，不循环
4. **死循环测试**：专门的 `test_gate4_no_loop.py` 验证

#### R7: 锚点覆盖率不足

**风险**：某些指标不在 CANONICAL_ALIASES 中，锚点校验跳过

**缓解**：
1. **扩展别名表**：从 dayu 的 Wind 字段映射借鉴
2. **降级标注**：锚点校验跳过的指标，添加警告
3. **日志记录**：记录所有跳过的指标，后续补充

---

## 十、附录

### A. 与 dayu-agent 的借鉴关系

| Qual v9 模块 | 借鉴 dayu 模块 | 借鉴内容 |
|--------------|----------------|----------|
| `contracts/` | `dayu/contracts/` | 强类型契约、状态机、事件系统 |
| `host/orchestrator.py` | `dayu/host/agent_execution.py` | 编排模式、Session/Run 生命周期 |
| `host/budget.py` | `dayu/host/budget.py` | LLM 调用预算管理 |
| `write_pipeline/` | `dayu/services/internal/write_pipeline/` | 报告写作流水线模式 |
| `prompting/` | `dayu/prompting/` | Prompt 渲染模式 |
| `storage/` | `dayu/fins/storage/` | 仓储协议 |
| `engine/` | `dayu/engine/tools/` | 工具注册/执行模式 |

### B. 从 qual v8 保留的模块

| 模块 | 来源 | 保留原因 |
|------|------|----------|
| `data_anchor.py` | `qual_v8/data_anchor.py` | 核心锚点机制，已验证 |
| `numeric_binder.py` | `qual_v8/numeric_binder.py` | PGNB 数字守卫，已验证 |
| `anchor_repair.py` | `qual_v8/anchor_repair.py` | ADVC 锚点修复，已验证 |
| `circuit_breaker.py` | `qual_v8/core/circuit_breaker.py` | 熔断器，已验证 |
| `audit_logger.py` | `qual_v8/core/audit_logger.py` | 审计日志，已验证 |
| `supervisor.py` | `qual_v8/core/supervisor.py` | 第三方监督，已验证 |
| `llm_caller.py` | `finance/llm_caller.py` | LLM 调用封装，已验证 |
| `wind_adapter.py` | `finance/assemble_wind_data.py` | Wind 数据适配，已验证 |
| `filing_service.py` | `finance/filing_downloader.py` | 财报下载，已验证 |

### C. 从 qual v8 删除的模块

| 模块 | 删除原因 |
|------|----------|
| `quality/depth_reviewer.py` | LLM 审查 LLM → 正反馈循环源 |
| `quality/fact_checker.py` | 与 CrossChapterChecker 重叠 |
| `quality/logic_consistency_check.py` | 规则过于复杂，精简到 CrossChapterChecker |
| `quality/data_reasonableness_check.py` | 与 NumericGuard 重叠 |
| `quality/date_anchor_check.py` | 通过 bind_fuzzy_dates 程序化修复 |
| `quality/valuation_arbitrator.py` | 在 Gate5（DCF 重算）中程序化解决 |
| `quality/assumption_checker.py` | LLM 检查假设 → 不确定性来源 |
| `quality/counter_validator.py` | LLM 对抗审查 → 正反馈循环源 |
| `quality/conclusion_validator.py` | LLM 审查结论 → 不确定性来源 |
| `quality/audit_validator.py` | 过度工程化 |
| `quality/roic_wacc_checker.py` | 与 NumericGuard 重叠 |
| `quality/config_validator.py` | 在 Gate0/2 中已覆盖 |
| `quality/review_integrator.py` | 死循环编排器 |
| `quality/debate_service.py` | LLM 辩论 → 已知卡死 |
| `quality/counter_validator.py` | LLM 对抗 → 正反馈循环 |

### D. 关键代码示例

#### D.1 Orchestrator 主流程

```python
# qual/host/orchestrator.py
class QualOrchestrator:
    """Qual 编排器（Gate0-8 调度）"""
    
    def run(self, ticker: str, company_name: str, market: str, 
            llm_caller: Callable | None = None) -> QualResult:
        """执行完整流程"""
        # 初始化上下文
        ctx = DataContextContract(
            ticker=ticker, company_name=company_name, market=market,
        )
        
        # 执行 Gate0-8
        gates = [
            Gate0DataSource(),
            Gate1TypeInference(),
            Gate2DataCollection(),
            Gate3ChapterWriting(llm_caller=llm_caller),
            Gate4ReviewRepair(),
            Gate5QualityEnhancement(llm_caller=llm_caller),
            Gate6Conclusion(llm_caller=llm_caller),
            Gate7ProblemTransformation(),
            Gate8FinalValidation(),
        ]
        
        gate_results = {}
        for gate in gates:
            result = gate.execute(ctx)
            gate_results[gate.spec.gate_num] = result
            
            if result.state == GateState.FAILED:
                # 关键 Gate 失败 → 阻断
                if gate.spec.gate_num in (0, 2, 8):
                    return QualResult(
                        success=False, chapters={},
                        errors=[f"Gate {gate.spec.gate_num} 失败: {result.errors}"],
                        gate_summary=gate_results,
                    )
                # 非关键 Gate 失败 → 降级继续
                logger.warning(f"Gate {gate.spec.gate_num} 失败，降级继续")
            
            # 更新上下文
            if result.chapters:
                ctx = ctx.with_chapters(result.chapters)
        
        # 组装报告
        report = self._assemble_report(ctx.chapters, ctx.company_name, ctx.ticker)
        
        return QualResult(
            success=True, chapters=ctx.chapters, report=report,
            gate_summary=gate_results,
        )
```

#### D.2 章节生成器

```python
# qual/write_pipeline/chapter_generator.py
class ChapterGenerator:
    """单章生成器（LLM 驱动 + 程序约束）"""
    
    def generate(self, chapter_num: int, ctx: DataContextContract,
                 llm_caller: Callable) -> str:
        """生成单个章节"""
        # 1. 构建 prompt（注入锚点数据）
        prompt = self.prompt_builder.build(chapter_num, ctx)
        
        # 2. LLM 生成
        raw_content = llm_caller("chapter_generation", prompt)
        
        # 3. PGNB 数字绑定
        content = self.numeric_binder.bind(raw_content, ctx.anchor)
        
        # 4. 占位符检测
        placeholders = self.placeholder_detector.check(content)
        if placeholders:
            # 单轮修复（不循环）
            fix_prompt = self.prompt_builder.build_fix_prompt(
                chapter_num, content, placeholders
            )
            fixed_content = llm_caller("chapter_fix", fix_prompt)
            content = self.numeric_binder.bind(fixed_content, ctx.anchor)
        
        return content
```

---

**文档版本**：v1.0  
**最后更新**：2026-08-22  
**作者**：Qual 架构重构团队
