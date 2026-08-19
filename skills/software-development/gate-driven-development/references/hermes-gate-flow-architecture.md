# Hermes Gate Flow (HGF) Architecture

## Overview

HGF is a complete programming workflow system that implements:
- User proposes → Agent writes code → Workflow auto-checks → User confirms
- Smart task classification (L0/L1/L2/L3/L3_LITE/IAC/CONFIG/DOCS)
- Risk assessment with safety guardrails
- Plugin-based gate execution (MUST_PASS/SHOULD_PASS/OPTIONAL)
- Git Hook enforcement + fail-closed strategy
- HeavySkill integration for proposal review

## File Structure

```
~/.hermes/workflow/
├── mcp_server.py              # MCP Server core (5 tools)
├── task_classifier.py         # Task classification
├── risk_assessor.py           # Risk assessment
├── gate_types.py              # Standardized output types
├── gate_plugin.py             # GatePlugin base class
├── gate_plugins.py            # 6 plugins (ruff, pytest, detect-secrets, semgrep, safety, checkov)
├── gate_executor.py           # GateExecutor with plugin architecture
├── failure_handler.py         # Failure handling + escalation
├── pre_commit_tools.py        # Requirements analysis + design review
├── post_deploy_tools.py       # Deployment check + monitoring
├── false_positive_checker.py  # False positive management
├── config/
│   ├── mcp-gates.yaml         # Gate configuration
│   ├── exceptions.yaml        # False positive config
│   ├── iac_governance.yaml    # IAC governance
│   └── workflow.yaml          # Workflow config
├── git_hooks/
│   └── pre-push               # Git pre-push hook
├── install_git_hooks.sh       # Hook installer
└── tests/
    ├── test_task_classifier.py
    ├── test_risk_assessor.py
    ├── test_failure_handler.py
    ├── test_mcp_server.py
    ├── test_pre_commit_tools.py
    ├── test_post_deploy_tools.py
    └── test_false_positive_checker.py
```

## MCP Tools

| Tool | Function | Input | Output |
|------|----------|-------|--------|
| classify_task | Task classification | description, files, lines | level, type, risk |
| assess_risk | Risk assessment | affected_areas, description | risk, score, factors |
| execute_gates | Gate execution | level, files | passed, failed, results |
| verify_tdd | TDD verification | git_history | has_test_evidence |
| check_security | Security check | files | all_passed, results |

## Task Classification

```python
def classify_task(task):
    # 0. Hotfix check
    if is_hotfix(task): return {"level": "L0", "type": "CODE"}
    
    # 1. Change type detection
    change_types = detect_change_types(task)
    
    # 2. Pure non-code return
    if change_types == ["DOCS"]: return {"level": "DOCS", "type": "DOCS"}
    if change_types == ["CONFIG"]: return {"level": "CONFIG", "type": "CONFIG"}
    if change_types == ["IAC"]: return {"level": "IAC", "type": "IAC"}
    
    # 3. Scale classification
    change_lines = get_change_lines(task, change_types)
    level = "L1"
    if task.file_count > 10 or change_lines > 500: level = "L3"
    elif task.file_count > 3 or change_lines > 100: level = "L2"
    
    # 4. Critical module check
    if is_critical_module(task.affected_areas): level = max_level(level, "L2")
    
    # 5. Risk assessment
    risk = assess_risk(task)
    
    # 6. Risk upgrade
    if risk == "high":
        level = "L3_LITE" if (task.file_count <= 3 and change_lines <= 100) else "L3"
    elif risk == "medium" and level == "L1": level = "L2"
    
    return {"level": level, "type": change_types[0]}
```

## Risk Assessment with Safety Guardrail

```python
HIGH_RISK_FACTORS = ["security", "auth", "payment", "crypto", "injection", "xss"]

def assess_risk(task):
    risk_score = 0
    matched_factors = []
    
    for area in affected_areas:
        if area in risk_factors:
            risk_score += risk_factors[area]
            matched_factors.append(area)
        elif area in risk_mapping:
            mapped = risk_mapping[area]
            if mapped in risk_factors:
                risk_score += risk_factors[mapped]
                matched_factors.append(mapped)
    
    # Combination bonus
    if "auth" in matched_factors and "payment" in matched_factors:
        risk_score += 3
    
    # Safety guardrail: NO downgrade when high-risk factors present
    has_high_risk = any(f in matched_factors for f in HIGH_RISK_FACTORS)
    if not has_high_risk:
        # Only apply reduction when no high-risk factors
        for keyword, reduction in reduction_rules.items():
            if keyword in description.lower():
                risk_score += reduction
    
    return "high" if risk_score >= 8 else "medium" if risk_score >= 5 else "low"
```

