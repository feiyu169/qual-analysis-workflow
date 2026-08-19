# Technical Proposal Review with K=8 + Third-Party Expert

> Verified: 2026-06-19
> Context: Investment analysis workflow V1.0 → V2.0

## When to Use K=8 for Technical Proposals

For complex technical proposals (15-30K chars), use `--reason_k 8 --summary_k 4` for deeper analysis. This costs ~90K-140K tokens but catches more issues than K=6.

## Review Pipeline

```
V1.0 (Initial) → HeavySkill K=8 → Extract P0/P1 issues
    ↓
Third-Party Expert Review (delegate_task)
    ↓ Extract blocking issues
V2.0 (Revised) → Fix blocking issues
    ↓
HeavySkill K=8 (Final) → Verify fixes + Extract new issues
    ↓
Pass → Implementation
```

## Step 1: HeavySkill Initial Review

```bash
cd ~/.hermes/skills/heavyskill && python3 scripts/run_heavyskill.py \
  --query "$(cat /tmp/review-query.txt)" \
  --include-file /tmp/proposal.md \
  --reason_k 8 --summary_k 4 --language cn \
  --output /tmp/review-v1.json
```

**Query template**:
```
请对以下技术方案进行深度审查，从以下维度评估：
1. 架构设计合理性
2. 代码质量
3. 错误处理
4. 安全性
5. 可测试性
6. 落地可行性

请给出详细的审查意见，包括每个维度的优点和不足、具体的改进建议、总体结论。
```

## Step 2: Third-Party Expert Review

```python
delegate_task(
    goal="你是第三方编程专家，请审查以下技术方案...",
    context="技术方案文件: /tmp/proposal.md",
    toolsets=["file", "terminal"]
)
```

**Expert focuses on**:
- Code quality (async bugs, serialization issues)
- Architecture (enforcement mechanism gaps)
- Error handling (retry/circuit-breaker)
- Security (input validation, key management)
- Testability (mock strategies, coverage)

## Step 3: Fix Blocking Issues

Categorize issues:
- **Blocking** (must fix before re-review)
- **Important** (fix during implementation)
- **Nice-to-have** (fix later)

Fix blocking issues, update proposal.

## Step 4: HeavySkill Final Review

```bash
cd ~/.hermes/skills/heavyskill && python3 scripts/run_heavyskill.py \
  --query "$(cat /tmp/review-query-v2.txt)" \
  --include-file /tmp/proposal-v2-fixed.md \
  --reason_k 8 --summary_k 4 --language cn \
  --output /tmp/review-v2.json
```

## Key Learnings

1. **K=8 is optimal** for technical proposal review (8 trajectories, 4 summary)
2. **Third-party expert catches different issues** than HeavySkill (code bugs vs architecture gaps)
3. **"附意见通过"** is the typical result — almost never clean pass on first review
4. **Blocking issues must be fixed** before second HeavySkill review
5. **Total tokens**: ~90K-140K for K=8 review of 15-30K char proposals
6. **Total time**: ~120-180 seconds per review

## Example Results

| Review | Trajectories | Tokens | Latency | Result |
|--------|-------------|--------|---------|--------|
| V1.0 (Initial) | 8/8 | 94,036 | 121s | 附意见通过 (5 blocking) |
| V2.0 (Final) | 8/8 | 142,339 | 122s | 附意见通过 (3 conditions) |
