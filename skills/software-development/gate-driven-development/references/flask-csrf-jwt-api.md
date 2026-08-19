# CSRF Disable for Flask JWT-Only APIs

## Problem
Flask CSRF middleware blocks POST/PUT/DELETE API calls even when using JWT authentication (no cookies/sessions). This is common for API-only backends consumed by SPA frontends or mobile apps.

## Solution: Disable CSRF for API backends

### Option 1: Environment variable (recommended)
```python
# config.py
import os

class Config:
    CSRF_ENABLED = os.environ.get('CSRF_ENABLED', 'true').lower() == 'true'
```

```env
# .env
CSRF_ENABLED=false
```

### Option 2: Direct config override
```python
# app/__init__.py — after CSRFProtect(app)
app.config['CSRF_ENABLED'] = False
```

### Option 3: Exempt specific prefixes
```python
# csrf.py
app.config.setdefault('CSRF_EXEMPT_PREFIXES', ['/api/v1/health', '/api/v1/auth'])
```

## When to Disable CSRF
- ✅ API-only backend (no server-rendered forms)
- ✅ JWT authentication (no cookies/sessions)
- ✅ Mobile app backend
- ❌ Server-rendered web app with forms
- ❌ Cookie-based authentication
- ❌ Mixed (API + server-rendered)

## Pitfalls

### P1: `setdefault` vs config file order
`app.config.setdefault('CSRF_ENABLED', True)` reads the DEFAULT, not the .env value, if called before the config is loaded. The .env value may be overridden.

**Fix**: Set the value AFTER config loading:
```python
# app/__init__.py
csrf = CSRFProtect(app)
app.config['CSRF_ENABLED'] = False  # ← after init, overrides setdefault
```

### P2: Multiple CSRF checks in code
If the CSRF module uses `current_app.config.get('CSRF_ENABLED', True)`, the default `True` means ANY config loading issue results in CSRF being enabled.

**Fix**: Change ALL defaults to `False`:
```python
# In _check_csrf:
if not current_app.config.get('CSRF_ENABLED', False):  # ← False default
    return None
```

### P3: Token endpoint must be exempted
Even with CSRF disabled globally, if you exempt only specific prefixes, the login endpoint must be in the exempt list:
```python
CSRF_EXEMPT_PREFIXES = ['/api/v1/health', '/api/v1/auth']
```

## Verification
```bash
# Should return 200 (not 403)
curl -X POST http://server/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}'

# Should return 401 (not 403) — JWT required, not CSRF
curl -X POST http://server/api/v1/exceptions \
  -H 'Content-Type: application/json' \
  -d '{"test": true}'
```
