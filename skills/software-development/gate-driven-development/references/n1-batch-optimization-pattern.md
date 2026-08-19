# N+1 Query Optimization — Batch Dict Pattern

When SQLAlchemy models lack `relationship()` definitions, `joinedload` is unavailable.
Use batch dict loading as a fallback.

## Pattern

```python
# BEFORE: N+1 (3 queries per record)
for r in records:
    plate = db.query(BlindPlate).filter(BlindPlate.id == r.blind_plate_id).first()
    user = db.query(User).filter(User.id == r.inspector_id).first()
    photos = db.query(Photo).filter(Photo.record_id == r.id).all()

# AFTER: Batch dict (3 queries total)
# Step 1: Collect all IDs
plate_ids = [r.blind_plate_id for r in records]
user_ids = [r.inspector_id for r in records]
record_ids = [r.id for r in records]

# Step 2: Batch query into dicts
plates = {p.id: p for p in db.query(BlindPlate).filter(BlindPlate.id.in_(plate_ids)).all()}
users = {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()}

# Step 3: Group one-to-many (photos)
photos_by_record = {}
if record_ids:
    for p in db.query(Photo).filter(Photo.record_id.in_(record_ids)).all():
        photos_by_record.setdefault(p.record_id, []).append(p.photo_url)

# Step 4: Assemble results
for r in records:
    plate = plates.get(r.blind_plate_id)
    user = users.get(r.inspector_id)
    photos = photos_by_record.get(r.id, [])
```

## Pitfalls

1. **Empty IN clause**: `db.query(X).filter(X.id.in_([]))` generates `WHERE id IN (NULL)`.
   Guard with `if ids:` before querying.

2. **Scan entire file for same pattern**: After fixing one function, grep the file for
   other occurrences of the same N+1 pattern:
   ```bash
   grep -n "for.*in.*\.all():" <file>
   grep -n "db\.query.*\.filter.*\.first()" <file>
   ```

3. **Relationship preferred**: If you can add `relationship()` to models, `joinedload`
   is cleaner and more maintainable. Batch dict loading is the fallback when models
   can't be modified (production systems, shared codebases).

## When to Use

- Models without `relationship()` definitions
- Production systems where modifying models is risky
- Quick fix without ORM schema changes
- Mixed Column/mapped_column codebases (migration in progress)
