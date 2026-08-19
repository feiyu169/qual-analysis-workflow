# HGF + HeavySkill Integration Architecture

> Verified via 6 rounds of iterative HeavySkill review (V1→V6, 2026-06-21)

## Architecture

```
Phase 0: Requirements Analysis (<10s)
Phase 1: Task Classification (HGF TaskClassifier, <5s)
Phase 2: Risk Assessment (HGF RiskAssessor, <5s)
Phase 3: HeavySkill Deep Review (K=8, 30s-5min)
  ├── Stage 0: Dynamic checklist loading (<1s)
  ├── Stage 1: Parallel reasoning (asyncio, 30-60s)
  ├── Stage 2: Sequential deliberation (1-2min)
  └── Stage 3: Conclusion validation (10-30s)
Phase 4: Gate Execution (HGF GateExecutor, <30s)
Phase 5: Report Generation (<10s)
Phase 6: Appeal Handling (optional, 0s-24h)
```

## Key Interface Contracts

### TaskClassifier
```python
@dataclass
class TaskClassification:
    level: str  # L0-L3
    type: str   # CODE/CONFIG/IAC/DOCS/REVIEW
    risk: str   # low/medium/high
    files: List[str]
    detected_domains: List[str]
    detected_languages: List[str]
```

### RiskAssessor
- Uses word-boundary matching (regex `\bkeyword\b`) to avoid false positives
- Only checks MR description, not code content (code checked by HeavySkill)
- `skip_heavyskill` is the FINAL decision (overrides TaskClassification)

### ConclusionValidator
```python
def validate(self, issues, llm_verdict, checklist, config) -> ValidationResult:
    # checklist: needed for check_scope processing
    # config: needed for process_items_handling, severity_overrides
```

## Checklist System Design

### Fields per check item
- `check_scope: [code, config, process]` — process items only warn, don't affect verdict
- `languages: [python, java, go, js]` — filters by project language
- `severity_overrides` — per-industry severity upgrades
- `upgrade_conditions` — conditional severity upgrades based on code context

### Dynamic loading by file extension
```python
FILE_EXTENSION_MAPPING = {
    '.jsx': 'frontend', '.tsx': 'frontend', '.vue': 'frontend',
    '.sql': 'database', '.yaml': 'deployment', '.tf': 'deployment',
}
# Always lowercase before matching
ext = os.path.splitext(file)[1].lower()
```

### Multi-industry support
```yaml
project:
  industries: [healthcare, finance]  # Take highest severity
```

## Configuration
- K=8 recommended (paper), K=16 has stability issues
- `process_items_handling: warn` (skip/warn/check)
- Model pricing configurable for cost estimation
- Checklist versions in YAML frontmatter

## Implementation Checklist
```
□ Define all interfaces BEFORE implementation
□ Define JSON schemas for data exchange
□ Define exception types and fallback strategies
□ Implement dynamic checklist loading
□ Implement severity_overrides with multi-industry
□ Add asyncio timeout control (90s total)
□ Test with both positive and negative cases
```

## Files
- V6 technical doc: `~/.hermes/skills/heavyskill-optimize/docs/hgf-heavyskill-integration-v6.md`
- Checklists: `~/.hermes/skills/heavyskill-optimize/checklists/`
- Integration code: `~/.hermes/skills/heavyskill-optimize/src/`
