# quality/_legacy — 死代码归档（HGF 遗留②，2026-08-22）

归档依据：`docs/qual-hgf-deep-check-2026-08-22.md` §七（HGF 检查发现 39 个未接线模块，
经全工作区引用扫描精确分类后，以下 6 个为**零外部引用**纯死代码）。

## 已归档模块与复活条件

| 模块 | 原职责 | 复活条件 |
|------|--------|---------|
| data_mapping.py | 数据映射工具 | 需要数据键映射时，应直接使用 `data_anchor.CANONICAL_ALIASES` |
| gate0_reviewer.py | Gate0 审查器 | qual_v8 gate0 需要独立审查层时 |
| gate_dependency.py | 闸门依赖管理 | qual_v8 gate_engine 需要依赖图时 |
| gate_regression.py | 闸门回归测试 | 需要闸门回归工具时（现有 gate_evaluator 已覆盖） |
| management_incentive.py | 管理层激励分析 | 买方分析需要激励维度时（未接入任何报告章节） |
| params_checker.py | 参数校验 | 与 config_validator 功能重叠，需要时用后者 |

## 归档纪律

- **不删除**（git 历史保留），仅移入 _legacy（HGF V3.2 死代码归档约定）
- 复活 = 从 _legacy 移回 quality/ 根 + 补充测试 + 接入业务（不允许无测试复活）
- 归档前验证：全工作区引用扫描确认零 import（含 v3 shim / tests / run 脚本）
- 被 feature_flags 字符串常量引用的模块（catalyst_calendar/margin_of_safety/
  risk_quantification）**未归档**——保留枚举语义，避免破坏 FeatureFlags 测试

## 验证

- `pytest tools/finance`：406 passed + 32 skipped（归档后零回归）
- `pytest tests/`（HGF 聚合）：248 passed + 17 skipped
