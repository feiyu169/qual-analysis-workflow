# Step 4.5 质量增强卡死调试记录 (2026-08-05)

## 问题描述

小鹏汽车（9868.HK）分析时，`run_analysis()` 在 Step 4.5 卡死28分钟。

## 代码级定位

### 文件1: `~/.hermes/tools/finance/quality/repairer.py` L216

```python
# 判定LLM修复内容是否有效的逻辑
if repaired and len(repaired.strip()) > len(current_content) * 0.5:
    current_content = repaired
    round_record["outcome"] = "repaired"
else:
    round_record["outcome"] = "repair_failed"
    logger.warning(f"修复 {chapter_id} 第 {round_num} 轮: LLM 返回内容异常，保留原内容")
```

**问题**: 50%阈值过严。LLM返回精简修复时被判定为"异常"。

### 文件2: `~/.hermes/tools/finance/data_repair.py` L575-592

```python
def _build_correct_values(wind_financials: dict) -> dict[str, float]:
    correct_values = {}
    income = wind_financials.get('income', {})
    if '年营业总收入' in income:      # ← 代码期望这个字段名
        vals = income['年营业总收入']
        if isinstance(vals, list) and vals:
            correct_values['营业收入'] = vals[-1]
    # ...
    return correct_values
```

**问题**: 调用方传入 `年营业收入`，代码期望 `年营业总收入`。字段名不匹配导致 `correct_values` 为空。

### 文件3: `~/.hermes/tools/finance/quality_enhancer.py` L132-156

```python
if enable_debate and llm_caller:
    for ch_num in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
        if ch_num in chapters:
            try:
                debate = run_debate(...)  # 每章3次LLM调用
            except Exception as e:
                logger.warning(f"第{ch_num}章辩论失败: {e}")
```

**问题**: 9章×3次=27次LLM调用，无超时保护。

### 文件4: `~/.hermes/tools/finance/llm_caller.py` L73

```python
client = openai.OpenAI(
    api_key=api_key,
    base_url=base_url,
    # 无 timeout 参数，默认 600 秒
)
```

**问题**: 默认 timeout=600秒（10分钟），27次LLM调用可能卡死4.5小时。

## 已实施修复（4个，2026-08-05验证）

| # | 文件 | 修复 | 效果 |
|---|------|------|------|
| 1 | `quality/repairer.py` L216 | 长度检查从 `> len(current_content)*0.5` 改为 `> 200` | LLM修复不再被误判为"异常" |
| 2 | `data_repair.py` L575 | `_build_correct_values` 增加fallback链 | 营业收入正确映射；毛利率优先直接获取 |
| 3 | `quality_enhancer.py` L128 | 辩论机制增加 `concurrent.futures.ThreadPoolExecutor` 120s超时 | 单章辩论超时后跳过，不阻塞 |
| 4 | `llm_caller.py` L73 | `openai.OpenAI(timeout=60.0)` | API调用60秒超时 |

## 关键教训

1. **HTTP timeout必须在客户端设置**: `concurrent.futures` 超时只能控制主流程，底层HTTP请求仍在等待。必须在 `openai.OpenAI(timeout=...)` 设置才能真正释放线程。

2. **毛利率不能用营业支出计算**: `年营业支出` 包含经营开支，不等于营业成本。需要直接获取毛利率字段，或从毛利计算。

3. **Wind数据字段名必须有fallback链**: 不同API返回不同字段名，不能硬编码单一字段名。
