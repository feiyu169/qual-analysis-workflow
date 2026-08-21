---
name: heavyskill
description: >-
  HeavySkill 多轨迹推理引擎（DSH 适配版）。适用于复杂推理、技术方案审查、算法设计、
  多步推导等需要探索多条独立路径的任务。提供两种模式：模式1 子代理模板（K 路并行
  子代理独立推理 + 综合审议，DSH 原生，无需外部依赖）；模式2 Python 流水线（K 路
  并行 LLM 调用 + 顺序审议，复用工作区 skills/heavyskill 代码）。
---

# HeavySkill — 多轨迹推理引擎（DSH 适配）

HeavySkill 的核心思想（论文 arXiv:2605.02396）：与其让单个推理路径直接回答，不如
**并行生成 K 条独立推理轨迹（temperature 高、互不共享上下文），再由一次"审议"环节
交叉验证、找错、综合出最终答案**。K 条轨迹提供多样性，审议捕获共识并纠正单条轨迹的错误。

## 何时使用

- 复杂推理问题（多解法并存、逻辑陷阱、多步推导链）
- 技术方案 / 代码 / 文档的深度审查（发现率优于单次直答）
- 数学 / STEM 问题（可验证性要求高）
- 需要"独立第三方视角"的评审（如买方报告质量审查、Gate 放行评估）

## 两种模式

| | 模式1：子代理模板（推荐） | 模式2：Python 流水线 |
|---|---|---|
| 依赖 | 无（DSH 子代理） | python + httpx + DEEPSEEK_API_KEY |
| 成本 | 受会话子代理配额约束 | 受 API 配额约束 |
| 适用 | 日常审查、内容已在本会话上下文 | 大批量、需要 JSON 输出、要留存轨迹 |
| 代码位置 | 本技能内模板 | `skills/heavyskill/`（导出代码） |

---

## 模式1：子代理模板（DSH 原生）

**阶段 A — K 路并行推理**：为每条轨迹启动一个独立子代理（`subagent`，`run_in_background: true`，
一次消息里全部发出，并行跑）。每个子代理的 prompt 必须**完全独立**，包含：

```
你是独立推理轨迹 #{n}。请独立解决以下问题，不要假设有其他人协作。
问题：{完整问题内容}
要求：
1. 展示完整推理过程
2. 验证你的答案（检查边界情况 / 替代方法）
3. 最后一行必须给出：最终答案：<答案>
```

**关键规则（实测教训）**：
- **子代理读不到本地文件**。问题内容必须**内联**在 prompt 里（文档关键段落、代码片段、
  数据样例、检查清单），禁止只传文件路径——否则子代理只能给泛泛而谈的评论，浪费 token。
- K 取值：K=4 快速（基线）／**K=8 标准（推荐）**／K=16 最佳但有稳定性问题。

**阶段 B — 综合审议**：K 条轨迹返回后，再做一次审议（可在本会话上下文内综合，或再
派一个子代理做"审议者"）。审议 prompt 模板：

```
你有 K 条针对同一问题的独立推理轨迹：

{逐条粘贴轨迹内容}

任务：
1. 逐条找出逻辑错误、计算错误、错误假设
2. 交叉验证：哪些轨迹收敛到同一答案？哪些分歧？
3. 综合：给出单一、经过验证的最终答案
4. 若多数轨迹一致，验证其推理是否成立；若分歧，判断哪条推理最可靠

最终答案：<答案>
```

**阶段 C — 迭代（可选）**：把审议结果作为下一轮上下文回灌，重复 A/B，直到收敛
（技术方案审查通常 3-6 轮）。

### 代码/文档审查的清单注入

审查类任务在 query 中注入领域检查清单，可将发现率从 71% 提升到 86%（实测）。
**单阶段注入 > 两阶段注入**（86% vs 60%）。标准中文审查维度：

- **有效性提升**：方案是否真正解决问题？数据流是否正确？预期效果是否量化？
- **架构简洁**：模块是否最少？边界是否清晰？是否重复造轮子？
- **代码质量**：错误处理、类型注解、可测试性、是否有可执行示例代码？

