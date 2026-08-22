# qual 投资方法论审查报告（投资专家）

> 生成：2026-08-22 双专家全面检查；送 heavyskill 评审用
> 审查范围：qual_v8/（Gate0-8）+ workflow.py（v2-v7 单体）+ quality*/（DCF/CAPM/终值/SOTP/审查组件）+ 财务处置表/锚点/ADVC/财年语义

## 一、总体评价

qual 的数据真实性链（财务 100% Wind、DataAnchor 锚点归因、ADVC 确定性修复、FiscalSemantics 财年语义）是自动化研报管线中防守最扎实的一层——把"数字可追溯、错位可程序修正、财年可归因"做成了确定性机制而非 LLM 自觉。但估值链与结论链存在方法论级硬伤：净负债用"总负债"近似并辅以 ×0.3 启发式、β 对所有公司硬编码 1.2、可比公司写死旧倍数且行业错配、毛利率被算成营业利润率——让"看起来每一处数字都对"的报告在投资结论层面系统性失真（对净现金成长股可低估估值 30%+）。默认 shadow 模式只审不修、质量标注以 HTML 注释写入（渲染后不可见）、人工确认默认通过，使"不静默放行"在默认配置下名存实亡。

**报告可信度评分：6.0/10**（数据链 8.5、估值链 4、过程诚信 5.5 加权）

## 二、数据真实性发现

- **A1 P1 口径扁平化**：data_anchor.py:24-49 别名表把"营业总收入"→"营业收入"、"年净利润"→"归母净利润"直接合并。A 股口径下营业总收入≠营业收入；"年净利润"若含少数股东损益会被无痕改写成归母口径（pitfalls Q2-2 实证过 -7.76 vs -8.44 混用）
- **A2 P0 毛利率=营业利润/营业收入**：wind_field_disposition.py:26-35 gross_margin 与 operating_margin 用同一公式。亏损期车企（小鹏 FY2024 营业利润为负）将输出"毛利率为负"（实际约 14%）；高研发公司营业利润率远低于毛利率
- **A3 P1 1% 容差**：data_anchor.py:141-160 归因 + :193-222 校验。多指标同向 1% 可累积 3-5% 目标价偏差；百分比指标（pct）完全无锚点（:288-301 只记录不校验）
- **A4 P1 ADVC 误改子公司数据**：data_anchor.py:249-269 语境排除表不含"子公司/分部/旗下/境内/境外"；anchor_repair.py:104-181 会命中 prefix_drop 签名并自证通过（自证只保证"改后无错位值"，不保证"改对地方"）
- **A5 P2 财年校验 fail-open**：data_anchor.py:468-469 except Exception: pass 吞异常；year_anchor.py:49-54 硬编码某公司特定数值（3082/111/8.4%）
- **A6 P0 净负债自相矛盾**：wind_field_disposition.py:41-48 标 cash/debt unavailable 禁启发式，workflow.py:2253-2265 却用总负债当净负债+×0.3 拍脑袋

## 三、方法论有效性发现

- **B1 P0 β=1.2 硬编码**：workflow.py:2235-2239 + valuation_engine.py:144-152 常数。小鹏 β 实际约 2.0+，Ke 从 13% 低估到 8.9% → WACC 低估 → DCF 系统性偏高。CAPMCalculator 存在但主链绕过它
- **B2 P0 净负债口径错误**：workflow.py:2253-2265 net_debt=总负债；净现金公司（快手类）真实净负债为负却被算成正 200-400 亿 → 目标价压低 20-40%
- **B3 P0 可比公司写死+行业错配**：valuation_engine.py:100-112 CORE_COMPARABLES 含迪士尼，Q3-1 实证缺陷仍在代码
- **B4 P1 评级一致性检查空转**：gate6.py:255-269 依赖 context["valuation"].dcf_value，但 gate5.py:143-149 只写 {pe_ttm,pb,ps_ttm,market_cap} 无 dcf_value → 检查被 if dcf_value>0 静默跳过
- **B5 P2 牛/熊=±20% 机械乘子**：valuation_engine.py:404-414
- **B6 P1 SOTP 未接入主流程**：compute_sotp_valuation 仅出现在 sotp_valuation.py 与测试，无调用点
- **B7 正面 终值双轨仲裁**：terminal_value_calculator.py:73-80 g≥WACC 抛错、:151-198 双轨差异分级仲裁、dcf_service.py:294-296 TV/EV>75% 警告——专业级设计
- **B8 P1 红队 fail-open + 分段截断**：gate8.py:511-513 except→passed=True；:427 12000 字符分段逐段审查，跨段矛盾漏检
- **B9 P1 风险披露=关键词覆盖**：gate4.py:352-371 "财务"二字即覆盖；conclusion_validator.py:401-408 含"问题"字样即触发

