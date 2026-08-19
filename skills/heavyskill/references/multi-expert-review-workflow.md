# Multi-Expert Review + Delivery Workflow

## Pattern

When the user asks to "review with experts" or "审查方案", use this workflow:

### Step 1: Generate Proposal
Write the proposal/analysis to a temp file:
```python
# Use write_file or execute_code to create
write_file(path="/tmp/proposal.md", content=proposal_content)
```

### Step 2: HeavySkill Review
Run HeavySkill with `--include-file`:
```bash
cd ~/.hermes/skills/heavyskill && python3 scripts/run_heavyskill.py \
  --query "请审查以下方案，从技术可行性、架构设计、工作流完整性、安全性、成本效益、风险遗漏 6 个维度评估" \
  --include-file /tmp/proposal.md \
  --reason_k 6 --summary_k 3 --language cn \
  --output /tmp/review.json
```

### Step 3: Extract & Deliver
Parse the JSON and send via messaging:
```python
import json
with open('/tmp/review.json') as f:
    data = json.load(f)
# Key fields:
# - data['final_answer'] — summary (may be low quality)
# - data['consensus_answer'] — consensus across trajectories
# - data['reasoning']['trajectories'] — list of full review strings
```

**Delivery to messaging platforms:**
- Split into multiple messages (~1500 chars each)
- First message: overview + consensus
- Subsequent messages: detailed review sections
- Last message: action items / confirmation request

### Example Prompt Template
```
你是一个技术方案审查专家。请审查以下方案，从以下维度评估：
1. 技术可行性
2. 架构设计
3. 工作流完整性
4. 安全性
5. 成本效益
6. 风险遗漏

对每个维度给出：评估、问题、改进建议。
```

## Pitfalls

1. **HeavySkill has no tool access** — MUST use `--include-file` to embed file content
2. **trajectories are strings, not dicts** — Access as `data['reasoning']['trajectories'][i]` directly
3. **final_answer may be garbage** — Use `consensus_answer` or extract from trajectories
4. **WeChat message limit** — Split long reviews into multiple messages
5. **Timeout on complex reviews** — Use `--reason_k 4 --summary_k 2` for faster results
