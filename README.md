# Qual Analysis Workflow

AI投资分析质量保证框架 - 基于qual分析流程的结构化投资分析工具

## 概述

本项目实现了一个完整的买方投资分析质量保证框架，包含：

- 标准化计算公式（PE/PB/ROE/增速）
- 数据口径映射（净利润/净资产/股本/PE四种口径）
- 自动校验（PE/PB/市值/增长率）
- DCF 估值模块
- 敏感性分析
- SOTP 分部估值
- 压力测试
- 推理引擎（因果建模+反面论证）
- 评分引擎（5维度加权+证伪得分）

## 核心模块

### 估值模块

| 模块 | 文件 | 功能 |
|------|------|------|
| 标准化公式 | `quality/formulas.py` | PE/PB/ROE/增速计算 |
| DCF 估值 | `quality/dcf.py` | 现金流折现估值 |
| SOTP 分部估值 | `quality/sotp_valuation.py` | 多业务分部独立估值 |
| 敏感性分析 | `quality/sensitivity.py` | 单变量/双变量/情景分析 |
| 安全边际 | `quality/margin_of_safety.py` | 安全边际计算 |

### 数据验证模块

| 模块 | 文件 | 功能 |
|------|------|------|
| 数据口径映射 | `quality/data_mapping.py` | GAAP/adjusted/core/deducted |
| 自动校验 | `quality/validators.py` | PE/PB/市值/增长率校验 |
| 结构化预检 | `quality/structural_check.py` | 章节格式检查 |

### 风险分析模块

| 模块 | 文件 | 功能 |
|------|------|------|
| 压力测试 | `quality/stress_test.py` | 收入/利润率/现金流压力测试 |
| 风险量化 | `quality/risk_quantification.py` | 风险识别和量化 |

### 评分引擎

| 模块 | 文件 | 功能 |
|------|------|------|
| 评分引擎 | `quality/scoring/engine.py` | 5维度加权评分 |
| 评分维度 | `quality/scoring/dimensions.py` | 估值/数据/深度/风险/逻辑 |
| 推理引擎 | `quality/reasoning/causal_inference.py` | 因果建模+反面论证 |

## 快速开始

```python
from quality.formulas import Formulas
from quality.sotp_valuation import compute_sotp_valuation, BusinessSegment
from quality.stress_test import run_stress_test

# PE 计算
pe = Formulas.pe_ratio(market_cap=1000, net_income=50, net_income_type="GAAP")
print(f"PE: {pe.value:.1f}x")

# SOTP 分部估值
segments = [
    BusinessSegment(name="直播", revenue=100, comparable_multiple=3.0),
    BusinessSegment(name="电商", revenue=50, comparable_multiple=5.0),
]
sotp = compute_sotp_valuation(segments=segments, shares=10)
print(f"SOTP 每股价值: {sotp.value_per_share:.2f}元")

# 压力测试
stress = run_stress_test(
    base_revenue=100,
    base_net_income=10,
    base_fcf=15,
)
print(f"最坏情景: {stress.worst_case.scenario.name}")
```

## 测试

```bash
# 运行所有测试
python3 -m pytest quality/tests/ -v

# 运行 SOTP 测试
python3 -m pytest quality/tests/test_sotp_valuation.py -v

# 运行压力测试
python3 -m pytest quality/tests/test_stress_test.py -v
```

## 目录结构

```
qual-analysis-workflow/
├── quality/
│   ├── __init__.py
│   ├── formulas.py              # 标准化计算公式
│   ├── validators.py            # 自动校验
│   ├── dcf.py                   # DCF 估值
│   ├── sotp_valuation.py        # SOTP 分部估值
│   ├── sensitivity.py           # 敏感性分析
│   ├── stress_test.py           # 压力测试
│   ├── data_mapping.py          # 数据口径映射
│   ├── structural_check.py      # 结构化预检
│   ├── checkpoint.py            # 断点恢复
│   ├── auditor.py               # 审计模块
│   ├── repairer.py              # 修复模块
│   ├── scoring/
│   │   ├── engine.py            # 评分引擎
│   │   ├── dimensions.py        # 评分维度
│   │   └── market_adjuster.py   # 市场调整
│   ├── reasoning/
│   │   ├── causal_inference.py  # 因果推理
│   │   ├── causal_modeler.py    # 因果建模
│   │   ├── counter_validator.py # 反面论证
│   │   └── cold_start.py        # 冷启动策略
│   └── tests/
│       ├── test_sotp_valuation.py
│       ├── test_stress_test.py
│       ├── test_golden_set.py
│       └── test_integration.py
└── README.md
```

## 版本历史

- **v2.0** - 新增 SOTP 分部估值、压力测试、留存率/LTV/CAC
- **v1.0** - 初始版本，包含基础估值和校验模块

## License

MIT
