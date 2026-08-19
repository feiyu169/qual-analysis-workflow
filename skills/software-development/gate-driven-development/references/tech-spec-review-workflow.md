# Technical Spec Review Workflow (Verified 2026-06-10)

## Overview

A 4-layer iterative review pattern for major technical proposals. Produces production-ready specs through expert panel → HeavySkill → user review cycles.

## Workflow

```
Layer 1: Parallel Expert Review
  delegate_task(tasks=[programming_expert, architecture_expert])
  → Synthesis into unified P0/P1/P2 table

Layer 2: HeavySkill Multi-Trajectory Review
  --reason_k 6 --summary_k 3 --language cn
  → Verdict: 通过 / 附意见通过 / 不通过
  → Extract conditions (通过条件)

Layer 3: User Review
  Present findings + conditions to user
  User provides own technical feedback (often catches practical issues)

Layer 4: Revision + Re-review
  Merge all findings → produce v2
  Re-run HeavySkill to verify fixes and catch regressions
  → v2.1 (fix HeavySkill conditions) → v2.2 (fix user feedback)
```

## Real Example: Hermes P0 Technical Spec

| Version | Review | Findings | Result |
|---------|--------|----------|--------|
| v1 | Expert panel (2 parallel) | 6 P0, 17 P1 | Synthesis table |
| v1 | HeavySkill (6 trajectories) | 5 new findings | "附意见通过" with 3 conditions |
| v2 | HeavySkill re-review | All P0 fixed, 3 new conditions | "附意见通过" |
| v2.1 | Apply conditions | C1/C2/C3 | Ready for implementation |
| v2.2 | User's own review | 6 more issues (error_code bug, schedule parsing, classify empty, cron bootstrap, config hardcode, time estimate) | 35h revised plan |

## Key Learnings

1. **User review catches what experts miss**: Python version deprecations (utcnow), library availability (croniter), empty function bodies, hard-coded configs. Experts focus on architecture; users focus on "will this actually run."

2. **HeavySkill conditions must be explicitly tracked**: "附意见通过" comes with specific conditions. Each condition must be addressed in the next revision and verified.

3. **consensus_answer is unreliable**: Always parse trajectories, not consensus_answer.

4. **Revision numbering matters**: v1 → v2 (expert+HeavySkill) → v2.1 (HeavySkill conditions) → v2.2 (user feedback). Each revision has a clear trigger.

5. **Token budget**: ~110K tokens per HeavySkill round on 40KB docs. Budget 2-3 rounds for critical specs.

## When to Use

- New system architecture proposals
- Major refactoring plans
- Security-critical design changes
- Any proposal where "getting it wrong" costs > 1 day of rework

## When NOT to Use

- Simple bug fixes
- Single-file changes
- Well-understood patterns with existing templates
