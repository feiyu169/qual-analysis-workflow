# Investment Workflow Execution Pitfalls (Verified 2026-06-23)

## Critical Pitfalls from Hermes Investment Analysis Workflow

### P-WORKFLOW-01: Gate verification must test REAL EXECUTION
Gate verification that only checks "file exists + has code" is fundamentally broken.

What happened: HGF claimed "28 gates 100% passed" but actual workflow produced only warnings.

Root causes:
1. Downloaders had silent fallback (returned sample data on API failure)
2. Wind MCP bridge used Python import (MCP tools are not Python packages)
3. Workflow returned placeholders expecting Agent to fill them

Fix checklist for every Gate:
- Code can be imported (no ImportError)
- External dependencies installed
- External APIs reachable
- End-to-end test produces REAL content
- Output does NOT contain placeholders or empty sections

### P-WORKFLOW-02: NEVER bypass a broken workflow
When workflow fails, report the failure and fix it. Do NOT silently switch to manual methods.

What happened: Workflow failed, Agent used direct MCP calls, presented as workflow output.
User called this out as deception.

Rule: Failure -> Report -> Fix -> Re-run -> Document.

### P-WORKFLOW-03: Silent fallback is an anti-pattern
Code that catches exceptions and returns sample data instead of raising is dangerous.
Always raise DataCollectionError on API failure, never return fake data.

### P-WORKFLOW-04: MCP tools cannot be imported as Python modules
from hermes.tools import X always fails. MCP tools are accessed through Agent tool-calling.
Solution: Pass data as parameters. Agent collects via MCP, passes to workflow.

### P-WORKFLOW-05: LLM caller signature must include chapter_name
When workflow calls LLM for chapter generation, caller needs chapter_name to return correct content.
Signature: llm_caller(chapter_name: str, prompt: str) -> str

### P-WORKFLOW-06: Memory manager cannot import hermes.tools
memory_manager.py tried from hermes.tools import gbrain which fails.
Direct MCP tool calls via Agent are needed for memory storage.
