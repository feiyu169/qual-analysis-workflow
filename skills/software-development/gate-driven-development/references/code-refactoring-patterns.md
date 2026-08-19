# Code Refactoring Patterns

## Enum Renaming Pattern

When renaming an enum (e.g., `GateStatus` → `GateExecutionStatus`):

### Step 1: Find all references
```bash
grep -rn "GateStatus" --include="*.py" .
```

### Step 2: Update source files
1. Rename enum class definition
2. Update all internal references
3. Update imports in dependent files

### Step 3: Update test files
1. Update imports
2. Replace all references

### Step 4: Handle import compatibility
```python
# For files that need both package and standalone import
try:
    from .gate_types import GateExecutionStatus
except ImportError:
    from gate_types import GateExecutionStatus
```

### Step 5: Verify
```bash
python -m pytest tests/ -q
```

**Pitfall**: Forgetting test files or files outside the main package (e.g., mcp_server.py).

## Import Compatibility Pattern

When a module needs to work both as part of a package and standalone:

```python
# Option 1: try/except (preferred)
try:
    from .module import Class
except ImportError:
    from module import Class

# Option 2: Conditional import
import sys
if __name__ == '__main__':
    from module import Class
else:
    from .module import Class
```

**When to use**:
- Test files that use `sys.path.insert` for standalone execution
- Plugin systems that load modules dynamically
- MCP servers that may be run standalone

**Pitfall**: Don't use relative imports in files that are meant to be run standalone (like mcp_server.py).

## Mapping Chain Integrity Testing

When you have a mapping chain (e.g., RISK_MAPPING → RISK_FACTORS):

```python
def test_mapping_chain_integrity(self):
    """Verify all mapping targets exist"""
    for source, target in self.mapping.items():
        if isinstance(target, str):
            assert target in self.factors or target in self.mapping, \
                f"Broken chain: {source} -> {target}"
```

**Why**: Mapping chains can break when:
1. New source keys added without corresponding target
2. Target keys renamed
3. Intermediate mapping removed

**Golden test**: Also verify the mapping produces expected values:
```python
def test_mapping_produces_score(self):
    result = self.assess(['order'], 'order management')
    assert result.score > 0  # Not just non-None, but positive
```
