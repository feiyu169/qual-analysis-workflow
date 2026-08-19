# Fullstack Sync Debugging — Multi-Layer Failure Patterns

When modifying a deployed fullstack app (FastAPI + Vue + Nginx + SQLite), changes often span multiple layers. Missing a layer causes silent failures that appear as mysterious 500s or empty UIs.

## The Sync Checklist

For ANY change to a deployed feature, verify ALL affected layers:

| Change Type | Layers to Update |
|-------------|-----------------|
| New DB column | DB → Model → API → Frontend |
| New API endpoint | Backend → Router registration → CSRF exempt → Frontend |
| New file upload | Backend → Nginx client_max_body_size → Frontend (no manual Content-Type) |
| Auth method change | Backend middleware → Frontend request library (axios vs fetch) |
| New frontend page | Vue component → Router → Menu/link entry → Build & deploy |

## Case Study: Blind Plate Abnormal Disposal Feature

### Failure Chain
1. **Added `photos` column** to DB via ALTER TABLE
2. **Updated API** to read `item.photos` → ✅ worked in isolation
3. **Forgot to update SQLAlchemy model** → ❌ `AttributeError` → 500 on list endpoint
4. **Frontend showed "暂无记录"** because API returned 500 silently

### Fix: Always grep model after ALTER TABLE
```bash
# After: sqlite3 db "ALTER TABLE x ADD COLUMN y TEXT"
grep -n "y" backend/app/models/x.py  # Must exist as Column
```

## Case Study: CSRF Blocking New Routes

### Failure Chain
1. **Added `/api/abnormal/` router** with POST endpoints
2. **Didn't update CSRF_EXEMPT_PREFIXES** → POST requests blocked with 403
3. **GET worked fine** (CSRF only checks mutating methods)
4. **Frontend showed "提交失败"** but no clear error

### Fix: New router → new CSRF exemption
```python
# In csrf.py, add to CSRF_EXEMPT_PREFIXES:
"/api/abnormal/",  # ← add when creating new router group
```

## Case Study: File Upload 413 Error

### Failure Chain
1. **Added photo upload** to abnormal disposal
2. **Backend endpoint worked** (tested with curl, small file)
3. **Frontend upload failed** — "上传失败"
4. **Nginx access log** showed `413 Request Entity Too Large`
5. **Root cause**: `client_max_body_size` defaults to 1MB, mobile photos are 3-8MB

### Fix: Nginx config for file uploads
```nginx
server {
    client_max_body_size 10m;  # Global
    
    location /api/ {
        client_max_body_size 10m;  # Per-location (redundant but explicit)
        proxy_pass http://127.0.0.1:8000;
    }
}
```

## Case Study: axios FormData Upload Breaks with Manual Content-Type

### Failure Chain
1. **Frontend used** `request.post("/upload", formData, { headers: { "Content-Type": "multipart/form-data" } })`
2. **Server received** request but couldn't parse body
3. **Root cause**: Manual Content-Type misses the `boundary` parameter that axios auto-generates

### Fix: Let axios handle FormData
```javascript
// ✗ WRONG
request.post("/api/upload", formData, { headers: { "Content-Type": "multipart/form-data" } })

// ✓ CORRECT
request.post("/api/upload", formData)
```

## Case Study: Cookie Auth vs localStorage Token

### Failure Chain
1. **Backend uses httponly cookies** for JWT (set via `response.set_cookie`)
2. **Frontend component used** `fetch` with `localStorage.getItem("token")`
3. **localStorage had no token** (it's in httponly cookie, invisible to JS)
4. **Result**: 401 Unauthorized on all API calls

### Fix: Use axios with withCredentials
```javascript
// In request.js
const request = axios.create({
  withCredentials: true,  // ← sends cookies automatically
})

// In component — use request, not fetch
import request from "../api/request"
const res = await request.get("/api/endpoint")
```

## Debugging Workflow

When a feature "doesn't work" after deployment:

1. **Check nginx access log** for HTTP status codes
   - 413 → nginx body size limit
   - 401 → auth issue (cookie/token)
   - 403 → CSRF or permission
   - 500 → backend error

2. **Check backend journal** for Python errors
   ```bash
   journalctl -u service-name -n 30 --no-pager
   ```

3. **Check frontend browser console** for JS errors

4. **Trace the full request path**:
   ```
   Frontend → Nginx → Backend → Database → Response
   ```
   Each hop can fail independently.
