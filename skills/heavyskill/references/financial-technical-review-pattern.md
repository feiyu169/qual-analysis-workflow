# Financial Technical Document Review with HeavySkill

## Context
Used when reviewing technical proposals for financial analysis workflows — PoW integration, DCF validation, data pipeline architecture, etc.

## Query Preparation Pattern

**CRITICAL**: HeavySkill subagents CANNOT read local files. Inline ALL relevant content.

### Template
```
## 审查任务
审查以下[方案类型]技术文档，从[维度1]、[维度2]、[维度3]评估。

## 用户背景
- [角色/行业]
- [现有工作流]
- [核心准则]
- [现有痛点列表]

## 被审查的方案
[方案全文或关键段落，含代码片段、架构图、阈值定义]

## 审查维度
### 1. [维度1]
- [具体关注点]
- [评估标准]

### 2. [维度2]
...

## 特别关注点
1. [关键问题1]
2. [关键问题2]
```

## Recommended Review Dimensions for Financial Proposals

| Dimension | Focus | What to Check |
|-----------|-------|---------------|
| **有效性提升** | 是否真正解决痛点 | 痛点命中率、效率提升幅度、"为X而X"嫌疑 |
| **架构简洁性** | 是否过度设计 | 层数是否冗余、职责边界是否清晰、概念是否必要 |
| **代码质量** | 实现是否健壮 | 阈值合理性、异常处理、维护成本 |
| **可行性** | 技术可实现性 | 隐藏的坑、依赖稳定性、降级策略 |

## Consensus Extraction Pattern

After K=8 parallel reasoning, look for:
1. **High convergence** (7-8 trajectories agree) → Strong signal, likely correct
2. **Split opinions** (4-4 or 5-3) → Needs deeper analysis, may need more K or manual review
3. **Unique insights** (1 trajectory has novel point) → Worth investigating, may be breakthrough or outlier

## Example: PoW Integration Review (2026-07-03)

**Query**: PoW与投资分析工作流整合方案，从有效性提升、架构简洁性、代码质量评估

**Key Findings**:
- 有效性：P15（年份标签）直接解决90%+，P18（自评虚报）基本无效0%
- 架构：三层设计存在冗余，建议合并为两层
- 代码：WACC 8%-15%阈值过窄，FCF/OCF 50%-150%不合理

**Consensus**: 方向正确但存在概念包装、阈值失当与职责模糊

**Actionable Output**:
1. 将WACC/FCF阈值改为Warning而非阻断
2. 三层合并为两层（结构完整性Gate + 计算卫生Gate）
3. 将"PoW"改名为"Gate Checks"
4. 实现异常分级（FATAL/ERROR/WARN）
