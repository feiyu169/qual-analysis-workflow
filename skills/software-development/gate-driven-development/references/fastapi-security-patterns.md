# FastAPI Security Patterns — Session-Learned

## CSRF Double Submit Cookie

For FastAPI SPAs that use Cookie-based JWT auth:

```python
# app/middleware/csrf.py
import secrets
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
# Exempt paths — use PREFIX matching, not exact paths
# This prevents 403 errors when new endpoints are added to exempt routers
CSRF_EXEMPT_PREFIXES = ["/api/auth/", "/api/audit/", "/api/ai/", "/api/health", "/"]

def _is_csrf_exempt(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in CSRF_EXEMPT_PREFIXES)

class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            response = await call_next(request)
            csrf_token = request.cookies.get(CSRF_COOKIE_NAME)
            if not csrf_token:
                csrf_token = secrets.token_hex(32)
            response.set_cookie(
                key=CSRF_COOKIE_NAME, value=csrf_token,
                httponly=False,  # JS needs to read it
                samesite="lax", max_age=3600,
            )
            return response

        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            if _is_csrf_exempt(request.url.path):
                return await call_next(request)
            
            cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
            header_token = request.headers.get(CSRF_HEADER_NAME)
            
            if not cookie_token or not header_token:
                raise HTTPException(status_code=403, detail="CSRF token missing")
            if not secrets.compare_digest(cookie_token, header_token):
                raise HTTPException(status_code=403, detail="CSRF token mismatch")
        
        return await call_next(request)
```

Register in main.py (production only):
```python
if not settings.DEBUG:
    app.add_middleware(CSRFMiddleware)
```

**CSRF Exempt Path Strategy**: Use prefix-based exemption (`/api/auth/`, `/api/audit/`) instead of listing individual paths. This way new endpoints added to exempt routers are automatically exempt.

**Security note**: With prefix matching, `/api/auth/logout` IS exempt. If you need logout to require CSRF, use an exact-path EXCLUDE list alongside the prefix list:
```python
CSRF_ENFORCE_PATHS = {"/api/auth/logout"}  # Override prefix exemption
```

**Rule of thumb**: Any endpoint that uses `Authorization: Bearer` header (not cookie) for auth MUST be exempt from CSRF. CSRF protects cookie-based auth from cross-site attacks; header-based auth is already immune.

## Magic Bytes File Validation

Prevent malicious file upload by checking file headers:

```python
MAGIC_BYTES = {
    ".jpg": [b"\xff\xd8\xff"],
    ".jpeg": [b"\xff\xd8\xff"],
    ".png": [b"\x89PNG\r\n\x1a\n"],
    ".gif": [b"GIF87a", b"GIF89a"],
    ".pdf": [b"%PDF"],
}

def check_magic_bytes(content: bytes, ext: str) -> bool:
    if ext not in MAGIC_BYTES:
        return True  # Unknown ext, skip (but whitelist should catch)
    return any(content.startswith(m) for m in MAGIC_BYTES[ext])
```

Validation order: extension whitelist → size limit → magic bytes → watermark.

## N+1 Query Batch Optimization (No Relationships)

When models lack SQLAlchemy `relationship()` definitions:

```python
# Instead of loop queries:
for r in records:
    plate = db.query(BlindPlate).filter(BlindPlate.id == r.blind_plate_id).first()

# Use batch dict:
plate_ids = [r.blind_plate_id for r in records]
plates = {p.id: p for p in db.query(BlindPlate).filter(BlindPlate.id.in_(plate_ids)).all()}

for r in records:
    plate = plates.get(r.blind_plate_id)
```

This reduces O(N) queries to O(1) batch queries per association.

## Random Password Generation (Secure)

```python
import secrets
import string

def generate_random_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    while True:
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.isupper() for c in password) and
            any(c.islower() for c in password) and
            any(c.isdigit() for c in password) and
            any(c in "!@#$%^&*" for c in password)):
            return password
```

**Never log the generated password** — log only the username. The password should be communicated to the user through a secure channel (admin UI, encrypted email).
