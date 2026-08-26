---
name: heavyskill
description: Multi-trajectory reasoning engine for complex problems — technical review, algorithm design, multi-step deduction. Uses K parallel reasoning paths + deliberation for high-quality analysis.
tags: [reasoning, review, analysis, architecture]
---

# HeavySkill — Multi-Trajectory Reasoning Engine

HeavySkill is a multi-trajectory reasoning engine for complex problems. Use when the user's query requires deep logical reasoning, mathematical problem-solving, algorithm design, or multi-step deduction that benefits from exploring multiple solution paths in parallel.

## When to Use

- Complex reasoning problems with multiple valid approaches
- Mathematical proofs or competition problems
- Algorithm design requiring exploration of trade-offs
- Logic puzzles with deceptive complexity
- Multi-step deduction chains
- **Technical proposal review with checklist injection** (see `references/checklist-injection-guide.md`)

## Checklist Injection for Code Review

When using HeavySkill for code/technical review, inject domain-specific checklists into the query to improve discovery rate from 71% to 86%.

**Key rule**: Single-stage injection > Two-stage injection (verified: 86% vs 60%).

See `references/checklist-injection-guide.md` for complete guide.

## K Value Selection

| K | Cost | Time | Quality | Use Case |
|---|------|------|---------|----------|
| 4 | 1x | 1x | Baseline | Quick review |
| 8 | 2x | 2x | Better | **Standard (recommended)** |
| 16 | 4x | 4x | Best | Critical review |

K=8 recommended per HeavySkill paper. K=16 has stability issues.

## CRITICAL PITFALL: Sub-agents Cannot Read Local Files

HeavySkill spawns LLM sub-agents that **have no access to local files**. If you pass a file path like `/tmp/plan.md` in the query, the sub-agents will say "I cannot read the file" and produce a generic review based only on the checklist — wasting tokens and producing low-quality results.

**Fix**: Inline all relevant content directly into the `--query` string:
- Document text (or key sections)
- Code snippets under review
- Data samples, schemas, field names
- Specific questions about the content

Bad: `--query "审查 /tmp/plan.md 的可用性"`
Good: `--query "审查以下方案的可用性：\n\n[方案全文或关键段落]\n\n代码片段：\n[code]\n\n检查清单：..."`

## Usage

### Step 1: Detect Problem Type

If the user's question matches the triggers above, invoke HeavySkill.

### Step 2: Prepare Query Content

**Inline all relevant material** into the query string. Do NOT reference file paths alone.
Include: document content, code snippets, data samples, schemas, and the checklist.

### Step 3: Execute Pipeline

```bash
cd ~/.hermes/skills/heavyskill && timeout 180 python3 scripts/run_heavyskill.py \
  --query "问题描述" \
  --reason_k 8 --summary_k 4 --language cn \
  --output /tmp/heavyskill-output.json
```

**Query optimization for technical document review** (verified 2026-06-30):
- HeavySkill subagents CANNOT read local files — they will do generic analysis
- Solution: inline the document's KEY content in the query (data contracts, code snippets, decision rationale)
- For multi-round review: list specific changes made between rounds so the reviewer can focus on delta
- Pattern: `v1审查发现X个问题，v2修订内容：1. ... 2. ... 请审查是否已解决`

## ⚠️ Pitfall: K=8 Default Timeout Kills the Run (verified 2026-07-04)

**Problem**: K=8 with default terminal timeout (60s) WILL timeout. Measured timings:
- Stage 1 (parallel reasoning, K=4): ~53s
- Stage 2 (deliberation): ~41s
- Total: ~94s — exceeds 60s default

**Fix**: Always set explicit timeout=200 on the terminal call:
```bash
# WRONG — times out at 60s
cd ~/.hermes/skills/heavyskill && python3 scripts/run_heavyskill.py --reason_k 8 ...

# CORRECT — explicit timeout
cd ~/.hermes/skills/heavyskill && timeout 180 python3 scripts/run_heavyskill.py --reason_k 8 ...
```

**Alternative**: Use K=4 with summary_k=2 for faster results (~94s, sufficient for most reviews):
```bash
cd ~/.hermes/skills/heavyskill && timeout 180 python3 scripts/run_heavyskill.py \
  --query "审查内容" \
  --include-file /tmp/document.md \
  --reason_k 4 --summary_k 2 --language cn \
  --output /tmp/heavyskill-review.json
```

## ⚠️ Pitfall: Truncated Review Outputs (P54, fixed 2026-08-21)

**Problem**: Review results were frequently truncated — `max_tokens` defaulted to 4096 and
`config.yaml` budgets were never loaded by the CLI (config loading gap). Reasoning models
(v4-pro) count thinking tokens against `max_tokens`, so visible output gets cut; `finish_reason`
was never checked, so truncated trajectories silently fed deliberation/consensus; and
`extract_answer` grabbed thinking/sentence fragments as answers, corrupting the consensus.

**Fix (already in code)**:
- `config.yaml` now controls budgets and is actually loaded: `max_tokens: 32768` (reasoning),
  `summary_max_tokens: 16384` (deliberation, independent budget). CLI overrides:
  `--max-tokens`, `--summary-max-tokens`.
