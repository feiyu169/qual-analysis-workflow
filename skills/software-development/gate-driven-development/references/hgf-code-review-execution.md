# HGF Code Review Execution Pattern

## When to Use

User says: "审查项目", "代码审查", "帮我检查代码", "用HGF审查"

## Execution Flow

### Step 1: Load Skills First

```python
# ALWAYS load gate-driven-development skill first
skill_view(name='gate-driven-development')
skill_view(name='workflow-gates')
```

### Step 2: Gather Project Info

```python
# Get file lists
find . -name "*.py" -not -path "./node_modules/*" | head -30
find . -name "*.vue" -o -name "*.js" | grep -v node_modules

# Count lines
find . -name "*.py" | xargs wc -l | tail -1

# Get git diff (if available)
git diff --stat HEAD~1
```

### Step 3: Task Classification

```python
import sys
sys.path.insert(0, '~/.hermes/workflow')
from task_classifier import TaskClassifier, Task

task = Task(
    description="审查XXX项目",
    files=[...],  # file list
    file_count=N,
    line_count=M,
    affected_areas=["auth", "api", "database", "frontend"],
    labels=["fullstack", "refactor", "security"]
)

classifier = TaskClassifier()
result = classifier.classify_task(task)
# Output: level (L0-L3), type (CODE/CONFIG/MIXED), risk (low/medium/high)
```

### Step 4: Execute Gates

```python
from gate_executor import GateExecutor

executor = GateExecutor()
result = executor.execute_gates(
    level="L3",  # from classification
    files=[...],
    working_dir="/path/to/project"
)
```

**If MCP tools unavailable**, execute manually:
```bash
# Static analysis
ruff check app/ tests/ config/

# Unit tests
pytest tests/ -v --tb=short

# Security scan
grep -rn 'password\|SECRET\|TOKEN' --include='*.py'
grep -rn 'execute\|text(' --include='*.py'  # SQL injection
```

### Step 5: Generate Report

Use this format:

```markdown
## HGF 审查报告

### 一、任务分级结果
| 维度 | 结果 | 说明 |
|------|------|------|
| Level | L3 | 大型任务 |
| Type | MIXED | 混合类型 |
| Risk | HIGH | 高风险 |

### 二、门禁执行结果
#### 静态分析（Ruff）
- 状态: ✅/❌
- 问题数: N

#### 单元测试（Pytest）
- 状态: ✅/❌
- 覆盖率: X%

#### 安全检查
- 硬编码密码: ✅/❌
- SQL注入: ✅/❌
- XSS风险: ✅/❌

### 三、代码质量评估
| 维度 | 评分 | 说明 |
|------|------|------|
| 架构设计 | X/10 | ... |
| 代码规范 | X/10 | ... |
| 安全性 | X/10 | ... |
| 可测试性 | X/10 | ... |
| 可维护性 | X/10 | ... |

### 四、改进建议
#### 高优先级
1. ...
2. ...

#### 中优先级
3. ...

### 五、结论
**整体评分**: X/10
**HGF审查结论**: ✅通过 / ⚠️有条件通过 / ❌不通过
```

## Level-Specific Gate Requirements

| Level | must_pass | should_pass | optional |
|-------|-----------|-------------|----------|
| L0 | secret_scan | - | - |
| L1 | static_analysis, unit_test, secret_scan | security_scan | - |
| L2 | static_analysis, unit_test, secret_scan, security_scan | dependency_scan | - |
| L3 | static_analysis, unit_test, secret_scan, security_scan, dependency_scan | - | performance_test, iac_scan |
| L3_LITE | static_analysis, secret_scan, security_scan | unit_test | - |

## Common Pitfalls

1. **Don't invent workflow names** — Always use "HGF", never "HAF" or other variants
2. **Load skills first** — gate-driven-development must be loaded before starting
3. **Report in HGF format** — Even when using manual tools, maintain the standard report structure
4. **Security redaction blocks config.py** — P37: `os.environ.get('SECRET_KEY')` gets redacted to `***`
5. **Python version mismatch** — MCP server may need dependencies in different Python version's site-packages
