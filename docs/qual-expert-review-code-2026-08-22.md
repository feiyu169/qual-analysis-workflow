# qual 代码与架构审查报告（代码专家）

> 生成：2026-08-22 双专家全面检查；送 heavyskill 评审用
> 审查对象：tools/finance（workflow.py 3282 行 + qual_v8 32 文件 + quality 69 平铺 / 27 shim / 6 归档 + normalize_values.py 222 行 + fact_extractor.py 1026 行 + 入口 run_qual_full / run_qual_v8 / run_xpev_full）
> 方法：纯只读，实读全部关键文件、实测 pytest（收集+执行）、全工作区 grep 引用扫描（接线普查 + fact_extractor 深读双独立核查）

## 一、总体评价

ADVC 三层数值修复、FiscalSemantics 财年归因、审查循环 fail-closed 纪律是三个**真正解决历史问题的架构决策**，每个都配有黄金回归测试，测试工程质量明显高于同类流水线项目。但历史包袱与"声称-现实"漂移显著：3282 行单体、69 平铺 + 27 shim + 6 归档四层并存；**简报中三个关键数字（654 测试、58 未接线模块、34 个 v3 引用）全部无法在当前代码树复现**（实测 438 = 406 passed + 32 skipped，0 fail）。无 P0 级致命漏洞，但存在 1 个 P1 级审查完整性漏洞（review_incomplete 静默通过）。

**架构健康度：6.5/10**

## 二、简洁性发现

- **A1 P1 双引擎真实结构**：run_qual_full.py:111 默认走 v8（QUAL_MODE="v8"≠legacy），v8 的 Gate3/4/5/6 实际调用 legacy workflow.py 函数（gate3.py:167-207 等）——不是两个平行引擎，而是"legacy=生成服务层、v8=编排层"。run_analysis 是第三条旧编排路径
- **A2 P1 死导入**：workflow.py:128-139 HAS_CIRCUIT_BREAKER/HAS_STAGE_MANAGER 无任何引用（HGF 纪律警告过的"HAS_* 只证明能导入"反例）
- **A3 P1 硬编码演示块**：workflow.py:2883-2948 T9 覆写真实 facts（硬编码 80.07/5.0）、T12 硬编码 base_revenue/net_debt、T14 硬编码 roic/wacc——非阅文公司会"计算错值但只打日志"
- **A4 P2 过时快照**："58 未接线"实为当前 69 平铺 = A59 已接线 + B3 仅测试引用（dcf/sotp/peer_comparison）+ C7 死代码（catalyst_calendar/falsification/margin_of_safety/risk_quantification/sensitivity 仅被 feature_flags 枚举字符串吊命 + gate_auto_check/gate_evaluator 假可选）+ D6 归档
- **A5 P2 v3 shim 反向依赖环**：quality/v3/__init__.py 空包；workflow_integration.py:60-76 从平铺延迟加载 17 个 v3 shim——"自己依赖自己的别名"运行时环
- **A6 P2 顶层 re-export 15/24 仅测试消费**：CausalInferenceChain/StandardScoringEngine/Formulas 等无生产调用点

## 三、有效性发现

- **B1 P2 ADVC 根治验证**：三层 + 三处接线 + 黄金回归证据充分；自证闭环漏洞：① 只覆盖 10 个锚定指标，非锚定（研发/销售费用）幻觉不可见；② prefix_drop 对"值恰为锚点数字串后缀但属另一口径"有误修残余
- **B2 P1 review_incomplete 静默通过（本次最严重）**：review_repair_loop.py:213-221 无新问题通过分支不检查 review_incomplete；Gate4 只取 result.passed → Gate8 红队照常触发——审查少检几项却照样绿灯
- **B3 P2 预算误杀**：Gate4 子预算 35 次（gate4.py:283），3 轮全量审查可合法超限 → fail-closed 误杀合法流程
- **B4 P2 triage 正则漏判/误判**：_is_value_issue（review_repair_loop.py:624-630）要求"指标名+`=`数字"——漏判安全但多一轮，误判导致假失败
- **B5 P2 Gate8 sweep 修复后不重跑跨章检查**：fixed_count>0 只重组 report（gate8.py:56-65）

