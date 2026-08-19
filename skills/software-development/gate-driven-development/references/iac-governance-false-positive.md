# IAC Governance & False Positive Management

## Branch Protection (IAC)

```yaml
# config/iac_governance.yaml
branch_protection:
  main:
    required_status_checks:
      strict: true
      contexts: ["quality-gates"]
    required_pull_request_reviews:
      required_approving_review_count: 1
      dismiss_stale_reviews: true
      require_code_owner_reviews: true
    enforce_admins: true
    restrict_pushes:
      force_pushes: false
```

**Key**: GitHub Cloud uses Branch Protection API, not pre-receive hooks.

## False Positive Management

```yaml
# config/exceptions.yaml
known_false_positives:
  - id: "fp-001"
    rule: "semgrep/python.lang.security.injection.sql-injection"
    file: "tests/test_database.py"
    reason: "测试文件，非生产代码"
    approved_by: "tech_lead"
    expiry: "2025-12-31"
    permanent: false

exemptions:
  - id: "ex-001"
    type: "legacy_code"
    scope: "incremental_only"
    approved_by: "tech_lead"
    expiry: "2025-12-31"
    conditions:
      - "不涉及安全敏感代码"
```

## False Positive Checker

```python
class FalsePositiveChecker:
    def is_false_positive(self, rule: str, file: str) -> bool:
        for fp in self.false_positives:
            if fp.rule == rule and fp.file == file:
                if fp.permanent:
                    return True
                if fp.expiry and fp.expiry > datetime.now().isoformat():
                    return True
        return False
    
    def has_exemption(self, exemption_type: str, context: Dict = None) -> bool:
        for ex in self.exemptions:
            if ex.type == exemption_type:
                if ex.expiry and ex.expiry < datetime.now().isoformat():
                    continue  # Expired
                return True
        return False
```

## Pitfalls

1. **Expiry checking**: Always check expiry date, don't assume permanent
2. **Condition checking**: Exemptions may have conditions that must be met
3. **Audit trail**: Log all false positive approvals and exemption usage
4. **Regular review**: Monthly review of all active exceptions
