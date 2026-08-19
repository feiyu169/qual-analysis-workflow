# HeavySkill Changelog

## 2026-05-30: --include-file fix

**Problem**: HeavySkill is a pure LLM reasoning engine (DeepSeek API direct, no tool access). When query references a file path like "请审查 /path/to/file.md", the model cannot read the file. All K trajectories fail with "没有权限读取文件".

**Root cause**: `parallel_reasoning.py` builds only [system_prompt, user: query] messages. No tools/function_calling. The LLM receives text but cannot execute file I/O.

**Fix**: Added `--include-file / -f` CLI argument to `scripts/run_heavyskill.py`:
- Accepts multiple files via `action="append"`
- Pre-reads files at CLI layer, embeds content into query with delimiters
- Fixes bug: `pipeline.run(query=args.query)` → `pipeline.run(query=query)` to use augmented query

**Verification**: Before fix: 0/8 trajectories succeeded (5,700 tokens). After fix: 8/8 succeeded (73,160 tokens).

**Usage**:
```bash
# Before (broken):
python3 scripts/run_heavyskill.py --query "请审查方案文件 /path/to/file.md"

# After (working):
python3 scripts/run_heavyskill.py --query "请审查这个方案" --include-file /path/to/file.md

# Multiple files:
python3 scripts/run_heavyskill.py --query "比较这两个方案" -f a.md -f b.md
```

**Why not add full tool calling?** HeavySkill's design philosophy is "pure reasoning engine" — simple, reliable, low-cost. Adding tools would break this architecture. `--include-file` is the right balance: keeps architecture clean, solves data input.
