# Multi-Trajectory Document Review Pattern (2026-05-30)

## When to Use HeavySkill for Document Review

HeavySkill is a pure LLM reasoning engine (no tools). Use it for document review when:
- The document content can be embedded in the query via `--include-file`
- You need multiple independent perspectives (K parallel trajectories)
- The review is analytical (not requiring file modification or testing)

Do NOT use HeavySkill when:
- The review requires running code/tests → use delegate_task
- The document is too large (>50K chars) → use Hermes self-review
- The review needs tool access → use delegate_task

## Workflow

1. Write the document to review to a file
2. Run HeavySkill with `--include-file` to embed the content
3. Extract review from the 8 trajectories (the deliberation may not always produce a clean "final answer")
4. Synthesize findings with Hermes's own analysis

## Template

```bash
cd ~/.hermes/skills/heavyskill && python3 scripts/run_heavyskill.py \
  --query "请从以下维度审查：1. X 2. Y 3. Z" \
  --include-file /path/to/document.md \
  --reason_k 8 --summary_k 4 --language cn \
  --output /tmp/heavyskill-review.json
```

## Known Limitation

HeavySkill's `final_answer` extraction sometimes produces garbage (e.g. "N-RPC 2").
Always read the individual trajectories from the JSON output for the actual review content.
The `deliberation_response` may be empty even when trajectories are rich.
