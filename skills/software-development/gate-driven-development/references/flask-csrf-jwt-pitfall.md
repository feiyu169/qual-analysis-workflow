# Flask CSRF + JWT Configuration Pitfall

## Problem

Flask CSRF protection blocks API calls even when using JWT authentication.

## Symptom

API returns 403 with "CSRF令牌无效或已过期" for POST/PUT/DELETE requests.

## Root Cause

Flask's CSRF middleware checks ALL non-GET requests, even when JWT is used for authentication. JWT APIs don't need CSRF protection because tokens are sent in headers, not cookies.

## Solution

### Option 1: Disable CSRF in config (Recommended for API-only apps)

```python
# config/config.py
class Config:
    CSRF_ENABLED = os.environ.get('CSRF_ENABLED', 'false').lower() == 'true'
```

```bash
# .env
CSRF_ENABLED=false
```

### Option 2: Disable CSRF in app initialization

```python
# app/__init__.py
def create_app():
    app = Flask(__name__)
    # ...
    csrf = CSRFProtect(app)
    # Disable CSRF for API (JWT is sufficient)
    app.config['CSRF_ENABLED'] = False
    # ...
```

### Option 3: Exempt specific routes

```python
# app/utils/csrf.py
app.config.setdefault('CSRF_EXEMPT_PREFIXES', [
    '/api/v1/health',
    '/api/v1/auth',
    '/api/v1/exceptions',  # Add API prefixes
])
```

## Verified (2026-06-17)

- Server: OpenCloudOS 9.4, Flask 3.x
- Config: `CSRF_ENABLED=false` in .env
- Result: All API calls work with JWT authentication

## Note

For web apps with form submissions, keep CSRF enabled and use CSRF tokens. Only disable for pure API backends.
