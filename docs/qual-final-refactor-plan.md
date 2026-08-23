# Qual v8 最终重构方案（待架构专家补充后定稿）

**日期**：2026-08-22  
**输入**：6 模块 dayu 全量代码审查 + 重型引擎对比 + 融合风险分析 + 代码专家逐文件规格  
**状态**：代码专家已完成，架构专家进行中

---

## 一、架构设计（四层分治，非融合）

```
┌─────────────────────────────────────────────────┐
│  Layer 4: 终局兜底（程序化）                       │
│  ADVC + PGNB + bind_fuzzy_dates + 组装            │
├─────────────────────────────────────────────────┤
│  Layer 3: 质量保障（确定性检查器）                  │
│  numeric_guard + structural_check + cross_chapter │
├─────────────────────────────────────────────────┤
│  Layer 2: 章节生成（LLM 驱动，只读 Layer 1 数据）  │
│  Gate3: LLM 写章节，数字必须来自 DataAnchor 占位符  │
├─────────────────────────────────────────────────┤
│  Layer 1: 数据获取（程序化控制）                    │
│  Wind MCP + 财报解析 + DataAnchor + 事实提取       │
│  LLM 不参与数据获取                                │
└─────────────────────────────────────────────────┘
```

**核心约束**：Layer 2 的 LLM **只能读取** Layer 1 的数据（通过占位符），**不能自己生成数字**。数字 100% 来自锚点。

---

## 二、Gate 设计（精简版）

| Gate | 层 | 职责 | 行为 |
|------|---|------|------|
| **Gate0** | L1 | 数据源验证 | Wind 覆盖率 + 财报存在性（程序化） |
| **Gate1** | L1 | 类型推断 + 事实提取 | 市场类型 + 结构化事实表（程序化） |
| **Gate2** | L1 | 数据收集 + 参数提取 | Wind 数据 + DCF 参数 + DataAnchor 构建（程序化） |
| **Gate3** | L2 | 逐章写作 | LLM 生成 11 章，数字用 [{{指标}}] 占位符，程序回填 |
| **Gate4** | L3+4 | 确定性检查 + 程序化修复 | 3 个检查器 + ADVC/PGNB/日期绑定（**无 LLM 修复**） |
| **Gate5** | L1 | 估值计算 | DCF/可比/PS 全程序化（无 LLM） |
| **Gate6** | L2 | 综合结论 + 决策章 | LLM 生成结论章 |
| **Gate7** | L2 | 概览章 | LLM 生成概览 |
| **Gate8** | L3+4 | 终局验证 + 组装 | 最终校验 + 报告组装 + 质量标注 |

**关键变化**：
- Gate4 **删除 LLM patch 修复**（死循环根源）→ 改为纯确定性检查 + 程序化修复
- Gate4 **检查器 16→3**（numeric_guard + structural_check + cross_chapter_consistency）
- Gate8 **删除红队 LLM 审查**（质量不可控）→ 改为确定性终局 sweep

---

## 三、代码专家逐文件规格摘要

### 新建文件（5 个，~620 行）

| 文件 | 行数 | 功能 |
|------|------|------|
| `qual_v8/contracts/__init__.py` | 30 | lazy import 导出 |
| `qual_v8/contracts/types.py` | 200 | frozen dataclass（GateResult/GateContext/DataPoint 等） |
| `qual_v8/contracts/protocols.py` | 80 | Protocol（GateProtocol/CheckerProtocol/RepairerProtocol） |
| `qual_v8/engine.py` | 150 | GateRunner（Gate 执行循环，从 workflow.py 拆出） |
| `qual_v8/report_builder.py` | 100 | 报告组装 + 质量标注 |
| `qual_v8/retry_policy.py` | 60 | 重试策略常量 + 墙钟守卫 |

### 大幅精简的文件（6 个核心）

| 文件 | 当前 → 目标 | 关键变化 |
|------|------------|---------|
| `workflow.py` | 495 → 180 | 拆出 engine/report_builder/retry_policy，只留门面 |
| `gate4.py` | 387 → 120 | **删除 LLM patch 修复**，改为纯确定性检查+修复 |
| `gate8.py` | 558 → 150 | 删除重复检查/红队审查，调用统一检查器 |
| `review_repair_loop.py` | 841 → 200 | **单轮确定性修复**（删除 max_rounds/LLM 修复/辩论） |
| `cross_chapter_consistency.py` | 505 → 200 | **只保留数据冲突**（删除结论/时间冲突检查） |
| `workflow_context.py` | 420 → 150 | 精简为 build_gate_context 函数 |

### 删除的文件（15+ 个，~3,300 行）

| 文件 | 行数 | 删除理由 |
|------|------|---------|
| `fact_checker.py` | 435 | 已被 DataAnchor 替代 |
| `conclusion_validator.py` | 451 | LLM 审查解析太粗糙 |
| `depth_reviewer.py` | ~300 | LLM 审查质量不可控 |
| `assumption_checker.py` | ~300 | LLM 审查 |
| `date_anchor_check.py` | 388 | 已被 bind_fuzzy_dates 替代 |
| `logic_consistency_check.py` | 383 | 与 cross_chapter 重复 |
| `data_reasonableness_check.py` | 381 | 与 DataAnchor 重复 |
| `debate_service.py` | ~200 | LLM 质量不可控 |
| `solutions.py` | ~100 | 修复逻辑已由 anchor_repair 覆盖 |
| `security/auth.py` | ~160 | dead code |
| `_legacy/*.py` | ~300 | 旧版代码 |

### 保留但精简的文件（~55 个）

详见代码专家完整规格（`docs/qual-v8-refactor-spec.md`）。

---

## 四、行数预算

| 模块 | 当前 | 目标 | 变化 |
|------|------|------|------|
| qual_v8/（含 contracts） | ~6,700 | ~4,575 | -32% |
| quality/（含删除） | ~20,000 | ~10,500 | -48% |
| workflow.py（主入口） | 3,446 | 0（拆分） | -100% |
| **核心模块合计** | ~30,146 | ~15,075 | **-50%** |

---

## 五、实施路线图

| Phase | 内容 | 工期 | 交付物 |
|-------|------|------|--------|
| **Phase 0** | contracts 层（3 新文件） | 1 天 | frozen dataclass + Protocol |
| **Phase 1** | workflow.py 拆分（4 新文件） | 1 天 | engine + report_builder + retry_policy |
| **Phase 2** | 检查器精简（16→3） | 2 天 | 删除 13 个检查器 + 精简 3 个 |
| **Phase 3** | Gate4/8 重构 | 2 天 | 删除 LLM patch + 单轮修复 |
| **Phase 4** | Gate0-3/5-7 精简 | 2 天 | context dict → GateContext |
| **Phase 5** | 测试 + pyright | 2 天 | 覆盖率 ≥80% + 零类型错误 |
| **总计** | | **10 天** | |

---

## 六、验收标准

| 维度 | 标准 |
|------|------|
| **类型安全** | `pyright --strict` 零错误 |
| **Any 消除** | `grep -r "typing.Any"` 返回空（contracts 层） |
| **workflow.py** | ≤250 行 |
| **检查器** | 3 个（numeric_guard + structural_check + cross_chapter） |
| **审查循环** | 单轮确定性修复（无 max_rounds） |
| **全流程** | 小鹏 9868.HK ≤20 分钟产出完整报告 |
| **Gate4 通过率** | ≥70%（当前 0%） |
| **向后兼容** | `from qual_v8 import QualWorkflow` 仍可用 |
