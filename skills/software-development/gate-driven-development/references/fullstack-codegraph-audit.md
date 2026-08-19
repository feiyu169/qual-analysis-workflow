# Fullstack CodeGraph Audit + Plan-vs-Actual Gap Analysis

## When to Use
- User asks to "review", "audit", or "审查" a project
- User asks to compare implementation against a design plan
- Post-implementation quality gate before deployment

## Phase 1: CodeGraph Index + Structure Analysis

```bash
cd /path/to/project && codegraph init -i
```

Then in parallel:
```
codegraph_files(includeMetadata=true)   → project structure, file counts, languages
codegraph_status()                      → index health, node/edge counts
codegraph_context(task="overall architecture") → entry points + related symbols + key code
```

**Key metrics to capture:**
- Total files / nodes / edges (complexity indicator)
- Languages breakdown (multi-language projects need cross-language tracing)
- Node kinds: class, function, method, route, component (architecture shape)

## Phase 2: Deep Exploration (Selective)

Use `codegraph_explore` grouped by concern:
```
codegraph_explore(query="models services config auth_utils")  → backend core
codegraph_explore(query="api routes endpoints")               → API surface
codegraph_explore(query="views components router")            → frontend
```

For critical flows, use `codegraph_trace`:
```
codegraph_trace(from="create_exception", to="notify_assign_task") → end-to-end flow
```

For change impact:
```
codegraph_impact(symbol="ExceptionRecord", depth=2) → blast radius
```

## Phase 3: Plan-vs-Actual Gap Analysis

### Step 1: Locate the design plan
Search in order: session_search → flomo memo_search → GBrain query → local docs/

### Step 2: Extract plan commitments
Create a checklist from the plan:
- Features promised (with acceptance criteria)
- API endpoints specified
- Database models/fields listed
- Documentation deliverables
- Security requirements

### Step 3: Systematic verification
For each commitment, verify against codegraph results:
```
| # | Plan Item | Code Location | Status | Gap |
|---|-----------|---------------|--------|-----|
| 1 | Feature X | service.py:45 | ✅ Done | — |
| 2 | Feature Y | — | ❌ Missing | Only field exists, no logic |
| 3 | API /foo | api/foo.py:12 | ⚠️ Stub | Returns 501 |
```

### Step 4: Classify gaps
- **P0 (Blocking)**: Security issues, data loss risks, core features broken
- **P1 (High)**: Missing documentation, incomplete features
- **P2 (Medium)**: Code quality, performance, error handling
- **P3 (Low)**: Style, dedup, nice-to-haves

### Step 5: Generate improvement plan
Write to `docs/IMPROVEMENT_PLAN.md` with:
- Phased execution order (P0 first)
- Gate definitions per phase
- Verification criteria

## Phase 4: Memory System Update

Save findings to all three memory layers:
```
flomo: memo_create(摘要 + 关键发现)     → user-visible
GBrain: put_page(完整审查记录)          → structured knowledge
MEMORY: pointer to flomo/GBrain         → session hot state
```

## Pitfalls

### P1: "Field exists" ≠ "Feature complete"
A model column or retry_count/version field existing does NOT mean the business logic uses it.
Check: grep for actual usage of the field in service/API code.

### P2: Expert review catches what implementation misses
The delegate_task expert review found 2 blocking issues:
- to_dict() missing version field → optimistic lock completely non-functional
- _record_notification() defined but never called → retry mechanism is a dead shell
**Always run expert review between phases.**

### P3: Notification status enum inconsistency
When multiple code paths create Notification records, ensure they use the same status values.
Found: scheduler used Chinese '成功'/'失败', service used English 'sent'/'failed'.
Retry logic queries English values → scheduler-created failures never retried.
**Checklist: grep for all Notification() constructors and verify consistent enum values.**

### P4: Security redaction blocks config writes
When writing config files with secrets (SECRET_KEY, JWT_SECRET_KEY), the security.redact_secrets
feature replaces values with `***` in write_file output. The file content becomes syntactically broken.

**Workaround**: Use patch() for targeted edits instead of full file rewrites.
Or accept that dev-default values in config.py are display-masked but functionally correct.

### P5: Optimistic lock needs DB-level atomicity
Python-level version check (if exception.version != expected) has a TOCTOU race:
two requests can read the same version and both pass. The UPDATE must include WHERE version=N.
For SQLite, this means: `UPDATE ... WHERE id=? AND version=?` then check rowcount.
