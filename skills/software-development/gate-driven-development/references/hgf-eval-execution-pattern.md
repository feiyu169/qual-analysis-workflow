# HGF Eval Execution Pattern

## Overview

Pattern for implementing multi-phase, multi-gate projects using HGF with todo tracking.

## Example: Hermes Eval System (25 gates, 5 phases)

### Phase Structure

```
Phase 1: Foundation (Gates 1-5)
  - Templates, test cases, rubrics, skeleton scripts
  - Verification: files exist + scripts run

Phase 2: Scoring Engine (Gates 6-11)
  - Behavior anchoring, weight templates, judge, classifier
  - Verification: integration test (extract → classify → score → output)

Phase 3: Active Evaluation (Gates 12-15)
  - Examiner spec, examiner script, more test cases
  - Verification: end-to-end loop (exam → judge → score)

Phase 4: Automation (Gates 16-19)
  - GBrain integration, improvement verification, cron, reports
  - Verification: cron job created, report generated

Phase 5: Real Integration (Gates 20-25)
  - Real session transcript, real scoring, MEMORY integration
  - Verification: all tests pass, improvements generated
```

### Todo Tracking Pattern

```python
# Initialize phase
todo(todos=[
    {"id": "G1-1", "content": "[Phase 1 Gate 1] Templates — 4 files", "status": "in_progress"},
    {"id": "G1-2", "content": "[Phase 1 Gate 2] First test case", "status": "pending"},
    # ...
])

# Gate completed
todo(merge=True, todos=[
    {"id": "G1-1", "status": "completed"},
    {"id": "G1-2", "status": "in_progress"}
])

# Phase completed → summary
# [CHECKPOINT] Phase 1: 5/5 gates completed
```

### Verification Pattern

Each gate needs:
1. **Entry criteria**: Previous gate passed
2. **Exit criteria**: Specific, measurable condition
3. **Verification method**: Real execution (not file-existence-only)

```python
# Gate verification example
print("[测试 1] Component Name")
result = subprocess.run([...], capture_output=True, text=True)
if result.returncode == 0:
    print("  ✅ Verification passed")
else:
    print(f"  ❌ Verification failed: {result.stderr}")
```

## Lessons Learned

1. **Start with 2 test cases, not 4** — Validate framework first
2. **Behavior anchoring is critical** — Without 0-5 definitions, variance is high
3. **Hard-pass items need grading** — Must-pass vs should-pass
4. **GBrain needs child pages** — Read-modify-write causes conflicts
5. **Examiner should simulate vague users** — Real users are vague
