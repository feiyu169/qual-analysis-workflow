# v3组件集成模式参考（2026-08-02，Phase 1-3完整版）

## 集成概览

### Phase 1: 核心集成（5个组件，3762行）

| 组件 | 集成位置 | 功能 |
|------|----------|------|
| ModuleLoader | `run_analysis()`开头 | 启动自检 |
| ContentValidator | `_write_chapters()`断点恢复 | 内容质量验证 |
| ExceptionHandler | `_write_chapters()`异常处理 | 异常分级 |
| UnifiedValuation | `quality_enhancer.py` Stage 4 | DCF估值替代 |
| (语法修复) | workflow.py导入部分 | 修复try-except错误 |

### Phase 2: 数据一致性集成（9个组件，+697行）

| 组件 | 集成位置 | 功能 |
|------|----------|------|
| DataMappingRegistry | `_collect_data()` | 字段映射校验 |
| DataContext | 已广泛使用 | 统一数据访问 |
| DecisionAggregator | `_generate_decision_chapter()` | 判断聚合 |
| FactTable | Step 4.5b | 事实表构建 |
| ComparableConfig | Step 4.5b | 可比公司配置 |
| MarketData | Step 4.5b | 市场数据 |
| FlipThresholdCalculator | Step 4.5b | 翻转阈值 |
| InsightAuditor | Step 4.5b | 洞察审计 |
| ROICChecker | Step 4.5b | ROIC<WACC检查 |

### Phase 3: Skill增强+度量（3个组件，+208行）

| 组件 | 集成位置 | 功能 |
|------|----------|------|
| QualMetricsTracker | Step 4.5b末尾 | 10个核心指标跟踪 |
| 问题转化流程 | Step 7 | 自动检测可修复问题 |
| buy_side_report_review | Skill更新 | Qual工作流集成说明 |

## 完整集成地图（16个组件）

| 阶段 | 组件 | 集成位置 | 引用数 |
|------|------|----------|--------|
| Phase 1 | ModuleLoader | run_analysis()开头 | 6 |
| Phase 1 | ContentValidator | _write_chapters()断点恢复 | 5 |
| Phase 1 | ExceptionHandler | _write_chapters()异常处理 | 4 |
| Phase 1 | UnifiedValuation | quality_enhancer Stage 4 | 已集成 |
| Phase 2 | DataMappingRegistry | _collect_data()开头 | 6 |
| Phase 2 | DecisionAggregator | _generate_decision_chapter()末尾 | 7 |
| Phase 2 | FactTable | Step 4.5b | 7 |
| Phase 2 | ComparableConfig | Step 4.5b | 7 |
| Phase 2 | MarketData | Step 4.5b | 7 |
| Phase 2 | FlipThresholdCalculator | Step 4.5b | 7 |
| Phase 2 | InsightAuditor | Step 4.5b | 7 |
| Phase 2 | ROICChecker | Step 4.5b | 6 |
| Phase 3 | QualMetricsTracker | Step 4.5b末尾 | 7 |
| Phase 3 | 问题转化流程 | Step 7 | 7 |
| Phase 3 | buy_side_report_review | Skill更新 | — |
| Phase 3 | 10个核心指标 | metrics.py | — |

## 关键代码变更

### workflow.py（2662行）
- 导入部分：13个HAS_*标志（含HAS_DATA_MAPPING, HAS_DECISION_AGGREGATOR）
- `run_analysis()`：ModuleLoader启动自检
- `_collect_data()`：DataMappingRegistry校验
- `_write_chapters()`：ContentValidator+ExceptionHandler集成
- `_generate_decision_chapter()`：DecisionAggregator集成
- Step 4.5b：FactTable/ComparableConfig/MarketData/FlipThreshold/InsightAuditor/ROICChecker/QualMetricsTracker
- Step 7：问题转化流程（placeholder检测+币种混用检测）

### quality_enhancer.py（306行）
- Stage 4：UnifiedValuation替代valuation_engine
- DCF计算：CAPM WACC=8.1%, 永续增长率=2%

### metrics.py（220行）
- 10个核心指标定义（METRIC_DEFINITIONS）
- track_metric/get_summary/generate_report方法

## QualMetricsTracker 10个核心指标

| 指标 | 目标值 | 与缺陷关联性 |
|------|--------|--------------|
| gate_checks_execution_rate | 100% | 0.90 |
| review_integration_rate | 100% | 0.85 |
| placeholder_rate | 0% | 0.95 |
| default_value_warnings | 0% | 0.80 |
| dcf_scenario_difference | <20% | 0.75 |
| current_price_consistency | 100% | 0.90 |
| flip_threshold_direction_accuracy | 100% | 0.85 |
| insight_audit_score | 非100/100 | 0.70 |
| issue_recurrence_rate | <10% | 0.80 |
| report_timeliness | <30分钟 | 0.50 |

## Step 7问题转化流程

自动检测报告中的可修复问题：
- **placeholder检测**：`[Placeholder]`/`XX亿元` → P0
- **币种混用检测**：同时出现`港元`和`人民币` → P1

输出：`result["review_issues"]`列表，供buy_side_report_review skill使用

## 验证结果（2026-08-02）

| 测试项 | 结果 |
|--------|------|
| 语法检查 | ✅ 13个文件全部通过 |
| 组件导入 | ✅ 13个HAS_*全部为True |
| DCF估值 | ✅ 18.24元 |
| 端到端测试 | ✅ 全部组件功能正常 |
| 代码行数 | ✅ 4662行总计 |
| 问题转化 | ✅ placeholder检测正常 |
| 度量追踪 | ✅ 10个指标跟踪正常 |

## Phase 1→2→3执行模式

当需要集成多个v3组件到现有工作流时：

1. **Gate 0**: 读取所有待集成组件代码，确认集成方案
2. **Gate 1**: 逐个组件集成（修复语法→添加HAS_*→在关键代码点集成）
3. **Gate 2**: 端到端测试（组件导入+功能调用+DCF计算）
4. **Gate 3**: 功能完整性验证（语法检查+集成点统计）
5. **Gate 4**: 代码质量门禁（语法+导入+集成完整性）

**关键规则**：
- 每个组件独立try-except，一个失败不影响其他
- 所有降级只记录warning，不阻断主流程
- 集成后必须验证HAS_*标志全部为True
