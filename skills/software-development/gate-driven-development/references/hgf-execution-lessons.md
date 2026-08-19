# HGF Execution Lessons - Downloaders & Parsers Refactor

## Session: 2026-06-24 Downloaders + Parsers Refactor

### Key Lesson: Deviation Notification is Mandatory

When executing HGF strictly against a technical document:

1. **Every deviation must be notified to user BEFORE proceeding**
   - Don't assume the deviation is acceptable
   - Don't silently fix and continue
   - Present the deviation with options, wait for user decision

2. **Example deviations encountered**:
   - inactive stock覆盖active (setdefault fix)
   - mineru是CLI不是Python库 (重大偏差)
   - typing_extensions版本不兼容 (环境问题)

3. **User's explicit requirement**: "有偏差的地方一定要通知我，让我确认后再执行，不允许欺骗"

### Key Lesson: Gate Verification Must Be Real

- Gate 1-6: `python3 -m py_compile` (syntax check)
- Gate 7: Actual test execution (not just "tests exist")
- Gate 8: Real API integration test (not mock)

### Key Lesson: HeavySkill Review Cycles

Technical documents rarely pass HeavySkill review on first attempt:

| Version | Issues Found | Action |
|---------|-------------|--------|
| v1.0 | 缺失5个核心接口 | 补齐接口 |
| v2.0 | search参数未明确、relabel_tables签名不清晰 | 补充签名 |
| v2.1 | convert_pdf_bytes命名不一致、文件类型未定义 | 修正命名 |
| v2.2 | 签名对照表不完整、错误处理未对齐 | 补充对照表 |
| v2.3 | **通过** | 开始实施 |

### Key Lesson: Python Environment Management

- uv manages the system Python (PEP 668)
- Use `uv pip install --system` for system-level packages
- Dayu's venv at `~/repos/dayu-agent/.venv/` has different package versions
- typing_extensions>=4.15.0 required for docling (Sentinel class)

### Key Lesson: Package Nature Discovery

Always verify a package is a Python library before designing import-based architecture:
```python
# Check 1: Can you import the class?
try:
    from package import Class
except ImportError:
    # Check 2: Is it a CLI tool?
    import subprocess
    result = subprocess.run(["package", "--help"], capture_output=True)
    if result.returncode == 0:
        # It's a CLI tool, not a Python library
```
