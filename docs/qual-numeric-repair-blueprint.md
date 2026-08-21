# 数值错位根治——双专家综合实施蓝图（2026-08-22）

> **实施状态（2026-08-22 已落地，commit 9174e3f）**：本蓝图 P0 五项全部实现并通过测试——
> - 层 0 `normalize_values.anchor_deviation`（×10ⁿ/÷10ⁿ、prefix_drop、digit_typo）✅ test_anchor_deviation（7 例）
> - 层 1 `qual_v8/data_anchor.extract_data_spans` last-wins 修复 ✅（同指标多处出现不漏检，span 逐出现定位）
> - 层 1 `qual_v8/anchor_repair.py` T1/T3（自证：替换后整章重跑校验器必须通过，否则全量回滚）✅ test_anchor_repair（8 例）
> - 层 2 `workflow._generate_chapter` 清洗层（clean-then-check：T1 修正后闸门过→不重试；T3→omit 指令"省略该数值"）✅ test_generate_chapter_cleans_misaligned_value
> - 层 2 `review_repair_loop._repair_chapters` 分层（sweep 先修 + 值类问题不进 LLM prompt）✅ test_repair_chapters_triage_value_issues
> - 全量 132 测试通过；ruff 零新增告警。P1（T2 开关）、P2（digit_typo 提示/负样本回流）按计划留待后续。
> 另修复 test_v31_p0a 裸模块属性赋值跨文件泄漏（monkeypatch 化），消除 pytest 全量运行的顺序污染。

> **P1/P2 实施状态（2026-08-22 追加，commit 待推送）**：
> - **P1 T2 低置信开关** ✅ `anchor_repair.repair_chapter_values(..., enable_t2=False)` / `sweep_all_chapters(..., enable_t2=False)`——弱签名（digit_typo）但 FY 上下文唯一目标（单候选）时仍自动替换，自证闭环兜底；默认关（宁可不修不误修）。配置：`WorkflowConfig.advc_enable_t2`（默认 False）→ context → Gate4 修复循环 / Gate8 救援 sweep。
> - **P1 组装闸门救援 sweep** ✅ `gate8._advc_rescue_sweep`——最终闸门前对 chapters 做全章确定性清洗（T1 恒开、T2 由 context 开关），有修复则就地更新并重组 report，随后数字校验器以清洗后内容为准。覆盖决策/概览章（不经 _generate_chapter 清洗层的第 0/10 章）。
> - **P2 digit_typo 弱提示** ✅ 新增 `ChapterRepairResult.hints` 通道——弱签名（digit_typo）不修复不阻断（T2 关时），进 hints 清单供调用方呈现；`sweep_all_chapters` 返回 4 元组 `(fixed, fixes, unresolved, hints)`。修复 digit_typo 全精度串长度淹没问题（2 位小数口径比较：1131.63 vs 1031.63 命中弱签名）。
> - **P2 T3 案例回流负样本** ✅ `test_advc_golden.py` 黄金回归集（15 例：真实错位 4 正样本 + 合法/历史/近似 5 负样本 + 幻觉只标注 + digit_typo 提示 + T2 开/关 + 幂等 + sweep 契约），已接入 `tests/test_qual_v31_aggregate.py`（HGF 门禁入口，防校验器回退）。
> - 全量 236 测试通过（含 tests/ 聚合 88）；ruff 零告警。P2 digit_typo 提示已随 Gate8/日志呈现，未做报告正文标注（留待闸三人工抽核呈现）。

问题：LLM 写作数值转写错位（1031.63→31.63），Gate4 拦截但修复循环 LLM 反复产错 → 报告无法产出。
双专家独立评审后综合：
- **投资分析专家**（方法论）：`docs/qual-anchor-repair-architecture.md` 前身为方法论评审（本文件合并）
- **编程专家**（架构）：`docs/qual-anchor-repair-architecture.md`（ADVC 三层架构，已落盘）

---

## 一、双专家共识（第一性原则）

> **报告中的财务数字是"引用"（citation），不是"创作"（composition）。**
> **值类问题（数字 vs Wind 锚点）是从 LLM 职责中整体移出的确定性任务——正确性由程序保证，LLM 只保留结构/表述/逻辑类修复。**

两专家独立得出同一结论：
1. 值类错误是**生成性错误**（LLM 生成通路不稳定），重写是独立采样——重试不降错误率只增成本
2. 修复必须"**查源—回填**"（数据系统直接纠正），不是"重新叙述"（LLM 重写）
3. 现状核心不对称：**checker 强**（Gate3/4/patch validators 全部确定性拦截）× **fixer 弱**（唯一手段 LLM）

## 二、结构缺口（编程专家源码核实）

