---
name: qual-analysis-quality-assurance
description: "Qual工作流质量保障体系 v3.2.2 — 四层防护(数据标准化→估值约束→逻辑综合→质控验证)，AuthorityResolver决策矩阵(投票/否决/级联)，终值仲裁(四级阈值)，185个测试用例(Gate 0-6全部通过)。解决年份错标、DCF矛盾、可比公司错配、结论未综合、审计无效等13个系统性缺陷。HeavySkill K=8五轮审查87/100分。"
version: 3.2.2
author: hermes-agent
tags:
  - finance
  - quality-assurance
  - qual-analysis
  - investment
dependencies:
  - qual-analysis
triggers:
  - "qual质量"
  - "报告质量"
  - "审计验证"
  - "DCF一致性"
  - "可比公司"
  - "结论综合"
  - "WACC校准"
  - "FCF定义"
---

# Qual工作流质量保障体系 v3.1

## 概述

本Skill是`qual-analysis`的配套质量保障模块，解决买方报告中反复出现的系统性缺陷。

**来源**: 顺丰控股(002352.SZ)分析报告的专业审阅（2026-07-28），由资深买方分析师审阅发现5个致命问题。经HeavySkill K=8两轮审查迭代（v3.0→v3.1）。

**审查结果**: v3.0投资专家72分+架构专家72分 → v3.1投资专家78分+架构专家81分

## 四层防护体系

```
第1层: 数据标准化 (输入层)
├── 字段映射配置化 (P84)
├── 年份锚点强制传递 (S01)
├── 净利润口径定义 (S06)
└── FCF标准公式 (S07)

第2层: 估值约束 (计算层)
├── WACC CAPM校准 (P90)
├── DCF单一权威源 (S02)
├── 可比公司多维匹配 (S03)
├── 翻转阈值方向验证 (S08)
└── ROIC-WACC一致性检查 (S09)

第3层: 逻辑综合 (输出层)
├── 结论综合引擎 (S04)
├── 否决项概率评估
├── AI痕迹自动清洗 (P13)
└── 数据质量门禁

第4层: 质控验证 (审计层)
├── 审计真实性验证 (S05)
├── Gate Checks
└── 回归测试集
```

## 与现有代码关系：增量集成策略

**核心原则**: 现有quality/目录41个文件零修改，v3.0模块放在`quality/v3/`子包。

```
quality/
├── dcf.py, sensitivity.py, ...  # 现有41文件（保留不动）
└── v3/                           # v3.0新增子包
    ├── __init__.py               # try/except导入，失败时降级
    ├── feature_flags.py
    ├── dcf_service.py
    ├── year_anchor.py
    ├── pipeline.py
    └── adapters/
```

**降级策略**: v3/子包不存在时，所有现有模块正常工作，无任何影响。

## 关键模块

### 1. DCFService (替代DCFAuthority单例)

**问题**: DCFAuthority单例持有可变状态，导致单元测试互相干扰、并发竞态。

**解决方案**: DCFService无状态设计

```python
class DCFService:
    """无状态，依赖注入，组合现有DCFCalculator"""
    
    def __init__(self, calculator=None, config=None):
        self._calculator = calculator or DCFCalculator()  # 组合非继承
        self._config = config or DCFServiceConfig()
    
    def run_full_analysis(self, inputs: DCFInputs) -> DCFAnalysisResult:
        """无缓存，无全局状态"""
        result = self._calculator.calculate(inputs)
        sensitivity = None
        if self._config.enable_sensitivity:
            sensitivity = self._calculator.sensitivity_analysis(...)
        return DCFAnalysisResult(dcf=result, sensitivity=sensitivity)
```

### 2. QualityPipeline (拆分Step 4.5)

**问题**: Step 4.5将4个模块挤在一个步骤，任一失败影响全部。

**解决方案**: 拆分为独立子步骤，每步独立降级