## 四、数据一致性发现

- **C1 DataAnchor 单源一致使用**：set_anchor 唯一生产调用是 init_from_wind_data，11+ 消费点全部走 get_data_anchor 缓存单例；唯一"绕过"是 A3 T9 硬编码块
- **C2 fact_extractor 同源但 7 项残留风险**：R1（高）财务填充不感知 fiscal_year（series[-1] 取最新财年 vs facts.fiscal_year 可能来自 filing）→ format_facts_as_context 表头错位；R3（中）"Wind 验 Wind"退化（偏差恒 0，Gate1 _check_value_deviation 比对已被 Wind 覆盖后的值）；R4（中）pct 指标无锚点；R5（中）运营字段（DAU/GMV/ARPU）完全无锚点
- **C3 跨章检查与 ADVC 职责边界清晰**：单章数值 vs 锚点 / 同指标同财年跨章比较，互补无覆盖
- **C4 财年语义三处口径不一致（分层但未文档化）**：Gate3 生成时严格重试 / Gate4 审查时宽松归因 / check_fiscal 章节级 {5,7} 从严

## 五、多轮测试问题根治评估

| # | 历史问题 | 评估 | 残留风险 |
|---|---------|------|---------|
| 1 | 死循环卡死 | ✅ 根治 | legacy 路径（QUAL_MODE=legacy）Step 4.7 不传 budget/deadline；review_incomplete 静默通过 |
| 2 | 数值错位 | ✅ 根治 | 非锚定指标幻觉不可见；prefix_drop 口径误修残余 |
| 3 | 841.63 误报 | ✅ 根治 | 低 |
| 4 | 测试断裂 | ⚠️ 部分 | 32 个 SKIP（hermes 契约未迁移）；"654 全绿"无法复现（实测 438） |
| 5 | ModuleLoader | ✅ 根治 | gate_auto_check/gate_evaluator 假可选 |
| 6 | 外部抖动 | ✅ 机制存在 | 未做网络 L3 实测 |
| 7 | 测试污染 | ✅ 根治 | test_golden_set 仍有 return bool（已补 assert 未删 return） |

## 六、优先级修复清单

| 级别 | # | 问题 | 位置 |
|------|---|------|------|
| P1 | 1 | review_incomplete 时仍 passed=True | review_repair_loop.py:213-221, gate4.py:296 |
| P1 | 2 | T9-T14 硬编码阅文值覆写 facts | workflow.py:2883-2948 |
| P1 | 3 | legacy 路径 review loop 无 budget/deadline | workflow.py:3050-3057 |
| P1 | 4 | 3282 行单体 + 死导入 | workflow.py |
| P2 | 5 | fact_extractor 财务填充不感知 fiscal_year | fact_extractor.py:778-786,948-964 |
| P2 | 6 | Wind 验 Wind 退化 | gate1.py:275-303 |
| P2 | 7 | Gate8 sweep 修复后不重跑跨章 | gate8.py:56-65 |
| P2 | 8 | C 类 7 个死代码 + 归档口径不一致 | quality/ |
| P2 | 9 | 32 个 SKIP 测试 | test_config_validator 等 |
| P2 | 10 | 654 声称与 438 实测不符 | docs |
| P2 | 11 | Gate4 子预算 35 硬编码 | gate4.py:283 |
| P2 | 12 | triage 正则漏判/误判 | review_repair_loop.py:624-630 |
| P2 | 13 | 财年语义三处口径未文档化 | 三处检查器 |
| P2 | 14 | return bool 残留/v3 空包/降级标记位置 | 多处 |

**审查结论**：ADVC + FiscalSemantics + fail-closed 三件套证明这套流水线"知道该怎么修"，当前无致命正确性漏洞、测试实测全绿；下一步架构价值在于**收敛**——拆 workflow.py、归档死代码、让声称数字与代码树对齐，并堵住 review_incomplete 静默通过这一个 P1 级审查完整性缺口。
