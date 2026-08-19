# --include-file Fix (2026-05-30)

## Problem
HeavySkill is a pure LLM reasoning engine — it calls DeepSeek API via httpx with no tool access.
When query references a file path, the model cannot read it, causing all K trajectories to fail.

## Root Cause
`parallel_reasoning.py` → `_build_messages(query)` → `[system_prompt, user: query]` → DeepSeek API
No tools parameter, no function-calling loop, no file I/O.

## Fix
Added `--include-file / -f` CLI argument to `scripts/run_heavyskill.py`:
- Accepts multiple files via `action="append"`
- Pre-reads files and embeds content into query
- Changed `pipeline.run(query=args.query)` to `pipeline.run(query=query)`

## Verification
- Before fix: 0/8 trajectories succeeded (5,700 tokens)
- After fix: 8/8 trajectories succeeded (73,160 tokens)

## Files Modified
- `scripts/run_heavyskill.py` — added --include-file argument and file pre-reading logic
