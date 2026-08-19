# Frontend Code Deduplication Pattern (Vue 3)

## Problem
Utility functions (status mappers, formatters, parsers) duplicated across multiple Vue components.

## Detection
```bash
# Find duplicated function definitions
grep -rn "const getStatusType" frontend/src/views/ --include="*.vue"
# If > 1 result → extract to shared utility
```

## Solution: Shared Utility File

### Step 1: Create utility file
```javascript
// frontend/src/utils/status.js
export function getStatusType(status) {
  const map = {
    '待接收': 'warning',
    '处置中': 'primary',
    // ...
  }
  return map[status] || 'info'
}
```

### Step 2: Update all components (via delegate_task)
```
delegate_task(
  goal="Replace inline functions with imports from @/utils/status",
  context="File list + function names to remove + import statement to add",
  toolsets=["file"]
)
```

### Step 3: Verify
```bash
grep -rn "const getStatusType" frontend/src/views/ --include="*.vue"
# Should return 0 results
```

## Checklist After Extraction
```
□ All inline definitions removed (grep confirms 0 remaining)
□ All files have correct import statement
□ No circular dependencies introduced
□ Functions are exported (not default-exported)
```

## Caught This Session
- `getStatusType` duplicated in 6 Vue files
- `getStatusClass` duplicated in 1 file (same logic, different name)
- `parsePhotos` in 1 file (extracted for consistency)
- Total ~83 lines of duplicate code eliminated