## Gate Configuration

```yaml
gates:
  must_pass:    # Failure = block
    - {name: "static_analysis", tool: "ruff", timeout: 60}
    - {name: "unit_test", tool: "pytest", timeout: 300, coverage_min: 80}
    - {name: "secret_scan", tool: "detect-secrets", timeout: 60}
  
  should_pass:  # Failure = warn
    - {name: "security_scan", tool: "semgrep", timeout: 120}
    - {name: "dependency_scan", tool: "safety", timeout: 60}
  
  optional:     # Failure = log
    - {name: "performance_test", tool: "pytest", timeout: 600}
    - {name: "iac_scan", tool: "checkov", timeout: 120}

level_gates:
  L0: {must_pass: ["secret_scan"]}
  L1: {must_pass: ["static_analysis", "unit_test", "secret_scan"], should_pass: ["security_scan"]}
  L2: {must_pass: ["static_analysis", "unit_test", "secret_scan", "security_scan"], should_pass: ["dependency_scan"]}
  L3: {must_pass: ["static_analysis", "unit_test", "secret_scan", "security_scan", "dependency_scan"], optional: ["performance_test", "iac_scan"]}
  L3_LITE: {must_pass: ["static_analysis", "secret_scan", "security_scan"], should_pass: ["unit_test"]}
  IAC: {must_pass: ["secret_scan", "iac_scan"]}
  CONFIG: {must_pass: ["secret_scan"]}
  DOCS: {must_pass: ["secret_scan"]}
```

## Fail-closed Strategy

```python
class FailClosedStrategy:
    def handle_mcp_failure(self, context):
        if self._check_emergency_approval(context):
            return True  # Emergency approved
        raise WorkflowError("MCP Server unavailable, operation rejected")
    
    def handle_tool_failure(self, tool, level, context):
        if level == "MUST_PASS":
            if not self._check_emergency_approval(context):
                raise WorkflowError(f"MUST_PASS tool {tool} unavailable, rejected")
        elif level == "SHOULD_PASS":
            logger.warning(f"SHOULD_PASS tool {tool} unavailable, skipping")
        else:
            logger.info(f"OPTIONAL tool {tool} unavailable, skipping")
```

## Git Hook

```bash
#!/bin/bash
# Pre-push hook: classify → check risk → execute fast gates
FILES=$(git diff --name-only HEAD~1)
LEVEL=$(python3 mcp_server.py classify --task "Pre-push" --files "$FILES" | jq -r '.level')
RISK=$(python3 mcp_server.py classify --task "Pre-push" --files "$FILES" | jq -r '.risk')

if [ "$RISK" = "high" ]; then
    echo "❌ High risk task, push blocked"
    exit 1
fi

ruff check . --quiet || exit 1
detect-secrets scan --list-all-files | grep -q "Potential secret" && exit 1
echo "✅ Check passed"
```

## MCP Registration

```yaml
# ~/.hermes/mcp_servers.yaml
servers:
  - name: "workflow-gates"
    type: "stdio"
    command: "python3"
    args: ["/home/lff7767162/.hermes/workflow/mcp_server.py"]
    description: "Code quality gates"
```

## Skill Definition

```yaml
# ~/.hermes/skills/workflow-gates/SKILL.md
name: workflow-gates
description: Code quality gates - task classification + risk assessment + gate execution
trigger:
  - "代码审查"
  - "质量检查"
  - "帮我检查代码"
  - "Gate Flow"
```

## Test Results

| Test File | Count | Status |
|-----------|-------|--------|
| test_task_classifier.py | 17 | ✅ |
| test_risk_assessor.py | 14 | ✅ |
| test_failure_handler.py | 16 | ✅ |
| test_mcp_server.py | 20 | ✅ |
| test_pre_commit_tools.py | 14 | ✅ |
| test_post_deploy_tools.py | 17 | ✅ |
| test_false_positive_checker.py | 10 | ✅ |
| **Total** | **108** | **✅** |

## GitHub

https://github.com/feiyu169/hermes-gate-flow
