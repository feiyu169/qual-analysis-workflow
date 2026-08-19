# Workflow vs Gate-Driven: Comparison Guide

## When to Use Which

| Criterion | Gate-Driven | Workflow |
|-----------|-------------|----------|
| Project size | 3+ components | Any size |
| Team size | Multi-person | Solo or team |
| Risk level | High | Any |
| Timeline | Weeks+ | Hours to weeks |
| Automation | Manual trigger | Auto-trigger |

## Gate-Driven (Large Projects)

Best for: infrastructure, multi-skill systems, security-critical code.

Flow: Phase 0→1→2→3→4 with strict entry/exit criteria per gate.

Key discipline: every gate must pass real-data verification before proceeding.

## Workflow (All Projects)

Best for: daily development, bug fixes, feature additions, mixed workloads.

Flow: L1 (small) → L2 (medium) → L3 (large), automatically classified.

Key discipline: automatic task classification + risk assessment determines flow strictness.

## Task Classification

```python
def classify_task(file_count, line_count, risk_factors):
    risk_score = sum(risk_factors.values())  # security=3, db=2, config=1
    
    if file_count <= 3 and line_count <= 100 and risk_score < 3:
        return "L1"  # Simplified: implement + verify
    elif file_count <= 10 and line_count <= 500 and risk_score < 5:
        return "L2"  # Standard: requirements + design + implement + verify
    else:
        return "L3"  # Full: all gates + expert review
```

## L1 Flow (Small Tasks)
- Implement
- Verify (automated)

## L2 Flow (Medium Tasks)
- Requirements
- Design
- Implement (TDD)
- Verify

## L3 Flow (Large Tasks)
- Requirements + Security
- Design + Threat Modeling
- Implement (TDD + SAST)
- Expert Review
- Integration Test + DAST
- Deploy + Monitor

## Risk Assessment

High risk factors (force upgrade to stricter level):
- Security changes (auth, encryption, permissions)
- Database schema changes
- Payment/financial logic
- External API integrations

Medium risk factors:
- Configuration changes
- Performance-sensitive code
- Third-party dependencies

## Hybrid Approach

For mixed projects, use Workflow for daily tasks but Gate-Driven for:
- Architecture decisions
- Security-critical changes
- Database migrations
- Deployment pipelines

The Gate Manager from Gate-Driven can be used within Workflow's L3 flow.
