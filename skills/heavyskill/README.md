# HeavySkill Pipeline

Two-stage LLM reasoning pipeline based on [arXiv:2605.02396](https://arxiv.org/abs/2605.02396).

## Overview

HeavySkill enhances LLM problem-solving through:

1. **Stage 1 - Parallel Reasoning**: Spawns K independent reasoning trajectories (default K=8), each with temperature=1.0 for maximum diversity.
2. **Stage 2 - Sequential Deliberation**: Analyzes all trajectories, cross-validates answers, identifies errors, and synthesizes a final answer.

Supports iterative refinement where deliberation results feed back as additional context.

## Features

- Async parallel LLM calls via httpx
- 3 trajectory selection strategies: `random`, `max_answer_frequency`, `max_diversity`
- Bilingual prompts (English/Chinese)
- Domain-specific prompts (`general` vs `stem`)
- Token budget management
- Trajectory quality filtering (repetitive detection)
- OpenAI-compatible API support (DeepSeek, OpenAI, etc.)
- CLI and programmatic interfaces

## Installation

```bash
cd ~/.hermes/skills/heavyskill
pip install -e .
```

## Quick Start

### CLI

```bash
# English general question
python -m heavyskill.scripts.run_heavyskill --query "What is the capital of France?"

# Chinese STEM problem
python -m heavyskill.scripts.run_heavyskill \
  --query "求解方程 x^2 - 5x + 6 = 0" \
  --language cn --prompt_type stem

# Custom configuration
python -m heavyskill.scripts.run_heavyskill \
  --query "Explain quantum entanglement" \
  --reason_k 16 --summary_k 8 --iterations 3 \
  --strategy max_diversity --output results.json
```

### Python API

```python
import asyncio
from heavyskill import HeavySkillConfig, HeavySkillPipeline

async def main():
    config = HeavySkillConfig(
        api_base="https://api.deepseek.com/v1",
        api_key="your-api-key",
        model="deepseek-v3",
        reason_k=8,
        summary_k=4,
    )
    
    pipeline = HeavySkillPipeline(config)
    result = await pipeline.run(query="What is 2+2?")
    
    print(result.final_answer)
    print(result.summary())

asyncio.run(main())
```

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `api_base` | `https://api.deepseek.com/v1` | API endpoint URL |
| `model` | `deepseek-v3` | Model for reasoning |
| `summary_model` | `deepseek-v3` | Model for deliberation |
| `reason_k` | `8` | Number of parallel trajectories |
| `summary_k` | `4` | Trajectories used in deliberation |
| `max_iterations` | `1` | Deliberation iterations |
| `temperature` | `1.0` | Reasoning temperature |
| `selection_strategy` | `max_answer_frequency` | Trajectory selection strategy |
| `language` | `en` | Prompt language (en/cn) |
| `prompt_type` | `general` | Domain (general/stem) |

## Architecture

```
Query → [Stage 1: K Parallel Reasoning] → Trajectories
                                              ↓
                                     [Memory Cache]
                                              ↓
                                   [Trajectory Selection]
                                              ↓
                              [Stage 2: Deliberation] → Final Answer
                                      (optional loop)
```

## License

MIT