- Truncated trajectories (`finish_reason=length`) are automatically **excluded from deliberation
  and consensus** (kept in JSON `reasoning.trajectories` for inspection); thinking-fallback
  trajectories (empty `content`) no longer vote in consensus.
- Output JSON adds a **`truncation` summary field**:
  `{reasoning_truncated_count, content_fallback_count, deliberation_truncated}`.
- Console prints a ⚠️ WARNING whenever truncation occurred.

**How to read review results (don't read the whole 100KB+ JSON, don't trust the console summary)**:
```python
import json
d = json.load(open("heavyskill-output.json", encoding="utf-8"))
print(d["truncation"])   # must be all 0/False before trusting the result
print(d["deliberation"][0]["deliberation_response"])  # full synthesis
```
If `truncation` is non-zero: re-run with larger `--summary-max-tokens` / `--max-tokens`,
or explicitly mark the partial result as accepted.

## Chinese Technical Review Dimensions Template

When user asks to review a technical document with dimensions like "有效性提升、架构简洁、代码质量", use this query pattern:

```
--query "请审查以下技术文档，从三个维度进行评估：1. 有效性提升：建议是否真正能提升目标系统的有效性？2. 架构简洁：建议是否会使架构更简洁？3. 代码质量：建议是否能提升代码质量？请给出具体评分和改进建议。"
```

Standard Chinese tech review dimensions (use when user says "审查" without specifying):
- **有效性提升** (Effectiveness): 方案是否真正解决问题？数据流是否正确？预期效果是否有量化？
- **架构简洁** (Architecture Simplicity): 模块是否最少？边界是否清晰？是否存在内容重复？
- **代码质量** (Code Quality): 错误处理、类型注解、可测试性、是否有可执行示例代码

These map to the existing English dimensions:
- 可用性 → 有效性提升
- 架构稳定性 → 架构简洁
- (code quality is universal)

### Step 4: Review and Iterate

Review the output. If issues found, iterate until clean.

**Standard review-iterate cycle** (user expectation):
1. Create document/plan
2. Run HeavySkill review (K=8)
3. Extract issues from review
4. Revise document to address issues
5. Run HeavySkill again to verify fixes
6. Repeat until clean

**Standard review dimensions** (when user says "审查"):
- 可用性: 方案是否能真正解决问题？代码能否运行？数据流是否正确？
- 架构稳定性: 修改是否破坏现有功能？是否有回滚方案？是否向后兼容？

## Iterative Review Pattern (Verified 2026-07-01)

When reviewing technical proposals that need multiple rounds of refinement:

1. **Submit v1** → HeavySkill K=8 review → collect all trajectory opinions
2. **Revise based on consensus** → submit v2 → re-review
3. **Repeat until convergence** — typically 3-6 rounds

**Key lessons from v1.0→v6.0 iteration:**
- Each round's feedback MUST be addressed in the next version
- Prioritize by severity: architecture > interfaces > implementation details
- Avoid over-design: each round should simplify, not add complexity
- Interface contracts must be complete (signatures + types + exceptions)
- Real-world testing is the final validation — cannot skip

**Review dimensions for technical proposals:**
1. Architecture simplicity — minimal modules, clear boundaries
2. Code quality — error handling, type annotations, testability
3. Domain feasibility — can the proposed methods actually work?
4. Standards compliance — backward compatible, rollback capable

## Mode Selection (4 runnable forms, enhanced 2026-08-21)

| Form | Mechanism | Needs | When |
|------|-----------|-------|------|
| **Mode 1** subagent template | K parallel DSH subagents + in-context deliberation | none | content already in session, no API key, fast iteration |
| **Mode 2-basic** | K parallel LLM calls + sequential deliberation | DEEPSEEK_API_KEY | batch, JSON output, regular reviews (K=8 ≈ 85K tokens) |
| **Mode 2-enhanced** | basic + quality_score ranking + auto-k + **mimo validator & independent second review** | + XIAOMI_TOKEN_PLAN_CN_API_KEY | critical gates / architecture reviews needing an independent model's view |
| **Mode 2-chunked** | split large content (>18K chars) into chunks, review each, meta-deliberate | DEEPSEEK_API_KEY | large proposals/code — avoids the 20K inline truncation |

Decision tree: content already in session / no key → Mode 1; content > 18K chars → Mode 2-chunked;
critical verdict → Mode 2-enhanced (`--enable-validator --enable-second-review [--auto-k]`,
fails open to basic when the mimo key is missing); otherwise Mode 2-basic.
See `references/enhancement-plan-dual-model.md` for the full design and CLI switches.

## References

- `references/checklist-injection-guide.md` — Checklist injection technique for code review
- `references/financial-technical-review-pattern.md` — Pattern for reviewing financial technical proposals (query template, dimensions, consensus extraction)
- `references/gate-check-design-patterns.md` — Gate Check/PoW design patterns for financial workflows (architecture, thresholds, exception grading)
