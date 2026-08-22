# qual 双专家全面检查 + HeavySkill 评审综合报告（2026-08-22）

> 评审链路：代码专家全面检查（独立子代理）→ 投资专家全面检查（独立子代理）→
> HeavySkill K=8 多轨迹评审 + 审议（交叉验证双专家结论并纠错）
> 评审维度：简洁性 / 有效性 / 数据一致性 + 多轮真实 E2E 测试问题根治评估
> 评分汇总：**代码专家 6.5/10 → 投资专家 6.0/10 → HeavySkill 综合 5.5/10**

---

## 一、三方评分与共识

| 评审方 | 评分 | 核心判断 |
|--------|------|---------|
| 代码专家 | **6.5/10** | ADVC+FiscalSemantics+fail-closed 三件套真正解决历史问题，无 P0 致命漏洞；架构负债（3282 行单体/四层结构）显著 |
| 投资专家 | **6.0/10** | 数据真实性链接近生产级；估值链有 4 个 P0 方法论硬伤（毛利率/净负债/β/可比） |
| HeavySkill 审议 | **5.5/10** | 双专家评分略偏乐观（"代码无 P0"不成立）；review_incomplete 应升级 P0；死循环应为"部分根治" |

**三方共识**：
1. 数据真实性防线（Wind 唯一源 + ADVC + 财年归因）是强项，工程质量高
2. 估值链口径/硬编码是投资结论可信度的最大威胁（P0）
3. review_incomplete 静默通过破坏核心 fail-closed 纪律（应升级 P0）
4. T9-T14 硬编码覆写 facts 绕过 DataAnchor 单源（应删）
5. 架构收敛（三路径→单一 v8 + 拆 3282 行 + 清死代码）是主要技术债

---

## 二、简洁性发现（三方合并）

| 级别 | 问题 | 证据 | 建议 |
|------|------|------|------|
| P1 | 三条执行路径并存（v8 编排 / legacy 生成服务 / run_analysis 旧路径） | run_qual_full.py:111 默认 v8；gate3.py:167-207 调用 legacy 函数 | 收敛到单一 v8 状态机；run_analysis 冻结标注 deprecated |
| P1 | workflow.py 3282 行单体混合 6 类职责 + 2 个死 HAS_* 导入 | workflow.py:128-139 HAS_CIRCUIT_BREAKER/HAS_STAGE_MANAGER 无引用 | 拆分生成服务层；删死导入 |
| P2 | quality/ 69 平铺 + 27 shim + 6 _legacy 四层结构 | 子代理接线普查 | 价值复核后归档；统一归档纪律口径 |
| P2 | v3/__init__.py 空包 + shim 反向依赖环 | workflow_integration.py:60-76 自加载 17 个 shim | 补聚合导出或标记 deprecated |
| P2 | 顶层 re-export 15/24 符号仅测试消费 | quality/__init__.py:15-50 | 死代码标注或移除 |

---

## 三、有效性发现（三方合并）

| 级别 | 问题 | 证据 | 建议 |
|------|------|------|------|
| **P0** | 毛利率=营业利润率 | wind_field_disposition.py:26-35 | 接 Wind 真实毛利率或改"营业利润率"剔除毛利率分析章 |
| **P0** | 净负债=总负债+×0.3 启发式 | workflow.py:2253-2265 | 从财报提取有息负债+现金；不可得则弃用 EV→Equity 桥并显式标注 |
| **P0** | β=1.2 等 WACC 参数硬编码 | workflow.py:2235-2239 | β 从 Wind/可比 bottom-up 取，无源走显式降级+敏感性 |
| **P0** | 可比公司写死含迪士尼 | valuation_engine.py:100-112 | 实时拉取可比；无源标注"静态快照" |
| **P0** | review_incomplete 静默通过（HeavySkill 升级） | review_repair_loop.py:213-221 + gate4.py:296 | passed 分支加 not review_incomplete；Gate4 显式读取 |
| **P0** | T9-T14 硬编码阅文值覆写 facts | workflow.py:2883-2948 | 删除或从 ctx.wind 取真实值 |
| P1 | 评级一致性检查空转 | gate5.py:143-149 无 dcf_value → gate6 静默跳过 | Gate5 输出补 dcf_value；单测覆盖 |
| P1 | 默认 shadow 只审不修 | qual_v8/workflow.py:253 | DSH 接入默认 enforce |
| P1 | 质量标注 HTML 注释不可见 | workflow.py:447-452 | 改报告头部可见"质量受限声明" |
| P1 | 人工确认默认 True | gate8.py:297 | 默认 False + 标注"未经人工复核" |
| P1 | ADVC 误改子公司数据 | data_anchor.py:249-269 | 排除表加限定词；限定词后 span 降 T3 |
| P1 | 红队 fail-open + 分段截断 | gate8.py:511,427 | 失败 fail-closed；分段加重叠+跨段一致性 |
| P1 | legacy 路径 review loop 无 budget/deadline | workflow.py:3050-3057 | 补传；或冻结 legacy |
| P1 | 风险披露=关键词覆盖 | gate4.py:352-371 | 结构化风险清单+最小内容量 |
| P2 | Gate4 子预算 35 硬编码可误杀 | gate4.py:283 | 配置化（按章节比例/每轮上限） |
| P2 | triage 正则漏判/误判 | review_repair_loop.py:624-630 | 改"sweep 覆盖判定" |
| P2 | Gate8 sweep 修复后不重跑跨章 | gate8.py:56-65 | fixed_count>0 补跑跨章检查 |
| P2 | 牛/熊=±20% 机械乘子 | valuation_engine.py:404-414 | 用敏感性矩阵分位数 |

