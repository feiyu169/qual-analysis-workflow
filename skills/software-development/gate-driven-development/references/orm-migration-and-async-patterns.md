# SQLAlchemy ORM Migration Pattern — Column → mapped_column

## When to Use
Migrating legacy SQLAlchemy 1.x `Column()` style to 2.0 `mapped_column()` style.

## Migration Pattern

### Before (Legacy Column style)
```python
from sqlalchemy import Column, Integer, String, DateTime, func
from app.models.base import Base

class User(Base):
    __tablename__ = "user"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
```

### After (mapped_column style)
```python
from datetime import datetime
from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin

class User(Base, TimestampMixin):
    __tablename__ = "user"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    # created_at/updated_at inherited from TimestampMixin
```

### TimestampMixin
```python
from datetime import datetime
from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

## Type Mapping Rules

| Old (Column) | New (mapped_column) |
|--------------|---------------------|
| `Column(Integer)` | `Mapped[int] = mapped_column()` |
| `Column(String(50))` | `Mapped[str] = mapped_column(String(50))` |
| `Column(Boolean, default=True)` | `Mapped[bool] = mapped_column(Boolean, default=True)` |
| `Column(DateTime, nullable=True)` | `Mapped[datetime \| None] = mapped_column(DateTime)` |
| `Column(Text, comment="...")` | `Mapped[str \| None] = mapped_column(Text, comment="...")` |
| `Column(ForeignKey("table.id"))` | `Mapped[int] = mapped_column(ForeignKey("table.id"))` |

## Nullable Fields
Use Python 3.10+ union syntax:
```python
# Nullable string
phone: Mapped[str | None] = mapped_column(String(20))

# Nullable datetime
audited_at: Mapped[datetime | None] = mapped_column(DateTime)
```

## Enum Fields
```python
from sqlalchemy import Enum

# Old
status = Column(Enum("pending", "approved", "rejected", name="audit_status"))

# New
status: Mapped[str] = mapped_column(
    Enum("pending", "approved", "rejected", name="audit_status"),
    default="pending",
    index=True,
)
```

## Verification After Migration
```bash
# Should return 0 results
grep -r "from sqlalchemy import Column" app/models/

# Should return all model files
grep -r "from sqlalchemy.orm import Mapped" app/models/
```

## Pitfalls
- Don't forget `from datetime import datetime` when using `Mapped[datetime]`
- ForeignKey imports come from `sqlalchemy`, not `sqlalchemy.orm`
- `func.now()` import stays the same (`from sqlalchemy import func`)
- Remove `Integer` import when no longer needed (mapped_column infers from `Mapped[int]`)

## Async Wrapping Pattern for Sync HTTP Calls

When FastAPI endpoints are `async def` but call synchronous HTTP libraries:

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Optional: custom executor (otherwise asyncio uses default)
_executor = ThreadPoolExecutor(max_workers=4)

def _sync_http_call(url: str) -> str:
    """Synchronous HTTP call (blocking)"""
    import urllib.request
    with urllib.request.urlopen(url, timeout=30) as resp:
        return resp.read().decode()

async def async_http_call(url: str) -> str:
    """Async wrapper — runs sync call in thread pool"""
    return await asyncio.to_thread(_sync_http_call, url)

# In FastAPI endpoint:
@router.post("/analyze")
async def analyze(...):
    result = await async_http_call(url)  # Non-blocking
    return {"result": result}
```

Key points:
- `asyncio.to_thread()` runs the sync function in a thread pool
- The FastAPI event loop is NOT blocked
- No need for `httpx` or `aiohttp` if the sync library works fine
- `ThreadPoolExecutor` is optional — `asyncio.to_thread()` uses a default one
