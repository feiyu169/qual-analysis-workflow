# HeavySkill K Value Selection Guide

## Recommended K Values

| K Value | Token Cost | Latency | Quality | Use Case |
|---------|-----------|---------|---------|----------|
| K=4 | 1x | 1x | Baseline | Quick review |
| K=8 | 2x | 2x | Better | **Standard review (recommended)** |
| K=16 | 4x | 4x | Best | Critical review |

## Paper Recommendation

HeavySkill paper recommends K=8 or K=16:
- K=8: Best stability/quality balance
- K=16: Can be unstable, diminishing returns

## Cost Estimation

Single review (~75,000 tokens):
- Input: $0.14/Mtokens → $0.011
- Output: $0.28/Mtokens → $0.021
- Total: ~$0.03 per review

Daily cost (50 reviews): ~$1.50
Monthly cost: ~$45

## Latency Estimation

With true async (asyncio + aiohttp):
- K=8: 30-60s for Stage 1 (parallel)
- Total: 2-5 minutes

With pseudo-parallel (fallback):
- K=8: 4-8 minutes for Stage 1
- Total: 10-15 minutes

## Pitfall: Using K=4

K=4 is too conservative for HeavySkill:
- Reduces trajectory diversity
- Limits problem discovery rate
- Paper recommends K=8 minimum

Always use recommended K=8 unless cost is critical constraint.
