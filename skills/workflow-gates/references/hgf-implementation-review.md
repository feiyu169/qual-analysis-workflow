# HGF Implementation Code Review (2026-07-10)

## Review Summary
Full code review of `~/.hermes/workflow/` implementation against standard SE practices.
- Expert score: 50/100 (before fixes)
- Issues found: 35 (7 P0, 14 P1, 14 P2)
- Issues fixed: 27/35
- Tests after fixes: 75/75 passing

## Key Findings

### Critical Issues Found & Fixed
1. `_verify_criteria()` returned True unconditionally — entire gate mechanism was non-functional
2. L3/L4/L5 verification engines returned passed=True without doing anything
3. `failure_count` double-incremented on each failure (execute_gate + handle_failure both counted)
4. `reset_gate()` bypassed terminal state protection (PASSED gates could be reset)
5. SQLite connections leaked on exceptions (no context manager)
6. `shell=True` in subprocess calls — command injection risk
7. Variable shadowing in verify loop (`result` parameter overwritten)

### Unfixed P2 Issues (8 items, low risk)
- SQLite row field ordering (use sqlite3.Row)
- Coverage report parsing (use JSON format)
- .json file type priority in change detection
- Plugin registration with empty config
- Default config path hardcoded
- Timeout string format support
- Config-code threshold duplication

## Standard SE vs HGF Comparison

| Dimension | Standard SE | HGF |
|-----------|------------|-----|
| Flow completeness | 6 phases | 6 Phases, 16 Gates |
| Security built-in | Post-hoc | Every Phase has security Gates |
| Automation | Low | Medium (some stubs) |
| Traceability | Documents | State machine + SQLite |
| Flexibility | High | Low (rigid Gates) |
| Practical usability | High | Medium (implementation gaps) |

## Lesson Learned
Design diagrams can be excellent while implementation quality is poor. The HGF architecture (state machine + plugin + classifier) was well-designed, but 3/5 verification engines were empty stubs. Always verify implementation completeness against design intent.
