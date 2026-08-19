# User Technical Proposal Review Pattern

## Overview

When presenting a technical proposal for user review, expect a structured 7-category feedback format. This pattern is verified from user reviews of complex multi-phase proposals.

## User Review Format

The user reviews proposals with this structure:

```
✅ 完全同意（N项）
- Item 1: [reason]
- Item 2: [reason]

⚠️ 需讨论（N项）
- Item N: [specific concern + suggested fix]

❌ 不同意（N项）
- Item N: [reason + alternative]
```

## Key Corrections to Expect

### 1. Risk Assessment: Never "无风险"

User will reject "无风险" (no risk) assessments. Always use:
- "低风险" + 已知未知清单 (known unknowns)
- Each project/component gets a table: 风险等级 | 已知未知清单 | 缓解措施

**Template:**
```markdown
| 项目 | 风险等级 | 已知未知清单 | 缓解措施 |
|------|---------|-------------|---------|
| X    | 低      | ① 依赖安全 ② 性能 ③ 兼容性 | ① audit ② benchmark ③ test |
```

### 2. Data Validation: Cross-Validate Everything

User will flag any unverified data. Required actions:
- Stars counts: use GitHub API (`curl -s "https://api.github.com/repos/owner/repo" | python3 -c "import sys,json; print(json.load(sys.stdin)['stargazers_count'])"`)
- Baseline metrics: mark as "实测值" or "估算值"
- Comparison data: verify consistency across sources

### 3. Conflict Analysis: Multi-Dimensional

User expects detailed conflict analysis, not one-liner mitigations. For memory system conflicts:

```markdown
| 冲突类型 | 风险描述 | 缓解策略 |
|---------|---------|---------|
| 双写冲突 | 系统A和B写入路径不同 | 分层隔离 |
| 检索冲突 | A图遍历 vs B向量检索 | 统一检索接口 |
| 存储膨胀 | 多种存储同时增长 | 容量预算+衰减 |
| 版本控制冲突 | 各有版本控制 | 统一版本时间线 |
```

### 4. Downgrade Overconfident Claims

User will reject overconfident assertions. Preferred pattern:

| 原断言 | 修正后 |
|--------|--------|
| "X优于Y" | "X方向与Y吻合，模块化程度较高，但功能覆盖不及Y" |
| "无风险" | "低风险+已知未知清单" |
| "基线: ~60%" | "基线: ~60%（估算值，待实测）" |

### 5. Priority Reordering

User may request timeline changes (e.g., moving research tasks earlier). Accept and adjust.

## Incorporating Feedback

After receiving review feedback:

1. **Acknowledge each category** (完全同意/需讨论/不同意)
2. **Merge all corrections** into the original document (not as appendix)
3. **Update version** (v1.0 → v2.0)
4. **Add review record** with version history
5. **Re-present** for final approval

**Critical:** Fixes must be merged INTO the original document, not appended as a separate section. User explicitly rejects "V2 修订说明" appendix pattern.

## Verification Checklist

Before presenting a proposal:
- [ ] No "无风险" assessments exist
- [ ] All data has source annotations (实测/估算)
- [ ] Conflict analyses have multi-dimensional tables
- [ ] Claims are appropriately hedged
- [ ] Baseline metrics are cross-validated
