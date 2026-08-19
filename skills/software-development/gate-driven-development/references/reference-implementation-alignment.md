# Reference Implementation Alignment — HGF Pattern

**Session**: 2026-06-24 downloaders refactoring (Dayu-agent alignment)
**Pattern**: Systematic function-by-function comparison with a reference codebase

## When to Use

- Refactoring existing code to match a proven reference implementation
- Migrating from one library/architecture to another while preserving functionality
- Ensuring feature parity between two codebases

## Workflow

### Phase 0: Reference Analysis
1. Read ALL reference source files completely (not just signatures)
2. Catalog every public function, class, constant, and type
3. Note line numbers for each implementation (for citation during review)

### Phase 1: Gap Analysis Document
Create a technical document with:
- Function-by-function comparison table (Reference vs Target)
- Each row: function name, reference location (file:line), target status (✅/⚠️/❌)
- Explicit "implementations notes" for each gap

### Phase 2: HeavySkill Review Cycle
```
Draft v1 → HeavySkill K=8 review → Fix gaps → Draft v2 → HeavySkill K=8 review → ... → Approve
```
- Use K=8 (standard quality)
- Inject domain-specific checklist into query
- Each review must compare against reference implementation
- Iterate until all gaps are closed

### Phase 3: HGF Gate Execution
Execute per the standard HGF flow:
- Gate per module: syntax check (py_compile)
- Gate for unit tests: all helper functions
- Gate for integration tests: **real API calls** (not mocks)

## Critical Pitfalls

### Pitfall 1: Priority in Data Merging
When merging data from multiple sources where priority matters:
```python
# WRONG — later source overwrites earlier
mapping[code] = entry

# CORRECT — first source wins (active over inactive)
mapping.setdefault(code, entry)
```
**Caught by**: Real API integration test (HKEX active vs inactive stock lists)

### Pitfall 2: "Implementation Notes" ≠ "Implementation"
Writing `# implementation略` in a technical document is NOT acceptable for P0 items.
Every function that will be called at runtime must have complete code in the spec.

### Pitfall 3: Inactive Overwriting Active
When fetching from multiple API endpoints (e.g., active + inactive stock lists),
always process the authoritative source FIRST and use `setdefault` to prevent
non-authoritative data from overwriting.

### Pitfall 4: Integration Tests Must Use Real APIs
Mock-based tests would NOT have caught the active/inactive stock priority bug.
Integration tests must hit real endpoints (with rate limiting) to catch data-level issues.

## Review Checklist for Reference Alignment

- [ ] Every function in reference has corresponding implementation
- [ ] Every constant/type in reference is defined
- [ ] Data merging uses correct priority (setdefault for first-seen-wins)
- [ ] Integration test uses real API, not mock
- [ ] HeavySkill review completed with K=8
- [ ] All P0 gaps closed before proceeding to implementation
