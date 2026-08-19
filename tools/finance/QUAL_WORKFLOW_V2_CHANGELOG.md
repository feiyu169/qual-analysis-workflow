# Qual 工作流 v2.0 接口变更说明

## 变更概述

本次修复解决了两个核心缺陷：
1. `success` 判断掩盖静默降级
2. 辩论覆盖审计修复后的章节

## 新增字段

### run_analysis 返回值

| 字段 | 类型 | 说明 | 新增 |
|------|------|------|------|
| `success` | bool | 是否成功（语义变更） | 否 |
| `quality_degraded` | bool | 是否发生质量降级 | **是** |
| `degradation_reasons` | list[str] | 降级原因列表 | **是** |

### success 字段语义变更

**v1.0 语义**：`success = len(errors) == 0`
- 只要没有 exception 就算成功
- 静默降级场景下 success=True

**v2.0 语义**：`success = len(errors) == 0 and not quality_degraded`
- 关键步骤失败 → success=False
- 质量降级 → success=False
- 全部成功 → success=True

## 兼容性矩阵

| success | quality_degraded | 含义 | 建议操作 |
|---------|------------------|------|----------|
| True | False | 全部成功，质量未降级 | 直接使用报告 |
| False | True | 质量降级，报告可用但质量较低 | 使用报告，但注意降级原因 |
| False | False | 关键步骤失败，报告不可用 | 不使用报告，排查 errors |

## 迁移指南

### 旧代码（仅依赖 success）

```python
result = run_analysis(...)
if result["success"]:
    use_report(result["report"])
else:
    handle_error(result["errors"])
```

### 新代码（区分降级和失败）

```python
result = run_analysis(...)
if result["success"]:
    use_report(result["report"])
elif result.get("quality_degraded"):
    # 质量降级，报告可用但质量较低
    use_report_with_caution(result["report"], result["degradation_reasons"])
else:
    # 关键步骤失败，报告不可用
    handle_error(result["errors"])
```

## degradation_reasons 可能值

| 值 | 触发条件 |
|---|----------|
| "财报获取返回空: {ticker}" | 自动获取财报返回 None |
| "财报获取异常: {e}" | 自动获取财报抛异常 |
| "事实提取失败: {e}" | fact_extractor 失败 |
| "Wind数据不完整: 缺少{missing}" | Wind 三表不完整 |
| "Wind数据不可用" | ctx.wind 为 None |
| "DCF参数提取失败: {e}" | extract_dcf_params 失败 |
| "数据收集降级（Wind/财报解析失败）" | _collect_data 内部失败 |
| "质量增强失败: {e}" | enhance_report_quality 抛异常 |
| "辩论增强未生效" | 辩论全部失败 |
| "Gate Checks阻断: {e}" | GateChecksBlockedError |
| "Gate Checks模块未找到" | ImportError |
| "Gate Checks失败: {e}" | 其他异常 |
| "{子阶段warning}" | quality_enhancer 内部 warnings |

## 辩论合并模式变更

### v1.0 行为

```python
# 直接覆盖原始章节
chapters[ch_num] = debate.pm_synthesis
```

### v2.0 行为

```python
# 合并模式：保留原始内容，追加辩论洞察
chapters[ch_num] = _merge_debate_result(original_content, debate)
```

### 输出格式

```markdown
[原始章节内容]

---

> **辩论增强** (确信度: 80%)

<details><summary>看多论点</summary>

[完整看多论点]

</details>

<details><summary>看空质疑</summary>

[完整看空质疑]

</details>

> **催化剂**: 催化剂1, 催化剂2
> **触发条件**: 触发条件1, 触发条件2

<details><summary>PM 综合判断</summary>

[完整 PM 综合判断]

</details>
```

## 测试验证

```bash
# 运行回归测试
python3 -m pytest test_qual_fix_regression.py -v

# 预期结果
# 11 passed
```
