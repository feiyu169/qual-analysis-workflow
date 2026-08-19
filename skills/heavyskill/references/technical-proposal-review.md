# Technical Proposal Review with HeavySkill

## Workflow

### Step 1: Prepare Review Material

Create a comprehensive markdown file with:
1. Problem summary (from testing or requirements)
2. Technical proposals (one per problem)
3. Code examples
4. Implementation timeline
5. Review questions (6 dimensions)

### Step 2: Run HeavySkill

```bash
cd ~/.hermes/skills/heavyskill && python3 scripts/run_heavyskill.py \
  --query "请审查这个技术方案。从以下6个维度进行深度审查：
1. 完整性：技术方案是否覆盖了所有发现的问题？
2. 可行性：技术方案是否可行？是否有技术风险？
3. 优先级合理性：优先级划分是否合理？
4. 工作量估算：工作量估算是否准确？
5. 实施风险：实施过程中可能遇到哪些风险？
6. 改进建议：有哪些可以优化或补充的地方？" \
  --include-file /tmp/review-material.md \
  --reason_k 6 --summary_k 3 --language cn \
  --output /tmp/review-result.json \
  --quiet
```

### Step 3: Extract Key Findings

```python
import json

with open('/tmp/review-result.json', 'r') as f:
    data = json.load(f)

trajectories = data.get('reasoning', {}).get('trajectories', [])

# Extract consensus findings
for i, traj in enumerate(trajectories, 1):
    print(f"轨迹 {i}: {len(traj)} 字符")
    print(traj[:1500])
```

### Step 4: Generate Summary Report

Consolidate findings into:
1. Consensus analysis (what all trajectories agree on)
2. Critical issues (must fix)
3. Recommendations
4. Revised estimates

## Proven Results (2026-06-17)

- Test plan review: 6/6 trajectories, 54,340 tokens, 158.75s
- Technical proposal review: 6/6 trajectories, 49,248 tokens, 86.06s

## Common Findings Pattern

When reviewing technical proposals, HeavySkill typically identifies:
1. **Missing features** not covered in proposals
2. **Technical risks** in implementation approach
3. **Work underestimation** (usually 30-50% more than proposed)
4. **Security concerns** in design
5. **Performance implications** not considered
