# Error Sanitization Pattern (Flask)

## Problem
API endpoints returning `str(e)` to clients expose internal implementation details (stack traces, SQL queries, file paths) in production.

## Solution: Centralized safe_error_message

```python
# app/utils/error_handlers.py
import logging
from flask import current_app

logger = logging.getLogger(__name__)

def safe_error_message(error, fallback='服务器内部错误'):
    """Production-safe error message wrapper.
    
    - Always logs detailed error to server logs
    - Production: returns generic fallback message
    - Development: returns detailed str(error)
    """
    error_detail = str(error)
    logger.error(f"操作异常: {error_detail}", exc_info=True)
    
    if not current_app.debug:
        return fallback
    return error_detail
```

## Usage Pattern
```python
# In API routes — replace ALL str(e) for 500 errors
try:
    result = service.do_something()
except Exception as e:
    return jsonify({'code': 500, 'message': safe_error_message(e)}), 500

# Keep str(e) for:
# - 409 ConflictError (business logic, user needs to know why)
# - 502 external service errors (user needs to know which service)
# - 400 validation errors (user needs to know what to fix)
```

## Migration Checklist
```bash
# Find all str(e) in API routes
grep -rn "str(e)" app/api/ --include="*.py"
# Count: should be reduced to only 409/502/400 cases
```

## Caught This Session
- 25 `str(e)` occurrences found across 4 API files
- 19 replaced with `safe_error_message(e)` (500 errors)
- 6 kept as `str(e)` (409 ConflictError, 502 DingTalk errors, health check)
