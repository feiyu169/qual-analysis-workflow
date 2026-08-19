# HeavySkill Test Plan Review Pattern (Verified 2026-06-17)

## Use Case

HeavySkill can review test plans, not just technical specs. Use when:
- Test plan needs comprehensive coverage validation
- Multiple stakeholders need to agree on test priorities
- Test plan has complex business logic to verify

## How to Invoke

```bash
cd ~/.hermes/skills/heavyskill && python3 scripts/run_heavyskill.py \
  --query "请审查这个测试补充方案。从以下6个维度进行深度审查：
1. 完整性：测试用例是否覆盖了设计文档中的所有业务场景？
2. 优先级合理性：P0/P1/P2 的划分是否合理？
3. 可执行性：测试用例的步骤是否清晰可执行？
4. 风险覆盖：是否覆盖了生产环境的主要风险点？
5. 测试数据需求：需要准备哪些测试数据？
6. 改进建议：有哪些可以优化或补充的地方？" \
  --include-file /tmp/test-plan.md \
  --reason_k 6 --summary_k 3 --language cn \
  --output /tmp/test-review-result.json \
  --quiet
```

## Key Parameters

- `--reason_k 6`: 6 trajectories for diverse perspectives
- `--summary_k 3`: 3 summaries to capture consensus
- `--language cn`: Better for Chinese test plans
- `--include-file`: Test plan file (must be self-contained)

## Processing Output

1. Read trajectories: `data['reasoning']['trajectories']`
2. Each trajectory is a STRING (not dict)
3. Extract findings by searching for:
   - `P0` / `P1` / `P2` severity markers
   - `完整性` / `优先级` / `可执行性` / `风险` / `测试数据` / `改进建议`
   - Lines with `|` delimiter containing severity
4. Look for consensus across trajectories (high agreement = high confidence)

## Real Example (2026-06-17)

**Input**: Test plan for 异常管理系统 (30 test cases)
**Output**: 6/6 trajectories successful, 54,340 tokens, 158 seconds

**Key Findings**:
- 预警提醒模块完全缺失（6/6 共识，最大遗漏）
- 管理员/系统管理员功能未测试（5/6 共识）
- 前端测试空白（5/6 共识）
- 测试数据准备方案缺失（5/6 共识）
- 可执行性细节不足（5/6 共识）

**Priority Adjustments**:
- TC49 取消异常: P1 → P0
- TC50 撤回异常: P1 → P0
- TC61 重复提交: P1 → P0
- TC62 并发接收: P1 → P0
- TC63 并发处置: P1 → P0
- TC66 操作日志完整性: P1 → P0

**New Test Cases Added**: 14 (预警提醒 5, 管理功能 3, 安全测试 2, 状态机补充 2, 权限测试 2)

## Test Plan Review Checklist

When reviewing test plans, HeavySkill checks:

### 1. 完整性
- 状态机所有转换路径是否覆盖？
- 分支流程是否完整？
- 边界条件是否考虑？
- 异常场景是否覆盖？

### 2. 优先级合理性
- P0 是否涉及核心业务流程？
- P0 是否涉及安全风险？
- P0 是否涉及数据完整性？
- P1/P2 划分是否合理？

### 3. 可执行性
- 步骤是否清晰？
- API 端点是否明确？
- 前置条件是否说明？
- 预期结果是否量化？

### 4. 风险覆盖
- 权限越权风险？
- 并发冲突风险？
- 数据一致性风险？
- 业务连续性风险？

### 5. 测试数据需求
- 用户数据准备？
- 异常数据准备？
- 基础数据准备？
- 数据依赖关系？

### 6. 改进建议
- 缺失的测试用例？
- 优先级调整建议？
- 可执行性改进？
- 风险覆盖补充？

## Pitfalls

1. **Test plan must be self-contained**: HeavySkill cannot access external files. Include all context in the test plan file.

2. **Include design document**: Test plan should reference or include the design document for context.

3. **Include existing test results**: If some tests already passed, include results to avoid re-testing.

4. **Consensus across trajectories**: If 5/6 trajectories agree on a finding, it's high confidence. If only 2/6, it's lower confidence.

5. **Priority adjustments**: HeavySkill may suggest priority changes. Always validate against business requirements.

## Output Format

```markdown
## HeavySkill Test Plan Review Summary

### Consensus Findings (5/6+ trajectories)
| Finding | Consensus | Importance |
|---------|-----------|------------|
| 预警提醒模块缺失 | 6/6 | 🔴 极高 |
| 管理员功能未测试 | 5/6 | 🟡 中高 |

### Priority Adjustments
| Test Case | Current | Suggested | Reason |
|-----------|---------|-----------|--------|
| TC49 | P1 | P0 | 核心业务流程 |

### New Test Cases
| ID | Name | Priority | Description |
|----|------|----------|-------------|
| TC73 | 新异常提醒 | P0 | 上报后接收人收到通知 |

### Coverage Assessment
- Before: 70%
- After: 90%
```
