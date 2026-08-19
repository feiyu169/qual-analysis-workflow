# HGF V5 Optimization Patterns

## Core Principle: "先做减法再做加法" (First subtract, then add)

When optimizing workflows, always start by removing unnecessary steps before adding new ones.

**Evidence**: V2 added features → architecture score 5/10. V3 applied subtraction → architecture score 9/10.

## Layered Independent Review Mechanism

Independent review is THE quality guarantee mechanism. NEVER weaken it during optimization. Use risk-based layering:

```yaml
review_levels:
  level_1:  # Low risk (lite mode)
    name: "Automated Gate"
    content: [existence, syntax, basic static analysis (ruff)]
    time: "2-5 min"
    reviewer: "Gate auto-validation"
  
  level_2:  # Medium risk (full mode)
    name: "Light Independent Review"
    content: [7-step checklist, stage1 review gate, key module spot check]
    time: "30min-1h"
    reviewer: "Gate + expert spot check"
  
  level_3:  # High risk (critical projects)
    name: "Deep Independent Review"
    content: [HeavySkill K=8, expert line-by-line review, 3-person team]
    time: "4-8h"
    reviewer: "Independent expert + HeavySkill"
```

## Mandatory Deep Review Triggers

Must trigger level 3 when ANY condition is met:
- Checklist score < 11/14
- Security-sensitive functions (auth, encryption)
- Financial data processing
- Architecture changes (module split, interface change)
- User explicit request

## 7-Step Checklist (Objective Scoring)

Replace subjective reviews with objective 0/1/2 scoring:

| Step | Question | 2pts | 1pt | 0pts |
|------|----------|------|-----|------|
| 1 | Requirements clear? | Stakeholder confirmed | Doc complete, unconfirmed | Vague/missing |
| 2 | Risks identified? | Full matrix | Main risks only | Not identified |
| 3 | Minimal design? | YAGNI followed | Slight redundancy | Over-engineered |
| 4 | Test coverage? | 100% key paths | >80% | <80% |
| 5 | Docs complete? | API docs correct | Basic docs | Missing |
| 6 | Security boundaries? | Rules + validation | Basic rules | Vague |
| 7 | Rollback possible? | Script tested | Plan exists | No plan |

**Total**: 14 points. **Threshold**: 11/14 (78.6%) to pass. Below → trigger HeavySkill review.

## Evidence Association Mechanism

Subjective checklist items require evidence links:
- Requirements → Jira issue link (status: confirmed)
- Risk → Structured YAML risk matrix file
- Security → SECURITY.md file exists
- Rollback → rollback.sh with execute permission

## Key Lesson: Independent Review Weakening (CRITICAL)

**NEVER** weaken independent review when optimizing workflows.

**The V5 design flaw**:
- Removed HeavySkill K=8 from Phase 1 → quality dropped
- Replaced expert review with auto-validation only → missed deep issues
- Architecture score dropped from 9/10 to 5/10

**Correct approach**: Keep expert involvement at key decision points:
1. Stage 1 Review Gate → expert confirmation (15 min sync)
2. Stage 2 key modules → expert spot check (per risk level)
3. Stage 3 delivery → expert sign-off

## Feasibility Assessment for Major Changes

For any major workflow change, perform 8-dimension feasibility assessment:
1. Technical feasibility
2. Organizational feasibility
3. Risk feasibility
4. Timeline feasibility
5. Cost feasibility
6. Compatibility
7. Maintainability
8. Extensibility

Use HeavySkill K=4 for quick assessment, K=8 for final review.

## Iterative Review Pattern

1. Submit V1 → HeavySkill K=8 review → collect all trajectory opinions
2. Revise based on consensus → submit V2 → re-review
3. Repeat until convergence (typically 3-6 rounds)

**Key lessons**:
- Each round's feedback MUST be addressed in the next version
- Prioritize: architecture > interfaces > implementation details
- Avoid over-design: each round should simplify, not add complexity
- Interface contracts must be complete (signatures + types + exceptions)

## User Preferences (Verified 2026-07-04)

- Extremely detailed + zero tolerance for deception
- Must respond in Chinese
- Technical solutions must strictly follow documentation
- New feature evaluation: workflow → pain point mapping → solution → HeavySkill 3-dimension review → revision → re-review
- Major workflow changes require 8-dimension feasibility assessment
- Iterative strategy: K=4 for quick iteration + K=8 for final review
- Quantitative metrics must be falsifiable
