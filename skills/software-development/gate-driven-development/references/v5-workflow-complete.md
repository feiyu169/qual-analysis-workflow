# V5 Gate-Driven Workflow — Complete Reference

## Evolution History

| Version | Key Change | HeavySkill Finding |
|---------|-----------|-------------------|
| V2 | Initial gate-driven + review panels | Flow too heavy for small tasks |
| V3 | Auto task classification + risk assessment | Risk factors Chinese/English mismatch |
| V4 | English keys + mapping tables + multi-signal | Risk reduction vulnerability |
| V5 | Safety guards + mixed types + incremental coverage | All critical issues resolved |

## Eight-Layer Design

```
L0: Emergency Hotfix     → critical_path_test + secret_scan + security_scan
L1: Small Task (≤3 files, ≤100 lines, low risk)
L2: Medium Task (≤10 files, ≤500 lines, medium risk)
L3: Large Task (>10 files, >500 lines, high risk)
L3-Lite: High-risk small task (high risk, ≤3 files, ≤100 lines)
IAC: Infrastructure change (.tf, .tfvars, k8s/)
CONFIG: Config change (.yaml, .json, .toml)
DOCS: Documentation change (.md, .rst)
```

## Task Classification Logic

```python
def classify_task(task):
    # 0. Emergency check (keywords: hotfix, emergency, urgent, sev0)
    if is_hotfix(task): return {"level": "L0", "type": "CODE"}
    
    # 1. Detect change types (MAY return multiple)
    change_types = detect_change_types(task)
    
    # 2. Pure non-code: return type directly, skip level calculation
    if change_types == ["DOCS"]: return {"level": "DOCS", "type": "DOCS"}
    if change_types == ["CONFIG"]: return {"level": "CONFIG", "type": "CONFIG"}
    if change_types == ["IAC"]: return {"level": "IAC", "type": "IAC"}
    
    # 3. Scale (use change_lines = additions + deletions, NOT file line count)
    change_lines = get_change_lines(task)  # from diff_stats
    level = classify_by_scale(task.file_count, change_lines)
    
    # 4. Critical module boost (at least L2)
    if is_critical_module(task.affected_areas): level = max(level, "L2")
    
    # 5. Risk upgrade (high risk → L3 or L3-Lite)
    risk = assess_risk(task)
    if risk == "high": level = "L3_LITE" if small_task else "L3"
    elif risk == "medium" and level == "L1": level = "L2"
    
    # 6. Mixed type: return with types array
    if len(change_types) > 1:
        return {"level": level, "type": "MIXED", "types": change_types}
    
    return {"level": level, "type": change_types[0]}
```

## Risk Assessment with Safety Guards

```python
RISK_FACTORS = {
    "security": 3, "auth": 3, "payment": 3, "crypto": 3, "encryption": 3,
    "database": 2, "migration": 3, "external_api": 2, "core": 3,
    "injection": 3, "xss": 3, "command_execution": 3,
    "user_impact": 2, "performance": 2, "compliance": 2,
}

HIGH_RISK_FACTORS = ["security", "auth", "payment", "crypto", "injection", "xss", "command_execution"]

COMBINATION_RULES = [
    (["auth", "payment"], 3), (["privacy", "external_api"], 2),
    (["crypto", "database"], 2), (["security", "auth"], 2),
]

def assess_risk(affected_areas, description):
    score, matched = calculate_base_score(affected_areas)
    score += apply_combinations(matched)
    
    # SAFETY GUARD: if ANY high-risk factor present, NO reduction
    has_high_risk = any(f in matched for f in HIGH_RISK_FACTORS)
    if not has_high_risk:
        score += apply_reduction(description)  # fix: -1, refactor: -1, format: -2
    
    return classify(score)  # <3=low, <5=medium, >=8=high
```

## Mapping Tables (English keys)

```yaml
risk_mapping:
  auth: "auth", login: "auth", oauth: "auth", jwt: "auth", session: "auth"
  payment: "payment", billing: "payment", checkout: "payment", stripe: "payment"
  database: "database", db: "database", migration: "migration", sql: "database"
  security: "security", crypto: "crypto", encryption: "encryption", xss: "xss"
  core: "core", kernel: "core", engine: "core"
  api: "external_api", webhook: "external_api"
  config: "config", settings: "config", env: "config"
  user: "user_impact", admin: "user_impact"
  privacy: "privacy", gdpr: "privacy", pii: "privacy"

keyword_mapping:  # Chinese → English
  "支付": "payment", "鉴权": "auth", "认证": "authentication"
  "数据库": "database", "安全": "security", "加密": "encryption"
  "漏洞": "security", "注入": "injection", "隐私": "privacy"
```

## Mixed Type Gate Merging

```python
def merge_gates(gate_types):
    merged, seen = [], set()
    for gate_type in gate_types:
        for gate in GATE_MAP.get(gate_type, []):
            if gate.name not in seen:
                merged.append(gate)
                seen.add(gate.name)
    return merged
```

## Failure Handling

```python
RETRYABLE = ["network_error", "timeout", "rate_limit"]
NON_RETRYABLE = ["code_error", "test_failure", "security_vulnerability"]

# Gate retry: max 3, exponential backoff (5s, 10s, 20s)
# Pipeline retry: max 1, manual trigger
# Escalation: 2 failures → notify lead, 3 failures → freeze
# Timeout: L0=1h, L1=2h, L2=4h, L3=24h
```

## Quality Gates Summary

| Level | Gates |
|-------|-------|
| L0 | critical_path_test, secret_scan, security_scan(diff), rollback_plan |
| L1 | ruff, pytest(cov≥80%), semgrep, detect-secrets |
| L2 | +safety, +integration_test |
| L3 | +checkov, +performance_test, +zap-cli(DAST) |
| L3-Lite | ruff, semgrep, detect-secrets, pytest(cov≥80%) |
| IAC | tflint, checkov, detect-secrets, plan_review |
| CONFIG | yamllint, detect-secrets, diff_review, backup |
| DOCS | markdownlint, link_check, spell_check, detect-secrets |

## Key Pitfalls Found During Iteration

1. **Chinese/English mismatch**: risk_factors keys MUST be English; use mapping tables for Chinese
2. **Risk reduction vulnerability**: MUST gate reduction behind high-risk factor check
3. **File line count vs change lines**: Use diff stats, not total file lines
4. **Mixed type classification**: detect_change_types MUST support returning multiple types
5. **Non-code bypass**: DOCS/CONFIG/IAC should return type directly, skip level calculation
6. **max_level function**: Must define level ordering explicitly (L0>L3>L3-Lite>L2>L1)
7. **get_affected_areas filtering**: Must exclude vendor/, node_modules/, tests/
8. **Path matching depth**: Only use last 2 directory levels to reduce false positives
