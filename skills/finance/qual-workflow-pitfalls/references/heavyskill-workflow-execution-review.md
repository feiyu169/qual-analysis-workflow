# HeavySkill Workflow Execution Review Pattern

## Query Template for Financial Workflow Review

When auditing whether a financial workflow (qual, DCF, comps) executed correctly:

```
审查以下{workflow_name}流程执行记录，判断是否按流程执行：

执行记录：
- Step 1: {step_name} ✅/⚠️/❌ {status_detail}
- Step 2: ...
...

报告结果：
- 报告路径: {path}
- 报告行数: {lines}行
- 耗时: {seconds}秒

审查维度：
1. 流程完整性：是否所有步骤都执行了？
2. 流程正确性：每个步骤是否按规范执行？
3. 问题处理：发现问题后是否按流程修复？
4. 最终质量：报告质量是否达标？

请给出审查结论和改进建议。
```

## Execution Pattern
```bash
cd ~/.hermes/skills/heavyskill && timeout 200 python3 scripts/run_heavyskill.py \
  --query "审查内容" \
  --reason_k 8 --summary_k 4 --language cn \
  --output /tmp/heavyskill-flow-review.json
```

## Interpreting Results
- **Consensus answer** is the key output — all K trajectories must agree
- If verdict is "不合格", extract the specific failure points
- Common failure patterns:
  - Gate Checks skipped (module not found)
  - Review-repair loop exhausted without fixing issues
  - FCF=0 not triggering hard stop
  - Format validation passing but content validation failing

## Verified Example (2026-08-08)
Qual workflow v7.0 execution review for XPeng (9868.HK):
- 8/8 trajectories agreed: "不合格"
- Key failures: Step 4.6 Gate Checks skipped, Step 4.7 repair failed (170+ issues), Step 7 code error
- Consensus: "报告不可作为直接交付物，需经人工深度复核修正"

## 9-Dimension Review Architecture

### Step 4.7: Form Review (5 dimensions)
1. **Cross-chapter consistency** — Same data point referenced in different chapters must match
2. **Logic consistency** — Valuation model output must match narrative conclusions
3. **Data reasonableness** — Financial values must be within plausible ranges (e.g., revenue not 3-4x actual)
4. **Valuation arbitration** — Multiple valuation methods must converge within 100%
5. **Date anchor consistency** — Time references must be consistent across chapters

### Step 4.8: Substantive Review (4 dimensions)
1. **Fact checking** — Compare report data against Wind MCP actuals (tolerance <5%)
2. **Analysis depth** — LLM evaluates quantitative rigor per chapter (score 0-100)
3. **Conclusion reasonableness** — Investment rating must match analysis direction
4. **Assumption reasonableness** — WACC, terminal growth, margins must be within industry norms

### Review-Repair Loop
```
1. Execute review (all 9 dimensions)
2. Check if passed
3a. Passed → continue to Step 5
3b. Not passed → use LLM to fix issues
4. Re-review
5. Repeat until passed or max_rounds (3)
```

## Key Pitfall: Review Without Repair

**Symptom**: Review finds 166+ problems but report is still output without attempting fixes.

**Root cause**: Review and repair are separate; review results not passed to repair module.

**Fix**: Use `review_repair_loop.py` to implement review→fix→re-review cycle.

**User correction (2026-08-08)**: "qual流程应该是审查后自动修复，再审查" — this is a fundamental workflow design principle.
