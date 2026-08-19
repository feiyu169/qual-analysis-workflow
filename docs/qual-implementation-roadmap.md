# Qual 流水线统一实施路线图（v2.1）

日期：2026-08-19
来源：`docs/qual-loop-fix-design-v3.md`（v3.1 死循环修复）+ `docs/securities-expert-review.md`（证券专家数据真实性）+ `docs/qual-review-loop-efficiency.md`（审查环节优化）+ `docs/qual-stage-c-adjudication.md`（阶段 C 综合审议）
目标：**先让流水线"跑得完、不卡死"，再让报告"数据可信、可决策使用"，最后让审查"高效不重复"**

---

## 一、总览：三阶段路线

```
阶段 A：死循环修复（v3.1 技术方案）——"跑得完"
  A1-A4 四个合并提交 → 小鹏 9868.HK 运行验收（≤60 分钟有界终止）
阶段 B：数据真实性改进（证券专家 Top 10）——"可信、可决策"
  B1-B5 工作包 → 重跑验证（财年错位 0 / 目标价程序化 / 事实表可复核）
阶段 C：审查环节优化（审查专家评审）——"高效不重复"
  C1-C4 工作包 → 审查成本降 60-70%、去重、增量审查
```

**依赖**：阶段 A 是阶段 B 的前提（校验阻断、deadline、fail-closed 是数据真实性的机制基础）；
阶段 B 中 B1（当期财年校验）依赖 A 的 Gate8 接线，B2（财务 100% Wind）依赖 A 的 canonical/仲裁。

---

## 二、阶段 A：死循环修复（v3.1，详见 qual-loop-fix-design-v3.md）

### A1 提交 #1：P0-A 三项 + gate4 fail-open + 签名修订
- 缺陷16 签名保留章节号（三段式正则）
- 缺陷1 豁免 PASS 累积清单判据
- 缺陷6 单调守卫先减后置零
- P0-7 gate4.py:226-228 双 fail-open 修复
- 全部新签名（review_and_repair_loop / _run_substantive_review / _issue_signature）

### A2 提交 #2：deadline + 熔断 + with_fallback（原子化）
- P0-3 with_fallback 白名单前置（except 顺序）
- P0-4 逃生直连 deadline 预检
- P0-6 harness deadline 参数（三册统一"加"）
- P0-1 熔断阈值修正（workflow.py:181 → 2）+ RETRY_POLICY enforce=3
- P0-2 llm_fallback 模块落地（或内联改造）
- P0-5 预算 200 + S5 计入（三册统一）

### A3 提交 #3：P1 + 验收口径
- P1-8 不等式方向修正、P1-9 测试计数 20
- 20 个测试全绿验证

### A4 提交 #4：清理 + 运行验收
- 文档同步（arch/code/导读三册一致）
- 小鹏 9868.HK shadow 运行验收：有界终止 ≤60 分钟、无死循环、日志时间戳审计

**A 阶段验收**：Terminal = 20 测试绿 + 小鹏运行有界终止；Gate4 不再 6h 卡死。

---

## 三、阶段 B：数据真实性改进（证券专家 Top 10，详见 securities-expert-review.md）

### B1 工作包：财年语义代码化 + 分级阻断（Top 1/2，综合审议修订版）
| 项 | 内容 | 文件 | 验收 |
|---|---|---|---|
| B1-1 | **Gate8 当期财年语义校验（章节级）**：当期锚断言全章节阻断 + 历史引用上下文豁免（对比/趋势语境+强制 FY 标注）+ 章节调参（ch5/7 从严、ch6/4 放行）；**合并扩展 numeric_guard.check_fiscal（不删 any-fy，其保护场景进回归单测）** | numeric_guard.py / data_anchor.py / gate8.py | 单测：ch5 写 FY2024 当期 → fail；ch6 合法历史引用（带"对比"标注）→ 通过 |
| B1-2 | **qual_mode 分级阻断**：Gate8+当期财年 enforce；Gate0/2 soft 或按错误类型分级（数值矛盾阻断 vs 字段缺失降级+标注）；**A4 验收后翻转默认** | mode_manager / run 脚本 | 默认运行 Critical 阻断；数据源降级路径仍产出带标注报告 |
| B1-3 | **ch0/ch10 纳入审计**（_AUDIT_ORDER 全 11 章；v8 在 Gate6 后第二审计遍） | workflow.py | 概览/结论受审 |

