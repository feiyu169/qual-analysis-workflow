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

## 模式总览（4 种运行形态）

| | 模式1：子代理模板（推荐日常） | 模式2-基础：Python 流水线 | 模式2-增强：双模型 | 模式2-分批：大内容 |
|---|---|---|---|---|
| 机制 | K 路并行子代理 + 会话内审议 | K 路并行 LLM + 顺序审议 | 基础 + 质量分择优/auto_k + mimo 验证/二审 | 大内容分块独立审查 + 元审议 |
| 依赖 | 无（DSH 子代理） | python + httpx + DEEPSEEK_API_KEY | + XIAOMI_TOKEN_PLAN_CN_API_KEY（mimo） | 同模式2-基础 |
| 适用 | 内容已在本会话、无 key、快速迭代 | 大批量、需 JSON 留存轨迹、常规审查 | **关键门禁/架构级评审、需独立第三方视角** | 方案/代码 >18000 字符 |
| 代码位置 | 本技能内模板 | `skills/heavyskill/` | 同左（四路径增强） | `workflow/chunked_review.py` |

**选择决策树**（自上而下）：

```
内容在会话上下文且无/不想用 API key？──是→ 模式1（K=4 快速 / K=8 标准）
                    │否
内容 > 18000 字符？──────────────────是→ 模式2-分批（--chunk-content-file，超限不再截断）
                    │否
关键裁决/门禁放行？──────────────────是→ 模式2-增强（--enable-validator --enable-second-review
                    │                        [可选 --auto-k]；无 mimo key 自动退化为基础）
                    │否
常规审查/留痕/批量───────────────→ 模式2-基础
```

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
- 控制台在存在截断/退化时打印 ⚠️ WARNING。
- 审议响应截断时自动**回退共识**（不采信残稿结论，P54-R3）。
- 截断且无最终答案时 **exit 2**（除非 `--accept-partial` 显式接受部分结果，P54-R5）。

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
或加 `--accept-partial` 显式接受部分结果（否则截断且无答案时退出码为 2，自动化可感知）。

### K 值选择

| K | 成本 | 时间 | 质量 | 用途 |
|---|------|------|------|------|
| 4 | 1x | 1x | 基线 | 快速审查 |
| 8 | 2x | 2x | 更好 | **标准（推荐）** |
| 16 | 4x | 4x | 最佳 | 关键审查（有稳定性问题） |

### 模式选择对照（含四路径增强，2026-08-21）

| 维度 | 模式1 | 模式2-基础 | 模式2-增强 | 模式2-分批 |
|---|---|---|---|---|
| 成本（tokens） | 子代理配额 | K=8 ≈ 85K tokens / ~4min（PGNB 实测） | 基础 + 2 次 mimo（~12s×2） | 基础 × 块数 + 元审议 |
| 质量保障 | 多轨迹+审议 | 多轨迹+审议+截断治理 | **+ 质量分择优 + 动态 K + mimo 异质校验/二审** | 分块全覆盖 + 元审议 |
| 输入约束 | 内容必须内联 prompt | 内联 ≤18000 字符（超出截断） | 同基础 | `--chunk-content-file` 自动分块 |
| 关键命令 | — | `--reason_k 8 --summary_k 4 --language cn` | 加 `--enable-validator --enable-second-review [--auto-k]` | `--chunk` 或直接用 `ChunkedReviewer` |

**增强开关说明（模式2-增强）**：
- `--enable-validator`：审议后 mimo 校验（规则：verdict 格式/P0 一致性/维度覆盖；LLM：逻辑矛盾/遗漏/过度自信），输出 JSON `validation` 字段；FAIL 时告警
- `--enable-second-review`：mimo **独立二审**（不注入一审结论）→ 确定性仲裁（任一 FAIL 取 FAIL / 一致提置信度 / 分歧标记人工复核），输出 `second_review` 字段
- `--auto-k`：按 query 长度自动定 K（short 2 / medium 4 / long 8）+ 首轮质量不足自动补跑（输出 `k_extended`）
- mimo key 未配置时 validator/二审**自动降级**（fail-open，不阻断主链路），等价于模式2-基础

**mimo key 注入**：`--validator-api-key $env:XIAOMI_KEY`（或改 `config.yaml` 的 `validator_api_key`，勿提交真实密钥）。

---

## 与导出资产的关系

- Python 实现：`skills/heavyskill/`（`configuration.py`、`workflow/{pipeline,parallel_reasoning,sequential_deliberation,memory_cache,utils}.py`、`agent/openai_compatible.py`、`scripts/run_heavyskill.py`）
- 纯 prompt 模式原版：`skills/heavyskill/skill/heavyskill.md`
- 审查模式沉淀（hermes 侧实践）：`skills/heavyskill/references/`（多轨迹审查、清单注入、
  迭代审查、双阶段审查等模式）

---

## 插件工具（一期，2026-08-22，会话级需重建）

heavyskill 已提供 Cordis 动态插件 `heavyskill-tools`（持久化源码
`workflow/plugin/heavyskill-tools.js`，**会话级——DSH 重启即失，需 cordis_define +
cordis_run 重建**）。4 个原生工具，经长驻桥 `heavyskill_bridge.py --serve` 调用引擎：

| 工具 | 作用 | 关键参数 |
|---|---|---|
| `hsk_review` | K 路多轨迹审查（basic/enhanced/chunked） | query, content?, k?, mode?, api_key?, validator_api_key? |
| `hsk_verify` | 对已有结论做 mimo 验证 | conclusion, trajectories?, query?, validator_api_key? |
| `hsk_history` | 读样本库最近记录 | limit? |
| `hsk_adjudicate` | 人工裁决样本（adopt/reject/amend，audit 双签名） | sample_id, verdict, notes?, adjudicator? |

要点：
- 工具返回**摘要（≤5KB）+ 完整结果文件路径**（80KB JSON 不直接回传，防 stdout 截断）
- `hsk_review` 内置**蜜罐自检**（已知结果用例，防缓存/硬编码伪装）
- key：默认读环境 `DEEPSEEK_API_KEY` / `XIAOMI_KEY`，也可显式传参
- 重建步骤（重启后）：读 `workflow/plugin/heavyskill-tools.js` → cordis_define（kind new，
  idPrefix 'hsk'，code.host = 文件 `return {...}` 函数体）→ cordis_run
