# MCP Server Workflow Implementation

## File Structure

```
~/.hermes/workflow/
├── gate_types.py           # GateResult/GateConfig/GateExecutionReport dataclasses
├── gate_plugin.py          # GatePlugin ABC (execute, is_available, get_version)
├── gate_plugins.py         # 6 plugins: Ruff, Pytest, DetectSecrets, Semgrep, Safety, Checkov
├── gate_executor.py        # GateExecutor with plugin registry
├── pre_commit_tools.py     # RequirementsAnalyzer + DesignReviewer
├── post_deploy_tools.py    # DeploymentChecker + MonitoringSetupper
├── false_positive_checker.py # Expiry-aware exception checking
├── mcp_server.py           # MCP Server CLI + 5 core tools + audit logging
├── config/
│   ├── mcp-gates.yaml      # Gate definitions + level mappings
│   ├── iac_governance.yaml # Branch protection + audit config
│   └── exceptions.yaml     # False positives + exemptions
├── tests/
│   ├── test_task_classifier.py
│   ├── test_risk_assessor.py
│   ├── test_failure_handler.py
│   ├── test_mcp_server.py
│   ├── test_pre_commit_tools.py
│   ├── test_post_deploy_tools.py
│   └── test_false_positive_checker.py
└── workflow.db             # SQLite audit log
```

## MCP Server Registration

```yaml
# ~/.hermes/mcp_servers.yaml
servers:
  - name: "workflow-gates"
    type: "stdio"
    command: "python3"
    args:
      - "/home/lff7767162/.hermes/workflow/mcp_server.py"
    description: "代码质量门禁 - 任务分级、风险评估、门禁执行"
```

## Skill Registration

```yaml
# ~/.hermes/skills/workflow-gates/SKILL.md
name: workflow-gates
description: 代码质量门禁
trigger:
  - "代码审查"
  - "质量检查"
  - "提交前检查"
mcp_tools:
  - classify_task
  - execute_gates
  - check_security
```

## Key Design Decisions

1. **Plugin architecture**: GatePlugin ABC + registry, easy to add new tools
2. **Three-tier gates**: MUST_PASS (block) / SHOULD_PASS (warn) / OPTIONAL (log)
3. **Fail-closed**: MCP down → reject, MUST_PASS tool down → reject
4. **Audit logging**: SQLite database for all MCP calls
5. **Emergency channel**: EMERGENCY_APPROVAL_TOKEN env var

## Test Results

108 tests total, all passing:
- test_task_classifier.py: 17
- test_risk_assessor.py: 14
- test_failure_handler.py: 16
- test_mcp_server.py: 20
- test_pre_commit_tools.py: 14
- test_post_deploy_tools.py: 17
- test_false_positive_checker.py: 10
