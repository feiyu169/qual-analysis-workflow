# HGF 经验档案库（Lessons）

> V3.3.3（V2 记忆长效机制 L2）：详细踩坑与根因存档于此。
> 规则：**每个 .md 档案必须在本索引登记**（self_audit 检查器第 4 项强制，
> 防死文档）。新坑 → 新建档案 + 登记本索引 + 更新 pitfalls-registry.md。

## 档案索引

| 档案 | 日期 | 主题 | 关联 P# |
|------|------|------|---------|
| [2026-08-21-self-audit.md](2026-08-21-self-audit.md) | 2026-08-21 | HGF 自审查 3 个 P0 根因（failure_log 自锁 / baseline 损坏 / requirements 伪文件） | P53 |
| [2026-08-21-productivity-review.md](2026-08-21-productivity-review.md) | 2026-08-21 | HGF 生产力第三方评审（heavyskill K=8）：部分具备生产力，短板为自证闭环/门禁自锁/维护成本 | P53 |

## 沉淀流程

1. 踩坑 → 建档案 `<日期>-<主题>.md`（含现象/根因/修复/验证）
2. 在本索引登记一行
3. 更新 `../pitfalls-registry.md`（新 P# 或状态变更）
4. 若涉及核心操作流程变化 → 更新 `../../SKILL.md`（否则不更新，防膨胀）
5. 跑 `workflow_cli.py --lifecycle advance gate_5_3` 验证索引完整性
