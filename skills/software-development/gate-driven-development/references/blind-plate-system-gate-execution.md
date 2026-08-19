# Blind Plate System — Gate-Driven Security Fix Execution

Project: ~/blind-plate-system (Vue3 + Vant4 + FastAPI + MySQL)
Original audit score: 5.3/10
Post-fix score: 7.9/10
GitHub: https://github.com/feiyu169/blind-plate-system (private)
Deployed: http://101.43.83.237 (Tencent Cloud OpenCloudOS)
systemd: /etc/systemd/system/blind-plate.service
Nginx: /etc/nginx/conf.d/blind-plate.conf

## Phase 1: Security Fixes (4 gates)

G1-1: JWT Secret Key Hardening
  - Status: PASS
  - What existed: config.py already had validator (≥32 chars + "change-me" check)
  - Verification: Tested 5 scenarios (short, placeholder, normal, .env fallback, missing)
  - Pitfall: Pydantic reads .env even when env var is absent (P13)

G1-2: Admin Password Hardening
  - Status: CONDITIONAL PASS
  - What existed: No default value, validator ≥8 chars
  - Missing: No random password generation on first start
  - Decision: Core security requirement met via env var enforcement

G1-3: Create .gitignore
  - Status: CONDITIONAL PASS
  - Created: Root .gitignore covering .env, *.db, __pycache__/, venv/, uploads/
  - Issue: `git rm --cached` blocked by approval system (P11)

G1-4: Cookie Secure Flag
  - Status: PASS
  - Added: USE_HTTPS config option, secure=settings.USE_HTTPS in auth.py

## Phase 2: Performance & Security Hardening (4 gates)

G2-1: N+1 Query Optimization
  - Status: PASS
  - Files: audit.py (get_pending + get_audit_history), notifications.py
  - Pattern: Batch dict loading (see n1-batch-optimization-pattern.md)
  - Pitfall: get_audit_history missed on first pass, caught by third-party reviewer (P6)

G2-2: CORS Precise Configuration
  - Status: PASS
  - Changed: allow_methods/allow_headers from ["*"] to explicit lists via config

G2-3: File Upload Security
  - Status: PASS
  - Added: check_magic_bytes() function for JPEG/PNG/GIF/PDF/DOC/DOCX/XLS/XLSX
  - Note: StaticFiles already safe (html=False by default, no directory listing)

G2-4: API Rate Limiting
  - Status: FAIL → fixed → PASS
  - Critical bug: auth.py created separate Limiter instance (P8/P10)
  - Fix: Extracted to app/limiter.py, imported by both main.py and auth.py

## Phase 3: Code Quality (3 gates)

G3-1: ORM Style Unification
  - Status: CONDITIONAL PASS (only user.py migrated in Phase 1)
  - Phase 2: All 4 remaining models migrated (audit, dynamic, inspection, photo)
  - Pattern: Column → mapped_column with TimestampMixin

G3-2: Silent Error Handling
  - Status: PASS
  - Changed: excel_service.py distinguishes ValueError/TypeError (recoverable) vs Exception (fatal)
  - Fatal errors trigger db.rollback() and return error response

G3-3: Dependency Cleanup
  - Status: PASS
  - Removed: passlib, replaced with bcrypt
  - Fixed: Wildcard import → explicit imports in main.py

## P0/P1 Fixes (Post-Audit)

P0-1: REG-1 Regression Fix
  - save_upload_file() changed return type from str to dict
  - inspection.py upload_signature still assigned dict to string field
  - Fix: `result = save_upload_file(...); record.signature_url = result["url"]`
  - Checklist after changing return type: grep ALL callers

P0-2: Integration Tests
  - Created: tests/conftest.py, test_auth.py, test_upload.py
  - 28 tests total (11 auth + 17 upload/config)
  - Pitfall: slowapi causes cascading test failures → disable in conftest.py

P1-1: CSRF Protection
  - Double Submit Cookie pattern (see fastapi-security-patterns.md)
  - Production only (DEBUG=False)
  - Exempt paths: login, logout, health

P1-2: Random Password for Excel Import
  - secrets.choice-based, 12 chars, 4 char classes
  - force_change_password=True on created users
  - Never log the password (only log username)

P1-3: README Documentation
  - Environment variable table (required + optional)
  - Security features checklist
  - Quick start guide

## P2 Implementation Phase (Post-P0/P1)

P2-1: ORM Migration (all models)
  - Migrated: audit.py, dynamic.py, inspection.py, photo.py
  - Pattern: `Column(Type)` → `Mapped[type] = mapped_column(Type)`
  - Added TimestampMixin to all models
  - Verification: `grep -r "from sqlalchemy import Column" app/models/` returns 0 results

P2-2: AI Service Async
  - Changed: urllib.request.urlopen → asyncio.to_thread(sync_func)
  - ThreadPoolExecutor(max_workers=4) for concurrent requests
  - ai_analysis.py: `result = await analyze_inspection_record(...)`
  - Removed unused _executor variable (asyncio.to_thread uses default executor)

P2-3: Date Filtering Fix
  - Created: _parse_date(date_str, end_of_day=False) helper
  - Applied to: 4x date_to (end_of_day=True) + 4x date_from
  - BUG found by reviewer: date_from was NOT calling _parse_date() on first pass
  - Lesson: when fixing a pattern, grep ALL occurrences, not just the obvious ones

P2-4: Upload Test Coverage
  - Filled 5 empty test stubs with real tests
  - Tests: JPEG upload, PNG upload, invalid extension, oversized file, magic bytes mismatch
  - Pitfall: PNG files converted to JPEG by watermark → assert .jpg or .png

P2-5: CSRF Tests
  - 8 tests total, but 5 are "hollow" (CSRF middleware disabled in DEBUG mode)
  - Effective tests: login exempt, health exempt, 2 config tests
  - Lesson: CSRF tests need a dedicated fixture that forces middleware loading

## Final Test Count

- test_auth.py: 11 tests
- test_upload.py: 28 tests (5 file upload + 4 magic bytes + 8 config + 11 auth)
- test_csrf.py: 8 tests
- Total: 47 tests, all passing

## Third-Party Review Findings (Cumulative)

Phase 1 review: Pass with conditions (test coverage 3/10)
Phase 2 review: Conditional pass — found 3 blockers:
  1. Duplicate Limiter instance (P8/P10)
  2. Duplicate settings import in auth.py
  3. get_audit_history() still had N+1

P0/P1 review: Conditional pass — found 2 blockers:
  1. Log leaking plaintext temporary password
  2. CSRF check missing PATCH method

P2 review: Conditional pass — found 1 blocker:
  1. date_from not calling _parse_date() (4 occurrences)

Final review: Pass — all blockers resolved
  - Score: 5.3 → 7.9
  - Tests: 0 → 47
  - Security: 4.0 → 7.5
