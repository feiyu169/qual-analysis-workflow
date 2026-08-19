# Multi-Expert Architectural Review Workflow

> Pattern: use HeavySkill as a multi-perspective technical reviewer

## When to Use

- Reviewing a technical architecture proposal before implementation
- Getting "second opinions" from multiple expert perspectives (programming, finance, security, etc.)
- Stress-testing a plan before committing resources

## Workflow

### Step 1: Write the plan to a temp file

```python
# Use write_file, NOT terminal echo
write_file(path="/tmp/proposal.md", content="full plan content here...")
```

### Step 2: Write the review query to a temp file

```python
write_file(path="/tmp/heavyskill-query.txt", content="""
请审查这个方案，从以下6个维度进行深度评估：

1. 技术可行性：方案中每个组件的移植是否技术上可行？
2. 架构契合度：是否存在结构性错配？
3. 数据层替代：覆盖率和数据质量是否足够？
4. 工作量评估：时间估算是否合理？
5. 风险遗漏：有没有遗漏的重大风险？
6. 优先级建议：分期排序是否合理？

请给出具体的、可操作的审查意见，包括"方案中正确的地方"和"需要修改的地方"。
""")
```

### Step 3: Run HeavySkill

```bash
cd ~/.hermes/skills/heavyskill && python3 scripts/run_heavyskill.py \
  -q "$(cat /tmp/heavyskill-query.txt)" \
  -f /tmp/proposal.md \
  --reason_k 6 --summary_k 3 --language cn \
  -o /tmp/heavyskill-review.json --quiet 2>&1
```

### Step 4: Extract trajectories

```python
import json
with open('/tmp/heavyskill-review.json') as f:
    data = json.load(f)

# Trajectories are STRINGS, not dicts
for i, t in enumerate(data['reasoning']['trajectories']):
    print(f"=== Trajectory {i+1} ===")
    print(t)  # t is a string

# Deliberation is a LIST of dicts
for d in data.get('deliberation', []):
    print(d.get('deliberation_response', ''))
```

### Step 5: Synthesize and present

Extract consensus points (mentioned by 3+ trajectories) as high-confidence findings.
Points from 1-2 trajectories are worth noting but lower confidence.

## Parameters That Work Well

| Scenario | reason_k | summary_k | Expected time |
|----------|----------|-----------|---------------|
| Quick review | 4 | 2 | ~3 min |
| Standard review | 6 | 3 | ~4 min |
| Deep review | 8 | 4 | ~6 min |

## Verified Results

- Hermes↔Reasonix integration review: 6/6, 58,835 tokens
- delegate_task ACP review: 6/6, 63,564 tokens
- CodeGraph integration review: 6/6, 58,835 tokens
- Financial migration plan review: 6/6, 45,828 tokens (238s)
