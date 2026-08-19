# Qual分析质量保障体系架构 (v3.2.2, 2026-07-29验证)

## 四层防护体系

```
第1层: 数据标准化
├── 字段映射配置化 (WindFieldMapper)
├── 年份锚点强制传递 (YearPromptBuilder+YearErrorDetector+YearTextFixer)
├── 净利润口径定义 (FinancialStandards)
└── FCF标准公式 (FCFF/FCFE/LFCF三层)

第2层: 估值约束
├── WACC CAPM校准 (多因子+Alpha分项+Blume调整)
├── DCF单一权威源 (DCFService, 无状态)
├── 可比公司多维度匹配 (五维度: 业务40%+模式25%+规模15%+成长10%+地理10%)
├── 终值仲裁 (四级差异阈值)
└── ROIC-WACC四象限分析

第3层: 逻辑综合
├── 结论综合引擎 (各章权重+否决项优先+单一结论)
├── 否决项概率评估
├── AI痕迹自动清洗
└── 数据质量门禁

第4层: 质控验证
├── 审计真实性验证 (5种已知问题模式)
├── Gate Checks
└── 回归测试集 (84个用例, 95%通过率)
```

## 关键模块

| 模块 | 功能 | 设计原则 |
|------|------|----------|
| DCFService | DCF计算服务 | 无状态+依赖注入+组合DCFCalculator |
| AuthorityResolver | 权威冲突解决 | 投票/否决/级联三种模式 |
| TerminalValueArbitrator | 终值仲裁 | 四级差异阈值+保守优先 |
| QualityPipeline | 质量流水线 | 4子步骤独立降级 |
| ConclusionSynthesizer | 结论综合 | 权重加权+否决项优先 |

## 集成策略

- **v3/子包**: 现有41个文件零修改
- **try/except导入**: 失败时降级到no-op
- **FeatureFlags**: 4种profile(full/minimal/no_llm/valuation_only)

## 详细设计文档

- `/tmp/qual-workflow-quality-assurance-v3.2-complete.md` — 完整版
- `/tmp/qual-workflow-quality-assurance-v3.2.1-patch.md` — 权威分层+测试策略
- `/tmp/qual-workflow-quality-assurance-v3.2.2-patch.md` — 决策矩阵+终值仲裁