---

## 四、数据一致性发现（三方合并）

| 级别 | 问题 | 证据 | 建议 |
|------|------|------|------|
| P1 | fact_extractor 财务填充不感知 fiscal_year（R1） | fact_extractor.py:778-786,948-964：series[-1] vs facts.fiscal_year 脱钩 | Step5 按 facts.fiscal_year 取对应财年值；修表头渲染 |
| P1 | pct/运营字段（DAU/GMV/ARPU）完全无锚点 | data_anchor.py:288-301 | 建锚点或报告显式标注"运营数据未经锚点校验" |
| P2 | "Wind 验 Wind"退化（偏差恒 0） | gate1.py:275-303 | 改为对 LLM 提取的运营字段抽样校验 |
| P2 | 财年校验异常被吞（fail-open） | data_anchor.py:468-469 | 异常显式记 warning |
| P2 | 财年语义三处口径不一致未文档化 | Gate3 严格/Gate4 宽松/check_fiscal 章节级 | 写 docs 固化分层口径 |
| P2 | 汇率 0.92 硬编码 | base_valuation.py:107 | 实时汇率+币种统一 |
| P2 | SOTP 未接入主流程（声称缺环） | sotp_valuation.py 无调用点 | 接入或从方案文档移除 |

---

## 五、多轮测试问题根治评估（HeavySkill 审议修正）

| # | 历史问题 | 代码专家 | 投资专家 | HeavySkill 综合 |
|---|---------|---------|---------|----------------|
| 1 | 死循环卡死（Gate4 卡 6h） | ✅ 根治 | ✅ 根治 | ⚠️ **部分根治**（legacy 路径无 budget/deadline） |
| 2 | 数值错位（1031.63→31.63） | ✅ 根治 | ✅ 根治 | ✅ 根治（残留：非锚定指标/口径误修） |
| 3 | 841.63 财年误报 | ✅ 根治 | ✅ 根治 | ✅ 根治 |
| 4 | 测试体系断裂（27 collection 错误） | ⚠️ 部分（32 SKIP） | — | ⚠️ **部分根治**（32 SKIP 未迁移） |
| 5 | ModuleLoader 启动报错 | ✅ 根治 | — | ✅ 根治 |
| 6 | 外部数据抖动 | ✅ 机制存在 | ✅ 根治 | ✅ 根治 |
| 7 | 测试污染 | ✅ 根治 | — | ✅ 根治 |

**残留风险最关键 3 项**：① legacy 路径未纳入预算/墙钟保护；② ADVC 自证闭环对子公司/非锚定口径误修；③ 事实源被 T9-T14 硬编码绕过。

---

## 六、最终修复清单（HeavySkill 合并去重，按影响排序）

### P0 必须修（7 项）
1. **估值链口径/硬编码系列**（毛利率/净负债/β/可比）——投资结论可信度地基
2. **review_incomplete 静默通过**——恢复 Gate4 fail-closed
3. **T9-T14 硬编码覆写 facts**——恢复 DataAnchor 单源

### P1 应当快速修（6 项）
4. ADVC 自证闭环误改子公司/非锚定口径
5. fact_extractor 财务填充不感知 fiscal_year
6. 评级一致性检查空转
7. legacy 路径 review loop 无 budget/deadline
8. pct/运营字段无锚点
9. 流程防护弱化（默认 shadow / 人工确认 True / 标注不可见 / 红队 fail-open）

### P2 可选优化（6 项）
10. 架构收敛（三路径→v8 + 拆 3282 行 + 清死代码）
11. 测试迁移与口径澄清（32 SKIP；654 vs 438）
12. "Wind 验 Wind"退化修复
13. 财年校验异常被吞
14. 汇率 0.92 配置化
15. SOTP 接入

---

## 七、评审产物

| 文档 | 说明 |
|------|------|
| docs/qual-expert-review-code-2026-08-22.md | 代码专家完整报告（6.5/10） |
| docs/qual-expert-review-investment-2026-08-22.md | 投资专家完整报告（6.0/10） |
| heavyskill-qual-review.json | HeavySkill K=8 原始轨迹 + 审议（5.5/10） |
| 本报告 | 三方综合 + 最终修复清单 |

**一句话结论**：qual 的"数据真实性"防线（Wind 唯一源 + ADVC + 财年归因）已是生产级水准，但"投资结论"防线（估值参数、评级映射、过程诚信）仍有 4 个 P0 硬伤 + 1 个 P1 审查完整性漏洞；当前输出定位应为"数据可信、结论需人工复核"的研究草稿，修复 P0 七项后可升级为可落仓的买方报告。
