# HeavySkill Proposal Review Pattern

## Overview

HeavySkill can be used as an **automated expert reviewer** for technical proposals, architectural designs, and workflow specifications. This pattern uses multiple parallel trajectories to simulate diverse expert perspectives.

## Workflow

### Step 1: Prepare the Proposal

Write the proposal to a temporary file:
```bash
cat > /tmp/proposal.md << 'EOF'
# Proposal Title
...content...
EOF
```

### Step 2: Design Review Questions

Structure the query with **6 specific dimensions**:
```
请审查以下方案，从以下6个维度评估：
1. [维度1]：[具体问题]
2. [维度2]：[具体问题]
3. [维度3]：[具体问题]
4. [维度4]：[具体问题]
5. [维度5]：[具体问题]
6. [维度6]：[具体问题]

请给出详细的审查意见，包括优点、不足、改进建议。
```

### Step 3: Execute Review

```bash
cd ~/.hermes/skills/heavyskill && python3 scripts/run_heavyskill.py \
  --query "审查问题" \
  --include-file /tmp/proposal.md \
  --reason_k 6 --summary_k 3 --language cn \
  --output /tmp/review.json
```

### Step 4: Parse Results

Key fields in the JSON output:
- `reasoning.trajectories[]` - Individual review trajectories (the real content)
- `deliberation[0].deliberation_response` - Synthesized review
- `cache_stats.consensus_answer` - Key consensus point

### Step 5: Iterate

Based on review findings:
1. Address P0 issues first
2. Update the proposal
3. Re-run HeavySkill review
4. Repeat until all trajectories converge on "通过"

## Review Dimensions by Proposal Type

### Architecture Review
1. 流程设计的合理性
2. 模块划分的清晰度
3. 接口设计的标准化
4. 安全性的完整性
5. 可扩展性
6. 可观测性

### Workflow Review
1. 流程设计的完整性
2. 任务分级的准确性
3. 风险评估的全面性
4. 质量门禁的有效性
5. 失败处理机制
6. 可行性与落地性

### Code Review
1. 代码质量
2. 安全性
3. 性能
4. 可维护性
5. 测试覆盖
6. 文档完整性

## Iteration Pattern

```
V1 → HeavySkill Review → 发现6个问题 → 修改
V2 → HeavySkill Review → 发现3个问题 → 修改  
V3 → HeavySkill Review → 无阻塞性问题 → 通过
```

**Convergence indicator**: When trajectories say "观点高度收敛" or "未发现明显逻辑错误", the proposal is ready.

## Pitfalls

### P0: Don't Trust Final Answer
The `final_answer` field is often a generic summary. The real review content is in `reasoning.trajectories[]`. Always read the trajectories.

### P1: Parse Trajectories Carefully
Trajectories are raw text, not structured JSON. Use string parsing to extract:
- 优点 (advantages)
- 不足 (disadvantages)  
- 改进建议 (improvement suggestions)

### P2: Chinese Language Works Best
For Chinese proposals, use `--language cn`. The review quality is significantly better than English reviews of Chinese content.

### P3: 6 Trajectories is Optimal
- `reason_k=6` provides diverse perspectives
- `summary_k=3` synthesizes the best insights
- Lower values miss important viewpoints
