# HGF执行计划v4.0

**执行日期**: 2026-07-11
**执行依据**: HeavySkill K=8四审通过的v4.0技术方案

## Gate定义

### Gate 0: 阻断性问题修复 (5h)
- P76: success判断 → quality_degraded标志 ✅(已存在)
- P77: 辩论覆盖 → 合并模式 ✅(已修复)
- P11: 年份标签 → WindData._year_labels ✅(已修复)
- WACC统一 → DCF动态计算 ✅(无需修复)

### Gate 1: 消除致命硬伤 (9h)
- T1: 年份硬编码 → _build_wind_summary() ✅
- T4: AI痕迹清洗 → BANNED_PHRASES + clean_ai_artifacts() ✅
- T7: 估值交叉验证 → cross_validate_pe_pb() ✅
- O2: success判断 → quality_degraded标志 ✅

### Gate 2: 数据可信度+论点锚定 (16h)
- T6: 事实核查 → structural_check.py 检查7 ✅
- T11: 敏感性+情景 → SensitivityAnalyzer ✅(已存在)
- ANCH: 投资论点锚定 → _generate_anch_hypothesis() ✅

### Gate 3: 估值内核 (17h)
- T9: SOTP分部估值 → sotp_valuation.py ✅(已存在)
- T10: WACC参数校准 → dcf.py CAPM ✅(已存在)
- T12: ROIC/WACC → Formulas.nopat/invested_capital/roic/roic_spread ✅
- T3: 综合结论章 → _generate_synthesis_chapter() ✅

### Gate 4: 深度提升 (18h)
- T13: DCF反推 → implied_growth_from_dcf() ✅
- T2: 可比公司增强 → compute_comparable_valuation() ✅
- T14: 证伪指标 ⏳
- T15: 行业周期 ⏳
- T5: 辩论结构化 ⏳
- T18: 催化剂日历 ⏳

### Gate 5: 专业对齐 (10h)
- T16: 同行对比矩阵 ⏳
- T17: 管理层评估 ⏳
- T8: 分部数据优化 ⏳

### E2E测试 (12h)
- 顺丰控股002352.SZ完整跑通
