# heavyskill 模式2 审查结果被截断（P54）

> 档案：2026-08-21-heavyskill-mode2-truncation.md | 新 P#：P54
> 现象域：skills/heavyskill（模式2 Python 流水线），HGF 工作流会话多次复现
> 证据：`output/hgf-productivity-review-result.json`（2026-08-21 生产力评审，K=8，110KB）

## 现象

在 HGF 工作流的会话中多次出现"读取审查结果时处于被截断状态"：

- **审议结论（最终综合意见）被硬切**：`deliberation[0].deliberation_response` 仅 1612 字符，
  尾停在 `### 主要分歧\n- Attempt 2 `（断在列表中途，无最终答案）。
- **部分推理轨迹被截断**：traj[3] 2082 字符断在句中；traj[4] 仅 118 字符（标题即断）。
- **共识被垃圾污染**：`consensus_answer = 'ning process maybe structured'`（思维链碎片）；
  `answer_frequencies` 8 项全不同（8/8 unique）→ 共识机制名存实亡。
- **历史佐证**：PROGRESS.md L127 记录 R5 评审"有效轨迹 4/8（其余 maxTokens 截断）"。

## 根因（代码级）

1. **配置断裂（主因）**：`run_heavyskill.py` 的 `--max_tokens` 默认 4096，且从 config.yaml
   只加载 api_key/api_base/model/timeout——`max_tokens: 80000` 从未生效（实测一直是 4096）。
   长审查输出 + 推理模型思维链占预算 → 硬截断。
2. **静默截断**：`finish_reason == "length"` 被记录但全管线无人检查（parallel_reasoning 只判
   "error"），截断轨迹照常进入审议与共识；输出 JSON 也不带 finish_reason → 消费端无法感知。
3. **语义错位**：content 为空时回退 reasoning_content（思维链）当轨迹（openai_compatible.py），
   思维链没有"最终答案"；`extract_answer` 又对截断/思维文本抓任意片段/末行 → 共识变垃圾。
4. **审议预算不独立**：审议复用 `max_tokens`（4096），config.yaml 的 `summary_max_tokens` 字段
   根本不存在于 HeavySkillConfig——最终结论（最关键输出）同样被截断。
5. **读取端二次截断**：110KB JSON 超会话单次读取；`summary()` 只打印两个短字段且都是垃圾。

## 修复（已实施，2026-08-21）

| 文件 | 改动 |
|------|------|
| `configuration.py` | 新增 `summary_max_tokens: int = 16384`；`max_tokens` 默认 4096→32768；校验 |
| `agent/openai_compatible.py` | LLMResponse 新增 `truncated`（finish_reason=length）与 `content_fallback` 标记 |
| `workflow/parallel_reasoning.py` | 统计 `truncated_count`/`content_fallback_count`；to_dict 输出逐轨迹截断标记与 finish_reason；告警 |
| `workflow/memory_cache.py` | 截断轨迹 `is_valid=False`（剔除出审议/共识）；思维链回退轨迹 answer=None（不投票但保留素材） |
| `workflow/utils.py` | `extract_answer` 加固：无终止符的截断残稿不走末行回退；答案标记大小写不敏感防残段；正则停止符补 `\n` |
| `workflow/sequential_deliberation.py` | 审议改用 `summary_max_tokens` 独立预算；DeliberationResult 带 `truncated` 标记 |
| `workflow/pipeline.py` | 透传截断标记；输出 JSON 新增 `truncation` 摘要；`summary()` 截断告警 |
| `scripts/run_heavyskill.py` | 从 config.yaml 加载 max_tokens/summary_max_tokens（CLI > config > 默认）；新增 `--summary-max-tokens`；截断告警 |
| `config.yaml` | `max_tokens: 32768`、`summary_max_tokens: 16384`（80000 会超时，4096 会截断） |
| `tests/test_truncation.py` | 9 项防回归单测（截断标记/剔除/提取加固/预算字段） |

**注意事项（防复发）**：
- 预算不可盲目拉到 80000：`reasoning-model-pitfall` 实测 v4-pro K=6×80000 会超时（300s+）。
  32768/16384 是截断与超时的平衡点；仍截断时优先加 `--summary-max-tokens`。
- 读取审查结果的标准姿势：先看 JSON 的 `truncation` 摘要字段，再取
  `deliberation[0].deliberation_response` 全文，勿整读 JSON、勿只信控制台 summary。

## 验证

- `python -m pytest skills/heavyskill/tests/test_truncation.py -v` → 9 passed
  （截断轨迹剔除、思维链不投票、extract_answer 拒绝截断/思维碎片、truncated/content_fallback 标记、
  truncation 摘要、summary_max_tokens 字段）
- 真实 JSON 样本回归：`hgf-productivity-review-result.json` 中的 traj[3]/traj[4]/consensus 垃圾
  在加固后的 extract_answer 下均返回 None（不再污染共识）。
- 待 API 可用后重跑 K=8 冒烟：断言全部轨迹含"最终答案"标记、deliberation 完整收尾、
  `truncation` 全 0/False。
