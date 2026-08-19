# Investment Analysis HGF Pattern — Complete Example

> **Verified**: 2026-06-23
> **Project**: Hermes 买方投资分析工作流
> **Gates**: 28 total, 100% pass rate

---

## 1. Project Context

**Goal**: Build a buy-side investment analysis workflow inspired by dayu-agent's architecture, using Hermes native capabilities.

**Key Principle**: Borrow design ideas, not code. ("借思路、不借代码")

**Architecture**:
```
Layer 1: Skill Layer (routing + workflow definition)
Layer 2: Framework Layer (10+1 chapters + 37 business models + 26 constraints)
Layer 3: Data Layer (dual-layer: qualitative filing data + quantitative Wind MCP)
Layer 4: Quality Layer (structural check + LLM audit + repair + checkpoint)
Layer 5: Memory Layer (GBrain + flomo + nocturne + state-store)
```

---

## 2. Gate Definitions (Phase 0)

### Phase 1 Gates (Framework)
| Gate | Component | Exit Criteria |
|------|-----------|---------------|
| 1.1 | Skill directory | `~/.hermes/skills/finance/qual-analysis/` exists |
| 1.2 | Analysis template | 10+1 chapters, CHAPTER_GOAL + CHAPTER_CONTRACT per chapter |
| 1.3 | Facet catalog | 37 business models + 26 constraints in valid JSON |
| 1.4 | Prompt files | 4 files (infer/write/audit/repair) with {{variables}} |

### Phase 2 Gates (Data Layer)
| Gate | Component | Exit Criteria |
|------|-----------|---------------|
| 2.1 | SEC downloader | list_filings() + download_filing() |
| 2.2 | CNInfo downloader | A-share annual/quarterly support |
| 2.3 | HKEX downloader | HK annual/interim/quarterly support |
| 2.4 | Docling parser | parse() → ParsedFiling |
| 2.5 | MinerU parser | parse() → ParsedFiling (CJK optimized) |
| 2.6-2.11 | 6 processors | extract_sections() + extract_tables() |
| 2.12 | Table extractor | income/balance/cash_flow/segment |
| 2.13 | Rate limiter | SEC 10 req/sec, others 5 req/sec |
| 2.14 | Filing service | 5 query methods + download_with_cache() |

### Phase 3 Gates (Integration)
| Gate | Component | Exit Criteria |
|------|-----------|---------------|
| 3.1 | DataContext | All dataclasses defined with data_quality property |
| 3.2 | Wind MCP | 4 tools verified working |
| 3.3 | Data collector | Dual-layer collection with fallback |

### Phase 4 Gates (Quality)
| Gate | Component | Exit Criteria |
|------|-----------|---------------|
| 4.1 | Structural check | 6 rule checks (sections, evidence, format) |
| 4.2 | Semantic audit | LLM-as-Judge, 6-dimension scoring |
| 4.3 | Repair agent | Max 3 rounds of audit→repair→re-audit |
| 4.4 | Checkpoint | Step/chapter level state persistence |

### Phase 5 Gates (Memory)
| Gate | Component | Exit Criteria |
|------|-----------|---------------|
| 5.1 | GBrain writer | put_page with slug investment/{ticker}-{date} |
| 5.2 | flomo writer | memo_create with #hermes/投资研究 tag |
| 5.3 | nocturne writer | create_memory with trigger condition |

### Phase 6 Gates (E2E Testing)
| Gate | Component | Exit Criteria |
|------|-----------|---------------|
| 6.1 | US test (AAPL) | Full workflow completes, report generated |
| 6.2 | HK test (0700.HK) | Full workflow completes, report generated |
| 6.3 | CN test (600519.SH) | Full workflow completes, report generated |

---

## 3. Key Design Decisions

### 3.1 Dual-Layer Data Architecture
```
Qualitative Layer (filing text):
  SEC/CNINFO/HKEX → PDF → Docling/MinerU → Markdown → 8 processors → sections/tables

Quantitative Layer (structured numbers):
  Wind MCP → quote/valuation/financial_data/news
```

**Why**: Financial reports contain qualitative information (MD&A, risk factors, governance) that structured APIs cannot provide. Wind MCP provides quantitative data for cross-validation.

### 3.2 Processor Mapping Strategy
| Market | PDF Parser | Processors |
|--------|-----------|------------|
| US (SEC) | Docling | us_10k, us_10q, us_20f, us_8k |
| CN (巨潮) | MinerU | cn_sections |
| HK (披露易) | MinerU | hk_sections |
| Fallback | MinerU | section_identifier (generic) |

**Why**: MinerU has best CJK support; Docling has best SEC HTML parsing. Each market needs dedicated section mapping because report formats differ significantly.

### 3.3 Memory Integration Pattern
```python
# Three-layer parallel write with error isolation
class MemoryManager:
    def save_analysis(ctx, report):
        # Each layer independent try/except
        try: write_to_gbrain(ctx, report)
        except: pass  # Don't block other layers
        
        try: write_to_flomo(ctx, report)
        except: pass
        
        try: write_to_nocturne(ctx, report)
        except: pass
```

**Why**: Memory persistence is important but not critical-path. Single layer failure should not block analysis completion.

---

## 4. Pitfalls Encountered

1. **"File exists" ≠ "works"**: Created SKILL.md but didn't verify it was loadable. Always run `skill_view` after creating.

2. **MCP parameter format**: Wind MCP `wind_financial_data` needs `question` parameter, not `windcode`+`type`. Always check actual API signature.

3. **Ticker format inconsistency**: `0700.HK` vs `00700.HK` — Wind MCP expects 5-digit HK codes. Implement zero-padding.

4. **Audit false positives**: Low data quality triggers "missing Markdown heading" warnings. Distinguish quality-related issues from structural issues.

5. **HeavySkill checklist injection**: Long checklists (>10 items) cause attention dilution. Keep to 5-10 focused items per domain.

---

## 5. Deliverable Inventory

```
~/.hermes/skills/finance/qual-analysis/
├── SKILL.md                    (3.4 KB)
├── qual-analysis-template.md   (17.7 KB, 10+1 chapters)
├── facets/catalog.json         (21.2 KB, 37+26 types)
└── prompts/                    (4 files, 15.9 KB)

~/.hermes/tools/finance/
├── data_context.py             (DataContext definition)
├── data_collector.py           (dual-layer collection)
├── workflow.py                 (main entry point)
├── rate_limiter.py             (SEC compliance)
├── downloaders/                (3 downloaders + base)
├── parsers/                    (2 parsers + base)
├── processors/                 (8 processors + table + generic)
├── quality/                    (4 modules)
└── memory/                     (4 modules)
```

Total: 35+ files, 5000+ lines of code.
