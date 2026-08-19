# Three-Expert Review Pattern

## Overview

A review pattern where the agent collaborates with two simulated experts (Programming Expert + Architecture Expert) to review proposals and implementations before execution.

## When to Use

- Major architectural decisions
- Security-critical changes
- Process/workflow design
- Any change affecting multiple components

## Pattern

```
Agent proposes plan
  ↓
Auto-submit to Programming Expert
  - Code quality review
  - Test coverage review
  - Error handling review
  ↓
Auto-submit to Architecture Expert
  - Design review
  - Scalability review
  - Security review
  - Observability review
  ↓
Both experts give verdict: PASS / PASS WITH NOTES / FAIL
  ↓
If PASS WITH NOTES: Agent evaluates notes, accepts or argues back
  ↓
If disagreement: Experts respond to Agent's counter-argument
  ↓
Consensus reached → Execute
  ↓
Post-execution: Both experts review results
```

## Expert Roles

**Programming Expert** focuses on:
- Code quality (readability, naming, structure)
- Test coverage and quality
- Error handling completeness
- Performance implications
- Dependency management

**Architecture Expert** focuses on:
- Module separation and boundaries
- Interface design
- Scalability and extensibility
- Security design
- Observability (logging, monitoring, alerting)
- Data model correctness

## Review Checklist Template

```yaml
review_checklist:
  code_quality:
    - "Functions have single responsibility"
    - "Error handling covers all failure modes"
    - "Test coverage ≥ 80%"
    - "No hardcoded values"
    - "Consistent naming conventions"
  
  architecture:
    - "Clear module boundaries"
    - "Dependency direction correct"
    - "Interface contracts defined"
    - "Security controls in place"
    - "Monitoring hooks present"
  
  security:
    - "Input validation present"
    - "Authentication/authorization correct"
    - "Sensitive data encrypted"
    - "No injection vulnerabilities"
    - "Audit logging enabled"
```

## HeavySkill Integration

For independent multi-trajectory review, use HeavySkill:

```bash
cd ~/.hermes/skills/heavyskill && python3 scripts/run_heavyskill.py \
  --query "Review this proposal from 6 dimensions: process effectiveness, code quality, architecture, security, feasibility, risk" \
  --include-file /path/to/proposal.md \
  --reason_k 6 --summary_k 3 --language cn
```

HeavySkill provides unbiased review from multiple reasoning trajectories.

## Key Rules

1. **Experts must review before execution** — no skipping
2. **Disagreements must be resolved** — Agent can argue back with evidence
3. **Review results are recorded** — for audit trail
4. **Post-execution review is mandatory** — verify implementation matches plan
