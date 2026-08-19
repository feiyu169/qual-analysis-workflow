# HeavySkill 推理模型兼容性修复 (2026-06-01)

## 问题

HeavySkill 使用 deepseek-v4-pro (推理模型) 时，6 条并发请求全部超时失败。

## 根因链

```
config.yaml: model=deepseek-v4-pro (推理模型)
    ↓
v4-pro 返回: content="" , reasoning_content="实际输出"
    ↓
openai_compatible.py 只读 message.content → 空
    ↓
同时: 每条推理耗时 330s, K=6 并发 → API 限流
    ↓
run_heavyskill.py 未加载 config.yaml 的 timeout → 默认 120s
    ↓
全部请求超时, 3 次重试后失败
```

## 修复 (3 处)

### 1. openai_compatible.py — 支持推理模型输出

```python
# Before (line 152):
content=message.get("content", "")

# After:
content = message.get("content", "")
reasoning = message.get("reasoning_content", "")
if not content and reasoning:
    content = reasoning
```

同时 LLMResponse dataclass 新增 `reasoning_content: str = ""` 字段。

### 2. run_heavyskill.py — 加载 timeout

```python
# Before:
config = HeavySkillConfig(
    ...
    verbose=args.verbose,
)

# After:
config = HeavySkillConfig(
    ...
    timeout=_defaults.get("timeout", 120.0),
    verbose=args.verbose,
)
```

### 3. config.yaml — 推理模型参数

```yaml
timeout: 300        # 新增，默认 120 对推理模型不够
max_tokens: 80000   # 保持，推理 token 消耗大
```

## 验证

```bash
# K=1 验证通过: 328s, 3168 tokens, content 正常返回
cd ~/.hermes/skills/heavyskill && python3 scripts/run_heavyskill.py \
  --query "审查方案可行性" --include-file /tmp/plan.md \
  --reason_k 1 --summary_k 1 --language cn
```

## 推理模型 vs 非推理模型参数对照

| 参数 | 推理模型 (v4-pro/r1) | 非推理模型 (v3/chat) |
|------|---------------------|---------------------|
| reason_k | 3 | 6-8 |
| summary_k | 2 | 3-4 |
| timeout | 300 | 120 |
| 单条耗时 | 330s | 10-30s |
| K=3 总耗时 | ~6 min | ~30s |
| K=6 总耗时 | ❌ 超时 | ~30s |
