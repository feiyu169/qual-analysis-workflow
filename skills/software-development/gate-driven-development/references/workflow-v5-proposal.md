# Workflow V5.0 Complete Proposal (Final)

## Overview

V5 is the final iteration of the Hermes Agent Workflow, reviewed by HeavySkill 4 times (V2→V3→V4→V5). Each iteration fixed issues found by the review. This proposal was implemented as **Hermes Gate Flow (HGF)** with 108 tests all passing.

## Key Design Decisions

1. **Safety guardrail for risk reduction** (P32): High-risk factors prevent downgrade
2. **Mixed change type support** (P34): Multiple types in single PR (CODE+CONFIG+IAC+DOCS)
3. **Change lines vs file lines**: Use git diff stats, not total file lines
4. **Pure non-code return**: DOCS/CONFIG/IAC skip level calculation
5. **English risk keys with mapping** (P31): Avoid language mismatch
6. **Fail-closed with emergency channel**: MCP down → reject unless emergency token

## Eight-Layer Design

| Layer | Trigger | Flow | Gates |
|-------|---------|------|-------|
| L0 | Hotfix | Quick→fix→verify→deploy | secret_scan |
| L1 | ≤3 files, ≤100 lines, low risk | Analysis→implement→verify | ruff+pytest+detect-secrets |
| L2 | ≤10 files, ≤500 lines, medium risk | Requirements→design→implement→verify | +semgrep+safety+integration |
| L3 | >10 files, >500 lines, high risk | Full lifecycle | +checkov+performance+DAST |
| L3_LITE | High risk + small change | Requirements→security→implement→verify | ruff+semgrep+detect-secrets+pytest |
| IAC | .tf/.tfvars files | Format→security→plan review | tflint+checkov+detect-secrets |
| CONFIG | .yaml/.json files | Format→secret scan→diff review | yamllint+detect-secrets |
| DOCS | .md files | Format→link check→spell check→secret scan | markdownlint+detect-secrets |

## Risk Assessment Architecture

```
affected_areas (file paths, description, labels, commit messages)
    ↓
risk_mapping (English→English, Chinese→English)
    ↓
risk_factors (English keys, weights 1-3)
    ↓
combination_rules (auth+payment → +3)
    ↓
safety_guardrail (high-risk factors → NO downgrade)
    ↓
risk_level (low/medium/high)
```

**Risk factors (English keys)**:
```python
risk_factors = {
    "security": 3, "auth": 3, "payment": 3, "crypto": 3,
    "database": 2, "migration": 3, "concurrency": 2,
    "external_api": 2, "third_party": 2, "config": 2,
    "breaking_change": 3, "core_algorithm": 3, "core": 3,
    "user_impact": 2, "performance": 2, "compliance": 2,
    "command_execution": 3, "injection": 3, "xss": 3,
}
```

**Safety guardrail** (P32):
```python
high_risk_factors = ["security", "auth", "payment", "crypto", "injection", "xss"]
has_high_risk = any(f in matched_factors for f in high_risk_factors)
if not has_high_risk:
    # Only apply reduction when NO high-risk factors present
    for keyword, reduction in reduction_rules.items():
        if keyword in description.lower():
            risk_score += reduction
```

## get_affected_areas Implementation

5 signal sources with file filtering:
1. File paths (last 2 directories)
2. Directory structure
3. Task description (Chinese + English keywords)
4. PR labels
5. Commit messages

**Filter patterns**: vendor/, node_modules/, tests/, .git/

## HeavySkill Review History

| Version | Issues Found | Key Fixes |
|---------|-------------|-----------|
| V2 | 6 | Risk assessment language mismatch, safety guardrail needed |
| V3 | 5 | Mixed change types, non-code flows, CI integration |
| V4 | 3 | Platform adaptation, fail-closed, emergency channel |
| V5 | All passed | Final implementation approved |

**Convergence signal**: V4→V5 had only minor issues, indicating design stability.

## Implementation Status

- GitHub: https://github.com/feiyu169/hermes-gate-flow
- Local: ~/.hermes/workflow/
- Tests: 108/108 passing
- Components: 11 Python files + 7 config files + 9 test files
