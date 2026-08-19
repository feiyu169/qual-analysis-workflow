# Two-Stage Review Pattern: delegate_task Expert + HeavySkill

> Verified: 2026-06-19 (Investment workflow V3→V4→V5)

## Problem

Single-stage HeavySkill review on pseudo-code often misses code-level issues:
- Concurrency safety (locks, race conditions)
- Type safety and boundary conditions
- Error handling completeness
- Implementation-specific bugs

## Solution: Two-Stage Review

### Stage 1: Independent Programming Expert (delegate_task)

Delegate to a leaf subagent with file access for **code-level review**:

```python
delegate_task(
    goal="你是资深 Python 架构师，请对技术方案进行全面代码审查...",
    context="方案路径: /tmp/spec.md\n审查重点: 并发安全、错误处理、边界条件",
    toolsets=["file"],
    role="leaf"
)
```

Expert reads the full spec and outputs structured P0/P1/P2 issues.

### Stage 2: HeavySkill Multi-Trajectory Review

After fixing all P0/P1 from Stage 1, run HeavySkill for **domain-level review**:

```bash
cd ~/.hermes/skills/heavyskill && python3 scripts/run_heavyskill.py \
  --query "请审查方案，从落地执行、代码质量、专业性 3 个维度..." \
  --include-file /tmp/spec-v2.md \
  --reason_k 6 --summary_k 3 --language cn \
  --output /tmp/review.json
```

HeavySkill often catches domain-specific issues the programming expert missed.

## When to Use

- Technical proposals with **real code** (not just architecture diagrams)
- Proposals that involve **concurrency, state management, error handling**
- When the proposal will be **implemented** (not just conceptual)

## When NOT to Use

- Pure architecture/design proposals (HeavySkill alone is sufficient)
- Simple tasks with no code-level complexity
- When the proposal is already in final form (no iteration planned)

## Example Results (2026-06-19 Investment Workflow)

| Stage | Input | Issues Found | Output |
|-------|-------|--------------|--------|
| Stage 1 (Expert) | V3 | 5 P0 + 7 P1 | V4 (all fixed) |
| Stage 2 (HeavySkill) | V4 | 3 new P0 | V5 (to be fixed) |

**Key insight**: Stage 1 catches implementation bugs, Stage 2 catches domain logic gaps.
The two stages are complementary, not redundant.

## Cost

- Stage 1: ~30s, ~100K tokens (delegate_task)
- Stage 2: ~100s, ~120K tokens (HeavySkill 6 trajectories)
- Total: ~130s, ~220K tokens

Compared to single-stage HeavySkill: ~100s, ~120K tokens
The extra 30s and 100K tokens are worth it for catching 5+ P0 issues that HeavySkill alone would miss.
