# Qual 工作流缺陷修复记录（2026-07-11）

## 缺陷 1：success 判断掩盖静默降级

### 问题

`workflow.py` 中 `success = len(errors) == 0` 掩盖了静默降级：
- Step 1.5（财报获取）失败只 warning，不写入 errors
- Step 1.6（事实提取）失败只 warning
- Step 2.5（DCF参数）失败只 warning
- Step 4.5（质量增强）失败只 warning

### 修复

添加 `quality_degraded` 和 `degradation_reasons`：
```python
quality_degraded = False
degradation_reasons: list[str] = []

# 每个降级点
quality_degraded = True
degradation_reasons.append(f"财报获取异常: {e}")

# 最终结果
result = {
    "success": len(errors) == 0 and not quality_degraded,
    "quality_degraded": quality_degraded,
    "degradation_reasons": degradation_reasons,
}
```

## 缺陷 2：辩论覆盖审计修复后的章节

### 问题

`quality_enhancer.py` 中 `chapters[ch_num] = debate.pm_synthesis` 直接覆盖。

### 修复

改为合并模式：
```python
if not debate.degraded:
    chapters[ch_num] = _merge_debate_result(chapters[ch_num], debate)

def _merge_debate_result(original, debate):
    merged = original
    merged += "\n\n---\n\n"
    merged += f"> **辩论增强** (确信度: {debate.conviction_score:.0%})\n\n"
    merged += f"<details><summary>看多论点</summary>\n\n{debate.bull_argument}\n\n</details>\n\n"
    merged += f"<details><summary>看空质疑</summary>\n\n{debate.bear_argument}\n\n</details>\n\n"
    if debate.catalysts:
        merged += f"> **催化剂**: {', '.join(debate.catalysts)}\n"
    if debate.triggers:
        merged += f"> **触发条件**: {', '.join(debate.triggers)}\n"
    if debate.pm_synthesis:
        merged += f"\n<details><summary>PM 综合判断</summary>\n\n{debate.pm_synthesis}\n\n</details>"
    return merged
```

## 审查版本收敛轨迹

| 版本 | 结果 | 核心问题 |
|------|------|----------|
| v1 | ❌ 不通过 | 数据源降级遗漏、辩论信息丢失 |
| v2 | ❌ 不通过 | Gate Checks ImportError、截断丢失、测试不足、兼容性 |
| v3 | ✅ 通过 | 3项代码级修正 + 4项建议 |

## HeavySkill 审查关键发现

1. **Gate Checks `ImportError` 未标记降级**
2. **辩论看多/看空论点截断丢失信息** → 改为折叠标签
3. **回归测试严重不足** → 需覆盖所有降级分支
4. **上游对齐缺少兼容性说明** → 需要迁移指南
