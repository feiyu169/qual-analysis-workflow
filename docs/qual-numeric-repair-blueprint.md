# 数值错位根治——双专家综合实施蓝图（2026-08-22）

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
| **P1** | T2 开关、组装闸门救援 sweep | 低置信场景可开启 |
| **P2** | digit_typo 提示、T3 案例回流负样本 | 防校验器回退 golden set |

## 六、回归防线

历史错例（1031.63→31.63 等）固化为 golden set 测试用例——任何校验/回填改动必须全量通过（防"修好一个错位、放开十个错位"）。

## 七、风险与平衡

- 过度拦截：P0/P1 阻断 → 报告受阻 → 缓解：**回填优先于阻断**（能程序修复不阻断）+ 分级（P2 不阻断）+ 锚点缺失降级占位+标注
- 拦截不足：失真数字进报告 → 缓解：T1 自证兜底（100% 修复不依赖 LLM）+ 标注兜底（未修复必显式）+ 闸三人工抽核关键数字
- 单一数据源伴生风险：源本身错（口径切换/单位混用）→ sanity check（负资产/量级突变/同比超阈值提示）
