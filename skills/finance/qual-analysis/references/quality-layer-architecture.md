# 质量层架构 (quality/ 包)

> 创建日期: 2026-07-01
> 状态: 已实施并通过独立评审

## 架构概述

质量层是独立于 workflow.py 的可复用包，位于 `~/.hermes/tools/finance/quality/`。

```
quality/
├── __init__.py              # 统一导出
├── types.py                 # QualityContext、量化输出类型
├── exceptions.py            # 异常体系（6个异常类）
├── budget.py                # BudgetController + CircuitBreaker
├── interfaces.py            # 4个ABC接口
├── formulas.py              # 标准化计算公式库
├── data_mapping.py          # 数据口径映射表
├── validators.py            # 自动校验机制
├── dcf.py                   # DCF估值模块
├── sensitivity.py           # 敏感性分析模块
├── risk_quantification.py   # 风险量化分析
├── margin_of_safety.py      # 安全边际分析
├── reasoning/
│   ├── causal_modeler.py    # 因果建模器（Granger+敏感性+模板）
│   ├── counter_validator.py # 反面论证验证器
│   ├── causal_inference.py  # 统一推理链（单链3阶段）
│   └── cold_start.py        # 冷启动策略
├── scoring/
│   ├── engine.py            # 评分引擎
│   ├── dimensions.py        # 5维度评分器
│   └── market_adjuster.py   # CN/HK Scorer
├── templates/
│   └── management_incentive.py  # 管理层激励分析模板
├── tests/
│   ├── test_integration.py  # 端到端测试
│   └── test_golden_set.py   # 黄金集测试
└── docs/
    └── data_mapping_spec.md # 数据口径规范文档
```

## 核心接口

```python
# 评分维度接口
class ScoreDimensionCalculator(ABC):
    def calculate(content, context) -> ScoreDimensionResult
    def get_max_score() -> float
    def get_weight() -> float      # 权重（0-1），与满分独立
    def get_dimension_id() -> str
    def explain() -> str

# 评分引擎接口
class ScoringEngine(ABC):
    def score(reasoning_result, context) -> ScoreReport
    def register_dimension(calculator) -> None

# 推理链接口
class ReasoningChain(ABC):
    def run(evidence, config, budget) -> ReasoningResult

# 冷启动策略接口
class ColdStartPolicy(ABC):
    def get_seed_data() -> EvidenceBundle
    def get_min_data_threshold() -> dict
    def get_fallback_output() -> ReasoningResult
    def is_cold_start(evidence) -> bool
```

## 评分权重

| 维度 | 权重 | 说明 |
|------|------|------|
| D1 数据完整性 | 20% | 数据源覆盖、时效性、交叉验证 |
| D2 逻辑一致性 | 25% | 因果链、数据距离、估值一致性 |
| D3 分析深度 | 25% | 维度覆盖、横纵对比、正反论证 |
| D4 结论可靠性 | 20% | 投资建议、催化剂、风险矩阵 |
| D5 可操作性 | 10% | 目标价、仓位、止损 |

## 证伪得分公式

```
falsification_score = 
    avg(counter_strengths) * 40 +   # 反方论点强度
    indicator_quality * 40 +         # 证伪指标可操作性
    has_monitoring_plan * 20         # 监控计划完整性
```

强制降级规则：
- 证伪 < 5分 → 强制D级
- 证伪 < 10分 → 降级到C级（仅S/A/B）

## 关键修复记录

| 编号 | 问题 | 修复 |
|------|------|------|
| P45 | get_weight() vs get_max_score() 混淆 | 接口添加get_weight()抽象方法 |
| P47 | 证伪得分丢失strength信息 | CounterResult添加counter_strengths字段 |
| P48 | ColdStartPolicy未集成 | CausalInferenceChain构造函数接受policy参数 |
| P53 | 增长率校验"实现但未接入" | validate_report()和_validate_data()添加增长率 |
| P54 | 情景分析缺少置信区间 | ScenarioAnalysisResult添加confidence_interval |
| P58 | CircuitBreaker HALF_OPEN无探测限制 | 添加half_open_max_probes参数 |
| P59 | BudgetController阈值硬编码 | 添加min_time_threshold/min_tokens_threshold |
| P62 | statsmodels依赖冲突 | 用scipy.stats.f.cdf实现F检验 |
| P60 | 中文标点导致SyntaxError | Python文件只使用ASCII字符 |

## 黄金集测试结果

```
万华化学(600309.SH): PE=17.18x, PB=1.99x, 市值=2148亿 ✅
快手(1024.HK): PE_GAAP=9.67x, PE_Adjusted=8.74x, 市值=1810亿 ✅
推理链: 置信度=0.30, 检查点通过=0/1 ✅
评分引擎: 得分=44.1, 等级=F, 证伪=88.0 ✅
```

## 实测发现的数据问题

| 问题 | 公司 | 影响 | 根因 |
|------|------|------|------|
| PB用总权益而非归母净资产 | 万华化学 | PB低估11% | 公式定义不清晰 |
| Non-IFRS vs 扣非口径混淆 | 快手 | PE偏差21% | 口径映射缺失 |
| 总股本单位错误(4.35→43.5亿) | 快手 | 市值差10倍 | 单位换算缺失 |
| 经营利润增速计算错误 | 快手 | 增速偏差7.9pp | 基期值错误 |
