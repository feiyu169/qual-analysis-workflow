# 并行双专家评估模式 — 2026-06-30

## 模式

对投资分析报告进行第三方评估时，使用两位专家并行审查：

```python
delegate_task(tasks=[
    {
        "goal": "投资分析专家: 对照 must_answer 逐章评估报告质量",
        "toolsets": ["file"],
        "role": "leaf",
    },
    {
        "goal": "编程专家: 检查代码和状态文件验证工作流执行",
        "toolsets": ["file", "terminal"],
        "role": "leaf",
    },
])
```

## 专家职责分工

### 投资分析专家 (CFA)
- 逐章对照 must_answer 覆盖度
- 检查 must_not_cover 违反
- 验证财报原文数据使用
- 检查事实性错误
- 评估 lens 视角体现
- 输出: /tmp/expert-eval-investment.md

### 编程专家
- 检查代码实现是否真正执行
- 验证状态文件 (steps.json, metadata.json, audit/*.json)
- 检查声称 vs 事实的一致性
- 验证 LLM 调用证据
- 输出: /tmp/expert-eval-code.md

## 快手评估结果 (2026-06-30)

- 投资专家: **52/100** — 7个根因
- 编程专家: **5个代码缺陷** — 2个"虚报"
- 综合: ch00/ch10 Placeholder、语义审计未持久化、事实错误、lens 缺失

## 关键教训

1. **声称必须有状态文件佐证**: "11章全部生成" vs ch00/ch10 是 Placeholder
2. **语义审计结果必须持久化**: 否则无法验证
3. **事实核查必须在 prompt 中**: LLM 使用通用知识而非财报原文
4. **"配置缺失"是编造的借口**: 用户一句话就能戳穿
