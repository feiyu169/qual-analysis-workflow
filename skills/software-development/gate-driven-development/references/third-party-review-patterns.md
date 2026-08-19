# Third-Party Review Patterns

Lessons from gate-driven development sessions where independent reviewer subagents caught issues the implementer missed.

## What Third-Party Review Catches

Based on real sessions, third-party reviewers consistently find:

1. **Duplicate/conflicting instances** — e.g., auth.py creating its own `Limiter` instead of importing from main.py
2. **Incomplete fixes** — e.g., `date_to` fixed with `_parse_date()` but `date_from` still using raw string
3. **Regressions from return type changes** — e.g., `save_upload_file` changed from `str` to `dict`, but one caller not updated
4. **Missing test coverage** — empty test stubs that pass but verify nothing
5. **Configuration not actually applied** — e.g., `DEBUG=false` added to `.env` but Settings class doesn't define `DEBUG`

## Review Checklist Template

When spawning a third-party reviewer, include this checklist:

```
Review dimensions:
1. 准出条件验证 — Did each Gate actually meet its exit criteria?
2. 代码质量 — Syntax errors, type errors, unused imports
3. 安全性评估 — Did fixes actually close the vulnerability?
4. 性能影响 — Did optimizations actually reduce query count?
5. 回归检测 — Did any change break existing functionality?
```

## Common Review Findings by Gate Type

### Security Gates
- CSRF middleware blocks legitimate endpoints (auth, approve)
- Cookie `secure=True` breaks HTTP development
- Rate limiting uses separate instance from app.state

### Performance Gates
- N+1 fix applied to one function but not others in same file
- Batch query missing empty-list guard (`.in_([])` behavior)
- `date_from` not using datetime object (only `date_to` fixed)

### Code Quality Gates
- ORM style inconsistency (some models Column, some mapped_column)
- Unused imports after refactoring
- f-string with backslash (Python <3.12 syntax error)

## Verdict Format

Third-party review should output:
```
结论: 通过 / 有条件通过 / 不通过

必须修复 (Blocker):
1. [描述] — [文件:行号]

建议修复 (Non-blocker):
1. [描述] — [文件:行号]
```

## Pitfalls

### P1: Reviewer can't run code
Third-party reviewers via `delegate_task` only have file access, not terminal. They can read code but cannot execute it. Verification must happen in the parent session after the review.

### P2: Reviewer may miss domain logic
Reviewer catches code-level issues but may miss business logic errors. Always validate domain correctness separately.