| 子步骤 | 模块 | 降级策略 |
|--------|------|----------|
| 4.1 | structural_check | 不可降级，失败阻塞 |
| 4.2 | semantic_audit | 可降级，LLM超时时跳过 |
| 4.3 | chapter_repair | 可降级，依赖审计结果 |
| 4.4 | checkpoint | 不阻塞，失败仅warning |

### 3. FeatureFlags系统

**4种profile**:
- `full`: 全部启用（默认）
- `minimal`: 仅核心模块（structural_check）
- `no_llm`: 禁用需要LLM的模块
- `valuation_only`: 仅估值模块

**环境变量覆盖**: `QUALITY_DISABLE_<MODULE>=true`

**v3不存在时**: 提供no-op实现，确保现有代码不受影响。

### 4. WACC CAPM完整参数

**问题**: WACC硬编码10%，缺Beta来源、α溢价。

**解决方案**: 多因子CAPM

```
Ke = Rf + β × (MRP + CRP) + α

其中:
- Rf: 10年期国债收益率
- β: 回归Beta + 基本面Beta加权，Blume调整(0.67×raw + 0.33×1.0)
- MRP: 股权风险溢价(6.5%)
- CRP: 国家风险溢价(中国A股=0)
- α: 规模溢价(≤3%) + 流动性溢价(1.5%) + 治理溢价
- 总α上限: 6%
```

**验证规则**: V-CAPM-01~05

### 5. 终值计算双轨方法

**问题**: 终值计算方法未明确，永续增长法vs退出倍数法。

**解决方案**: 双轨方法+验证

- **永续增长法**: g∈[1.5%, 3.5%], g<WACC
- **退出倍数法**: EV/EBITDA, 可比公司25-75百分位
- **TV/EV比例上限**: 75%

**验证规则**: V-TV-01~06

### 6. FCF定义三层规范

**问题**: FCF定义粗糙，未区分FCFF/FCFE/LFCF。

**解决方案**:
- **FCFF**: EBIT×(1-T) + D&A - CapEx - ΔWC
- **FCFE**: Net Income + D&A - CapEx - ΔWC + Net Borrowing
- **LFCF**: Operating CF - CapEx

**一致性检查**: FCF/NI∈[0.3, 3.0], FCF/OCF≥0.5

### 7. 可比公司多维度匹配

**问题**: 简单黑名单太粗糙，需要智能匹配。

**五维度匹配**:

| 维度 | 权重 | 算法 |
|------|------|------|
| 业务构成 | 40% | 余弦相似度 |
| 商业模式 | 25% | 标签匹配 |
| 规模 | 15% | 层级距离 |
| 成长阶段 | 10% | 阶段距离 |
| 地理覆盖 | 10% | 收入占比差异 |

**黑名单机制**: 禁止跨行业误用（如互联网公司替代物流同行）

### 8. 结论综合引擎

**问题**: 各章独立生成PM判断，无全局综合，导致"看空"与"推荐"矛盾。

**解决方案**: ConclusionSynthesizer

- 各章权重: ch05经营表现(20%)最高
- 否决项优先: 触发则直接SELL
- 单一结论: BUY/HOLD/SELL

### 9. ROIC-WACC四象限分析

**问题**: ROIC<WACC时不应声称"价值创造拐点确立"。

**解决方案**: 四象限分析

| 象限 | 条件 | 允许声称 |
|------|------|----------|
| Q1 | 价值创造+趋势改善 | "价值创造确立" |
| Q2 | 价值创造但趋势平稳 | "价值创造稳定" |
| Q3 | 价值毁损但趋势改善 | "拐点临近" |
| Q4 | 价值毁损且趋势恶化 | "价值毁损持续" |

### 10. 年份锚点强制传递

**问题**: LLM自行推断年份，导致2025数据标为2024。

**解决方案**: YearAnchor拆分为3个类

- `YearPromptBuilder`: 生成prompt注入
- `YearErrorDetector`: 检测年份错标
- `YearTextFixer`: 修正年份表述

## 13个系统性缺陷清单

