# Auth Middleware Patterns — Session-Learned

## Dual-Source JWT Authentication (Cookie + Authorization Header)

When a FastAPI app uses Cookie-based JWT auth, API clients (curl, Postman, frontend fetch) often need Authorization header support too.

### Problem
Default middleware only reads from Cookie:
```python
def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get("access_token")  # ← Only Cookie!
    if not token:
        raise HTTPException(status_code=401, detail="未登录")
```

This fails for:
- `curl -H "Authorization: Bearer <token>"` API testing
- Frontend SPAs that prefer header-based auth
- Third-party API integrations

### Solution
```python
def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = None
    
    # Priority 1: Authorization header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
    
    # Priority 2: Cookie (fallback)
    if not token:
        token = request.cookies.get("access_token")
    
    if not token:
        raise HTTPException(status_code=401, detail="未登录，请先登录")
    
    # ... rest of validation
```

### f-string Pitfall with join()
Python f-strings cannot contain backslashes. When building error messages with `.join()`:
```python
# ✗ WRONG — backslash in f-string
detail=f"权限不足，需要角色: {', '.join(roles)}"

# ✓ CORRECT — pre-compute
roles_str = ", ".join(roles)
detail=f"权限不足，需要角色: {roles_str}"
```

## Export API Date Range Validation

When an export endpoint generates Excel files, requiring date range prevents accidental full-database exports:

```python
@router.get("/export/dynamic")
def export_dynamic_excel(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Require date range
    if not date_from or not date_to:
        raise HTTPException(
            status_code=400,
            detail="请选择导出的时间段（开始日期和结束日期）"
        )
    # ... proceed with export
```

Apply this pattern to ALL export endpoints, not just one. Grep for `def export_` to find all.
