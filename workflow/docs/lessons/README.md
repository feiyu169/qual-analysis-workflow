# HGF 经验档案库（Lessons）

> V3.3.3（V2 记忆长效机制 L2）：详细踩坑与根因存档于此。
> 规则：**每个 .md 档案必须在本索引登记**（self_audit 检查器第 4 项强制，
> 防死文档）。新坑 → 新建档案 + 登记本索引 + 更新 pitfalls-registry.md。

## 档案索引

| 档案 | 日期 | 主题 | 关联 P# |
|------|------|------|---------|
| [2026-08-21-self-audit.md](2026-08-21-self-audit.md) | 2026-08-21 | HGF 自审查 3 个 P0 根因（failure_log 自锁 / baseline 损坏 / requirements 伪文件） | P53 |
| [2026-08-21-productivity-review.md](2026-08-21-productivity-review.md) | 2026-08-21 | HGF 生产力第三方评审（heavyskill K=8）：部分具备生产力，短板为自证闭环/门禁自锁/维护成本 | P53 |
| [2026-08-21-v34-review.md](2026-08-21-v34-review.md) | 2026-08-21 | V3.4 方案架构+代码审查（K=8）：架构正确但代码 5 处 P0 缺陷（glob 匹配/伪签名/对照污染/空集合/非原子写） | P53 |
| [2026-08-21-heavyskill-mode2-truncation.md](2026-08-21-heavyskill-mode2-truncation.md) | 2026-08-21 | heavyskill 模式2 审查结果被截断：max_tokens 配置断裂 + finish_reason 不检查 + 思维链回退污染共识（已修复+9 单测） | P54 |
| [2026-08-21-heavyskill-p54-hgf-review.md](2026-08-21-heavyskill-p54-hgf-review.md) | 2026-08-21 | HGF 审查 P54 修复：裁决 FAIL——CLI 标志断裂/冒号守卫误杀/审议截断无保护（3×P1 实证），修复清单 R1-R7 | P54 |
| [2026-08-21-roi-benchmark.md](2026-08-21-roi-benchmark.md) | 2026-08-21 | ROI 对照实验：HGF 净拦截 2 缺陷（逃逸 2 vs 4），首次通过率 +50%；修复循环是实验必要组件 | P53 |
| [2026-08-22-invisible-tests-ruff-mask.md](2026-08-22-invisible-tests-ruff-mask.md) | 2026-08-22 | qual 隐形测试：27 文件长期不可收集（v3 路径断裂）被门禁掩盖；ruff --fix 静默删断裂 import；声称-现实漂移 | P55 |

## 沉淀流程

1. 踩坑 → 建档案 `<日期>-<主题>.md`（含现象/根因/修复/验证）
2. 在本索引登记一行
3. 更新 `../pitfalls-registry.md`（新 P# 或状态变更）
4. 若涉及核心操作流程变化 → 更新 `../../SKILL.md`（否则不更新，防膨胀）
5. 跑 `workflow_cli.py --lifecycle advance gate_5_3` 验证索引完整性
