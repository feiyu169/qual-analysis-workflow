# MCP Server Integration Workflow

## Overview

Standard workflow for integrating external MCP servers into hermes-agent. Proven during hermes-agent enhancement project (2026-06-21).

## Integration Steps

### 1. Clone and Inspect

```bash
cd /tmp
git clone https://github.com/owner/repo.git
ls repo/
cat repo/README.md | head -50
cat repo/package.json  # or requirements.txt
```

**Key checks**:
- Language (Python/Node.js/Rust)
- Dependencies (npm/pip/cargo)
- Entry point (main.py/index.js)
- Storage backend (SQLite/PostgreSQL/file)

### 2. Install Dependencies

**Node.js projects**:
```bash
cd repo
npm install
npm audit  # Security check (may fail on some registries)
npm run build
```

**Python projects**:
```bash
cd repo
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

**Global npm packages**:
```bash
npm install -g package-name
```

### 3. Move to Permanent Location

```bash
mkdir -p ~/.hermes/mcp-servers
mv /tmp/repo ~/.hermes/mcp-servers/
```

### 4. Register in mcp_servers.yaml

```yaml
# ~/.hermes/mcp_servers.yaml
servers:
  - name: "server-name"
    type: "stdio"
    command: "node"  # or "python3" or "uvx"
    args:
      - "/home/user/.hermes/mcp-servers/repo/dist/index.js"
    description: "Server description"
    env:
      - "DATA_DIR=/home/user/.hermes/mcp-data/server-name"
    timeout: 300
    retry:
      max_retries: 3
      retry_delay: 5
```

**Common command patterns**:
- Node.js: `command: "node"`, args: `["path/to/index.js"]`
- Python: `command: "path/to/.venv/bin/python"`, args: `["path/to/server.py"]`
- uvx: `command: "uvx"`, args: ["package-name"]`
- npm global: `command: "package-name"` (if installed globally)

### 5. Create Data Directory

```bash
mkdir -p ~/.hermes/mcp-data/server-name
```

### 6. Test Server Startup

```bash
# Test that server starts without errors
timeout 5 node dist/index.js 2>&1 || true
timeout 5 python3 server.py 2>&1 || true
```

**Expected**: Server starts and waits for stdin (no error output)

### 7. Verify Registration

```bash
grep -A 10 "server-name" ~/.hermes/mcp_servers.yaml
```

## Pitfalls

### P1: npm audit fails on Chinese registries

Some npm registries (e.g., registry.npmmirror.com) don't support the security audit API. This is expected — skip the audit and note it in the risk assessment.

### P2: Python 3.11 externally managed

When system has uv-managed Python 3.11, `pip install` fails with "externally-managed-environment". Use `uv venv .venv` instead.

### P3: Workspace protocol not supported by npm

Monorepos using yarn workspaces have `workspace:*` dependencies that npm can't resolve. Install yarn first: `npm install -g yarn`, then `yarn install`.

### P4: MCP server waits for stdin

MCP servers using stdio transport wait for input on stdin. `timeout 5 server` will always exit after 5 seconds — this is expected behavior, not an error.

### P5: Frontend build may be slow

Some MCP servers (e.g., nocturne_memory) have frontend components that need building. Use `SKIP_FRONTEND_BUILD=true` env var to skip on first run.

## Risk Assessment Template

```markdown
| 检查项 | 状态 |
|--------|------|
| 仓库克隆 | ✅ |
| 依赖安装 | ✅/⚠️ |
| npm audit | ✅/⚠️ (registry不支持) |
| 构建成功 | ✅ |
| 移动到永久位置 | ✅ |
| 注册到mcp_servers.yaml | ✅ |
| 创建数据目录 | ✅ |
| 服务器启动测试 | ✅ |

**已知未知**:
1. [具体风险1]
2. [具体风险2]

**Gate结论**: PASS / CONDITIONAL PASS / FAIL
```

## Example: Complete Integration

```bash
# 1. Clone
cd /tmp && git clone https://github.com/cjo4m06/mcp-shrimp-task-manager.git

# 2. Install
cd mcp-shrimp-task-manager && npm install && npm run build

# 3. Move
mkdir -p ~/.hermes/mcp-servers
mv /tmp/mcp-shrimp-task-manager ~/.hermes/mcp-servers/

# 4. Register
cat >> ~/.hermes/mcp_servers.yaml << 'EOF'

  - name: "shrimp-task-manager"
    type: "stdio"
    command: "node"
    args:
      - "/home/user/.hermes/mcp-servers/mcp-shrimp-task-manager/dist/index.js"
    description: "任务规划工具"
    env:
      - "DATA_DIR=/home/user/.hermes/mcp-data/shrimp"
    timeout: 300
    retry:
      max_retries: 3
      retry_delay: 5
EOF

# 5. Create data dir
mkdir -p ~/.hermes/mcp-data/shrimp

# 6. Test
timeout 5 node dist/index.js 2>&1 || true

# 7. Verify
grep -A 10 "shrimp-task-manager" ~/.hermes/mcp_servers.yaml
```