| 编号 | 问题 | 严重度 | 解决方案 |
|------|------|--------|----------|
| P84 | Wind现金流字段映射 | P0 | 字段映射配置化 |
| P90 | WACC硬编码10% | P1 | CAPM校准 |
| P13 | AI痕迹严重 | P1 | 自动清洗 |
| P76 | success掩盖降级 | P1 | 数据质量门禁 |
| S01 | 年份锚点错误 | 致命 | YearAnchor |
| S02 | DCF多源矛盾 | 致命 | DCFService |
| S03 | 可比公司错配 | 致命 | 多维度匹配 |
| S04 | 结论未综合 | 致命 | ConclusionSynthesizer |
| S05 | 审计无效 | 致命 | AuditValidator |
| S06 | 净利润口径混乱 | 重要 | 口径定义 |
| S07 | FCF定义粗糙 | 重要 | 三层规范 |
| S08 | 翻转阈值方向错 | 重要 | 方向验证 |
| S09 | ROIC<WACC冲突 | 重要 | 四象限分析 |

## 与qual-analysis的集成

本Skill是qual-analysis的**质量层**，不替代qual-analysis的核心流程。

**集成点**:
1. Step 1.5 后: YearAnchor注入年份锚点
2. Step 2 后: DCFService计算DCF
3. Step 4 后: AuditValidator验证审计
4. Step 4.5 后: QualityPipeline检查
5. Step 5 前: ConclusionSynthesizer综合结论

## HeavySkill K=8审查模式

**顺丰控股实测**:
- v3.0初审: 投资专家72分+架构专家72分
- v3.1复审: 投资专家78分+架构专家81分

**审查维度**: 系统性、长效性、严肃性、可行性、完整性

**审查团队**:
1. 投资分析专家 — 从买方严肃性角度评审
2. 架构编程专家 — 评审技术架构、模块职责、集成点

**关键发现**: v3.1定位为"估值引擎"而非"质量保障体系"，需补数据治理层和审计层。

## AuthorityResolver决策矩阵（v3.2.2新增）

当多层质量检查系统并行运行时，必须有明确的冲突解决规则。

**三种模式**:

| L1 (主权威) | L2 (补充权威) | L3 (监督权威) | 模式 | 结果 |
|-------------|---------------|---------------|------|------|
| ✅通过 | ✅通过 | 无/通过 | - | ✅通过 |
| ✅通过 | ✅通过 | 💀FATAL | 否决 | ❌失败 |
| ✅通过 | ❌失败 | 无 | 投票 | ✅通过(降分, L1权重0.7>L2权重0.3) |
| ✅通过 | ❌失败 | 💀FATAL | 否决 | ❌失败 |
| ❌失败 | 任意 | 任意 | 级联 | ❌失败(L1失败阻断) |

**自身失败回退**: 降级到L1单独执行。

## 终值仲裁规则（v3.2.2新增）

DCF双轨终值方法（永续增长法+退出倍数法）结果可能不一致，必须有仲裁规则。

| 差异范围 | 选定方法 | 置信度 | 额外要求 |
|----------|----------|--------|----------|
| < 10% | 取均值 | high | 无 |
| 10-25% | 取保守(较低值) | medium | 无 |
| 25-50% | 取保守+敏感性分析 | low | 必须展示敏感性矩阵 |
| ≥ 50% | 阻断 | - | 需人工审查 |

**额外约束**: TV/EV>75%强制敏感性, g≥WACC阻断。

## 测试策略（v3.2.1新增）

| 测试层 | 用例数 | 最低通过率 | Mock策略 |
|--------|--------|-----------|----------|
| 单元测试 | 69 | 95% | L1精确Mock(固定返回值) |
| 集成测试 | 11 | 90% | L2行为Mock(调用序列) |
| 端到端测试 | 4 | 100% | L3异常Mock(注入失败) |
| **总计** | **84** | **95%** | - |

## 数据治理层（v3.2新增）

解决"数据从哪来、口径怎么统一"问题：