## 四、报告可信度发现

- **C1 P1 默认 shadow 模式名存实亡**：qual_v8/workflow.py:253 默认 "shadow"、:67 skip_repair=True；B1-2 分级阻断仅 enforce 模式
- **C2 P1 质量标注是 HTML 注释**：qual_v8/workflow.py:447-452 <!-- ⚠️ --> 渲染后不可见，位于文末
- **C3 P2 降级参数兜底**：gate5.py:199-200 fiscal_year 默认 2025、current_price 默认 0、shares 默认 0
- **C4 P1 人工确认默认 True**：gate8.py:297 context.get("human_confirmed", True)
- **C5 P2 财年标注过度/漏标并存**：numeric_guard.py:295 豁免窗口 80 字符；强制 FY 标注会逼 LLM 堆年份标签

## 五、多轮测试问题投资视角评估

- **D1 33 倍量级错位：部分根治**。prefix_drop 签名+自证+救援 sweep 拦截"丢前缀"；但同量级错误（1031.63→1031.73）dev<1% 被当精确命中跳过。pct 指标无锚点是最大缝隙
- **D2 财年误判：根治**。validate_chapter_any_fy 命中任一财年即通过 + attribute_value 归因 + 双通道年份识别
- **D3 Gate4 卡死：根治（有条件）**。max_rounds=3 + 收敛早停 + 豁免学习（豁免非空即 fail-closed）+ 单调守卫 + 墙钟/预算。残余：C2-2 增量审查只审受影响章，依赖传播仅覆盖 ch0/ch10
- **D4 外部数据抖动：根治**。错误分类-重试-熔断-降级链路完整

## 六、优先级修复清单

| 级别 | 问题 | 位置 | 投资影响 |
|------|------|------|----------|
| P0 | 毛利率=营业利润率 | wind_field_disposition.py:26-35 | 亏损公司报负毛利率 |
| P0 | 净负债=总负债+×0.3 | workflow.py:2253-2265 | 净现金股目标价低 20-40% |
| P0 | β=1.2 硬编码 | workflow.py:2235-2239 | 高波动股估值偏高 |
| P0 | 可比写死+行业错配 | valuation_engine.py:100-112 | 相对估值失真 |
| P1 | 评级一致性检查空转 | gate5/gate6 数据契约 | 评级铁律不执行 |
| P1 | 默认 shadow 不阻断 | qual_v8/workflow.py:253 | 审查空转 |
| P1 | 质量标注不可见 | workflow.py:447-452 | 读者看不到未验证 |
| P1 | 人工确认默认 True | gate8.py:297 | 无复核放行 |
| P1 | ADVC 误改子公司数据 | data_anchor.py:249-269 | 正确数字被错改 |
| P1 | 红队 fail-open+截断 | gate8.py:511,427 | 致命问题漏检 |
| P1 | 风险披露=关键词 | gate4.py:352 | 格式替代深度 |
| P1 | SOTP 未接入 | sotp_valuation.py | 声称链缺环 |
| P2 | 财年校验异常被吞 | data_anchor.py:468 | 漏标无告警 |
| P2 | pct 无锚点+1%累积 | data_anchor.py | 边界评级漂移 |
| P2 | 牛/熊机械乘子 | valuation_engine.py:404 | 无情景信息 |
| P2 | 汇率 0.92 硬编码 | base_valuation.py:107 | 港股偏差 8-10% |

**核心结论**：qual 的数字真实性防线接近生产级，但投资结论防线（估值参数、可比、评级映射、过程诚信）停留在"组件齐备但接线断裂+默认不执法"。当前输出应定位为"数据可信、结论需人工复核"的研究草稿。
