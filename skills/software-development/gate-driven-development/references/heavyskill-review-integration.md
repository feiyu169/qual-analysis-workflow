# HeavySkill Review Integration

## Pattern: Iterative Review with HeavySkill

When designing complex systems, use HeavySkill for multi-dimensional review:

1. Write proposal
2. Run HeavySkill review
3. Form 3-person team to address findings
4. Run HeavySkill again
5. Repeat until approved

## Command

```bash
cd ~/.hermes/skills/heavyskill && python3 scripts/run_heavyskill.py \
  --query "审查问题" \
  --include-file /path/to/proposal.md \
  --reason_k 6 --summary_k 3 --language cn \
  --output /tmp/review.json
```

## Standard Review Dimensions

1. Completeness
2. Unbypassability
3. Feasibility
4. Integration
5. Extensibility
6. Risk control
