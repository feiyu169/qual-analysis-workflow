# MCP Server Workflow Architecture

## Overview

MCP Server as the core of a complete programming workflow, with Skill for intent routing, Git Hook for enforcement, and CI/CD as backup.

## Architecture

```
User Request → Skill (Intent Routing) → MCP Server (Core) → Git Hook (Enforcement) → CI/CD (Backup)
```

## 5 Core MCP Tools

1. **classify_task**: Task classification (L0/L1/L2/L3/L3_LITE/IAC/CONFIG/DOCS)
2. **assess_risk**: Risk assessment with safety guardrails
3. **execute_gates**: Quality gate execution
4. **verify_tdd**: TDD evidence verification
5. **check_security**: Security checks (detect-secrets, semgrep)

## Key Design Decisions

1. **MCP Server as Core**: Complete tool interface, non-bypassable at protocol level
2. **Audit Logging**: Every call logged to SQLite for traceability
3. **Safety Guardrails**: High-risk factors prevent risk downgrade
4. **Mixed Change Support**: Detect CODE/IAC/CONFIG/DOCS in single PR
5. **Incremental Coverage**: Only measure changed lines, not total project
6. **Fail-Closed**: MCP unavailable → reject operation, not degrade

## Implementation

See `mcp-server-workflow-architecture.md` for complete implementation details.