### B2 工作包：估值程序化先行 + 财务 100% Wind（Top 3/4，审议拆分 B2a/B2b）
| 项 | 内容 | 文件 | 验收 |
|---|---|---|---|
| B2a-1 | **current_price/shares 从 Wind quote 动态取**（删 21.48/46.52 硬编码；quality_enhancer 默认 41.6 一并删） | run 脚本 / quality_enhancer.py | 无硬编码股价 |
| B2a-2 | **币种断言**（hk→港元；估值链统一币种或显式 fx 标注） | extract_dcf_params / 估值模块 | 无港元/人民币混用 |
| B2a-3 | **DCF 参数专业化**：β 动态取/净有息负债/FCF 含 ΔWC/shares fail-fast + **亏损公司 DCF fail-fast 降级链**（小鹏即样本：full_dcf→comparable→PE） | extract_dcf_params / dcf_service / valuation_engine | 负 FCF 不输出无意义目标价 |
| B2a-4 | **目标价程序计算注入 ch7/ch10**（复用 valuation_engine 降级链） | workflow.py | 目标价=程序输出 |
| B2b-1 | **fact_extractor 移除 financial 字段提取**（财务 100% Wind）；**Wind 缺失字段处置表先行**（有息负债等无源字段盘点，禁止 LLM 补值） | fact_extractor.py / B5-1 | 事实表无财务行；无源字段显式标注"未披露" |
| B2b-2 | **仲裁扩展到全部 canonical 字段**（≤1% 保留/>1% 覆盖/异财年降级；统一 cross_validate 5% 与 reconcile 1% 容差口径） | _reconcile_facts_with_wind | 5 字段 → 全部 |
| B2b-3 | **data_repair 走 canonicalize + 负号正则统一** | data_repair.py | 无硬编码 wrong_years/快手 pattern |

### B3 工作包：事实提取表多财年化 + 可复核（Top 7，审议修订版）
| 项 | 内容 | 文件 | 验收 |
|---|---|---|---|
| B3-1 | 按年报份数分组提取（每份独立 fiscal_year）→ 3 张单年表程序化合并（不走 LLM）；fetch 3 份年报成本计入预算 | run_xpev_full.py / fact_extractor.py | 多财年列 |
| B3-2 | **前置 MinerU 页码结构验证**（sections 是否带 page 元数据）；字段增补：页码(不可得→null+unverified)/原文片段(≤80字)/置信度/仲裁状态/对比期 | fact_extractor.py / parsers | 事实行可翻原文；无 LLM 编造页码 |
| B3-3 | 批次一致性仲裁（冲突保留 confidence 高者+写入 warnings） | _merge_chunk_data | 无静默覆盖 |
| B3-4 | "宁可缺失不可杜撰" prompt + 禁止用前批值补当前批 | EXTRACTION_PROMPT | null 而非猜测 |

### B4 工作包：运营数据验证链 + 行业/结论修正（Top 6/8/9/10，审议修订版）
| 项 | 内容 | 文件 | 验收 |
|---|---|---|---|
| B4-1 | **运营数据验证链**：原文正则复核（配对 B5-2 数值转写归一）→ 多批次一致性 → 交叉披露 → 派生钩稽（**warning 级+口径例外白名单**，仅结构性铁律 MAU≥DAU≥付费 用阻断） | fact_extractor.py | 运营数字可复核 |
| B4-2 | **删除默认值填充**（_calculate_unit_economics 毛利率 50%）；normalize_units 改"超范围标注不修正"（配对 B5-2 预处理器，防单位错误漏出） | fact_extractor.py | 无杜撰数据源 |
| B4-3 | **行业判定动态化**（补 legacy review_repair_loop 默认参数）；ch2 数据年份标注（不可确定性强制时降级"标注或年份未知"） | adapters.py / workflow.py / review_repair_loop.py | 阅文不落"新能源汽车" |
| B4-4 | **修复循环锚点注入转验收**：v8 Gate4 已生效（review_repair_loop.py:299-319）→ 补事实表注入 + legacy 路径覆盖 | review_repair_loop.py | 修复带锚（补漏为主） |
| B4-5 | **ch10 锚点注入 + 元裁决规则（与 Gate6 合并）**：前置规则注入 prompt + 后验阻断（gate6 已有 RATING_VALUATION_MAPPING）双保险 + 否决项联动（ch9）为新开发点；评级=规则输出+人工 override 留痕（非绝对禁止） | _build_decision_prompt / gate6.py | 结论可复现 |
| B4-6 | **可比公司矩阵重写+数据源化**（提级中-大）：前置 Wind 可比可用性验证 → 泛化重写 peer_comparison（删顺丰硬编码+错误 ticker）→ 控股股东排除（腾讯 70.05%）→ 接线 ch2/ch7；验证不过降级"标注不可比" | peer_comparison.py / valuation_engine | 可比表非装饰且数据动态 |
| B4-7 | **ROIC vs WACC / FCF 含 ΔWC** 程序化支撑 | roic_wacc_checker.py / fcf_calculator.py | 价值创造门槛有数据 |

