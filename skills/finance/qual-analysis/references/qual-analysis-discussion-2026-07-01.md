# 快手分析报告未按qual框架执行 — 三人小组讨论报告

**日期**: 2026-07-01  
**讨论参与方**: 投资分析专家、编程专家、协调者  
**讨论轮次**: 3轮（各专家独立分析 → 协调者综合）

---

## 1. 问题概述

快手分析报告虽然技术上调用了 `run_analysis()` 并生成了 11 章（ch00-ch10），且显示 `success=True quality=high`，但实际内容没有按照 qual 框架的核心精神执行。

**核心矛盾**：结构上"过关"不等于内容上"达标"。

---

## 2. 投资分析专家分析

### 2.1 主要问题（按严重程度排序）

#### 问题一：形式合规 vs 实质合规的断裂（🔴 致命）

系统输出 `success=True quality=high`，关键词匹配验证也通过（ch05有DAU/GMV、ch07有DCF/PE/目标价）。但这恰恰暴露了一个根本性问题：**验证逻辑仅检查关键词存在性，而非CHAPTER_CONTRACT的must_answer是否被实质性回答**。

以第7章为例，CHAPTER_CONTRACT要求：
- 历史股东回报（股价表现、分红、回购）
- 当前估值水平（PE、PB、PS、EV/EBITDA）
- 估值合理性分析
- 未来回报路径（增长、分红、回购、估值提升）
- **安全边际评估**

仅出现"DCF""PE""目标价"等关键词，不等于这些must_answer项被逐一、严谨地回答。

#### 问题二：行业视角（preferred_lens）可能未被正确应用（🟠 严重）

快手作为平台经济公司，模板明确要求：
- 第1章应用 **platform** 视角（网络效应、双边市场）
- 第2章应用 **tech** 视角（技术迭代、颠覆风险）
- 第5章应用 **growth** 视角（收入增速、用户增长、TAM）

#### 问题三：ITEM_RULE条件项可能未被触发（🟠 严重）

快手作为多业务公司（直播+电商+广告+本地生活），触发条件项"多业务公司"（business_model数组长度>2），要求：
- 分部收入占比
- 各业务协同关系

### 2.2 根本原因分析

| 根因层面 | 具体原因 | 影响 |
|----------|----------|------|
| **验证机制** | 验证逻辑仅检查关键词存在性，而非must_answer的语义覆盖 | 形式合规掩盖实质缺失 |
| **审计深度** | `_audit_and_fix` 可能仅做结构审计，未做语义审计 | 框架约束力失效 |
| **LLM遵循度** | LLM可能在生成长文本时偏离具体指令 | 专业深度不足 |
| **数据管线** | 财报原文截断、Wind数据可能不完整 | 分析缺乏数据支撑 |

---

## 3. 编程专家分析

### 3.1 技术问题（按优先级排序）

#### P0 — 审计不检查 `must_answer` 覆盖度（架构缺陷）

**位置**: `workflow.py` 第986-1068行，`_audit_and_fix` 函数

`structural_check`（结构化预检）**完全不检查** `must_answer` 是否被回答。它只检查：
- 章节是否存在（非空）
- 最小内容长度（200字符）
- 三个必需小节（结论要点/详细情况/证据与出处）
- 证据溯源标记数量
- 占位符检测
- `item_rules` 关键词匹配

**关键缺陷**：`must_answer` 列表虽然被传入 `contract` 参数，但 `structural_check` 从未遍历它来验证每个问题是否被回答。

#### P1 — 语义审计 JSON 解析脆弱

LLM 返回的 JSON 必须精确匹配格式，否则解析失败。解析失败时返回 `passed=False, score=0.0`，导致所有章节都进入修复循环。

#### P2 — 行业视角（lens）未被审计验证

`structural_check` **不验证** 章节是否应用了指定的行业视角。没有关键词检查来验证 lens 特定术语是否出现。

#### P3 — `_audit_and_fix` 只审计 ch1-9，不审计 ch0/ch10

`_CHAPTER_WRITE_ORDER = [1, 2, 3, 4, 5, 6, 7, 8, 9]`，ch0 和 ch10 从未经过审计修复。

#### P4 — `quality_enhancer` 与 `_audit_and_fix` 职责重叠

Step 4.5 的辩论机制会**覆盖** Step 4 修复后的章节内容，可能引入退化。

#### P5 — 降级处理静默吞错

几乎所有步骤都用 `try/except` 包裹，失败时只记录 warning 并继续。`success=True` 可能掩盖了多个步骤的失败。

### 3.2 代码执行路径

