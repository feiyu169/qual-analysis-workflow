# HeavySkill K8 审查结论：Qual v9 技术方案

**审查日期**：2026-08-23  
**审查方式**：HeavySkill 模式 2，K=8（4 轨迹成功）+ 综合审议  
**截断状态**：0 截断  
**总体结论**：**有条件通过（作为灰度版本），对标 dayu 不通过**

---

## 核心判断

> v9 是"局部修复/过渡版本"，不是架构级重构。  
> 如果目标是"v9 先解决小鹏样本并继续推进"：有条件通过。  
> 如果目标是"达到 dayu-agent 使用效果"：不通过。

---

## 分维度审查结论

| 维度 | 结论 | 理由 |
|------|------|------|
| **1. 数据控制范式** | **不通过，除非补结构化事实上下文** | PGNB 财年感知扩展仍是 regex 事后拦截，无法从源头保证数值与财年/来源绑定。需引入 `FinancialFact(company, metric, value, fiscal_year, period, source)` 结构；无财年标注不得默认"最新财年" |
| **2. Gate 依赖图** | **有条件通过** | DAG 降级方向正确，但必须区分 HARD/SOFT 依赖，定义最终发布门禁 |
| **3. 质量保障** | **有条件通过，不达 dayu 闭环** | 分类统计不是闭环。需实现 audit→confirm→repair→verify 状态机 |
| **4. 效率** | **通过** | 15 分钟可接受 |
| **5. 可维护性** | **有条件通过** | frozen dataclass 不够，需 Protocol；正则要命名化、测试化 |
| **6. 遗漏风险** | **不通过，除非补测试与根因分析** | 缺回归测试集、审计日志、误报/漏报评估 |

---

## 6 项整改要求

### P0：必须完成才能作为灰度版本

1. **P1 财年感知**：引入结构化财年上下文，不能只靠 regex
2. **P2 Gate 依赖**：定义 HARD/SOFT 依赖 + 最终发布门禁
3. **P3 误报过滤**：规则可回滚、可审计，给出量化效果
4. **P4 公司名**：后缀剥离使用官方枚举，仅用于证券简称维度
5. **P5 NoneType**：记录 MISSING_FIELD / PARSE_ERROR / UNSUPPORTED_FORMAT 根因
6. **回归测试**：Gate 0-3 回归 + 小鹏 + 多个港股后缀类型样本

### P1：对标 dayu 需要的后续版本

- 数值仓储协议/事实绑定层（类似 dayu fins/storage）
- contracts/Protocol 强类型（类似 dayu contracts/）
- audit/confirm/repair 闭环（类似 dayu write_pipeline）
- HARD/SOFT Gate 依赖策略
- 可追溯数据血缘

---

## 4 轨迹收敛结论

| 收敛点 | 内容 |
|--------|------|
| v9 定位 | 局部修复/过渡版本，不是架构级重构 |
| PGNB 范式 | regex 事后拦截 ≠ dayu 的"宿主强约束" |
| DAG 降级 | 方向正确，但缺少硬/软依赖和发布门禁 |
| 检查器 | 3 检查器 + 确定性修复缺少 audit/confirm/repair 闭环 |
| 效率 | 15 分钟可接受 |
| contracts | frozen dataclass 不够，需要 Protocol |
| 测试 | 缺回归测试、审计日志、误报/漏报评估 |
