# Flask Security Middleware Patterns

## CSRF Protection (app/utils/csrf.py)

### Design
- Before-request hook checks non-safe methods (POST/PUT/DELETE/PATCH)
- After-request hook sets CSRF cookie on GET requests
- Supports view-level and prefix-level exemptions
- Token stored in Flask session + cookie (httponly=False for JS access)

### Integration
```python
# app/__init__.py
from app.utils.csrf import CSRFProtect
csrf = CSRFProtect(app)

# Exempt health check endpoints
app.config['CSRF_EXEMPT_PREFIXES'] = ['/api/v1/health']
```

### Frontend Usage
```javascript
// Read CSRF token from cookie or response header
const csrfToken = getCookie('csrf_token') || response.headers['x-csrf-token'];

fetch('/api/v1/exceptions', {
    method: 'POST',
    headers: {
        'X-CSRF-Token': csrfToken,
        'Content-Type': 'application/json'
    },
    body: JSON.stringify(data)
});
```

### Config Options
- CSRF_ENABLED: bool (default True)
- CSRF_SECRET_KEY: str (auto-generated)
- CSRF_TOKEN_TIMEOUT: int (default 3600s)
- CSRF_EXEMPT_PREFIXES: list of URL prefixes

## Rate Limiting (app/utils/rate_limiter.py)

### Design
- Before-request hook checks global rate limit
- Decorator `@rate_limiter.limit('10/minute')` for endpoint-specific limits
- In-memory storage (extendable to Redis)
- Client key from X-Forwarded-For or remote_addr

### Integration
```python
# app/__init__.py
from app.utils.rate_limiter import RateLimiter
rate_limiter = RateLimiter(app)

# Global limit
app.config['RATE_LIMIT_DEFAULT'] = '100/hour'

# Endpoint-specific
@rate_limiter.limit('10/minute')
def login():
    pass
```

### Limit Format
- '100/hour', '10/minute', '1000/day', '5/second'
- Returns 429 when exceeded

### Config Options
- RATE_LIMIT_ENABLED: bool (default True)
- RATE_LIMIT_DEFAULT: str (default '100/hour')
- RATE_LIMIT_STORAGE: str ('memory' or 'redis')

## Pitfalls

### P1: CSRF exempt for API-only backends
If the backend serves only JSON APIs (no HTML forms), CSRF may cause issues with frontend frameworks that don't send cookies automatically. Consider disabling CSRF for /api/ prefixes and relying on JWT + CORS instead.

### P2: Rate limiter memory storage
In-memory rate limiting doesn't persist across restarts and doesn't work with multiple workers. For production, use Redis-backed storage.

### P3: Slowapi vs custom rate limiter
The gate-driven-development skill documents slowapi integration pitfalls (P10, P18, P19). The custom RateLimiter in this pattern avoids those issues by not requiring shared Limiter instances.