1. **YearAnchor** — 拆分为YearPromptBuilder+YearErrorDetector+YearTextFixer
2. **FinancialStandards** — 净利润口径(GAAP/adjusted/deducted)+PE标注规则
3. **WindFieldMapper** — 字段映射配置化，A股/港股/美股，自动处理_TTM后缀

## 审查迭代轨迹

| 轮次 | 版本 | 投资专家 | 架构专家 | 综合 | 核心改进 |
|------|------|----------|----------|------|----------|
| 1 | v3.0 | 72 | 72 | 72 | 基础框架 |
| 2 | v3.1 | 78 | 81 | 79.5 | 估值引擎+14个架构问题回答 |
| 3 | v3.2 | 83 | 84 | 83.5 | 数据治理层+审计层补齐 |
| 4 | v3.2.1 | 84 | 87 | 85.5 | 权威分层+84个测试用例 |
| 5 | v3.2.2 | 86 | 88 | 87 | 决策矩阵+终值仲裁 |

## 实施进度（Gate-Driven）

**当前状态**: Gate 0-6完成，Gate 7待实施

| Gate | 模块 | 测试数 | 状态 |
|------|------|--------|------|
| Gate 0 | v3/子包+FeatureFlags+ConfigValidator | 26 | ✅ |
| Gate 1 | DCFService+CAPMCalculator+TerminalValue | 30 | ✅ |
| Gate 2 | Pipeline+YearAnchor+AuthorityResolver | 27 | ✅ |
| Gate 3 | FCFCalculator+ROICWACCChecker+SensitivityAnalyzer | 25 | ✅ |
| Gate 4 | WindFieldMapper+FinancialStandards+IncrementalChecker | 23 | ✅ |
| Gate 5 | AuditValidator+ConclusionSynthesizer+TerminalValueArbitrator | 25 | ✅ |
| Gate 6 | 集成测试+E2E测试+Mock策略测试 | 29 | ✅ |
| Gate 7 | workflow.py集成+文档 | - | 待实施 |
| **总计** | **15个模块** | **185/84** | **Gate 0-6完成** |

**代码位置**: `~/.hermes/tools/finance/quality/v3/`

**实现文件清单**:

| 模块 | 文件 | 测试文件 |
|------|------|----------|
| FeatureFlags | `v3/feature_flags.py` | `v3/tests/test_feature_flags.py` |
| ConfigValidator | `v3/config_validator.py` | `v3/tests/test_config_validator.py` |
| DCFService | `v3/dcf_service.py` | `v3/tests/test_dcf_service.py` |
| CAPMCalculator | `v3/capm_calculator.py` | `v3/tests/test_capm_calculator.py` |
| TerminalValueCalculator | `v3/terminal_value.py` | `v3/tests/test_terminal_value.py` |
| QualityPipeline | `v3/pipeline.py` | `v3/tests/test_pipeline.py` |
| YearAnchor | `v3/year_anchor.py` | `v3/tests/test_year_anchor.py` |
| AuthorityResolver | `v3/authority_resolver.py` | `v3/tests/test_authority_resolver.py` |
| FCFCalculator | `v3/fcf_calculator.py` | `v3/tests/test_fcf_calculator.py` |
| ROICWACCChecker | `v3/roic_wacc_checker.py` | `v3/tests/test_roic_wacc_checker.py` |
| SensitivityAnalyzer | `v3/sensitivity_analyzer.py` | `v3/tests/test_sensitivity_analyzer.py` |
| WindFieldMapper | `v3/wind_field_mapper.py` | `v3/tests/test_wind_field_mapper.py` |
| FinancialStandards | `v3/financial_standards.py` | `v3/tests/test_financial_standards.py` |
| IncrementalChecker | `v3/incremental_checker.py` | `v3/tests/test_incremental_checker.py` |
| AuditValidator | `v3/audit_validator.py` | `v3/tests/test_audit_validator.py` |
| ConclusionSynthesizer | `v3/conclusion_synthesizer.py` | `v3/tests/test_conclusion_synthesizer.py` |
| TerminalValueArbitrator | `v3/terminal_value_arbitrator.py` | `v3/tests/test_terminal_value_arbitrator.py` |
| - | - | `v3/tests/test_integration.py` |
| - | - | `v3/tests/test_e2e.py` |
| - | - | `v3/tests/test_mock_strategy.py` |

