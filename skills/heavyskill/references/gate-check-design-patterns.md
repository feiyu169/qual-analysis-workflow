# Gate Check Design Patterns for Financial Workflows

## Context
When designing automated validation gates (PoW/Gate Checks) for financial analysis workflows, these patterns emerged from HeavySkill K=8 review.

## Architecture Pattern: Two-Layer Gate

**Avoid three-layer designs** — they create redundancy. Use two layers:

```
Gate 1: 结构完整性检查 (Structural Integrity)
├─ _year_labels 存在性与一致性
├─ 关键财务字段存在性
├─ 章节非Placeholder
└─ 审计产物基础结构

Gate 2: 计算卫生检查 (Calculation Hygiene)
├─ DCF参数非空
├─ 数组对齐检查
└─ 数量级合理性（宽松范围，仅Warning）
```

## Exception Grading (必须实现)

```
FATAL（硬阻断）：
├─ _year_labels 缺失
├─ 关键章节缺失
└─ 审计JSON格式错误

ERROR（阻断但可重试）：
├─ DCF参数缺失
├─ 数组长度不匹配
└─ 数量级明显异常

WARN（警告不阻断）：
├─ WACC 超出行业常见范围
├─ FCF/OCF 比例异常
└─ 非关键字段缺失
```

## Threshold Anti-Patterns (来自HeavySkill审查)

### ❌ WRONG: Hard-coded percentage ranges
```python
# BAD: FCF/OCF 50%-150%
if not (0.5 <= fcf/ocf <= 1.5):
    raise ValidationError("FCF/OCF out of range")

# BAD: WACC 8%-15%
if not (0.08 <= wacc <= 0.15):
    raise ValidationError("WACC out of range")
```

**Why wrong**:
- FCF/OCF: High CapEx industries (semiconductors, data centers) can have FCF/OCF < 0.5 for years
- FCF/OCF: FCF > OCF means negative net CapEx (asset sales), which is a red flag, not normal
- WACC: HK tech stocks can have WACC 6-8% in low-rate environments
- WACC: High-risk startups can have WACC > 15%

### ✅ RIGHT: Signal marking + human explanation
```python
# GOOD: Mark for human review, don't block
if wacc < 0.06 or wacc > 0.18:
    warnings.append({
        "check": "wacc_unusual",
        "severity": "WARN",
        "value": wacc,
        "message": "WACC outside 6%-18% range, requires human explanation"
    })

# GOOD: Use accounting identity instead of ratio
# FCF ≈ OCF - CapEx (allow for timing differences)
expected_fcf = operating_cashflow - capex
if abs(fcf - expected_fcf) / max(abs(expected_fcf), 1) > 0.2:
    warnings.append({
        "check": "fcf_ocf_mismatch",
        "severity": "WARN",
        "value": {"fcf": fcf, "ocf": operating_cashflow, "capex": capex},
        "message": "FCF does not match OCF - CapEx, check for unusual items"
    })
```

## Configuration Externalization

**Never hardcode field lists or thresholds**. Use YAML config:

```yaml
# gate_check_config.yaml
structural:
  required_fields:
    hk: ["年营业总收入", "净利润", "经营活动现金流量净额"]
    us: ["Total Revenue", "Net Income", "Operating Cash Flow"]
    cn: ["营业收入", "净利润", "经营活动产生的现金流量净额"]

calculation:
  wacc:
    warn_range: [0.06, 0.18]
    description: "Outside range requires human explanation"
  fcf_reconciliation:
    tolerance: 0.20
    description: "FCF should approximate OCF - CapEx"
```

## Gate Position in Workflow

**Wrong**: 3 checkpoints (after data collection, after writing/audit, after memory storage)
**Right**: 1 checkpoint after "writing+audit", before HeavySkill

```
数据收集 → 写作+审计 → [Gate Check] → HeavySkill审查 → 三人小组讨论
```

**Why**: All gate checks are essentially "verify artifacts before semantic review". Splitting them creates unnecessary interruption.

## Integration with P4 Rule

P4 requires "execution logs must be based on evidence". Gate Check reports are the **automated executor** of P4:

```
Gate Check Report → Auto-inject into P4 evidence chain
├─ Data fingerprint
├─ Timestamp
├─ Pass/Fail/Skip status
└─ Human override requires written justification
```

## Naming Convention

**Don't call it "PoW"** — the blockchain metaphor confuses financial engineers.
**Call it**: "Gate Checks", "Pre-flight Checks", "Quality Gates", "Automated QC"
