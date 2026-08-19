# MCP Server Plugin Architecture for Programming Workflow

**Source**: Blind-plate-system V3.0 workflow implementation (2026-06-06)
**Status**: Verified through 5 iterations (V2→V3→V4→V5) with HeavySkill review

## Architecture Overview

```
MCP Server (Core)
  ├── 5 Core Tools:
  │   ├── classify_task: Task classification (L0/L1/L2/L3/L3_LITE/IAC/CONFIG/DOCS)
  │   ├── assess_risk: Risk assessment (English keys + mapping + safety guardrail)
  │   ├── execute_gates: Gate execution (plugin architecture)
  │   ├── verify_tdd: TDD evidence verification (SHOULD_PASS)
  │   └── check_security: Security checks (detect-secrets + semgrep)
  │
  ├── Plugin System:
  │   ├── GatePlugin (base class)
  │   ├── RuffPlugin, PytestPlugin, DetectSecretsPlugin
  │   ├── SemgrepPlugin, SafetyPlugin, CheckovPlugin
  │   └── GATE_PLUGINS (registry)
  │
  ├── Configuration:
  │   ├── .mcp-gates.yaml (gate definitions + level mapping)
  │   └── project_overrides (coverage_min, exclude_patterns)
  │
  └── Persistence:
      ├── workflow.db (audit_log + gate_results)
      └── AuditLogger (structured logging)
```

## Key Design Decisions

### 1. Three-Tier Gate Classification

**Rationale**: Not all gates are equal. Some are critical (MUST_PASS), some are important (SHOULD_PASS), some are nice-to-have (OPTIONAL).

**Implementation**:
- MUST_PASS: Failure blocks push/merge
- SHOULD_PASS: Failure generates warning
- OPTIONAL: Failure logged only

### 2. Plugin Architecture

**Rationale**: Different tools have different interfaces, output formats, and availability. Plugin architecture allows:
- Easy addition of new tools
- Standardized output format
- Graceful degradation when tools unavailable

**Implementation**:
```python
class GatePlugin(ABC):
    @abstractmethod
    def execute(self, files, working_dir) -> GateResult
    @abstractmethod
    def is_available(self) -> bool
    def get_version(self) -> Optional[str]
```

### 3. Fail-closed Strategy

**Rationale**: Security-first approach. When in doubt, reject.

**Implementation**:
- MCP Server unavailable → reject (unless emergency approval)
- MUST_PASS tool unavailable → reject
- SHOULD_PASS tool unavailable → warn and skip
- OPTIONAL tool unavailable → log and skip

**Emergency channel**: Environment variable `EMERGENCY_APPROVAL_TOKEN` + external approval system

### 4. Risk Assessment with Safety Guardrail

**Rationale**: Risk reduction rules (e.g., "fix" → -1) can accidentally downgrade critical security fixes.

**Implementation**:
```python
high_risk_factors = ["security", "auth", "payment", "crypto", "injection", "xss"]
has_high_risk = any(f in matched_factors for f in high_risk_factors)

if not has_high_risk:
    # Only apply reduction when NO high-risk factors present
    for keywords, reduction in reduction_rules:
        if keyword in description_lower:
            risk_score += reduction
```

### 5. Platform Adaptation

**Rationale**: GitHub Cloud doesn't support pre-receive hooks. Self-hosted GitLab does.

**Implementation**:
- GitHub: Actions + Branch Protection API
- GitLab: CI + pre-receive hook
- Auto-detection via `git remote get-url origin`

## Configuration Files

### .mcp-gates.yaml

```yaml
gates:
  must_pass:
    - name: "static_analysis"
      tool: "ruff"
      command: "ruff check ."
      timeout: 60
    - name: "unit_test"
      tool: "pytest"
      command: "pytest tests/ -v --cov=."
      timeout: 300
      coverage_min: 80
    - name: "secret_scan"
      tool: "detect-secrets"
      command: "detect-secrets scan"
      timeout: 60
  
  should_pass:
    - name: "security_scan"
      tool: "semgrep"
      command: "semgrep --config=p/r2c-ci"
      timeout: 120
    - name: "dependency_scan"
      tool: "safety"
      command: "safety check"
      timeout: 60
  
  optional:
    - name: "performance_test"
      tool: "pytest"
      command: "pytest tests/performance/ -v"
      timeout: 600
    - name: "iac_scan"
      tool: "checkov"
      command: "checkov -d ."
      timeout: 120

level_gates:
  L0: {must_pass: ["secret_scan"], should_pass: [], optional: []}
  L1: {must_pass: ["static_analysis", "unit_test", "secret_scan"], should_pass: ["security_scan"], optional: []}
  L2: {must_pass: ["static_analysis", "unit_test", "secret_scan", "security_scan"], should_pass: ["dependency_scan"], optional: []}
  L3: {must_pass: ["static_analysis", "unit_test", "secret_scan", "security_scan", "dependency_scan"], should_pass: [], optional: ["performance_test", "iac_scan"]}
  L3_LITE: {must_pass: ["static_analysis", "secret_scan", "security_scan"], should_pass: ["unit_test"], optional: []}
  IAC: {must_pass: ["secret_scan", "iac_scan"], should_pass: [], optional: []}
  CONFIG: {must_pass: ["secret_scan"], should_pass: [], optional: []}
  DOCS: {must_pass: ["secret_scan"], should_pass: [], optional: []}

project_overrides:
  coverage_min: 70  # Override default 80
  exclude_patterns: ["vendor/", "node_modules/"]
```

## Iteration History

| Version | Key Changes | HeavySkill Findings |
|---------|-------------|---------------------|
| V2 | Basic workflow design | 6 issues (risk assessment, mixed types, etc.) |
| V3 | Fixed risk assessment, added safety guardrails | 5 issues (non-code flows, tool availability) |
| V4 | Fixed mixed change types, added IAC/CONFIG/DOCS | 3 issues (platform adaptation, emergency channel) |
| V5 | Fixed remaining issues, all reviews passed | 0 issues (approved for implementation) |

## Lessons Learned

1. **Risk assessment language mismatch**: risk_factors keys must match affected_areas sources (English keys, mapped from Chinese)
2. **Safety guardrail essential**: Without it, "fix critical auth bypass" gets risk-reduced
3. **Mixed change types common**: Single PR may contain CODE + CONFIG + IAC
4. **Fail-closed is correct**: MCP Server down → reject, not degrade
5. **Platform matters**: GitHub vs GitLab have different enforcement capabilities
