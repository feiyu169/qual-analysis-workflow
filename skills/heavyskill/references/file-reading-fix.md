# HeavySkill File Reading Fix

**Date**: 2026-05-30
**Issue**: HeavySkill runs DeepSeek API directly with NO tool access. Query referencing file paths fails — model cannot read files.
**Fix**: Added `--include-file / -f` CLI parameter to `run_heavyskill.py`.

## Before (0/8 trajectories succeeded)

```bash
# FAILS — model has no file I/O capability
python3 scripts/run_heavyskill.py --query "请审查方案文件 /path/to/file.md"
```

## After (8/8 trajectories succeeded)

```bash
# File content is embedded into query before sending to DeepSeek API
python3 scripts/run_heavyskill.py \
  --query "请审查这个方案" \
  --include-file /path/to/file.md

# Multiple files
python3 scripts/run_heavyskill.py \
  --query "比较这两个方案" \
  -f proposal_a.md -f proposal_b.md
```

## Implementation

In `scripts/run_heavyskill.py`:
1. New CLI arg: `--include-file / -f` (action="append", dest="include_files")
2. Pre-reads files before pipeline, embeds content with delimiters
3. Fixes bug: `pipeline.run(query=args.query)` → `pipeline.run(query=query)`

## Verification

| Metric | Before | After |
|--------|--------|-------|
| Trajectory success | 0/8 (0%) | 8/8 (100%) |
| Token consumption | 5,700 | 73,160 |
| Review content | None | 8 complete reviews |
