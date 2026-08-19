# API Reference

## MCP Server Protocol

Shrimp Task Manager implements the Model Context Protocol (MCP) specification for communication with AI clients.

## Tool Endpoints

### Task Management

#### `plan_task`
Plans and analyzes a task, creating a structured approach.

**Parameters:**
- `content` (string, required): Task description

**Returns:**
```json
{
  "taskId": "string",
  "title": "string",
  "status": "pending",
  "subtasks": []
}
```

#### `execute_task`
Executes a specific task or the highest priority pending task.

**Parameters:**
- `taskId` (string, optional): Task ID to execute
- `taskName` (string, optional): Task name to execute

**Returns:**
```json
{
  "taskId": "string",
  "status": "completed",
  "result": "string"
}
```

#### `list_tasks`
Lists all tasks with their current status.

**Parameters:**
- `filter` (string, optional): Filter by status (pending, completed, failed)
- `includeSubtasks` (boolean, optional): Include subtasks in response

**Returns:**
```json
{
  "tasks": [
    {
      "id": "string",
      "title": "string",
      "status": "string",
      "priority": "number",
      "dependencies": []
    }
  ]
}
```

#### `split_tasks`
Decomposes a complex task into smaller subtasks.

**Parameters:**
- `taskId` (string, required): Task ID to split
- `approach` (string, optional): Splitting strategy

**Returns:**
```json
{
  "parentTask": "string",
  "subtasks": [
    {
      "id": "string",
      "title": "string",
      "dependencies": []
    }
  ]
}
```

### Project Management

#### `init_project_rules`
Initializes project-specific rules and standards.

**Parameters:**
- `projectPath` (string, optional): Project directory path
- `framework` (string, optional): Primary framework
- `language` (string, optional): Primary language

**Returns:**
```json
{
  "rules": {
    "coding_standards": {},
    "file_structure": {},
    "dependencies": []
  }
}
```

#### `research_mode`
Enters research mode for systematic exploration.

**Parameters:**
- `topic` (string, required): Research topic
- `depth` (string, optional): Research depth (shallow, medium, deep)

**Returns:**
```json
{
  "findings": [],
  "recommendations": [],
  "resources": []
}
```

### Task Operations

#### `update_task`
Updates task properties.

**Parameters:**
- `taskId` (string, required): Task ID
- `updates` (object, required): Properties to update

**Returns:**
```json
{
  "taskId": "string",
  "updated": true
}
```

#### `delete_task`
Removes a task from the queue.

**Parameters:**
- `taskId` (string, required): Task ID

**Returns:**
```json
{
  "deleted": true,
  "backupCreated": true
}
```

#### `verify_task`
Validates task completion.

**Parameters:**
- `taskId` (string, required): Task ID
- `criteria` (array, optional): Verification criteria

**Returns:**
```json
{
  "verified": true,
  "issues": []
}
```

## Data Models

### Task Object

```typescript
interface Task {
  id: string;
  title: string;
  description?: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  priority: number;
  dependencies: string[];
  parentId?: string;
  subtasks?: Task[];
  metadata?: {
    createdAt: Date;
    updatedAt: Date;
    completedAt?: Date;
    assignedAgent?: string;
    tags?: string[];
  };
  result?: any;
  error?: string;
}
```

### Project Rules

```typescript
interface ProjectRules {
  coding_standards: {
    style_guide: string;
    linting_rules: Record<string, any>;
    formatting: Record<string, any>;
  };
  file_structure: {
    src_layout: string[];
    naming_conventions: Record<string, string>;
  };
  dependencies: {
    allowed: string[];
    restricted: string[];
    versions: Record<string, string>;
  };
  testing: {
    framework: string;
    coverage_threshold: number;
    test_patterns: string[];
  };
}
```

### Research Result

