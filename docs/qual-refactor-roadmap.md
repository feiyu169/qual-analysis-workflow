# Qual 架构重构路线图（基于三方专家审查 + dayu-agent 代码对比）

**日期**：2026-08-22  
**前提**：三方专家一致认为 Qual 的"检查器拦截修正"范式根本性地劣于 dayu 的"宿主强约束"范式

---

## 一、核心问题诊断（一句话）

> **Qual 用 57,000 行代码 + 16 个检查器 + LLM 重试循环来对抗 LLM 的不确定性，但代码本身的复杂度超过了 LLM 的不确定性——系统在对抗自己的复杂度。**

## 二、从 dayu 借鉴的核心理念

| dayu 理念 | qual 现状 | 重构方向 |
|-----------|-----------|---------|
| **contracts 层**（frozen dataclass，零 dict 传递） | Gate 间用 `dict[str, Any]` 传递 | 引入 `qual/contracts/` 强类型层 |
| **四层边界**（UI→Service→Host→Agent） | workflow.py 3,446 行 God File | 拆分为 orchestrator / generator / collector / assembler |
| **"不负责"清单**（每层精确边界） | Gate 职责漂移（Gate8 承载 7 个子检查） | 每个 Gate 只做一件事 |
| **宿主强约束**（数据访问被仓储协议接管） | LLM 写数字 → 检查器拦截 → 重写 | LLM 只能通过 DataAnchor 读数据，不能写 |
| **AGENTS.md 编码约束** | 无编码规范 | 引入 pyright + 禁止 Any/God object |
| **audit/confirm/repair 三步闭环** | 16 个检查器全量重查 | 精简为 3 个检查器 + 独立审计模型 |

## 三、分阶段重构路径

### Phase 0（1 周）：数据契约层 — 根治 Gate 间数据流混乱

**目标**：用 frozen dataclass 替代 `dict[str, Any]` 上下文传递

```python
# qual/contracts/data_context.py
@dataclass(frozen=True)
class DataContextContract:
    ticker: str
    company_name: str
    market: str
    fiscal_year: int
    wind_data: WindDataContract
    filing_data: FilingDataContract | None
    facts: FactsContract | None
    chapters: dict[int, str]
```

**收益**：Gate 间数据流类型安全，运行时错误在编译期发现

### Phase 1（1 周）：审查修复循环重构 — 根治死循环

**目标**：从"LLM 对抗 LLM"转向"确定性检查 + 精准修复"

```
当前：LLM 生成 → 16 个检查器 → 全部失败 → LLM 重写 → 又失败 → 死循环
目标：LLM 生成 → 3 个确定性检查器 → 程序化修复（不依赖 LLM）→ 通过
```

**保留的 3 个检查器**（从 16 个精简）：
1. **DataAnchor 数字校验**（PGNB + bind_bare_numbers + bind_fuzzy_dates）— 程序化，零 LLM
2. **结构检查**（structural_check）— 确定性 regex
3. **跨章一致性**（精简版：只检查同指标同财年数值冲突，不检查结论/时间）

**删除的 13 个检查器**：
- fact_checker → 已被 DataAnchor 替代
- conclusion_validator → LLM 审查响应解析太粗糙（"问题"关键词触发）
- depth_reviewer → LLM 审查，质量不可控
- assumption_checker → LLM 审查
- date_anchor_check → 已被 bind_fuzzy_dates 替代
- logic_consistency_check → 与 cross_chapter 重复
- data_reasonableness_check → 与 DataAnchor 重复
- 其他 6 个辅助检查器

### Phase 2（2-3 周）：Gate3 并行章节生成 — 运行时间减半

**目标**：11 章并行生成（当前串行 → 40 分钟，并行 → 15-20 分钟）

```
当前：ch1 → ch2 → ... → ch11（串行，每章 2-4 分钟）
目标：[ch1, ch2, ch3] | [ch4, ch5, ch6] | [ch7, ch8, ch9, ch10, ch11]（3 批并行）
```

**约束**：同批次章节无依赖（ch4 依赖 ch1-3 的摘要，但可以异步获取）

### Phase 3（3-4 周）：workflow.py 拆分

**目标**：3,446 行 → 5 个模块

```
workflow.py (3,446行)
├── orchestrator.py    (~300行) — 编排入口，只做 Step 调度
├── generator.py       (~600行) — 章节生成 + PGNB
├── collector.py       (~400行) — Wind/SEC 数据收集
├── assembler.py       (~200行) — 报告组装 + 质量标注
└── adapters.py        (~200行) — v8 Gate 引擎适配
```

### Phase 4（4-6 周）：检查器收敛 + 独立审计模型

**目标**：16 → 3 个确定性检查器 + 1 个独立审计模型

**独立审计模型**（借鉴 dayu 的 audit/confirm/repair）：
- 用不同模型（或不同 prompt）审查生成的报告
- 只输出结构化 JSON（问题类型 + 严重性 + 位置 + 建议）
- 不做"修复"——修复由程序化层完成

---

## 四、预期收益

| 指标 | 当前 | Phase 0-1 后 | Phase 2-4 后 |
|------|------|-------------|-------------|
| **报告耗时** | 40-60 分钟（失败） | 20-30 分钟 | 10-15 分钟 |
| **Gate4 通过率** | ~0%（7 轮全失败） | ~70% | ~95% |
| **LLM 调用次数** | 50-120 次 | 20-40 次 | 11-15 次 |
| **代码量** | 57,000 行 | ~45,000 行 | ~30,000 行 |
| **检查器数量** | 16 个 | 3 个 | 3 + 1 审计模型 |

---

## 五、立即可做（本周）

1. **Phase 0：DataContextContract** — 把 Gate 间传递的 dict 替换为 frozen dataclass
2. **Phase 1：精简检查器** — 删除 fact_checker / conclusion_validator / depth_reviewer / assumption_checker / date_anchor_check / logic_consistency / data_reasonableness（已被 DataAnchor + PGNB 覆盖）
3. **Phase 1：审查循环改为单轮** — 删除 max_rounds=3 的重试循环，改为"单次生成 + 程序化后处理 + 单次审计"
