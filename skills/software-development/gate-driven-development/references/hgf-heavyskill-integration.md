# HGF + HeavySkill Integration Pattern

## Architecture

```
HGF Flow Control Layer
    ├── TaskClassifier
    ├── RiskAssessor
    ├── GateExecutor
    └── AppealHandler
            ↓
HeavySkill Review Engine
    ├── ParallelReasoning (asyncio)
    ├── SequentialDeliberation
    └── ConclusionValidation
            ↓
Helper Components
    ├── QueryEnhancer
    ├── ChecklistManager
    └── ReportGenerator
```

## Key Design Decisions

1. **K=8 recommended** - Use recommended values, not conservative ones
2. **Single-stage checklist injection** - NOT two-stage (two-stage performs worse)
3. **Dynamic checklist loading** - Based on file extensions, not all 120 items
4. **AppealHandler** - Users can appeal REJECT decisions
5. **check_scope field** - Distinguish code/config/process items

## Checklist Injection

Inject checklist into HeavySkill query (single-stage):

```python
enhanced_query = f"""
{original_query}

## 专项检查清单（必须回答）
{checklist_text}

## 输出格式要求
1. 对每个检查项，给出 ✅/❌/⚠️/➖ 评估
2. 对不通过项，说明具体问题和位置
3. 给出总体结论
"""
```

## Pitfall: Two-Stage Injection

Two-stage injection (Stage1 free exploration + Stage2 checklist validation) performs WORSE than single-stage:
- Average discovery rate: 60% vs 86%
- Reason: Stage2 checklist matching is too strict

## Checklist Design Best Practices

### Required Fields

```yaml
- id: "S-01"
  question: "是否存在SQL注入风险？"
  severity: "P0"
  category: "输入验证"
  check_scope: [code, config]  # NEW
  languages: [python, java, go, js]  # NEW
  check_points: [...]
  fix_suggestion:
    steps: [...]
    example: "..."
```

### check_scope Values

| Value | Treatment |
|-------|-----------|
| code | Auto-check, affects verdict |
| config | Auto-check, affects verdict |
| process | Reminder only, no verdict impact |

### Dynamic Loading

| Extension | Domain |
|-----------|--------|
| .jsx, .tsx, .vue, .css | frontend |
| .sql, model, entity | database |
| .yaml, .yml, .tf | deployment |
| api, controller, route | api |
| * | security, architecture, performance |

## Interfaces

### AppealHandler

```python
class AppealHandlerInterface:
    def submit_appeal(request: AppealRequest) -> AppealResult
    def review_appeal(appeal_id: str, decision: str, reason: str) -> AppealResult
    def collect_false_positive(gate_id: str, issue_id: str, feedback: str)
```

### ChecklistManager

```python
class ChecklistManagerInterface:
    def get_checklist(domains: List[str]) -> Checklist
    def format_checklist(checklist: Checklist) -> str
    def update_from_feedback(feedback: List[Dict])
```

## Cost Optimization

- Full checklist: 120 items ~ 15,000 tokens
- Dynamic loading: 50-80 items ~ 8,000-10,000 tokens
- Savings: 30-50% token reduction
