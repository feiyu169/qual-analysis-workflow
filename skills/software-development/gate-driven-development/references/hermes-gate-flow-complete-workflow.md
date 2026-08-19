# Hermes Gate Flow (HGF) Complete Workflow Proposal V1.0

## Overview

HGF combines V5.0 workflow design with MCP Server V3.0 architecture into a complete programming workflow.

**Core principle**: User proposes → Agent writes code → Workflow auto-checks → User confirms

## Complete Flow

```
User: "帮我做一个登录功能"
    ↓
Phase 0: Requirements Analysis (analyze_requirements)
    - Check completeness (goal/scope/acceptance/priority)
    - Extract features
    - Generate acceptance criteria
    ↓
Phase 1: Agent Writes Code
    - Create files
    - Write code
    - Write tests
    ↓
Phase 2: Task Classification (classify_task)
    - Detect change types (CODE/IAC/CONFIG/DOCS/MIXED)
    - Scale classification (L0/L1/L2/L3/L3_LITE)
    - Risk assessment with safety guardrail
    ↓
Phase 3: Gate Execution (execute_gates)
    - MUST_PASS: ruff + pytest + detect-secrets
    - SHOULD_PASS: semgrep + safety
    - OPTIONAL: checkov + performance
    ↓
Phase 4: User Confirmation
    - Show results
    - Show fix suggestions
    - Wait for confirmation
    ↓
Phase 5: Commit
    - git add / commit / push
    - Git Hook auto-checks
```

## MCP Tools

| Tool | Phase | Function |
|------|-------|----------|
| analyze_requirements | 0 | Requirements analysis |
| review_design | 0 | Design review |
| classify_task | 2 | Task classification |
| assess_risk | 2 | Risk assessment |
| execute_gates | 3 | Gate execution |
| verify_tdd | 3 | TDD verification |
| check_security | 3 | Security check |
| check_deployment | 5 | Deployment check |
| setup_monitoring | 5 | Monitoring setup |

## Implementation Files

```
~/.hermes/workflow/
├── mcp_server.py              # MCP Server core
├── task_classifier.py         # Task classification
├── risk_assessor.py           # Risk assessment
├── gate_types.py              # Standardized types
├── gate_plugin.py             # Plugin base class
├── gate_plugins.py            # 6 plugins
├── gate_executor.py           # Gate executor
├── failure_handler.py         # Failure handling
├── pre_commit_tools.py        # Requirements + design
├── post_deploy_tools.py       # Deploy + monitoring
├── false_positive_checker.py  # False positive management
├── config/                    # Configuration
├── git_hooks/                 # Git hooks
└── tests/                     # 108 tests
```

## GitHub

https://github.com/feiyu169/hermes-gate-flow