### B5 小包（综合审议新增，支撑 B2b/B3/B4 复核链）
| 项 | 内容 | 文件 | 验收 |
|---|---|---|---|
| B5-1 | **Wind 缺失字段处置表**：有息负债/现金/汇率/每股股息等无源字段先盘点——有源→canonical；可派生→公式+标注；不可得→空缺+报告标注"未披露"，**禁止启发式回填** | canonical.py / data_context.py | 无静默丢数/无 0.3 启发式 |
| B5-2 | **数值转写归一预处理器**：约/以上/区间/千分位/单位归一，供原文正则复核配对（拦截"4.102亿→410.2亿"类单位错误） | fact_extractor.py / 新模块 | 复核命中原文才保留，未命中→confidence=low |

**B 阶段验收**：重跑小鹏 = 财年错位 Critical 0、目标价为程序输出、事实表每行可翻原文复核、运营数据验证链通过、无硬编码股价/行业/可比数据。

---

## 四、阶段 C：审查环节优化（审查专家评审，详见 qual-review-loop-efficiency.md）

### C0 前置：结构化问题身份（D2，解锁全部增量方案）
| 项 | 内容 | 文件 | 验收 |
|---|---|---|---|
| C0-1 | **issue 结构化**：issue_id + 归属检查器 + 章节 + 位置 + 状态（new/recurred/resolved/exempt） | 检查器输出改造 | 修复循环按 issue_id 路由而非正则抠章节号 |
| C0-2 | **gate_regression.FixVerification 接线**（已存在未接入 v8） | gate_regression.py | 修复后验证可复用 |

### C1 工作包：零风险去重（静态层）
| 项 | 内容 | 文件 | 验收 |
|---|---|---|---|
| C1-1 | **Gate4 内 logic_consistency 只跑一次**，结果挂 context，_detect_contradictions 与 check_criteria 复用 | gate4.py | 逻辑矛盾不再 2-3 次重复发现 |
| C1-2 | **Gate4a 裁剪**：去掉占位符/指纹/元股（交由 Gate8 收口一次）；Gate8 不再叠加 gate_4_formal_issues | gate4.py / gate8.py | 同一问题不再二次上报 |
| C1-3 | **Gate3 跨章一致性结果传 context**，Gate4 首轮复用（中间无修改，结果相同） | gate3.py / gate4.py | 首轮不再重复跑跨章 |
| C1-4 | **Wind 锚点表收敛单例**（depth/conclusion/debate/integrator/repair 5 处重建 → 一次构建挂 context） | 各检查器 | 锚点表只构建一次 |

### C2 工作包：分层触发（核心收益——LLM 调用降 60-70%）
| 项 | 内容 | 文件 | 验收 |
|---|---|---|---|
| C2-1 | **静态检查器每轮全量**（11 个，成本≈0，有效性底线） | review_repair_loop.py | 静态回归防线保留 |
| C2-2 | **LLM 检查器首轮全量 + 修复后仅受影响章**（depth/结论/辩论按 C0 issue 归属重审） | review_repair_loop.py | LLM 调用从 ~57 次/报告 → ~21+增量 |
| C2-3 | **受影响集计算**：IncrementalChecker.get_affected_chapters 接线（跨章引用链） | incremental_checker.py | 修 A 章不遗漏被 A 引用的 B 章 |

