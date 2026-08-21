---
name: heavyskill-review-workflow
description: "HeavySkill技术方案审查工作流 - 迭代式审查、与参考实现对比、K=8标准配置"
version: 1.0.0
---

# HeavySkill Review Workflow

## Overview

使用HeavySkill进行技术方案审查的标准工作流。核心原则：与参考实现（如Dayu-agent）逐项对比，不隐瞒不欺骗。

## Standard Configuration

```bash
cd ~/.hermes/skills/heavyskill && python3 scripts/run_heavyskill.py \
  --query "技术方案审查：..." \
  --reason_k 8 --summary_k 4 --language cn \
  --output /tmp/heavyskill-review-<topic>.json
```

**关键参数**:
- `--reason_k 8`: 标准K值（K=16有稳定性问题）
- `--language cn`: 中文用户必须设置
- `--output`: 保存审查结果，便于后续分析

## Limitations

### ⚠️ HeavySkill无法访问本地文件

HeavySkill子代理无法读取本地文件系统。**必须将关键内容注入到query中**，而非引用文件路径。

**错误写法**:
```
审查Hermes方案（/path/to/spec.md），对照Dayu实现（/path/to/dayu/）
```

**正确写法**:
```
审查Hermes方案v2.0。
方案核心内容：1. xxx 2. xxx 3. xxx
Dayu功能清单：1. xxx 2. xxx 3. xxx
审查点：1. xxx 2. xxx
```

### ⚠️ 审查结果可能被截断（P54，2026-08-21 已修复+显性化）

**旧问题**：HeavySkill 的 deliberation_response 可能被截断（max_tokens 默认 4096 + 推理模型
思维链占预算），且截断静默无标记——必须读 JSON 全文才能拿到完整结论。

**现行为**：预算由 config.yaml 控制（`max_tokens: 32768` / `summary_max_tokens: 16384`，CLI 可覆盖）；
输出 JSON 带 `truncation` 摘要字段；截断轨迹自动剔除出审议/共识；控制台有 ⚠️ 告警。

**读取完整结果的标准姿势**（先看截断摘要，再取审议全文）：
```python
import json
with open('/tmp/heavyskill-review.json') as f:
    data = json.load(f)
print(data['truncation'])   # 全 0/False 才可放心采信
response = data['deliberation'][0]['deliberation_response']
```

## Iterative Review Pattern

技术方案通常需要2-4轮迭代才能通过HeavySkill审查：

```
v1.0 → HeavySkill → 发现缺失项 → 补充
v2.0 → HeavySkill → 发现细节问题 → 修正
v2.1 → HeavySkill → 发现命名/签名问题 → 修正
v2.2 → HeavySkill → 审查通过
```

**每轮必须**:
1. 读取上轮审查结果
2. 逐项补充/修正
3. 重新提交审查
4. 记录变更

## Query Template

```
技术方案审查：审查{项目名}{版本号}。
审查原则：对照{参考实现}的功能，一一核对，以满足功能实现为前提，全面审慎，不得隐瞒欺骗。

方案{版本号}核心改进：
1. {改进1}
2. {改进2}
...

{参考实现}功能清单对照：
【功能模块A】N项
1. {功能1}
2. {功能2}
...

【功能模块B】M项
1. {功能1}
...

审查点：
1. {审查点1}
2. {审查点2}
...

请给出详细审查报告，包括：
- 功能对齐度评估（逐项核对）
- 缺失功能清单
- 实施建议
- 风险评估
```

## Analyzing Results

```bash
# 提取最终结论
cat /tmp/heavyskill-review.json | python3 -c "
import sys, json
data = json.load(sys.stdin)
deliberation = data.get('deliberation', [])
if deliberation:
    print(deliberation[0].get('deliberation_response', '')[:3000])
"

# 提取推理轨迹
cat /tmp/heavyskill-review.json | python3 -c "
import sys, json
data = json.load(sys.stdin)
trajectories = data.get('reasoning', {}).get('trajectories', [])
for i, t in enumerate(trajectories[:3]):
    print(f'=== 轨迹 {i+1} ===')
    print(t[:2000])
"
```
