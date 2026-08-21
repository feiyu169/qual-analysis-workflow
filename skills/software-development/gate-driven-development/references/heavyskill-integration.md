# HeavySkill Integration Patterns

## Invocation Template

```bash
cd ~/.hermes/skills/heavyskill && python3 scripts/run_heavyskill.py \
  --query "审查以下 [方案名称]，从以下 N 个维度评估：
1. [维度1]：[具体问题]
2. [维度2]：[具体问题]
...
请给出详细的审查意见，包括优点、不足、改进建议。" \
  --include-file /path/to/proposal.md \
  --reason_k 6 --summary_k 3 --language cn \
  --output /tmp/[name]-review.json
```

## Parameter Guide

| Parameter | Recommended Value | When to Adjust |
|-----------|-------------------|----------------|
| `--reason_k` | 6 | Increase for more diverse perspectives |
| `--summary_k` | 3 | Keep at 3 for balanced synthesis |
| `--language` | cn | Match proposal language |
| `--include_file` | proposal.md | Include all relevant context |

## Output Processing

```python
import json

with open('/tmp/review-result.json') as f:
    data = json.load(f)

# Trajectories are STRINGS, not dicts
trajectories = data['reasoning']['trajectories']
for i, t in enumerate(trajectories):
    # Find conclusion by keyword search
    for kw in ['总体结论', '评审结论', '总体评审', '附意见通过', '不通过', '通过']:
        if kw in t:
            idx = t.rindex(kw)
            print(t[max(0,idx-100):min(len(t), idx+1500)])
            break
    else:
        print(t[-500:])  # Last 500 chars as fallback

# final_answer is often just a summary intro, NOT the full conclusion
# The real review content is in trajectories
# consensus_answer may be truncated — don't rely on it alone
```

## Common Review Dimensions

### Architecture Review
1. 模块划分的合理性
2. 接口设计的标准化
3. 可扩展性
4. 安全性

### Code Quality Review
1. 代码正确性
2. 错误处理
3. 测试覆盖率
4. 命名规范

### Workflow Review
1. 流程设计的完整性
2. 分级规则的准确性
3. 风险评估的全面性
4. 质量门禁的有效性
5. 失败处理机制
6. 可行性与落地性

## Iteration Pattern

```
V1 → HeavySkill(6 trajectories) → Extract findings
V2 → Address P0/P1 findings → HeavySkill(6 trajectories) → Verify fixes
V3 → Address remaining findings → HeavySkill(6 trajectories) → Final check
```

Each iteration costs ~60-90 seconds and ~50-80K tokens.

## Pitfalls

1. **Over-reliance on consensus**: If all 6 trajectories agree, it's likely correct. But check for correlated blind spots.

2. **Token budget**: Each HeavySkill run uses 50-80K tokens. Don't run on trivial changes.

3. **Language mismatch**: Always match `--language` to proposal language for accurate keyword analysis.

4. **Missing context**: Use `--include_file` for the FULL proposal. Partial context leads to partial reviews.

5. **Ignoring minority opinions**: The 1 dissenting trajectory may have caught something the 5 others missed.

6. **Trajectory content is strings, not dicts**: `data['reasoning']['trajectories']` returns a list of plain strings, NOT structured objects. Parse by keyword search (e.g., `t.rindex('总体结论')`), not by dict key access. The `final_answer` field is often just a one-line summary intro — the actual review content lives in the trajectory strings. The `consensus_answer` field may be garbage (previously also truncated) — **always check `data['truncation']` first** (added 2026-08-21, P54): if `reasoning_truncated_count > 0` or `deliberation_truncated` is true, re-run with larger `--max-tokens`/`--summary-max-tokens` or explicitly mark the result as partial. Truncated trajectories are now excluded from deliberation/consensus automatically.