```typescript
interface ResearchResult {
  topic: string;
  timestamp: Date;
  findings: {
    summary: string;
    details: string[];
    pros: string[];
    cons: string[];
  }[];
  recommendations: {
    primary: string;
    alternatives: string[];
    rationale: string;
  };
  resources: {
    title: string;
    url: string;
    relevance: number;
  }[];
}
```

## Web API (When GUI Enabled)

### REST Endpoints

#### `GET /api/tasks`
Retrieves all tasks.

**Query Parameters:**
- `status`: Filter by status
- `limit`: Maximum results
- `offset`: Pagination offset

**Response:**
```json
{
  "tasks": [],
  "total": 0,
  "offset": 0,
  "limit": 50
}
```

#### `GET /api/tasks/:id`
Retrieves a specific task.

**Response:**
```json
{
  "task": {}
}
```

#### `POST /api/tasks`
Creates a new task.

**Body:**
```json
{
  "title": "string",
  "description": "string",
  "priority": "number"
}
```

#### `PUT /api/tasks/:id`
Updates a task.

**Body:**
```json
{
  "status": "string",
  "priority": "number"
}
```

#### `DELETE /api/tasks/:id`
Deletes a task.

**Response:**
```json
{
  "deleted": true
}
```

### WebSocket Events

#### Connection
```javascript
ws.connect('ws://localhost:3000/ws')
```

#### Events

**`task:created`**
```json
{
  "event": "task:created",
  "data": { /* task object */ }
}
```

**`task:updated`**
```json
{
  "event": "task:updated",
  "data": { /* task object */ }
}
```

**`task:deleted`**
```json
{
  "event": "task:deleted",
  "data": { "id": "string" }
}
```

## Error Handling

### Error Response Format

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable message",
    "details": {}
  }
}
```

### Common Error Codes

| Code | Description |
|------|-------------|
| `TASK_NOT_FOUND` | Task ID doesn't exist |
| `INVALID_PARAMS` | Invalid parameters provided |
| `DEPENDENCY_CONFLICT` | Task has unmet dependencies |
| `EXECUTION_FAILED` | Task execution failed |
| `PERMISSION_DENIED` | Insufficient permissions |
| `RATE_LIMITED` | Too many requests |

## Rate Limiting

- Default: 100 requests per minute
- Burst: 20 requests per second
- Headers: `X-RateLimit-*`

## Authentication

MCP communication is handled through the client's authentication. Web API supports:

- No authentication (local use)
- API key authentication
- JWT tokens (when configured)

## Environment Variables

```bash
# Core Configuration
DATA_DIR=/path/to/data
PROMPT_LANGUAGE=en

# Web GUI
ENABLE_GUI=true
WEB_PORT=3000
GUI_AUTH=false

# Advanced
MAX_TASK_DEPTH=5
AUTO_BACKUP=true
BACKUP_INTERVAL=3600
LOG_LEVEL=info
```

## SDK Usage

### JavaScript/TypeScript

```typescript
import { ShrimpClient } from '@mcp/shrimp-task-manager';

const client = new ShrimpClient({
  dataDir: '/path/to/data',
  language: 'en'
});

// Plan a task
const task = await client.planTask('Implement user authentication');

// Execute task
const result = await client.executeTask(task.id);

// List all tasks
const tasks = await client.listTasks();
```

### Python

```python
from mcp_shrimp import ShrimpClient

client = ShrimpClient(
    data_dir='/path/to/data',
    language='en'
)

# Plan a task
task = client.plan_task('Implement user authentication')

# Execute task
result = client.execute_task(task['id'])

# List all tasks
tasks = client.list_tasks()
```

## Webhooks

Configure webhooks for task events:

```json
{
  "webhooks": {
    "task_created": "https://api.example.com/webhook",
    "task_completed": "https://api.example.com/webhook",
    "task_failed": "https://api.example.com/webhook"
  }
}
```

Webhook payload:
```json
{
  "event": "task_completed",
  "timestamp": "2024-01-01T00:00:00Z",
  "data": { /* task object */ }
}
```