### C3 工作包：问题清单驱动 + 红队门控
| 项 | 内容 | 文件 | 验收 |
|---|---|---|---|
| C3-1 | **冻结清单验证**：修复轮只验证清单内问题 + 无新回归（静态全量兜底）；LLM 级兜底边界明确（清单外新问题由静态+红队覆盖） | review_repair_loop.py | 修复轮 LLM 进一步降 |
| C3-2 | **红队触发门控**：Gate4 实质通过后才触发红队 + 显式覆盖 ch0/ch10；**新增红队 fatal 回流 Gate4 限 1 轮**（auto_fix_p0=True 或回流路径二选一明确） | gate8.py | 红队 fatal 有处理路径；不破坏 M1 |

### C4 工作包：预算与协同（与 A 阶段同点叠加，非正交）
| 项 | 内容 | 文件 | 验收 |
|---|---|---|---|
| C4-1 | **LLM 审查预算**：每报告 ≤35 次（35 ⊂ v3.1 总预算 200，核算关系明确）；超预算 fail-closed（降级全量静态+显式"未审完"标注，不静默放行）；worst case 37>35 处置定义 | 预算机制 | 超预算不静默放行；不破坏 v3.1 收敛 |
| C4-2 | **单调守卫修正**：与 A 缺陷6 同循环函数叠加（去"正交"表述）；"分"=issue 签名集；全量静态签名集单独计量，LLM 分只做受影响集内比较 | review_repair_loop.py | 增量审查不破坏单调守卫；test_monotonic_guard 保持绿 |
| C4-3 | **豁免与 D2 状态合并（fail-closed 硬约束）**：exempt 状态与累积豁免清单**同源不可清除**，永不 PASS，仅"不重复触发修复投入"；报告注明豁免数 | review_repair_loop.py | test_exemption_failclosed 保持绿；豁免问题仍计入收敛判定 |

### C5 验收口径修正包（综合审议新增，P0）
| 项 | 内容 | 验收 |
|---|---|---|
| C5-1 | 跨章去重补 **data_repair 第二套实现统一**（data_repair.py:304 改调统一检查器） | 跨章审查路径去重至 1 处有效执行 |
| C5-2 | 占位符 **统一 pattern 常量**（L1/G3/G4a/G8 同源，含待填写/TBD；G8 用全量 5 pattern） | 占位符 L1+G8 两处，无逃出收口 |
| C5-3 | 锚点单例化范围 **5 处 → 全部 10 个调用点**（gate2/gate5/gate8/integrator×2/repair×2 等）；DataAnchor 只读约束 | 锚点审查环节 10→1 处构建 |
| C5-4 | 降幅口径修正：**≤35 次 + 典型报告降 ~50-60%**（70→35 为 -50%，60-70% 需增量轮很小） | 验收数字与实现闭合 |

**C 阶段验收（修订）**：审查 LLM 调用 ≤35 次/报告（现最坏 ~70，典型降 50-60%）；跨章审查路径去重至 1 处有效执行、logic 上报 1 次、占位符 L1+G8 两处（统一常量）、锚点审查环节 10→1 处；死循环不复发（test_exemption_failclosed/test_monotonic_guard 保持绿）；红队 fatal 有回流；报告质量不降（静态纵深保留）。

---

## 五、依赖与优先级矩阵

| 依赖 | 说明 |
|---|---|
| B1-1 ← A2 | Gate8 接线依赖阶段 A 的 fail-closed/deadline |
| B2-1/2 ← A1 | canonical/仲裁是 A1 的 P0-A 基础 |
| B3-1 ← B2-1 | 财务移出后事实表才专注运营/定性 |
| B4-2 ← B3 | 删除默认值依赖提取重构 |
| B4-5 ← B2a-4 | 结论锚依赖估值程序化 |
| B2b-1 ← B5-1 | 财务 Wind 化依赖 Wind 缺失字段处置表先行 |
| **C2-3 ← C0** | 受影响集依赖问题身份（D2 章节归属） |
| **C4-2 ← A1** | 单调守卫与 A 缺陷6 同函数叠加 |
| **C4-3 ← A1** | 豁免与 A 缺陷1 累积清单同源（不得回归） |
| **C1-4 ← B2b** | 锚点单例化在 canonical 扩展后做 |
| **C1-1 ← C0** | 缓存键需 issue 版本 |

