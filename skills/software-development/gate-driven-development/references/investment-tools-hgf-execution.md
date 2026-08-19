# Investment Tools HGF Execution Reference

> Verified: 2026-06-19
> Context: 投资分析工作流保障层 — 7 modules, 87 tests, 3-round HeavySkill review

## Architecture

```
~/.hermes/tools/investment/
├── field_mapping.py          # 55 fields (CN↔EN), FCF fields, unmapped warnings
├── circuit_breaker.py        # Thread-safe, state machine, half_open counting
├── stage_manager.py          # SQLite + optimistic lock + circuit breaker integration
├── report_linter.py          # 7 sections, 4 elements, forbidden patterns
├── mcp_health_checker.py     # HTTP /health → TCP → pgrep -x (3-tier fallback)
├── validate_financials.py    # Wind vs dayu consistency, P1-B critical field blocking
├── finance_calc.py           # WACC (tax shield cap), DCF (Gordon), sensitivity
└── tests/                    # 87 tests total
```

## Gate Execution Order (with dependencies)

```
Gate 1: field_mapping.py       ← no deps
Gate 2: circuit_breaker.py     ← no deps
Gate 3: stage_manager.py       ← Gate 1 + Gate 2
Gate 4: report_linter.py       ← no deps
Gate 5: mcp_health_checker.py  ← no deps
Gate 6: validate_financials.py ← Gate 1
Gate 7: finance_calc.py        ← no deps
Gate 8: integration test       ← Gate 1-7
```

## Key Design Decisions

1. **SQLite optimistic lock** over SELECT FOR UPDATE (SQLite doesn't support it)
2. **threading.Lock class-level** (all instances share) — correct for single-process
3. **Circuit breaker per-session** (`mcp_{session_id}`) — isolation between analyses
4. **P1-B critical field blocking** — revenue/net_profit/total_assets/total_equity missing → fail
5. **HTTP health endpoint** preferred over TCP port check — catches zombie processes
6. **WACC tax shield cap** — `ebit * max_interest_deduction_ratio` (default 30%)

## Pitfalls Encountered

1. **Optimistic lock merge bug** (P0): save local state BEFORE load_state()
2. **numpy hard dependency** in _json_serializer → use try/except
3. **socket resource leak** in _check_port → use try/finally
4. **Near-zero denominator** in validate_financial_logic → abs threshold guard
5. **fields_missing count** wrong in P1-B path → count issues, not warnings

## Review History

| Round | Reviewer | Score | Issues Found |
|-------|----------|-------|--------------|
| V3.0 | Programming Expert | 6.5/10 | 5 P0 + 7 P1 |
| V4.0 | HeavySkill 6轨迹 | 6.5/10 | 3 new P0 |
| V5.0 | HeavySkill 6轨迹 | 7.0/10 | 2 P1 |
| Code | Programming Expert | 7.5/10 | 1 P0 + 5 P1 |
| Final | All tests pass | 87/87 | 0 remaining |
