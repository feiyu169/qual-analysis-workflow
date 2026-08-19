# 五阶段报告质量改进框架 — 实施记录

**日期**: 2026-07-01
**状态**: Gate 1-4 已实施，Gate 5-6 待实施
**快手验证**: DCF每股57.7元，目标价牛/基/熊=69.2/57.7/46.1，上行空间38.6%

## 已实施模块

### Gate 1: data_repair.py (L1 数据修复)

**文件**: `~/.hermes/tools/finance/data_repair.py` (~500行)

**功能**:
1. `validate_pe_against_wind()` — PE实时校验（报告PE vs Wind PE，偏差>15%标记失败）
2. `fix_pe_in_report()` — PE修复（保持原文格式：倍→倍，x→x）
3. `fix_source_annotations()` — 来源标注模板化（支持带/不带"来源："前缀）
4. `check_cross_chapter_consistency()` — 跨章节一致性审计（上下文感知+约数过滤+5%阈值）
5. `clean_ai_traces()` — AI痕迹清洗（正则匹配"好的，作为您的"等pattern）
6. `repair_report()` — 主修复流程（带try/except错误处理和回滚）

**独立专家评估**: 78/100 条件放行

**关键陷阱**:
- 一致性审计误报率75% → 上下文感知+约数过滤+5%阈值
- PE修复格式混用 → 保持原文格式
- 来源标注遗漏 → 增加无前缀pattern

### Gate 2: base_valuation.py (L1.5 基础估值)

**文件**: `~/.hermes/tools/finance/base_valuation.py` (~200行)

**功能**:
1. `compute_base_valuation()` — PE/PB/PS自动计算（Wind估值API+自动推导缺失倍数）
2. `BaseValuation.summary()` — 估值摘要格式化（供辩论使用）
3. 历史PE中枢估算（3年平均）
4. HKD/CNY汇率转换

**数据结构**:
```python
@dataclass
class BaseValuation:
    pe_ttm: Optional[float]
    pb: Optional[float]
    ps_ttm: Optional[float]
    market_cap: Optional[float]  # 亿港元
    net_profit: Optional[float]  # 亿人民币
    pe_history_avg: Optional[float]
    warnings: list[str]
```

**快手测试**: PE=21.3x, PB=3.2x, PS=2.5x, 市值=1789亿港元

### Gate 3: debate_coordinator.py (L2 辩论机制)

**文件**: `~/.hermes/tools/finance/debate_coordinator.py` (~350行)

**功能**:
1. `run_debate()` — 三角色辩论（Bull→Bear→PM）
2. Bull Prompt: 数据支撑+预期差+催化剂
3. Bear Prompt: 逐条质疑+替代估值+被忽略的风险
4. PM Prompt: 确信度构成(数据/逻辑/预期差)+触发条件(上行+下行)
5. 降级策略: Bull失败→单次生成, Bear失败→用Bull结果, PM失败→用Bull结果

**数据结构**:
```python
@dataclass
class DebateResult:
    bull_argument: str
    bear_argument: str
    pm_synthesis: str
    conviction_score: float  # 0-1
    conviction_breakdown: dict  # {data, logic, expectation_gap}
    catalysts: list[str]
    triggers: list[str]
    degraded: bool
```

**独立专家评估**: 72/100 条件放行

### Gate 4: valuation_engine.py (L3 完整估值)

**文件**: `~/.hermes/tools/finance/valuation_engine.py` (~500行)

**功能**:
1. `compute_dcf()` — DCF估值（FCF预测+终值+折现+敏感性矩阵）
2. `build_comparable_analysis()` — 可比公司分析（核心+补充+中位数）
3. `derive_target_prices()` — 目标价推导（牛/基准/熊三情景）
4. `compute_full_valuation()` — 主估值流程（带降级链: DCF→可比公司→PE倍数）
5. `format_valuation_for_report()` — 报告格式化

**数据结构**:
```python
@dataclass
class ValuationResult:
    dcf: Optional[DCFResult]
    comparable_companies: list[ComparableCompany]
    target_price_bull/base/bear: Optional[float]
    value_per_share: Optional[float]
    upside: Optional[float]
    degraded: bool
```

**快手测试结果**:
- DCF每股价值: 57.7元
- 目标价: 牛=69.2, 基=57.7, 熊=46.1
- 上行空间: 38.6%
- 敏感性矩阵: WACC(8-12%) × TG(1-5%) = 25组合

## 待实施模块

### Gate 5: L4 深度优化 (3天)
- 情景分析+敏感性矩阵
- 结论翻转阈值标注
- 对比分析: YoY/环比/趋势偏离
- 洞察深度审计

### Gate 6: 集成+测试 (7天)
- pipeline.py 集成（AnalysisContext + 新Stage）
- ReportAssembler 扩展
- 单元测试 + 集成测试
- 端到端验证（快手案例重跑）