---

## 模式2：Python 流水线

代码在 `skills/heavyskill/`（hermes 导出），依赖 `httpx`（工作区 `tools/finance/.venv` 若不存在，
用系统 python，`python -m pip install httpx` 即可）。

```powershell
# 用工作区 venv 的 python 运行（含 httpx）；无 venv 时用系统 python
$py = "D:\OneDrive\文档\deepseek harness workspace\tools\finance\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
cd "D:\OneDrive\文档\deepseek harness workspace\skills\heavyskill"

& $py scripts\run_heavyskill.py `
  --query "请审查以下技术方案（内联方案全文）：..." `
  --reason_k 8 --summary_k 4 --language cn `
  --api_key $env:DEEPSEEK_API_KEY `
  --output "D:\OneDrive\文档\deepseek harness workspace\heavyskill-output.json"
```

要点（实测教训）：
- **必须显式传 `--api_key`**（默认 `config.yaml` 里的 key 是硬编码的历史密钥，应轮换）。
- **必须设置命令超时**：K=8 实测 94s+（Stage1≈53s + Stage2≈41s），pwsh 默认超时要给足
  （`timeoutMs: 300000`）。
- 内容一律内联进 `--query`；`--include-file` 会把文件内容追加进 query（子代理仍读不到文件）。

### ⚠️ 截断治理（P54，2026-08-21 修复）

**历史问题**：模式2 的审查结果常被截断——`max_tokens` 默认 4096 且 config.yaml 的预算从未被
CLI 加载（配置断裂）；推理模型（v4-pro）思维链计入预算，占满后可见输出被硬切；`finish_reason`
从不检查，截断轨迹静默进入审议与共识；`extract_answer` 把思维/断句碎片当答案 → consensus 变垃圾。

**修复后行为**（代码已改，`config.yaml` 生效）：
- `max_tokens: 32768`（推理）、`summary_max_tokens: 16384`（审议，独立预算）——由
  `run_heavyskill.py` 从 config.yaml 自动加载；CLI 可用 `--max-tokens` / `--summary-max-tokens` 覆盖。
- 截断轨迹（finish_reason=length）自动**从审议与共识中剔除**（保留在 JSON 的 trajectories 供查证）；
  思维链回退轨迹（content 为空）不参与共识投票。
- 输出 JSON 新增 **`truncation` 摘要字段**：`{reasoning_truncated_count, content_fallback_count, deliberation_truncated}`。
- 控制台在存在截断时打印 ⚠️ WARNING。

**读取审查结果的正确姿势（勿整读 100KB+ JSON，勿只信控制台摘要）**：
```python
# 1) 先看截断摘要
import json
d = json.load(open("heavyskill-output.json", encoding="utf-8"))
print(d["truncation"])   # 全 0/False 才可放心采信
# 2) 审议结论（最终综合意见）取全文
print(d["deliberation"][0]["deliberation_response"])
# 3) 需要逐条轨迹时按关键词切片（如 总体结论/最终答案），不整读
```
**若 `truncation` 非零**：增大 `--summary-max-tokens`（审议截断）或 `--max-tokens`（轨迹截断）后重跑；
或显式标注"部分结果接受"。

### K 值选择

| K | 成本 | 时间 | 质量 | 用途 |
|---|------|------|------|------|
| 4 | 1x | 1x | 基线 | 快速审查 |
| 8 | 2x | 2x | 更好 | **标准（推荐）** |
| 16 | 4x | 4x | 最佳 | 关键审查（有稳定性问题） |

---

## 与导出资产的关系

- Python 实现：`skills/heavyskill/`（`configuration.py`、`workflow/{pipeline,parallel_reasoning,sequential_deliberation,memory_cache,utils}.py`、`agent/openai_compatible.py`、`scripts/run_heavyskill.py`）
- 纯 prompt 模式原版：`skills/heavyskill/skill/heavyskill.md`
- 审查模式沉淀（hermes 侧实践）：`skills/heavyskill/references/`（多轨迹审查、清单注入、
  迭代审查、双阶段审查等模式）
