# Qual Workflow 代码级审查记录 (2026-07-11)

## 审查范围

- `workflow.py` (1959行) — 主工作流
- `fact_extractor.py` (846行) — 事实提取器
- `quality_enhancer.py` (212行) — 质量增强
- `quality/structural_check.py` — 结构化预检
- `debate_coordinator.py` — 辩论机制

---

## 问题 1：success 判断掩盖静默降级

### 问题定位

`workflow.py` L1940：

```python
result = {
    "success": len(errors) == 0,
    ...
}
```

### 完整对照表

| 步骤 | 写入 errors | 只 warning | success 影响 |
|------|-------------|------------|--------------|
| Step 1 类型推断 | ✅ | | 失败 → success=False |
| Step 1.5 财报获取 | | ✅ | 失败 → **success 仍 True** |
| Step 1.6 事实提取 | | ✅ | 失败 → **success 仍 True** |
| Step 2 数据收集 | ✅ | | 失败 → success=False |
| Step 2.5 DCF 参数 | | ✅ | 失败 → **success 仍 True** |
| Step 3 逐章写作 | ✅ | | 失败 → success=False |
| Step 4 审计修复 | ✅ | | 失败 → success=False |
| Step 4.5 质量增强 | | ✅ | 失败 → **success 仍 True** |
| Step 4.6 Gate Checks | ✅ (阻断时) | ✅ (非阻断) | 阻断 → success=False |
| Step 5a 决策章 | ✅ | | 失败 → success=False |
| Step 5b 概览章 | ✅ | | 失败 → success=False |
| Step 6 记忆存储 | ✅ | | 失败 → success=False |

### 具体场景

**场景 1：财报获取失败 + 质量增强失败**

```python
# Step 1.5: 财报获取失败
except Exception as e:
    logger.warning(f"自动获取财报失败: {ticker}")  # ← 只 warning

# Step 4.5: 质量增强失败
except Exception as e:
    logger.warning(f"Step 4.5 质量增强失败（非阻断）: {e}")  # ← 只 warning

# 最终结果
result = {
    "success": True,  # ← 错误！财报获取失败 + 质量增强失败，但 success=True
    "errors": [],     # ← 空的
}
```

**场景 2：事实提取失败 + DCF 参数提取失败**

```python
# Step 1.6: 事实提取失败
except Exception as e:
    logger.warning(f"Step 1.6 事实提取失败: {e}")  # ← 只 warning

# Step 2.5: DCF 参数提取失败
except Exception as e:
    logger.error(f"DCF 参数提取失败: {e}")  # ← logger.error 但不写 errors
    dcf_params = None

# 最终结果
result = {
    "success": True,  # ← 错误！两个关键步骤都失败，但 success=True
    "errors": [],
    "dcf_params": None,  # ← DCF 参数为空
}
```

### 修复方案

```python
# 方案 1：增加 quality_degraded 标志
quality_degraded = False
degradation_reasons = []

# Step 1.5
except Exception as e:
    quality_degraded = True
    degradation_reasons.append(f"财报获取失败: {e}")

# Step 4.5
except Exception as e:
    quality_degraded = True
    degradation_reasons.append(f"质量增强失败: {e}")

# 最终结果
result = {
    "success": len(errors) == 0 and not quality_degraded,
    "quality_degraded": quality_degraded,
    "degradation_reasons": degradation_reasons,
    "errors": errors,
}
```

---

## 问题 2：辩论覆盖审计修复后的章节

### 问题定位

`quality_enhancer.py` L120：

```python
if not debate.degraded:
    chapters[ch_num] = debate.pm_synthesis  # ← 直接覆盖
```

### 完整执行链

```
Step 3: 写作 → chapters[1-9]
    ↓
Step 4: 审计修复 → chapters[1-9] (已修复)
    ↓
Step 4.5: 质量增强
    ├── Stage 1: data_repair → chapters (修复数据)
    ├── Stage 2: base_valuation → 估值摘要
    ├── Stage 3: debate → chapters[ch] = pm_synthesis  ← 覆盖！
    ├── Stage 4: valuation_engine → chapters[7] += val_report  ← 追加
    └── Stage 5: depth_enhancer → chapters[7] += depth_report  ← 追加
```

