# HGF 流程改进技术方案

**日期**: 2026-07-01
**背景**: 基于快手项目 HGF 执行复盘（评分 80/100, B+）

## 复盘发现的核心问题

| # | 问题 | 影响 | 根因 |
|---|------|------|------|
| 1 | Gate 1 和 Gate 5+6 的 P0 问题本应在设计阶段识别 | 返工成本高 | 缺少 Gate 0 预审 |
| 2 | Gate 2+3 的 72 分条件放行标准模糊 | 遗留问题未验证 | 评估标准不统一 |
| 3 | Gate 间缺乏依赖检查 | 跨 Gate 问题遗漏 | 无问题传递机制 |
| 4 | 人工评估主观性强 | 评分不一致 | 缺少自动化检查 |
| 5 | 修复后未回归验证 | 修复引入新问题 | 无回归测试流程 |

## 改进方案

### 1. Gate 0 设计预审（新增）

检查清单：
- A-01: 模块接口是否清晰（函数签名、docstring、类型注解）
- A-02: 数据流是否完整（输入来源、输出去向）
- A-03: 错误处理是否完善（try/except 覆盖率）
- T-01: 测试策略是否明确

### 2. 统一评估标准（改进）

| 决策 | 分数 | P0 | HIGH | 动作 |
|------|------|-----|------|------|
| 直接放行 | ≥80 | 0 | 0 | 无需修复 |
| 条件放行 | 60-79 | 0 | ≤2 | 下一 Gate 前修复+复验 |
| 不放行 | <60 | >0 | >2 | 修复后重新评估 |

### 3. Gate 间依赖检查（新增）

GateDependencyTracker:
- record_issues(gate_id, issues) — 记录问题
- record_resolution(gate_id, issue_id) — 记录修复
- check_prerequisites(gate_id) — 检查前序遗留
- generate_dependency_report() — 生成依赖报告

### 4. 自动化检查点（新增）

GateAutoChecker:
- check_syntax(file_path) — 语法检查
- check_imports(file_path) — 导入检查
- check_none_handling(file_path) — None 崩溃检查

### 5. 回归测试流程（新增）

GateRegressionTester:
- run_regression() — 运行回归测试
- verify_fix(issue_id, fix) — 验证修复不引入新问题

## HeavySkill 审查结论

8轨一致通过，预期首次通过率从67%提升到85%+。

补充建议：
- Gate 0 预审应为最高优先级
- 统一标准是低成本"止血"措施，应优先实施
- 回归测试依赖测试资产成熟度
- 需配套变革管理（团队培训）

## 实施状态

全部 5 个模块已实施并通过测试：
- gate0_reviewer.py ✅
- gate_evaluator.py ✅
- gate_dependency.py ✅
- gate_auto_check.py ✅
- gate_regression.py ✅
