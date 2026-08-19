# MCP Server Configuration Patterns (Verified 2026-06-22)

## hermes mcp add Syntax

```bash
# Standard form
hermes mcp add <name> --command <binary> --args <arg1> <arg2> ...

# Node.js servers
hermes mcp add shrimp-task-manager --command node --args ~/.hermes/mcp-servers/mcp-shrimp-task-manager/dist/index.js

# Python venv servers
hermes mcp add nocturne-memory --command ~/.hermes/mcp-servers/nocturne_memory/backend/.venv/bin/python3 --args ~/.hermes/mcp-servers/nocturne_memory/backend/mcp_server.py

# npx-based servers
hermes mcp add octocode --command npx --args octocode-mcp

# uvx-based servers
hermes mcp add arxiv --command uvx --args arxiv-mcp-server
```

## Key Rules

1. `--args` must be LAST — consumes all remaining arguments
2. `--command` takes ONE binary or full path
3. For Python venv: use venv python as `--command`, script as `--args`
4. Connection timeout → saved as "disabled" → fix timeout or re-enable

## Auto-accept Interactive Prompts

```bash
echo "Y" | hermes mcp add <name> --command <cmd> --args <args>
```

## Post-configuration

```bash
hermes mcp test <name>     # Test connection + tool discovery
hermes mcp list             # Verify registration
```

## Common Pitfalls

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| Missing --command | "unrecognized arguments" | Use `--command <binary>` |
| --args not last | Only first arg captured | Put `--args` at end |
| venv python wrong | ModuleNotFoundError | Use `.venv/bin/python3` not `python3` |
| Timeout | Saved as disabled | Check server startup, increase timeout |
| Interactive prompt | Cancelled | Pipe `echo "Y"` |

## Discovered Tool Counts (2026-06-22)

| Server | Tools | Key Capabilities |
|--------|-------|------------------|
| shrimp-task-manager | 15 | plan_task, analyze_task, reflect_task, split_tasks, execute_task |
| nocturne-memory | 7 | read_memory, create_memory, update_memory, search_memory |
| octocode | 13 | githubSearchCode, localSearchCode, lspGotoDefinition, lspFindReferences |
| arxiv | N/A | Connection timeout (disabled) |