**优先级排序**（综合：可信度影响 × 依赖 × 工作量，按综合审议修订）：
1. **A 全阶段**（先跑得完）
2. **B1**（章节级财年语义 + 分级阻断——影响最大、工作量小）
3. **B2a**（估值程序化先行：current_price/shares/币种/DCF 降级链——影响大、工作量中）
4. **B5-1**（Wind 缺失字段处置表——B2b 前置）
5. **B2b**（财务 100% Wind + 仲裁扩展）
6. **B3**（事实表可复核，B3-2 前置 MinerU 页码验证）
7. **B5-2**（数值转写归一预处理器——B4-1 复核链配对）
8. **B4**（运营验证 + 行业 + 结论锚；4-4 转验收、4-5 与 Gate6 合并、4-6 可比重写）
9. **B5 收口**（护栏复核）
10. **C0**（结构化问题身份——解锁全部增量）
11. **C1**（去重 + data_repair 统一 + pattern 常量 + 锚点 10→1）
12. **C2**（分层触发 + 受影响集闭包）
13. **C3**（清单驱动 + 红队门控回流）
14. **C4/C5**（预算协同 + 验收口径）

---

## 六、验收总纲

| 里程碑 | 验收 |
|---|---|
| M1（A 完成） | 20 测试绿；小鹏运行有界终止 ≤60 分钟；无死循环 |
| M2（B1 完成） | 章节级财年校验拦截 ch5 历史财年（ch6 合法引用豁免）；Critical 阻断出厂；数据源降级仍产出带标注报告 |
| M3（B2 完成） | 无硬编码股价；目标价=程序输出（亏损公司走降级链）；币种断言生效；事实表无财务提取；无源字段显式标注 |
| M4（B3 完成） | 事实表多财年 + 每行可翻原文复核（页码 null+unverified 而非编造） |
| M5（B4/B5 完成） | 运营数据验证链通过（钩稽 warning 级+白名单）；行业判定正确；结论可复现（评级=规则输出+override 留痕）；无可比硬编码数据 |
| M6（C 完成） | 审查 LLM 调用 ≤35 次/报告（典型降 50-60%）；跨章审查路径去重至 1 处有效执行、logic 上报 1 次、占位符 L1+G8 两处（统一常量）、锚点审查环节 10→1 处；死循环不复发（exemption/monotonic 测试保持绿）；红队 fatal 有回流；报告质量不降 |

**最终形态**：一份"跑得完、数据可信、结论可决策使用、审查高效不重复"的买方研究报告流水线。

---

## 七、版本记录

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.0 | 2026-08-19 | 初版（A 死循环修复 + B 数据真实性） |
| v1.1 | 2026-08-19 | 按综合审议（docs/qual-expert-suggestions-adjudication.md）修订：B1 章节级财年语义+分级阻断；B2 拆 B2a/B2b；B4-4/4-5 转验收合并；B4-6 可比重写+数据源化；新增 B5 小包 |
| v2.0 | 2026-08-19 | 新增阶段 C（审查环节优化，docs/qual-review-loop-efficiency.md）：C0 D2 结构化问题身份 + C1 去重 + C2 分层触发 + C3 清单驱动/红队门控 + C4 预算协同；阶段 B 落地为 qual-stage-b-arch/code.md |
| v2.1 | 2026-08-19 | 按阶段 C 综合审议（docs/qual-stage-c-adjudication.md）修订：C4-3 豁免 fail-closed 硬约束（防缺陷1 回归）；新增 C2-3 受影响集闭包、C3-2 红队 fatal 回流、C0-2 FixVerification 扩展、C5 验收口径修正包（data_repair 统一/pattern 常量/锚点 10 处/降幅修正）；依赖矩阵新增 C←A/C←B 5 项；M6 验收重写 |