### 具体覆盖场景

**场景：第 5 章（运营数据）**

```python
# Step 4: 审计修复
# 结构化预检发现"缺少 DAU 数据" → 修复 → 添加 DAU 4.1亿
# 语义审计通过 → 评分 85/100
fixed[5] = "## 结论要点\nDAU 4.1亿，同比增长12%...\n## 详细分析\n..."

# Step 4.5 Stage 3: 辩论
debate = run_debate(
    chapter_num=5,
    chapter_title="第5章",
    chapter_content=fixed[5],  # ← 传入修复后的内容
    base_valuation_summary=valuation_summary,
    llm_caller=llm_caller,
)

# 辩论结果
# Bull: "DAU 4.1亿是低估，实际可能4.5亿..."
# Bear: "DAU 增速放缓，Q4 可能只有3.8亿..."
# PM 综合: "DAU 4.1亿是基准，上行空间4.5亿，下行风险3.8亿..."

if not debate.degraded:
    chapters[5] = debate.pm_synthesis  # ← 覆盖了 Step 4 修复的内容！
```

### 覆盖的风险

| 风险 | 说明 |
|------|------|
| 1. 数据准确性 | PM 综合可能引入新的数据错误（如"DAU 4.5亿"无财报支撑） |
| 2. 结构破坏 | PM 输出可能不包含"结论要点/详细情况/证据与出处"三个必需小节 |
| 3. 审计失效 | Step 4 的审计结论（85/100）对覆盖后的内容无效 |
| 4. 来源丢失 | PM 综合可能删除原始的"[来源：财报]"标注 |

### 修复方案

**方案 1：合并模式（推荐）**

```python
# quality_enhancer.py
if not debate.degraded:
    # 不直接覆盖，而是合并
    original = chapters[ch_num]
    enhanced = debate.pm_synthesis
    
    # 保留原始的结构化小节
    merged = _merge_chapters(original, enhanced)
    chapters[ch_num] = merged
    result.chapters_enhanced += 1

def _merge_chapters(original: str, enhanced: str) -> str:
    """合并原始章节和辩论增强内容"""
    # 1. 提取原始的"结论要点"小节
    original_conclusion = _extract_section(original, "结论要点")
    
    # 2. 提取增强的"详细分析"小节
    enhanced_analysis = _extract_section(enhanced, "详细分析")
    
    # 3. 保留原始的"证据与出处"小节
    original_evidence = _extract_section(original, "证据与出处")
    
    # 4. 合并
    return f"""
## 结论要点
{original_conclusion}

## 详细分析
{enhanced_analysis}

## 证据与出处
{original_evidence}
"""
```

**方案 2：增强标注模式**

```python
if not debate.degraded:
    # 在原章节末尾追加辩论增强内容
    chapters[ch_num] = chapters[ch_num] + "\n\n" + \
        "## 辩论增强\n" + \
        f"**确信度**: {debate.conviction_score:.0%}\n" + \
        f"**催化剂**: {', '.join(debate.catalysts)}\n" + \
        f"**触发条件**: {', '.join(debate.triggers)}\n\n" + \
        debate.pm_synthesis
```

**方案 3：重新审计模式**

```python
if not debate.degraded:
    chapters[ch_num] = debate.pm_synthesis
    
    # 对覆盖后的内容重新审计
    from .quality import structural_check
    struct_result = structural_check(chapter_id, chapters[ch_num], contract)
    if not struct_result.passed:
        logger.warning(f"辩论后结构化预检失败: 第{ch_num}章")
        # 回退到原始内容
        chapters[ch_num] = original_content
```

---

## 总结

| 问题 | 根因 | 影响 | 修复方案 |
|------|------|------|----------|
| success 掩盖降级 | Step 1.5/1.6/4.5 只 warning 不写 errors | 用户误以为全部成功 | 增加 `quality_degraded` 标志 |
| 辩论覆盖审计 | `chapters[ch] = pm_synthesis` 直接替换 | Step 4 审计结论失效 | 合并模式或重新审计 |
