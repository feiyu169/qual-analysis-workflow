# HeavySkill Review Examples — Real Session Outputs

## Example 1: Memory System Architecture Review (6 trajectories, 57,934 tokens)

**Query**: 6-dimension review (architecture, data consistency, scalability, security, ops, cost)

**Findings**:
- P0: Sync delay 24h → fix: cron 30min + on_session_end trigger
- P1: Sync coverage incomplete (only records/, not conversations/ scene_blocks/)
- P1: L2→GBrain auto-sync not implemented
- P1: Embed coverage 85.6%
- P1: Sync failure silent loss
- P1: API key file permissions 644
- P1: No process guardian
- P1: Monitor alerts no notification

**Verdict**: 附意见通过

## Example 2: Post-Fix Verification (6 trajectories, 50,267 tokens)

**Query**: Verify P0/P1 fixes, check new risks

**Findings**:
- R2-1: Concurrent sync conflict (Cron + on_session_end) → fix: flock mutex
- R2-2: Monitor threshold still 25h → fix: change to 1h
- R2-3: on_session_end --limit 50 → fix: remove limit

**Verdict**: 附意见通过

## Example 3: Experience Engine Design Review (dual expert, 178s)

**Programming Expert findings (4 P0, 6 P1)**:
- P0: dataclass defined but never used
- P0: SQLite connection leak (no context manager)
- P0: _update_error_occurrence string replace bug
- P0: Zero test coverage

**Architecture Expert findings (5 P0, 6 P1)**:
- P0: God Object (6 responsibilities in 1 class)
- P0: Dual storage no consistency (GBrain + SQLite)
- P0: Pending files no consumer
- P0: No concurrency safety
- P0: Multi-profile not considered

## Example 4: Post-Refactor Verification (6 trajectories, 115,283 tokens)

**Query**: Verify all P0/P1 fixes in v2

**Findings**:
- 18/21 items fully fixed
- 3 items partially fixed (P0-5 WAL coverage, P0-9 pending dir, P1-8 migration)
- 6 minor risks identified (all low impact, controllable)

**Verdict**: 附意见通过 (with 3 improvement items)

## Token Cost Reference

| Document Size | Trajectories | Tokens | Latency |
|---------------|-------------|--------|---------|
| 5-10K chars   | 6           | 40-50K | 100-120s |
| 40K chars     | 6           | 90-115K | 160-200s |
