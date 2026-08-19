# HeavySkill Checklist Injection Guide

> Verified via 7-case evaluation (2026-06-21)

## Summary

When using HeavySkill for code/technical review, inject domain-specific checklists into the query to improve discovery rate from 71% to 86%.

**Key rule**: Single-stage injection > Two-stage injection (verified: 86% vs 60%).

## When to Use

- Code review tasks
- Technical proposal review
- Architecture review
- Security audit

## Checklist Design Rules

1. Keep it short: 5-10 items max per domain
2. Dynamic loading: Only load checklists relevant to changed files
3. check_scope field: `[code, config, process]`
4. languages field: Filter by project language
5. fix_suggestion format: Use `steps` + `example`

## K Value Selection

| K | Cost | Time | Quality | Use Case |
|---|------|------|---------|----------|
| 4 | 1x | 1x | Baseline | Quick review |
| 8 | 2x | 2x | Better | **Standard (recommended)** |
| 16 | 4x | 4x | Best | Critical review |

## Files

- Checklists: `~/.hermes/skills/heavyskill-optimize/checklists/`
- Integration code: `~/.hermes/skills/heavyskill-optimize/src/`
- Technical doc: `~/.hermes/skills/heavyskill-optimize/docs/hgf-heavyskill-integration-v6.md`
