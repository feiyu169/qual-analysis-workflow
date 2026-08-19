# Qual工作流质量保障框架 v3.2.2 — 完整技术方案摘要

**来源**: 2026-07-29 顺丰控股分析 + 5轮HeavySkill K=8审查  
**最终评分**: 87/100

---

## 15个核心模块

| 模块 | 功能 | 层 |
|------|------|-----|
| FeatureFlags | 模块开关(4种profile) | 基础设施 |
| ConfigValidator | 配置验证 | 基础设施 |
| DCFService | DCF服务(无状态) | 估值层 |
| CAPMCalculator | WACC计算(多因子) | 估值层 |
| TerminalValueCalculator | 终值计算(双轨) | 估值层 |
| TerminalValueArbitrator | 终值仲裁(四级阈值) | 估值层 |
| FCFCalculator | FCF计算(三层) | 估值层 |
| ComparableMatcher | 可比公司(五维度) | 估值层 |
| ROICWACCChecker | ROIC检查(四象限) | 估值层 |
| QualityPipeline | 质量流水线(4子步骤) | 质量层 |
| AuthorityResolver | 权威冲突解决(三模式) | 质量层 |
| YearAnchor | 年份锚点(3类) | 数据治理层 |
| FinancialStandards | 财务标准(口径定义) | 数据治理层 |
| WindFieldMapper | 字段映射(三市场) | 数据治理层 |
| AuditValidator | 审计验证(5种模式) | 审计层 |
| ConclusionSynthesizer | 结论综合(加权+否决) | 审计层 |

## v3/子包集成策略

```
quality/                          # 现有41文件(保留不动)
├── v3/                           # v3.2新增子包
│   ├── __init__.py               # try/except导入, 失败时降级
│   ├── feature_flags.py
│   ├── dcf_service.py
│   ├── capm_calculator.py
│   ├── terminal_value.py
│   ├── fcf_calculator.py
│   ├── comparable_matcher.py
│   ├── roic_wacc_checker.py
│   ├── year_anchor.py
│   ├── financial_standards.py
│   ├── field_mapping.py
│   ├── pipeline.py
│   ├── authority_resolver.py
│   ├── incremental_checker.py
│   ├── audit_validator.py
│   ├── conclusion_synthesizer.py
│   └── config/                   # 10个YAML配置文件
```

## 实施计划

| 阶段 | 内容 | 工时 |
|------|------|------|
| Phase 1 | v3/子包+FeatureFlags+ConfigValidator | 6h |
| Phase 2 | DCFService+CAPMCalculator+TerminalValue+Arbitrator | 14h |
| Phase 3 | QualityPipeline+AuthorityResolver+YearAnchor | 10h |
| Phase 4 | FCFCalculator+ROICChecker+敏感性 | 8h |
| Phase 5 | 数据治理层(FieldMapper+FinancialStandards) | 6h |
| Phase 6 | 审计层(AuditValidator+ConclusionSynthesizer) | 6h |
| Phase 7 | 集成测试+回归测试(84用例) | 6h |
| Phase 8 | workflow.py集成+文档 | 4h |
| **总计** | | **60h (约7.5天)** |