| 缺口 | 说明 |
|---|---|
| (a) DataAnchor._extract_data **last-wins** | `data[k]=value` 覆盖——同指标多处出现时前错后对会被掩盖 → 漏检 |
| (b) normalize_values（B5-2）**未接线** | 模块已建+有测试，但 workflow.py 无任何 import |

## 三、架构方案（合并）

### 层 0：签名检测原语（normalize_values.py 扩展）
`anchor_deviation(value, anchors) -> list[AnchorDeviation]`
- ×10^n / ÷10^n（n=1..4：小数点位错、亿↔万、万亿↔亿）
- **prefix_drop**（数字串后缀关系：1031.63→31.63 丢"10"前缀）
- digit_typo（弱签名，仅提示）

### 层 1：修复引擎（新模块 qual_v8/anchor_repair.py，唯一新组件，零 LLM）
`repair_chapter_values / sweep_all_chapters`，三档置信：
- **T1 高置信自动替换**：指标绑定 + 唯一强签名 + 语境排斥 + span 精确定位 + **自证**（替换后整章重跑 validate_chapter_any_fy 必须通过）
- **T2 低置信**（FY 上下文唯一，默认关）
- **T3 只标注**：幻觉值/多候选歧义 → 证据化清单，**绝不喂 LLM**（第 1 轮立即豁免，带证据 fail-closed）

### 层 2：接线
- `_generate_chapter`：clean_ai_artifacts 后插入**强制清洗层**（clean-then-check：清洗有 fixes 且闸门过 → 接受不重试；T3 → 重试 prompt 用 omit 指令"省略该数值"）
- `_repair_chapters` 分层：全局 sweep → 问题 triage（**值类问题不进 LLM prompt**）→ LLM patch 仅结构/表述 → numeric validator 后置兜底
- 单调守卫兼容：sweep 先于快照、确定性修复不参与回滚

## 四、投资方法论映射（纪律层）

| 方法论 | 实现映射 |
|---|---|
| 单一事实来源（锚点卡） | anchor card：wind_data → {anchor_id, 财年, 数值, 单位, 币种}，写作 prompt 与校验器共用 |
| 数字身份四元组 | (指标, 财年, 单位, 币种)——锚点身份匹配替代量级启发式 |
| 重要性分级（审计 materiality） | P0（营收/净利/总资产/估值…）阻断+回填；P1 阻断+回填；P2 warning+标注 |
| 三道闸（防产生/防流入/防影响） | 闸一写作规范（锚点卡注入）→ 闸二生成后校验（全量 tie-out）→ 闸三发布前审核（红队+签字） |
| 显式标注（不静默放行） | 三态（✅/⚠️/❌）+ 未修复呈现差异 + 《数据核对声明》附录 + 草稿/受限发布分级 |
| 修复可靠性（回填非重写） | T1 程序化回填（自证闭环）；LLM 仅语义错配边界（正确值硬约束注入） |

## 五、实施优先级

| 优先级 | 项 | 验收 |
|---|---|---|
| **P0** | 签名检测 + 单测（test_anchor_deviation：签名谱系+歧义夹具） | 1031.63→31.63 命中 prefix_drop |
| **P0** | _extract_data last-wins 修复（extract_data_spans） | 同指标多处出现不漏检 |
| **P0** | anchor_repair T1/T3（自证：替换后校验器必须通过） | test_anchor_repair：同值不同指标/历史引用/幂等/自证 |
| **P0** | 接 _generate_chapter 清洗层 + _repair_chapters 分层 | test_generate_clean：mock LLM 错值→1 次调用不重试；test_repair_loop_no_llm_values：LLM prompt 不含值类问题 |
| **P1** | T2 开关、组装闸门救援 sweep（✅ 已落地：enable_t2 开关 + gate8 _advc_rescue_sweep） | 低置信场景可开启；最终闸门前确定性救援 |
| **P2** | digit_typo 提示、T3 案例回流负样本（✅ 已落地：hints 通道 + test_advc_golden 黄金集 15 例） | 防校验器回退 golden set |

## 六、回归防线

历史错例（1031.63→31.63 等）固化为 golden set 测试用例——任何校验/回填改动必须全量通过（防"修好一个错位、放开十个错位"）。

## 七、风险与平衡

- 过度拦截：P0/P1 阻断 → 报告受阻 → 缓解：**回填优先于阻断**（能程序修复不阻断）+ 分级（P2 不阻断）+ 锚点缺失降级占位+标注
- 拦截不足：失真数字进报告 → 缓解：T1 自证兜底（100% 修复不依赖 LLM）+ 标注兜底（未修复必显式）+ 闸三人工抽核关键数字
- 单一数据源伴生风险：源本身错（口径切换/单位混用）→ sanity check（负资产/量级突变/同比超阈值提示）
