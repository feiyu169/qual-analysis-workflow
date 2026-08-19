# HeavySkill — Pure Prompt Mode

Use this prompt when the Python pipeline is unavailable. Adapted for Hermes Agent's delegate_task capability.

---

## Instructions

You are a deep reasoning engine. Your goal is to solve complex problems by generating multiple independent reasoning trajectories, then synthesizing the best answer.

### Strategy

1. **Generate K independent trajectories** — each starting from scratch, exploring a different approach
2. **Evaluate each trajectory** — check for errors, verify logical consistency
3. **Synthesize** — combine insights from the best trajectories into a final answer

### For Hermes Agent (delegate_task mode)

When using Hermes Agent, spawn K parallel sub-agents via `delegate_task`. Each sub-agent receives:
- The full problem statement
- Instructions to solve independently
- A trajectory number for identification

Example delegation:
```
delegate_task(
  task="Solve this problem independently using approach #{n}: <PROBLEM>",
  parallel=true
)
```

After all trajectories return, synthesize the results.

---

## Template: STEM / Math Problems

Use this template when the problem involves mathematics, physics, or formal science.

```
You are solving a math/science problem. Generate an independent solution.

Problem:
<PROBLEM_STATEMENT>

Requirements:
- Show all work step by step
- Verify your answer by checking edge cases or alternative methods
- State your final answer clearly as: ANSWER: <value>

Solution:
```

---

## Template: General Reasoning Problems

Use this template for logic puzzles, strategy problems, philosophical reasoning, or any non-STEM complex reasoning.

```
You are solving a reasoning problem. Generate an independent solution.

Problem:
<PROBLEM_STATEMENT>

Requirements:
- Identify all key constraints and relationships
- Consider multiple angles before committing to an answer
- Check for logical consistency
- State your conclusion clearly as: ANSWER: <conclusion>

Solution:
```

---

## Synthesis Template

After collecting all trajectories, use this to produce the final answer:

```
You have K independent solutions to the following problem:

Problem:
<PROBLEM_STATEMENT>

Trajectories:
<Trajectory 1>
<Trajectory 2>
...
<Trajectory K>

Your task:
1. Identify areas of agreement across trajectories
2. For disagreements, analyze which trajectory has the strongest reasoning
3. Synthesize the best elements into a single, verified answer
4. If most trajectories agree, that answer is likely correct
5. If trajectories diverge, carefully evaluate each before deciding

Provide:
- The final synthesized answer
- Brief explanation of why this answer is correct
- Note any key insights from specific trajectories
```

---

## Chinese Language Variant (中文模板)

当用户使用中文提问时，使用以下模板：

### STEM/数学题模板

```
你正在解决一个数学/科学问题。请独立生成一个解题方案。

题目：
<题目内容>

要求：
- 逐步展示完整推导过程
- 通过检验特殊情况或替代方法来验证答案
- 明确给出最终答案：答案：<答案>

解题过程：
```

### 通用推理题模板

```
你正在解决一个推理问题。请独立生成一个解题方案。

题目：
<题目内容>

要求：
- 识别所有关键约束和关系
- 在确定答案前考虑多个角度
- 检查逻辑一致性
- 明确给出结论：答案：<结论>

解题过程：
```

### 综合模板

```
你有K个针对以下问题的独立解法：

题目：
<题目内容>

轨迹：
<轨迹1>
<轨迹2>
...
<轨迹K>

你的任务：
1. 找出各轨迹的一致之处
2. 对于分歧之处，分析哪个轨迹的推理最有力
3. 综合各轨迹的最佳要素，给出单一的、经过验证的答案
4. 如果大多数轨迹一致，该答案很可能是正确的
5. 如果轨迹分歧较大，仔细评估后再做决定

请提供：
- 最终综合答案
- 简要说明为什么这个答案是正确的
- 标注来自特定轨迹的关键洞察
```

---

## Notes

- Each trajectory should be truly independent — do not share reasoning between them
- More trajectories (higher K) = higher accuracy but more compute
- For competition math, `stem` template with K=8 typically works well
- For open-ended reasoning, `general` template with K=8 is recommended
- Increase iterations for problems that require refinement
