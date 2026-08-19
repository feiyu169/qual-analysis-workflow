# HeavySkill Code Review Patterns (verified 2026-07-10)

## Effective Query Template
```
你是资深代码审查专家。请对以下代码进行 K=8 多轨迹审查。
审查维度：正确性、安全性、可靠性、架构、可维护性。
逐文件给出 P0/P1/P2 问题，每个问题包含：文件名、行号、问题描述、修复建议。
最后给出整体评分(0-100)和Top5优先修复项。
```

## Key Learnings
1. **Inline ALL code** - sub-agents cannot read local files
2. **K=8 recommended** - K=4 misses cross-file issues
3. **timeout=180 required** - K=8 takes ~155s measured (247K tokens)
4. **Extract from trajectories** - deliberation output may be garbled
5. **Consensus threshold** - 7/8+ agreement = high confidence finding

## Expected Output Quality
- K=8 finds ~15 issues with high consensus
- Score converges across trajectories (±5 points)
- P0 findings have 8/8 consensus
- P1 findings have 5-7/8 consensus

## Real Example: HGF Code Review
- Input: 7 Python files, ~2500 lines
- Output: 15 issues found, score 72/100
- Consensus: 8/8 on P0s, 6/8 on P1s
- Total tokens: 247,213
- Total latency: 155.26s
