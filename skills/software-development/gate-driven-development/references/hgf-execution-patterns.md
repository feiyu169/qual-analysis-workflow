# HGF Execution Patterns — Lessons from Multi-Phase Projects

## Overview

This reference captures proven patterns for executing HGF on multi-phase refactoring projects, learned from real sessions (e.g., downloader refactoring 2026-06-24). Use when the user says "严格按照HGF流程" or "一步一步执行".

---

## Pattern 1: HeavySkill Integration

### Problem
HeavySkill subagents **cannot access local files** (verified 3+ times). They will fabricate responses or report inability to review.

### Solution
Inline all critical information directly in the query:
- Full function signatures from the reference implementation
- Full function signatures from the implementation under review
- Specific comparison tables with status columns

### Query Template
```
技术方案审查：审查[项目名]重构方案。

[参考实现]功能清单（来自[文件名] [行数]行）：
1. function_name(args) -> ReturnType: 说明
2. ...

[当前实现]（[文件名] [行数]行）：
1. function_name: 说明
2. ...

审查点：
1. [具体问题1]
2. [具体问题2]

请逐项核对，给出：
- 功能对齐度评估
- 缺失功能清单（按优先级P0/P1/P2）
- 实施建议
- 风险评估
```

---

## Pattern 2: Deviation Tracking

### When to Track
Every execution step that modifies code must verify against the technical spec.

### Format
After each Gate, record:
```
| # | 偏差 | 原因 | 修复 |
|---|------|------|------|
| 1 | [what deviated] | [root cause] | [fix applied] |
```

### User Communication Rule
If deviation found:
1. **Stop execution**
2. **Report**: "⚠️ 偏差发现: [description]"
3. **Wait for user decision** before continuing
4. **Never silently fix** deviations

---

## Pattern 3: Gate Definition for Refactoring

### Standard Gate Sequence
```
Phase N: Create/modify file
  → Gate N: Syntax check (py_compile)
  → Gate N+1: Import check (all symbols resolve)
  → Gate N+2: Unit tests
  → Gate N+3: Integration test (real API call)
```

### Gate Verification Commands
```bash
# Syntax
python3 -m py_compile file.py

# Imports
python3 -c "from module import Class; print('✅')"

# Unit test (when pytest unavailable)
python3 -c "
import sys; sys.path.insert(0, '/path')
from module import function
assert function('input') == 'expected'
print('✅ passed')
"

# Integration
python3 -c "
from module import Downloader
d = Downloader()
result = d.method(real_query)
assert len(result) > 0
print(f'✅ {len(results)} results')
"
```

---

## Pattern 4: Comparison-Based Review

### When Reference Implementation Exists
1. Read reference first (all signatures, models, error handling)
2. Create comparison table (feature-by-feature)
3. Run HeavySkill with inlined implementations
4. Every ❌ must be resolved before proceeding

### Comparison Table Format
| 功能点 | 参考实现 | 当前实现 | 状态 |
|--------|----------|----------|------|
| func1  | ✅ detail | ✅ detail | ✅ 对齐 |
| func2  | ✅ detail | ❌ 缺失   | ❌ 需补充 |

---

## Pattern 5: HGF Execution Checklist

Before starting:
- [ ] Technical spec exists and is reviewed
- [ ] HeavySkill review completed (with inlined content)
- [ ] All gaps addressed in spec
- [ ] Gate sequence defined
- [ ] Backup of existing files
- [ ] Deviation tracking table ready

During execution:
- [ ] Each file: syntax check passes
- [ ] Each file: imports resolve
- [ ] Each file: matches technical spec
- [ ] Deviations reported immediately
- [ ] User approval for spec changes

After execution:
- [ ] All gates passed
- [ ] Integration test with real data
- [ ] Deviation summary provided
- [ ] Expert review completed

---

## Anti-Patterns

- ❌ **Silent Deviation**: Finding and fixing without telling user
- ❌ **File Path to HeavySkill**: Passing paths expecting it to read them
- ❌ **Skipping Integration Test**: Only syntax checks, no real data
- ❌ **Assuming Spec Complete**: HeavySkill often finds spec gaps
