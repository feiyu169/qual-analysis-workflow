# Iterative HeavySkill Review Workflow

Verified pattern from P1 fix plan review (2026-06-29).

## Workflow

```
v1 Plan → HeavySkill Review → Revise → v2 Plan → HeavySkill Re-Review → Execute
```

## Step-by-Step

### 1. Write v1 Technical Document
- Include all fix plans with code snippets
- Include verification criteria
- Include execution order

### 2. First HeavySkill Review (K=8)
```bash
cd ~/.hermes/skills/heavyskill && python3 scripts/run_heavyskill.py \
  --query "你是架构稳定性审查专家。审查这份技术文档，重点关注：
  1. 原架构稳定性：修改是否引入破坏性变更？
  2. 功能实现：方案是否能真正解决所述问题？
  [注入检查清单 5-10 项]" \
  --include-file /tmp/plan-v1.md \
  --reason_k 8 --summary_k 4 --language cn \
  --output /tmp/review-v1.json
```

### 3. Parse Review Results
Extract from JSON:
- `consensus_answer`: Overall conclusion
- `reasoning.trajectories`: Individual review findings
- Look for: "需修改", "不通过", "通过"

### 4. Revise to v2
Address ALL findings from v1 review:
- Add missing rollback plans
- Add missing dependency verification
- Change breaking changes to gradual deprecation
- Add safety mechanisms (backup, soft-delete, config switches)

### 5. Second HeavySkill Review (K=8)
```bash
cd ~/.hermes/skills/heavyskill && python3 scripts/run_heavyskill.py \
  --query "这是经过第一轮审查后的修订版（v2版）。
  第一轮审查发现的问题：[列出7类问题]
  请逐项审查，判断v2是否解决了第一轮发现的问题。" \
  --include-file /tmp/plan-v2.md \
  --reason_k 8 --summary_k 4 --language cn \
  --output /tmp/review-v2.json
```

### 6. Verify v2 Passes
All check items should show "✅ 已解决". If any show "需修改", iterate to v3.

## Pitfalls

- **v1 review always finds issues**: This is expected. The value of HeavySkill is in finding issues before execution, not in passing first time.
- **Consensus answer may be truncated**: Full conclusions are in `reasoning.trajectories`. Parse those for detailed findings.
- **K=8 is sufficient for review**: K=16 has stability issues and is overkill for plan review.
- **Include file path must be absolute**: Use `/tmp/plan.md` not `./plan.md`

## Example Review Findings (v1 → v2)

| v1 Finding | v2 Fix |
|------------|--------|
| 破坏性变更 (raise ValueError) | 渐进式 (DeprecationWarning + 降级) |
| 数据格式兼容风险 | normalize_financial_data 函数 |
| 误删风险 | 软删除 + 备份 + 人工确认 |
| 缺失回滚方案 | 每项增加回滚步骤 |
| 缺失前置依赖 | Phase 0 验证清单 |
| Wind 能力未验证 | 前置验证 + 风险登记表 |
| 异常保护不足 | try-except + 错误报告 |
