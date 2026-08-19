# HeavySkill Review Query Construction

## Effective Query Pattern

HeavySkill cannot access local files. All context must be **inline in the query**.

### Structure that works:
```
技术方案审查：[方案名称]

审查原则：[user's principle, e.g., "对照dayu-agent解析器实现的功能，一一核对"]

[方案核心变更 - bullet list]
1. 变更1
2. 变更2

[功能对照清单 - numbered list]
1. 功能点A
2. 功能点B

审查点：
1. 具体问题1？
2. 具体问题2？

请给出[具体期望的输出格式]
```

### What to include in the query:
- **Complete function signatures** (not just names)
- **Data class field definitions** (not just class names)
- **Error handling patterns** (exception types, retry logic)
- **File type support lists** (explicit extensions/MIME types)
- **Configuration parameters** (env vars, defaults, ranges)

### What NOT to rely on:
- ❌ File paths (HeavySkill can't read them)
- ❌ "See document X for details" (must inline the details)
- ❌ Assumptions about what HeavySkill "already knows"

### Iteration pattern:
Round 1: Submit spec → Get findings
Round 2: Fix findings, resubmit → Get remaining issues
Round 3: Fix remaining → Usually passes

**Typical cycle: 2-4 rounds** before HeavySkill approves.

### K value guidance:
- K=8: Standard review (recommended)
- K=16: Critical review (more thorough but slower)
- K=4: Quick check (not recommended for important decisions)

## User Preference
User demands "全面审慎，不得隐瞒欺骗" (thorough, no concealment, no deception). HeavySkill queries must reflect this by including all relevant details, not hiding known gaps.