```
run_analysis("01024.HK")
  ├── Step 1: infer_market → "hk"
  ├── Step 1.5: fetch_filing
  ├── Step 1.6: extract_facts → 可能失败或部分成功
  ├── Step 2: _collect_data → DataContext
  ├── Step 3: _write_chapters(ch1-ch9)
  ├── Step 4: _audit_and_fix
  │   ├── structural_check → 检查格式，不检查must_answer
  │   ├── semantic_audit → LLM审计，可能JSON解析失败
  │   └── repair_chapter → 最多3轮修复
  ├── Step 4.5: enhance_report_quality
  │   ├── data_repair → 数据修复
  │   ├── debate → 覆盖ch1-9内容
  │   ├── valuation → 注入ch7
  │   └── depth → 注入ch7
  ├── Step 5a: _generate_decision_chapter → ch10 (未审计)
  ├── Step 5b: _generate_overview_chapter → ch0 (未审计)
  └── Step 6: _store_memory → MCP指令
```

---

## 4. 共识点

| # | 共识 | 说明 |
|---|------|------|
| 1 | **关键词匹配 ≠ 内容质量** | 当前验证机制太弱，无法捕捉"写了关键词但没有真正回答问题"的情况 |
| 2 | **行业视角可能未被有效应用** | `preferred_lens` 被传入 contract，但是否真的影响了 LLM 的写作策略存疑 |
| 3 | **语义审计是关键薄弱点** | 审计环节的质量直接决定最终报告质量，当前实现可能过于宽容 |
| 4 | **需要更好的验证标准** | 不应仅以"通过/未通过"的布尔结果衡量，而应有量化评分和逐项对照检查 |

---

## 5. 分歧点

| # | 分歧 | 投资分析专家 | 编程专家 |
|---|------|-------------|---------|
| 1 | **根因定位** | 认为主要是"理解问题"——LLM 没有真正理解 qual 框架的设计意图 | 认为主要是"技术问题"——验证机制不够精细，给了 LLM 蒙混过关的空间 |
| 2 | **改进优先级** | 应先强化 `must_answer` 的逐条对照机制 | 应先改进 `semantic_audit` 的 prompt 和评分标准 |
| 3 | **责任归属** | LLM 生成阶段就应该产出合格内容，审计只是兜底 | LLM 天然有不确定性，必须靠强验证机制来保证质量 |

---

## 6. 最终结论

**报告未按 qual 框架执行的根本原因是"验证机制不足以约束生成质量"，这既是技术问题也是设计问题。**

具体而言：
1. **生成阶段**：LLM 在写作时可能将 `CHAPTER_CONTRACT` 视为"参考建议"而非"硬性约束"
2. **审计阶段**：`structural_check` 的关键词匹配太粗糙；`semantic_audit` 的 LLM 判断标准不够严格
3. **报告阶段**：`success=True quality=high` 的输出给人以"一切正常"的错觉，掩盖了内容质量的不足

**这不是一个"bug"，而是一个"设计缺陷"**——框架的约束力在 LLM 生成→审计→修复的链条中逐级衰减。

**一句话总结**：问题的本质是"检查清单思维"vs"投资判断思维"的冲突——qual框架的每个must_answer项都对应一个投资决策所需的关键判断，而非一个需要打勾的checkbox。

---

## 7. 改进路线图

### Phase 1：强化验证（1-2天）
- 改造 `structural_check`：从"关键词存在"升级为"问题逐条对照"
- 引入"必须包含的结构元素"检查

### Phase 2：强化审计（2-3天）
- 改进 `semantic_audit` 的 prompt：要求 LLM **逐条对照** `must_answer` 清单
- 提高审计的严格度
- 增加审计结果的详细日志输出

### Phase 3：强化生成（3-5天）
- 在章节写作 prompt 中，将 `must_answer` 清单作为**显式指令**
- 要求 LLM 在生成内容后进行**自我对照检查**
- 将行业视角 `preferred_lens` 作为**强制约束**写入 prompt

### Phase 4：端到端验证（持续）
- 建立回归测试：对快手等典型案例，建立"黄金标准"章节
- 输出详细的质量报告

---

## 8. 相关文件

| 文件 | 说明 |
|------|------|
| qual-analysis模板 | `~/.hermes/skills/finance/qual-analysis/qual-analysis-template.md` |
| workflow.py | `~/.hermes/tools/finance/workflow.py` 第49行开始 |
| 审计修复函数 | `~/.hermes/tools/finance/workflow.py` 第928行开始 |
| 会话记录 | `session_id=20260701_011916_e6116b` |