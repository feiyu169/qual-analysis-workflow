# Vue3 + FastAPI Fullstack Pitfalls

## Frontend Pitfalls

### P1: Variable Not Defined (ref/reactive)

**Symptom**: Page loads but features don't work, no console error.

**Cause**: Using a variable in template that was never declared with `ref()` or `const`.

**Fix**: Always declare variables used in template:
```javascript
const user = ref({ role: "" })
const items = ref([])
const showPreview = ref(false)
```

**Caught this session**: `cameraInput` ref not declared → click handler silent fail.

### P2: Import Missing for API Function

**Symptom**: `getMe is not defined` or similar ReferenceError.

**Cause**: Using an API function without importing it from request.js.

**Fix**: Check imports match usage:
```javascript
import { searchPlate, getMe, getRegions } from "../api/request"
```

**Caught this session**: `getMe` not imported in Ledger.vue → user.role always empty → station tag not shown.

### P3: HTML Element Missing in Template

**Symptom**: CSS class defined but element not visible.

**Cause**: Adding CSS for a class but forgetting to add the HTML element.

**Fix**: After adding CSS, verify the template contains the element:
```html
<!-- Must exist in template -->
<div v-if="showPreview" class="photo-preview-mask" @click="showPreview=false">
  <img :src="previewUrl" class="photo-preview-img" />
</div>
```

**Caught this session**: `photo-preview-mask` CSS defined but HTML element missing in Audit.vue.

### P4: getMe Not Imported → Role-Based UI Silent Fail

**Symptom**: Station tags, admin-only features not showing despite correct code.

**Cause**: `getMe()` call without import silently fails, user.role stays "".

**Fix**: Always import getMe when using role-based UI:
```javascript
import { getMe } from "../api/request"
onMounted(async () => { user.value = await getMe() })
```

**Checklist after adding role-based UI**:
- [ ] `getMe` imported
- [ ] `user` ref declared
- [ ] `user.value = await getMe()` in onMounted
- [ ] Error handling for getMe failure

### P5: Camera API Requires HTTPS or Localhost

**Symptom**: `navigator.mediaDevices.getUserMedia` fails silently.

**Cause**: Browser blocks camera access on HTTP (non-localhost).

**Fix**: Use HTTPS or localhost. For mobile, use `<input type="file" accept="image/*" capture="environment">`.

### P6: Canvas Signature Not Working

**Symptom**: Drawing on canvas doesn't work, buttons work.

**Cause**: Canvas ref not initialized, or canvas inside v-if that hasn't rendered yet.

**Fix**: Initialize canvas in nextTick after v-if becomes true:
```javascript
nextTick(() => {
  const ctx = canvasRef.value.getContext("2d")
  // Set up event listeners
})
```

## Backend Pitfalls

### P7: Field Added to DB but Not to Model

**Symptom**: 500 error on API endpoint, `AttributeError: object has no attribute 'field_name'`

**Cause**: ALTER TABLE adds column but SQLAlchemy model not updated.

**Fix**: After every ALTER TABLE, immediately update the model class.

**Checklist for schema changes**:
- [ ] Database: ALTER TABLE
- [ ] Model: Add Column/field
- [ ] API: Update query/response
- [ ] Frontend: Update UI
- [ ] Test: Verify API response

### P8: Duplicate Import Causes Variable Scope Error

**Symptom**: `UnboundLocalError: cannot access local variable`

**Cause**: Importing a variable inside a function shadows the module-level import.

**Fix**: Remove duplicate imports inside functions. Import once at module level.

**Caught this session**: `from app.models.dynamic import DynamicRecord` inside function shadowed module import.

### P9: Station Filter Missing in API

**Symptom**: Non-admin users see data from other stations.

**Cause**: API doesn't filter by user's station.

**Fix**: Add station filter to all list APIs:
```python
if current_user.role != "admin" and current_user.station:
    plate_ids = [p.id for p in db.query(BlindPlate).filter(
        BlindPlate.station == current_user.station
    ).all()]
    query = query.filter(Record.blind_plate_id.in_(plate_ids))
```

**Checklist for new list API**:
- [ ] Admin sees all data
- [ ] Non-admin sees only own station data
- [ ] Station filter applied to query

### P10: f-string in sed/replace Breaks Code

**Symptom**: Python syntax error after sed replacement.

**Cause**: sed doesn't understand Python f-string syntax with curly braces.

**Fix**: Use Python script for complex replacements instead of sed:
```python
content = content.replace(old_text, new_text)
```
