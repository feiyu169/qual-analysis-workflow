# Pitfall: HeavySkill Two-Round Review for Technical Documents (Verified 2026-06-29)

**Pattern**: When using HeavySkill to review technical documents, use a two-round review cycle:
1. Round 1: Review original document → produces findings
2. Fix all findings → produce v2 document
3. Round 2: Review v2 with explicit checklist of "did you fix all Round 1 findings?"

**Verified Case (2026-06-29)**:
- Round 1: 8/10 checks found issues (破坏性变更, 格式兼容, 误删风险, etc.)
- v2 fixes applied: 渐进式校验, 数据标准化, 软删除+备份, 配置开关
- Round 2: 8/8 checks passed, all Round 1 issues resolved

**Key Insight**: Single-round review misses the verification that fixes actually address findings. Two-round ensures closure.

**HeavySkill Parameters for Technical Doc Review**:
- `--reason_k 8 --summary_k 4 --language cn`
- Include checklist injection in query for domain-specific checks
- Use `--include-file` to pass the document being reviewed

**Checklist Injection Template**:
```
【审查原则】
1. 原架构稳定性：修改是否引入破坏性变更？
2. 功能实现：方案是否能真正解决所述问题？

【检查清单】
1. [架构稳定性] 具体检查项...
2. [功能实现] 具体检查项...
3. [风险评估] 回滚方案...
4. [完整性] 是否遗漏...
```

**Output Interpretation**:
- `consensus_answer` is the final verdict (look for "全部解决" or "需修改")
- Each trajectory in `reasoning.trajectories` has per-item verdicts
- `answer_frequencies` shows consensus strength (8/8 agreement = high confidence)