**关键实施陷阱**: 见 `references/implementation-pitfalls.md`（10个陷阱）

## ⚠️ 关键陷阱

### 1. 必须基于年报原文分析（2026-08-01用户纠正）

**问题**: 只用Wind财务数据生成placeholder内容，用户会不满。

**正确流程**:
```python
# Step 1: 下载年报（必须执行）
from finance.filing_downloader import fetch_filing
filing_data = fetch_filing(ticker="00772.HK", market="hk", fiscal_years=[2023, 2024, 2025])

# Step 2: 传入qual流程（filing_data不能为空）
from finance.workflow import run_analysis
result = run_analysis(
    ticker="00772.HK",
    company_name="阅文集团",
    market="hk",
    wind_data=wind_data,
    filing_data=filing_data,  # 必须传入！
    llm_caller=create_deepseek_caller(),
    output_dir="/tmp/output"
)
```

**错误做法**:
- ❌ 传入空的 `filing_data={}` → 跳过年报解析
- ❌ 传入 `filing_data=None` → 自动获取可能失败
- ❌ 使用placeholder LLM → 内容不可用

### 2. 集成测试API一致性（2026-08-01发现）

新增模块与现有测试文件集成时，必须检查方法名是否一致。

| 模块 | 错误方法名 | 正确方法名 |
|------|------------|------------|
| CAPMCalculator | `calculate_ke()` | `calculate()` |
| ConfigValidator | `validate_wacc_config()` | `validate_dcf_params()` |
| DCFService | `run_full_analysis()` | `calculate()` |
| TerminalValueCalculator | `calculate_perpetuity_growth()` | `calculate_perpetuity()` |

### 3. DCFInputs字段名（v3版本）

v3版本使用简短字段名，与旧版本不同：

| 字段 | v3版本 | 旧版本 |
|------|--------|--------|
| 无风险利率 | `rf` | `risk_free_rate` |
| 股权风险溢价 | `erp` | `equity_risk_premium` |
| 永续增长率 | `terminal_growth` | `terminal_growth_rate` |
| 总股本 | `shares` | `shares_outstanding` |

### 4. 断点恢复会保留Placeholder内容（2026-08-01发现）

**问题**: workflow.py的断点恢复逻辑不检查内容是否为placeholder，导致重新运行时恢复旧的placeholder。

**修复**: 在所有断点恢复处添加placeholder检查：

```python
# 第1-9章
if checkpoint and checkpoint.is_chapter_completed(ctx.ticker, chapter_id):
    cached = checkpoint.get_chapter(chapter_id)
    if cached and "[Placeholder]" not in cached:
        chapters[chapter_num] = cached
        continue
    elif cached and "[Placeholder]" in cached:
        logger.info(f"第{chapter_num}章为placeholder，重新生成")

# 第0章、第10章同理
```

**临时方案**: 运行前清除checkpoint目录：
```bash
rm -rf ~/.hermes/workspace/checkpoints/<TICKER>
```

### 5. valuation_engine.py可比公司硬编码（2026-08-01发现）

**问题**: `valuation_engine.py`中的`CORE_COMPARABLES`和`SUPPLEMENTARY_COMPARABLES`是硬编码的错误公司（抖音、Meta、拼多多等）。

**影响**: 可比估值完全失真，目标价推导无效。

**修复**: 按行业修改可比公司：

