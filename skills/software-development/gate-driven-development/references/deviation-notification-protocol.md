# Deviation Notification Protocol

## User Requirement
When executing a technical plan, **any deviation from the spec must be reported to the user BEFORE proceeding**, not after.

## The Pattern

### What constitutes a deviation:
1. **API contract mismatch**: Spec says endpoint is `/parse`, reality is `/file_parse`
2. **Tool nature mismatch**: Spec assumes Python library, reality is CLI tool
3. **Dependency version conflict**: Required library version not available
4. **Missing capability**: Feature described in spec doesn't exist in the actual tool
5. **Environment constraint**: WSL/permission/container issues blocking execution

### How to notify:
```
⚠️ 偏差通知

**问题**: [clear description of what was expected vs what was found]
**影响**: [what breaks or changes]
**选项**:
- 方案A: [option with pros/cons]
- 方案B: [option with pros/cons]

**等待用户决策后再执行**
```

### What NOT to do:
- ❌ Implement a workaround silently
- ❌ Choose an option for the user
- ❌ Proceed with "best guess"
- ❌ Report deviation after already implementing the fix

### What TO do:
- ✅ Stop execution immediately
- ✅ Clearly state the deviation
- ✅ Present options with trade-offs
- ✅ Wait for explicit user decision
- ✅ Document the deviation in the execution log

## Case Study
In the parser refactor session, we discovered `mineru` was a CLI tool, not a Python library. Instead of silently switching to subprocess, we:
1. Stopped execution
2. Notified user with 3 options (subprocess, FastAPI, pdfplumber fallback)
3. Waited for user to choose (方案B: FastAPI)
4. Only then proceeded with implementation

This earned user trust and avoided implementing the wrong solution.
