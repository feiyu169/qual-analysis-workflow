# HeavySkill Checklist Design Best Practices

## Checklist Item Structure

```yaml
- id: "S-01"
  question: "是否存在SQL注入风险？"
  severity: "P0"
  category: "输入验证"
  check_scope: [code, config]  # NEW: code/config/process
  languages: [python, java, go, js]  # NEW: project language filter
  check_points:
    - "是否使用参数化查询？"
  fix_suggestion:
    steps:
      - "1. 识别所有 SQL 查询语句"
      - "2. 检查是否使用参数化查询"
    example: |
      cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
```

## check_scope Field

| Value | Description | HeavySkill Treatment |
|-------|-------------|---------------------|
| code | Checkable from code | Auto-check, affects verdict |
| config | Checkable from config | Auto-check, affects verdict |
| process | Organizational process | Reminder only, no verdict impact |

## languages Field

Checklist items are filtered by project language. If project language not in list, item is skipped.

## Dynamic Loading Strategy

HeavySkill loads checklists dynamically based on MR file extensions:

| Extension | Domain |
|-----------|--------|
| .jsx, .tsx, .vue, .css | frontend |
| .sql, model, entity | database |
| .yaml, .yml, .tf | deployment |
| api, controller, route | api |
| * | security, architecture, performance |

## Cost Optimization

- Full checklist: 120 items ~ 15,000 tokens
- Dynamic loading: 50-80 items ~ 8,000-10,000 tokens
- Savings: 30-50% token reduction

## Project-Level Severity Override

```yaml
severity_overrides:
  finance:
    D-07: P0  # Upgrade transaction management for finance
  healthcare:
    S-11: P0  # Upgrade encryption for healthcare
```