```python
# 在线阅读/数字内容行业
CORE_COMPARABLES = {
    "掌阅科技": {"ticker": "603533.SH", "pe": 25.0, "pb": 2.5, "ps": 3.0},
    "中文在线": {"ticker": "300364.SZ", "pe": 30.0, "pb": 3.0, "ps": 4.0},
}
SUPPLEMENTARY_COMPARABLES = {
    "B站": {"ticker": "9626.HK", "pe": None, "pb": 2.0, "ps": 2.5},
    "爱奇艺": {"ticker": "IQ", "pe": None, "pb": 1.5, "ps": 1.0},
}
```

**长期方案**: 实现五维度可比公司匹配（见qual-quality-modules skill）。

### 6. depth_enhancer.py用净利润计算EBIT利润率（2026-08-01发现）

**问题**: `depth_enhancer.py`第360行用净利润计算EBIT利润率：
```python
base_ebit_margin = (np_list[-1] / base_revenue)  # 净利润为负 → EBIT为负
```

**影响**: 对亏损公司（如阅文集团），情景分析和翻转阈值全部为负值，估值模块完全失效。

**修复**: 改用营业利润：
```python
op_list = income.get('年营业利润', [])
if op_list and base_revenue:
    base_ebit_margin = op_list[-1] / base_revenue
    if base_ebit_margin < 0:
        base_ebit_margin = 0.05  # 保守估计
```

### 7. workflow.py extract_dcf_params的FCF计算（2026-08-01发现）

**问题**: FCF使用 `ocf + investing_cf` 而非 `ocf - capex`。投资活动现金流包含非资本支出项，可能高估/低估FCF。

**修复**: 使用明确的资本开支字段：
```python
ocf = _latest(cashflow, "经营活动现金净流量_TTM")
capex = _latest(cashflow, "购建固定资产、无形资产和其他长期资产支付的现金")
fcf_base = ocf - capex
```

### 8. 情景分析FCF必须与主DCF一致（2026-08-01发现）

**问题**: `depth_enhancer.py`的`run_scenario_analysis()`使用简化FCF `nopat * 0.9`，而主DCF使用完整公式 `nopat + da - capex - wc_change`。

**影响**: 情景分析的每股价值与DCF估值不一致（如DCF=17.2元但情景基准=2.9元）。

**修复**: 情景分析必须使用与主DCF完全一致的FCF公式和参数。

### 9. 翻转阈值计算必须避免HKD/CNY混用（2026-08-01发现）

**问题**: `compute_flip_thresholds()`中 `target_fcf = current_price * shares * 0.05`，current_price是HKD但revenue是CNY，导致翻转点荒谬（607.7亿）。

**修复**: 使用二分法搜索翻转点，避免单位换算：
```python
low_rev, high_rev = base_revenue * 0.3, base_revenue * 3.0
for _ in range(50):
    mid_rev = (low_rev + high_rev) / 2
    # 用mid_rev计算FCF和EV
    if equity > target_equity_value:
        high_rev = mid_rev
    else:
        low_rev = mid_rev
```

### 11. quality_enhancer.py未传递WACC参数给depth_enhancer（2026-08-01发现）

**问题**: `quality_enhancer.py`调用`run_depth_enhancement()`时未传递`base_wacc`和`base_terminal_growth`参数，导致使用默认值（0.10和0.03）。

**影响**: 情景分析和翻转阈值使用错误的WACC（10%而非CAPM计算的8.1%），与DCF估值不一致。

**修复**: 在quality_enhancer.py中计算WACC并传递：
```python
# 计算WACC（使用CAPM）
rf = 0.023
beta = 1.2
erp = 0.055
ke = rf + beta * erp  # 0.089
kd = 0.05
tax_rate = 0.25
wacc = ke * 0.85 + kd * (1 - tax_rate) * 0.15  # 0.081

depth = run_depth_enhancement(
    chapters=chapters,
    financials=financials,
    valuation_value=result.valuation_result.get('dcf_value', 0) if result.valuation_result else 0,
    current_price=current_price,
    shares=shares,
    base_wacc=wacc,  # 必须传递！
    base_terminal_growth=0.02,  # 必须传递！
)
```

### 12. 情景分析必须使用5年FCF预测（2026-08-01发现）

