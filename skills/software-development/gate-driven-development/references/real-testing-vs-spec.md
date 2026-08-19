# Real Testing Reveals Spec-Implementation Gaps

## Problem Pattern
Technical specs often assume API contracts that differ from reality. After implementing code "correctly" per spec, real testing reveals mismatches.

## Case Study: MinerU FastAPI API

### What the spec assumed:
```python
# Spec said:
POST /parse
files={"file": (name, content, mime)}
data={"method": "auto", "backend": "pipeline"}
```

### What reality required:
```python
# Actual API:
POST /file_parse
files=[("files", (name, content, mime))]  # list of tuples, key is "files" not "file"
data={"parse_method": "auto", "backend": "pipeline", "return_md": "true"}
```

### How to discover actual API:
```bash
# 1. Check OpenAPI spec
curl http://localhost:8080/openapi.json | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin)['paths'], indent=2))"

# 2. Check component schemas for field names and types
curl http://localhost:8080/openapi.json | python3 -c "
import sys,json
data = json.load(sys.stdin)
for name, schema in data.get('components',{}).get('schemas',{}).items():
    if 'file_parse' in name.lower():
        print(f'{name}:')
        print(json.dumps(schema, indent=2))
"

# 3. Check required fields
# Look for "required": [...] in the schema
```

## Lesson
**Never trust spec documentation alone for API contracts.** Always verify against:
1. OpenAPI/Swagger spec (if available)
2. Source code of the server
3. A real curl test with verbose output

## Anti-pattern to avoid
Writing `files={"file": ...}` when the API expects `files=[("files", ...)]`. The difference between dict and list-of-tuples matters for multipart form encoding.
