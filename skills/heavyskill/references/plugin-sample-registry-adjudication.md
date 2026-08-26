# 裁判裁决书：HeavySkill 插件化 + 样本库

> 档案：plugin-sample-registry-adjudication.md | 日期：2026-08-22
> 裁决方式：三方独立评估（代码专家 / 架构专家 / 评审专家）→ 裁判综合
> 状态：**批准实施**——分期推进（一期插件化 → 二期样本库）

---

## 一、三方意见汇总

| 维度 | 代码专家 | 架构专家 | 评审专家 |
|---|---|---|---|
| 可行性 | A **有条件可行**（80KB JSON stdout 是 P0 → 桥端摘要压缩）；B **可行** | 两案 **有条件可行**（3 前提） | 两案 **有条件可验收**（补防伪后） |
| 核心挑战 | ① 80KB JSON 单行截断（P0）② 长驻 asyncio 内存 ③ 中文编码 | ① 生命周期错配（插件会话级 vs 样本持久）② 双维护债务（5-6 文件）③ 样本膨胀 | ① 缓存伪装（P0）② 桥进程泄漏（P0）③ 裁决伪造（P0）④ 校准过拟合 |
| 工作量 | A ~6.5 + B ~5.5 = ~12 人天，A 先 B 后 | — | — |
| 关键设计 | 工具合并为 3 个；侵入点 CLI+桥双写；portalocker 文件锁；Spearman+分桶校准 | **样本库私有 + hsk.v1 信封**（与 hgf.v1 同构）；桥复用 HGF 模式；**CLI 兜底保留** | 每功能 L1-L5 验收；纳入 gate_2_2/3_1；双签名；蜜罐输入防伪装；N<20 时 `insufficient_data` |

## 二、裁判裁定（分歧解决）

1. **工具集取 4 个**：`hsk_review`（mode=basic/enhanced/chunked，second_review 并入 enhanced）、`hsk_verify`（独立复核）、`hsk_history`、`hsk_adjudicate`——减少接口面 = 减少双维护
2. **样本库归属：HeavySkill 私有**（`skills/heavyskill/data/`），`hsk.v1` 信封与 `hgf.v1` 同构（未来可无损迁移）；**维持零依赖线**（不读 `.hgf/`、不调 HGF）；纳入 HGF gate 列为可选二期
3. **防伪三件套（准出强制）**：蜜罐输入自检（防缓存伪装）、进程树启停验证（防泄漏）、裁决 audit log + 双签名（防伪造）
4. **校准阈值**：N<20 时 quality_score 标记 `insufficient_data`；N<30 只做描述性统计（分桶采纳率）
5. **分期实施**：一期插件化（~6.5 人天，当下解决调用痛点）；二期样本库（~5.5 人天，长期校准资产）；**一期先埋 record_sample 采集 hook**，二期启用统计

## 三、最终裁决

**两草案可行，批准实施——一期插件化 → 二期样本库，合计 ~12 人天。**

**可行依据**：三方一致无架构级阻断风险；桥复用已验证的 hgf-tools 模式（~80% 基础设施）；样本库侵入点清晰、统计路径成熟；风险均有明确缓解。

**准出条件（不满足不得宣称完成）**：
1. hsk_review 真实调 LLM（蜜罐自检通过，非缓存/硬编码）——L3
2. bridge 启停无进程残留——L4
3. 现有 33 单测 + HGF 9 门禁全绿（插件化不改坏 pipeline）——L5
4. `--adjudicate` 有 audit log + 双签名——L3
5. 样本 <20 时 quality_score 标记 `insufficient_data`——L3
6. 完整结果写临时文件、桥返回 ≤5KB 摘要（80KB stdout P0 缓解）——L3

**风险接受**：双维护债务（薄桥层 + SKILL.md 流程化更新）、样本冷启动（N<30 描述性统计）、80KB 返回（摘要压缩）。

**止损点**：一期插件化后连续 2 周无真实使用 → 二期不启动。

## 四、一期实施要点（代码专家方案细化）

- `heavyskill_bridge.py --serve`：JSON-in/JSON-out 长驻进程；命令路由（review/history/adjudicate）；`safe_handle` 结构化错误（不杀进程）；`summarize_result` ≤5KB 摘要 + 完整结果写临时文件；`sys.stdout.reconfigure(encoding='utf-8')` + `ensure_ascii=False`；每次命令独立创建 pipeline（复用内部 `async with` 生命周期）
- `workflow/pipeline.py` 新增 `summary_for_bridge()`（trajectories 摘要为 {index, chars, answer}，deliberation_response 截断至 2000 字符）
- `workflow/sample_registry.py`：`record_sample`（一期占位 hook）/ `read_samples`（tail 语义）/ `adjudicate`（audit log + adjudicator 字段）
- `workflow/plugin/heavyskill-tools.js`：4 工具；队列串行；命令级超时表（review 10min/verify 2min/history+adjudicate 15s）；进程死亡自动重建；`inject: ['timer']` + `ctx.timeout`；进程树 terminate（Windows taskkill /T）
- 蜜罐：工具内置已知结果用例定期自检

## 五、验收（HGF 流程）

- 单测：test_bridge.py（路由/超时/崩溃恢复/中文往返/摘要 <10KB）+ test_sample_registry.py（CRUD/并发/audit）
- 门禁：ruff 全绿 + pytest 全套 + HGF CLI MUST_PASS（exit=0）
- 集成：真实 API K=2 端到端（基础/增强两种 mode）
- 沉淀：CHANGELOG + SKILL.md 工具说明