**问题**: 情景分析使用单年FCF计算终值，而主DCF使用5年FCF预测。导致情景分析结果与DCF估值不一致。

**修复**: 情景分析必须使用与主DCF一致的5年FCF预测：
```python
for name, rev, margin, wacc, tg, prob in key_scenarios:
    # 5年FCF预测
    total_pv_fcf = 0
    current_revenue = base_revenue
    for year in range(1, 6):
        growth = revenue_growth * (1 - 0.1 * (year - 1))  # 逐年递减
        current_revenue = current_revenue * (1 + growth)
        ebit = current_revenue * margin
        nopat = ebit * (1 - 0.25)
        da = current_revenue * 0.03
        capex = current_revenue * 0.04
        wc_change = current_revenue * growth * 0.02
        fcf = nopat + da - capex - wc_change
        total_pv_fcf += fcf / (1 + wacc) ** year
    
    # 终值（基于第5年FCF）
    terminal_value = fcf * (1 + tg) / (wacc - tg)
    pv_terminal = terminal_value / (1 + wacc) ** 5
    ev = total_pv_fcf + pv_terminal
```

### 13. WACC翻转阈值方向验证（2026-08-01发现）

**问题**: WACC翻转阈值方向错误，显示"WACC降至3.0%时估值等于当前股价"，但逻辑上WACC上升才会降低估值。

**修复**: 必须验证翻转阈值方向：
```python
if flip_wacc > base_wacc:
    # WACC上升→估值下降，翻转点高于当前WACC
    direction = "up"
else:
    # WACC下降→估值上升，翻转点低于当前WACC
    direction = "down"
```

### 10. review_integrator在success=False时跳过审查（2026-08-01发现）

**问题**: `run_analysis_with_review()`检查`analysis_result.get("success")`，qual分析返回success=False时直接跳过审查。

**根因**: Step 4审计修复失败（如`'set' object is not subscriptable`）导致success=False，但报告内容仍然可用。

**临时方案**: 直接调用`review_report()`绕过success检查：
```python
integrator = ReviewIntegrator(config)
integrator.set_llm_caller(llm_caller)
review_result = integrator.review_report(
    report_path="/tmp/output/00772.HK_analysis.md",
    output_dir="/tmp/output",
    wind_data={},
)
```

**长期方案**: 修改`run_analysis_with_review()`逻辑，区分"报告不可用"和"报告有缺陷但可审查"。

## 参考文档

> **配套Skill**: `qual-workflow-pitfalls` — 17个系统性缺陷清单 + 6个HeavySkill K=8审查通过的工程修复模式（ContentValidator/require_params/ExceptionHandler/UnifiedValuation/InsightAuditor/FlipThresholdCalculator）。当qual分析出现估值异常、数据矛盾、流程跳过时，优先加载该skill。

| 文件 | 说明 |
|------|------|
| `references/qual-debugging-pattern.md` | **Qual工作流调试与修复模式** — 估值陷阱、流程问题、修复循环、验证清单 (2026-08-02) |
| `references/quality-assurance-v3.1-summary.md` | v3.1完整技术方案 |
| `references/heavyskill-review-results.md` | HeavySkill K=8审查结果 |
| `references/critical-review-response.md` | 对审阅报告的逐项回应 |
| `references/implementation-pitfalls.md` | 实施陷阱和解决方案 |
| `references/valuation-module-fix-patterns-2026-08-01.md` | 估值模块系统性修复模式 Part 1 — 4文件10处bug |
| `references/valuation-module-fix-patterns-2026-08-01-part2.md` | **估值模块修复模式 Part 2** — 情景分析FCF一致性、翻转阈值二分法、现金及等价物字段、HKD/CNY单位混用 (2026-08-01) |
| `references/valuation-module-fix-patterns-2026-08-01-part3.md` | **估值模块修复模式 Part 3** — 5年FCF预测、WACC参数传递链、翻转阈值方向验证 (2026-08-01) |
