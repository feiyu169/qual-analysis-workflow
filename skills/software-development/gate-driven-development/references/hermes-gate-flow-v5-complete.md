# Hermes Gate Flow (HGF) V5.0 — Complete Implementation

**Status**: Implemented (108 tests passing)
**GitHub**: https://github.com/feiyu169/hermes-gate-flow
**Local**: ~/.hermes/workflow/

## Architecture Summary

```
User Request → Task Classification → Risk Assessment → Gate Execution → Result
     ↓              ↓                     ↓                  ↓
  Skill        classify_task()      assess_risk()      execute_gates()
  (intent)     (L0-L3, IAC,         (15 factors,       (plugin arch,
               CONFIG, DOCS)        safety guardrail)   3-tier gates)
```

## File Structure

```
~/.hermes/workflow/
├── mcp_server.py              # MCP Server core (5 tools)
├── task_classifier.py         # L0/L1/L2/L3/L3_LITE/IAC/CONFIG/DOCS
├── risk_assessor.py           # English keys + mapping + safety guardrail
├── gate_types.py              # GateResult/GateConfig/GateExecutionReport
├── gate_plugin.py             # GatePlugin ABC (execute, is_available)
├── gate_plugins.py            # 6 plugins: ruff, pytest, detect-secrets, semgrep, safety, checkov
├── gate_executor.py           # Plugin registry + 3-tier execution
├── failure_handler.py         # Retry (exponential backoff) + escalation
├── pre_commit_tools.py        # analyze_requirements + review_design
├── post_deploy_tools.py       # check_deployment + setup_monitoring
├── false_positive_checker.py  # Expiry-aware FP management
├── config/
│   ├── mcp-gates.yaml         # MUST_PASS/SHOULD_PASS/OPTIONAL + level_gates
│   ├── exceptions.yaml        # False positives + exemptions
│   ├── iac_governance.yaml    # Branch protection + audit config
│   ├── risk_mapping.yaml      # English→risk factor + Chinese→English
│   └── workflow.yaml          # Thresholds, critical_modules
├── git_hooks/pre-push         # Pre-push quality check
├── install_git_hooks.sh       # Hook installer
└── tests/                     # 108 tests, all passing
```

## Key Design Decisions

### 1. Safety Guardrail for Risk Reduction
Risk reduction rules (fix → -1, refactor → -1) are ONLY applied when NO high-risk factors are matched. This prevents "fix critical authentication bypass" from being downgraded.

### 2. English Keys + Mapping Layer
risk_factors uses English keys (auth, payment, security). A mapping layer converts file paths, Chinese keywords, and labels to these keys. This was a critical fix from V3 HeavySkill review.

### 3. Mixed Change Type Support
detect_change_types() returns a list (CODE, IAC, CONFIG, DOCS). For mixed changes, gates from all types are merged.

### 4. Fail-closed with Emergency Channel
MCP Server unavailable → reject (unless emergency token). MUST_PASS tool unavailable → reject. SHOULD_PASS → warn. OPTIONAL → skip.

### 5. Incremental Coverage
Uses incremental_coverage_min (not total coverage) to avoid blocking small changes in legacy codebases.

## User Preferences (Verified)

1. **MCP Server first**: User explicitly preferred MCP Server as core, not Skill
2. **Completeness over speed**: "不怕麻烦" — take time to do it right
3. **User proposes, agent executes**: "我提出修改的地方，你执行"
4. **Non-technical user**: Explain in plain language, use analogies
5. **HGF branding**: Hermes Gate Flow, trigger words: "Gate Flow", "代码审查"

## MCP Registration

```yaml
# ~/.hermes/mcp_servers.yaml
servers:
  - name: "workflow-gates"
    type: "stdio"
    command: "python3"
    args: ["/home/lff7767162/.hermes/workflow/mcp_server.py"]
    description: "代码质量门禁"
```

## Skill Registration

```yaml
# ~/.hermes/skills/workflow-gates/SKILL.md
trigger:
  - "代码审查"
  - "质量检查"
  - "帮我检查代码"
  - "Gate Flow"
mcp_tools:
  - classify_task
  - execute_gates
  - check_security
```

## HeavySkill Review History

- V2: Basic design → 6 issues found
- V3: Fixed risk assessment → 5 issues found
- V4: Fixed mixed types → 3 issues found
- V5: All reviews passed → Implementation started
- V5.0 Final: 108 tests, all passing
