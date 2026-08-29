# Qual v10 问题根本性与长效化治理方案（v3.0）

> 版本：v3.0 | 日期：2026-08-27
> 基于：HeavySkill K8 审查意见（6 项 P0 整改）+ 投资专家/CFA 持证人深度修订
> 目标：从"逐个修 bug"转向"系统性治理"
> 审查依据：CFA Institute Standards of Practice (V-A/V-B/V-C) + 买方研究报告质量底线

---

## 一、问题—根因—控制—测试追溯矩阵（P0 整改第 1 项）

| ID | 问题描述 | 根因 | 防线层 | 控制措施 | 测试用例 | 状态 |
|----|---------|------|--------|---------|---------|------|
| P-01 | DCF 负值注入报告 | 亏损公司 DCF 未禁用 | 估值引擎 | `quality_enhancer.py` 阻止负 DCF 注入 | `test_no_negative_dcf_injection` | ✅ 已修复 |
| P-02 | 翻转阈值方向错误 | depth_enhancer 数学公式方向反转 | 估值引擎 | 方向验证 + 20% 敏感度降级 | `test_flip_threshold_direction` | ✅ 已修复 |
| P-03 | 可比公司含迪士尼 | 静态可比池未更新 | 估值引擎 | 删除迪士尼，标注 static_snapshot | `test_comparables_no_disney` | ✅ 已修复 |
| P-04 | β=1.2 硬编码 | WACC 参数未从 Wind/可比获取 | 估值引擎 | 支持调用方传 β，无源显式降级 | `test_beta_explicit_degradation` | ✅ 已修复 |
| P-05 | 净负债=总负债+×0.3 | 有息负债未从财报提取 | 估值引擎 | 弃用近似，net_debt=None + 标注 | `test_net_debt_no_heuristic_backfill` | ✅ 已修复 |
| P-06 | 毛利率=营业利润率 | Wind 无毛利率字段时用营业利润率顶替 | 数据契约 | 改为 unavailable，禁用替代 | `test_gross_margin_not_masqueraded` | ✅ 已修复 |
| P-07 | 跨章净利润冲突 | PGNB regex 不检查财年上下文 | 数据契约 | `numeric_binder.py` 增加财年感知 | `test_bind_bare_numbers_fy_aware` | ✅ 已修复 |
| P-08 | Gate 5-8 级联失败 | Gate 依赖线性链 | 架构 | Gate DAG + 降级依赖 | `test_gate_degradation_on_gate4_fail` | ✅ 已修复 |
| P-09 | review_incomplete 静默通过 | passed 分支未检查 review_incomplete | 检查前移 | Gate4 显式读取 + passed 强制 | `test_review_incomplete_fail_closed` | ✅ 已修复 |
| P-10 | T9-T14 硬编码覆写 facts | 阅文集团特定值硬编码 | 数据契约 | 改从 ctx.wind 真实取值 | `test_no_hardcoded_facts_override` | ✅ 已修复 |
| P-11 | 估值偏差阈值一刀切 | <40% 阈值不分公司类型 | 估值引擎 | 分行业差异化阈值（§三） | `test_deviation_threshold_by_type` | 🔧 待实施 |
| P-12 | 缺乏 CFA 合规证据链 | 无审计日志 | 全链路 | 自动生成 va/vb/vc 三份审计文件（§四） | `test_audit_trail_generation` | 🔧 待实施 |
| P-13 | 回归股票池不足 | 仅 2 只股票 | 回归测试 | 扩展到 10 只覆盖 10 个场景（§五） | `test_regression_pool_full` | 🔧 待实施 |
| P-14 | 测试与验收方案不完整 | fatal 用例不足、无 CI/CD | 回归测试 | 扩展 fatal 用例 + 接入 CI/CD（§五） | `test_ci_cd_gate8_block` | 🔧 待实施 |
| P-15 | 执行级文档包缺失 | 无 RCA/数据字典/接口规范/Runbook/RACI | 文档 | 补充完整文档包（§八） | 文档 review | 🔧 待实施 |

---

## 二、四层防线

### 防线 1：数据契约层（源头治理）

**原则**：所有财务数据必须通过 Financials 契约传递，禁止 dict[str, Any] 直传。

**措施**：
1. **Wind 适配器强制化**：`wind_to_financials()` 作为唯一入口，缺失字段 fail-fast
2. **Canonical key 统一**：`canonical.py` 作为唯一真源，禁止绕过
3. **数据血缘追踪**：每个 Financials 字段记录 `source`/`timestamp`/`confidence`（见 §四 V-A 证据链）
4. **输入校验器扩展**：覆盖 12 项关键参数（WACC/g/PS/PB/EV-Rev/汇率/杠杆）

**验收标准**：任何财务数据可追溯到 Wind API 返回值。

### 防线 2：估值引擎层（逻辑治理）

**原则**：估值计算必须通过 ValuationArbiter 唯一出口，禁止 Gate 自行计算。

**措施**：
1. **ValuationArbiter 唯一出口**：gate5.py 只消费 Arbiter 结论
2. **DCF 适用性判断**：亏损公司 + OCF 为负 → DCF 不适用
3. **翻转阈值方向验证**：所有翻转点必须 ≤ 当前值
4. **评级-目标价映射**：`_derive_rating()` 自动推导

**验收标准**：任何估值输出必须包含 `rating` + `method` + `reconciliation`。

### 防线 3：检查前移层（流程治理）

**原则**：致命问题必须在 Gate 5-7 拦截，不能到 Gate 8 才暴露。

**措施**：
1. **Gate 5 增加估值一致性检查**：DCF vs 可比公司偏差按公司类型差异化阈值（见 §三）→ 警告
2. **Gate 6 增加评级-目标价校验**：评级与上行空间不一致 → 警告
3. **Gate 7 增加跨章数据校验**：关键指标跨章引用不一致 → 警告
4. **Gate 8 降级为"最终确认"**：fatal 来自 Gate 5-7 的 warning 升级

### 防线 4：回归测试层（长效治理）

**原则**：每个修复必须有对应的回归测试用例，防止复现。

**措施**：
1. **Fatal 回归错题库**：8 个已暴露 fatal 固化为测试用例（P-01 ~ P-10）
2. **多股票回归集**：10 只股票覆盖 10 个场景（见 §五）
3. **Gate 8 零 fatal 验收**：连续 N 只股票 Gate 8 零 fatal 作为升级标准
4. **数据血缘审计**：每次运行后自动检查数据一致性
5. **CI/CD 接入**：fatal 测试失败阻断发布（见 §五.C）

**验收标准**：回归测试覆盖率 ≥ 90%，新增标的首过率 ≥ 95%。

---

## 三、估值自洽阈值细化（P0 整改第 3 项）

> CFA 依据：Standard V-B（适当性）要求估值方法与公司特征匹配，Standard V-C（一致性）要求多方法 reconcile 时必须有差异化阈值逻辑。当前"DCF/PS/EV-Rev 偏差 <40%"一刀切过宽，对不同公司类型缺乏分辨力。

### 3.1 分行业·分公司类型估值自洽阈值矩阵

| 公司类型 | 判定条件 | 主方法 | 交叉验证方法 | 偏差阈值（主 vs 最远交叉） | 超阈值行动 |
|----------|---------|--------|-------------|-------------------------|-----------|
| **亏损公司（OCF 正）** | 净利润 < 0 且 OCF > 0 | EV/Revenue | PS, PB（若净资产 > 0） | **25%** | 超阈值 → 以 EV/Rev 为准，强制披露 PS 偏差来源；超 40% → Gate5 warning 升级 |
| **亏损公司（OCF 负）** | 净利润 < 0 且 OCF ≤ 0 | PS | EV/Revenue 辅助 | **20%** | 超阈值 → 以 PS 为准，标注"现金流为负，估值高度不确定"；超 35% → 阻断报告输出 |
| **盈利公司（高增长）** | 净利润 > 0 且营收 YoY ≥ 25% | DCF | PE, PS | **30%** | 超阈值 → 以 DCF 为主，披露 PE/PS 偏差；超 45% → Gate5 warning 升级 |
| **盈利公司（稳定）** | 净利润 > 0 且营收 YoY < 15% | PE | DCF, PB, PS | **25%** | 超阈值 → 以 PE 为主，披露 DCF 假设差异；超 40% → Gate5 warning 升级 |
| **周期公司** | 行业分类 ∈ {钢铁/有色/化工/煤炭/航运/建材} 且近 3 年净利润变异系数 > 50% | PB | PE（正常化）, EV/EBITDA | **30%** | 超阈值 → 以 PB 为主，要求附正常化 PE；超 45% → Gate5 warning 升级 |
| **金融公司** | 行业分类 ∈ {银行/保险/券商/多元金融} | PB | DDM, PE | **20%** | 超阈值 → 以 PB 为主，强制披露净资产质量分析；超 35% → Gate5 warning 升级 |

### 3.2 阈值设计原则（CFA 合规逻辑）

1. **亏损公司阈值更紧（20-25%）**：亏损公司的估值方法选择有限，交叉验证结果差异更大，因此需要更严的偏差控制。若主方法与交叉验证偏差过大，说明方法选择或参数假设存在根本性问题。CFA V-B 要求"方法与公司特征匹配"，偏差过大即违反此原则。
2. **高增长公司阈值较宽（30%）**：高增长公司的 DCF 对增速假设高度敏感，PE/PS 乘数也因增长溢价而分化，允许更大偏差但强制披露偏差来源。
3. **周期公司阈值适中（30%）**：周期公司的盈利波动大，PB 相对稳定但 PE 可能因周期位置而失真，允许适度偏差。
4. **金融公司阈值最紧（20%）**：金融公司的 PB 和 DDM 逻辑一致性高，偏差过大说明参数输入有误。
5. **40% 为绝对红线**：无论何种公司类型，偏差超过 40% 必须触发 Gate5 warning 升级审查，不允许静默通过。

### 3.3 实现方案：`valuation/arbiter.py` 阈值改造

```python
# 新增：按公司类型差异化阈值
_THRESHOLDS_BY_TYPE = {
    "loss_ocf_pos":   {"warn": 0.25, "block": 0.40, "desc": "亏损(OCF正)"},
    "loss_ocf_neg":   {"warn": 0.20, "block": 0.35, "desc": "亏损(OCF负)"},
    "growth":         {"warn": 0.30, "block": 0.45, "desc": "盈利高增长"},
    "stable":         {"warn": 0.25, "block": 0.40, "desc": "盈利稳定"},
    "cyclical":       {"warn": 0.30, "block": 0.45, "desc": "周期公司"},
    "financial":      {"warn": 0.20, "block": 0.35, "desc": "金融公司"},
}

def _classify_company_type(financials, industry: str = "", revenue_growth: float = 0) -> str:
    """根据财务指标 + 行业分类判定公司类型。

    CFA V-B: 方法选择必须与公司特征匹配。
    """
    is_loss = financials.net_profit_parent < 0
    ocf_pos = financials.operating_cashflow > 0

    # 行业优先判定
    if industry in ("银行", "保险", "券商", "多元金融"):
        return "financial"
    if industry in ("钢铁", "有色", "化工", "煤炭", "航运", "建材"):
        return "cyclical"

    # 亏损/盈利判定
    if is_loss:
        return "loss_ocf_pos" if ocf_pos else "loss_ocf_neg"

    # 盈利公司：看营收增速
    if revenue_growth >= 0.25:
        return "growth"
    return "stable"

def get_deviation_threshold(company_type: str) -> tuple[float, float, str]:
    """返回 (warn_threshold, block_threshold, description)。"""
    t = _THRESHOLDS_BY_TYPE.get(company_type, _THRESHOLDS_BY_TYPE["stable"])
    return t["warn"], t["block"], t["desc"]
```

### 3.4 验收标准

| 检查项 | 方法 | 通过条件 |
|--------|------|---------|
| 亏损公司（OCF 正）偏差 ≤ 25% | 小鹏 9868.HK 回归 | EV/Rev vs PS 偏差 < 25% |
| 亏损公司（OCF 负）偏差 ≤ 20% | 构造 OCF 为负的测试用例 | PS 唯一主方法 |
| 盈利高增长偏差 ≤ 30% | 协鑫能科 002015.SZ 回归 | DCF vs PE 偏差 < 30% |
| 周期公司偏差 ≤ 30% | 海螺水泥 600585.SH | PB vs 正常化 PE 偏差 < 30% |
| 金融公司偏差 ≤ 20% | 汇丰控股 0005.HK | PB vs DDM 偏差 < 20% |
| 绝对红线 40% | 任意股票 | 偏差 > 40% → Gate5 warning 升级 |

---

## 四、CFA 合规证据链（P0 整改第 4 项）

> CFA 依据：Standards of Professional Conduct V-A（勤勉与合理基础）、V-B（适当性）、V-C（表述与一致性）。qual v10 当前仅在代码层面实现了部分合规，但缺乏可审计的证据链——即"如何证明合规"的记录。

### 4.1 CFA V-A：勤勉与合理基础（Diligence and Reasonable Basis）

| 要求 | qual v10 当前状态 | 需要补充的证据 | 实现方式 |
|------|------------------|--------------|---------|
| 估值输入有合理来源 | Wind MCP 作为数据源，Financials 契约记录 `source="Wind"` | **输入溯源日志**：每个 Financials 字段记录 Wind API 返回的原始值、转换时间、财年 | `contracts/financials.py` 增加 `provenance: dict[str, InputProvenance]`，`InputProvenance` 含 `raw_value`/`api_endpoint`/`fetch_time`/`fiscal_year` |
| 估值假设有依据 | WACC/g/β 参数来源未记录 | **假设来源记录**：每个估值假设记录"来源类型"（Wind 实证/行业中枢/分析师判断）和"置信度" | `valuation/arbiter.py` 的 `ValuationVerdict` 增加 `assumptions_log: list[AssumptionRecord]`，`AssumptionRecord` 含 `param_name`/`value`/`source_type`/`confidence`/`rationale` |
| 分析师具备专业能力 | qual v10 作为自动化管线，无人工分析师 | **免责声明**：报告头部标注"本报告由 qual v10 自动化管线生成，未经人工分析师复核" | `gate8.py` 输出模板增加自动声明区块 |
| 数据验证已完成 | DataAnchor 锚点校验 | **数据验证报告**：每次运行输出 DataAnchor 校验摘要（匹配率/偏差率/异常列表） | 新增 `audit/data_validation_report.py`，每次运行生成 JSON 验证摘要 |

**V-A 证据链产物**：每次 qual v10 运行自动生成 `audit_trail_va.json`：
```json
{
  "run_id": "qual-v10-xpev-20260827-001",
  "data_provenance": {
    "revenue": {"raw_value": 76720000000, "api": "wind/income/年营业总收入", "fetch_time": "2026-08-27T10:00:00Z", "fiscal_year": 2025},
    "net_profit_parent": {"raw_value": -1139000000, "api": "wind/income/年净利润", "fetch_time": "2026-08-27T10:00:00Z", "fiscal_year": 2025}
  },
  "assumption_log": [
    {"param": "WACC", "value": 0.095, "source_type": "wind_beta_bottomup", "confidence": "medium", "rationale": "β=1.8(可比中位数), Rf=2.5%, ERP=6%"},
    {"param": "terminal_growth", "value": 0.025, "source_type": "industry_central", "confidence": "low", "rationale": "新能源汽车行业中枢2-3%"}
  ],
  "data_validation": {"anchor_match_rate": 0.97, "fiscal_year_consistency": true, "anomalies": []},
  "disclaimer": "本报告由 qual v10 自动化管线生成，未经人工分析师复核。所有估值结论仅供参考，不构成投资建议。"
}
```

### 4.2 CFA V-B：适当性（Suitability）

| 要求 | qual v10 当前状态 | 需要补充的证据 | 实现方式 |
|------|------------------|--------------|---------|
| 估值方法与公司特征匹配 | `method_selector.py` 已实现方法选择矩阵 | **方法选择审计**：记录"为什么选这个方法"、"排除了哪些方法及原因" | `MethodSelection` 增加 `decision_trace: str`，格式化为人类可读的决策链 |
| 敏感性分析已执行 | `depth_enhancer.py` 有翻转阈值但无完整敏感性 | **敏感性矩阵**：WACC ±1%、g ±0.5%、营收增速 ±5% 的目标价矩阵 | 新增 `valuation/sensitivity.py`，输出 `SensitivityMatrix` 含 `wacc_range`/`growth_range`/`revenue_growth_range` 对应的目标价网格 |
| 可比公司选择有标准 | 静态可比池（已删除迪士尼但仍是快照） | **可比公司选择记录**：记录可比公司列表、选择标准、数据截止日 | `ValuationVerdict` 增加 `comparable_universe: list[ComparableRecord]`，`ComparableRecord` 含 `ticker`/`name`/`selection_reason`/`multiples`/`data_date` |
| 估值区间已建立 | `ValuationVerdict` 有 bear/base/bull | **区间推导逻辑**：记录每个区间的假设变化（如"悲观：PS 降至行业中位数 75%"） | 已在 `target_bear_assumptions`/`target_bull_assumptions` 中实现，需确保每个股票都填充而非留空 |

**V-B 证据链产物**：`audit_trail_vb.json`：
```json
{
  "method_selection": {
    "primary": "EV/Revenue",
    "reason": "亏损公司(净利=-11.39亿)，OCF正(82.59亿)，营收高增长 → EV/Rev最适当",
    "excluded": [{"method": "PE", "reason": "负EPS无意义"}, {"method": "DCF", "reason": "仅作辅助情景(OCF正但会计亏损)"}],
    "decision_trace": "净利润<0 → PE排除 → OCF>0 → DCF降级为辅助 → EV/Rev选为主方法"
  },
  "sensitivity_matrix": {
    "base_target": 45.0,
    "wacc_sensitivity": {"8.5%": 52.3, "9.5%": 45.0, "10.5%": 39.1},
    "growth_sensitivity": {"2.0%": 41.2, "2.5%": 45.0, "3.0%": 49.5},
    "revenue_growth_sensitivity": {"20%": 38.7, "25%": 45.0, "30%": 52.1}
  },
  "comparable_universe": [
    {"ticker": "NIO", "name": "蔚来", "selection_reason": "新能源汽车亏损期可比", "ps": 2.1, "ev_rev": 1.8, "data_date": "2026-08-27"},
    {"ticker": "LI", "name": "理想", "selection_reason": "新能源汽车扭亏过渡期可比", "ps": 3.5, "ev_rev": 2.8, "data_date": "2026-08-27"}
  ]
}
```

### 4.3 CFA V-C：表述与一致性（Representation and Consistency）

| 要求 | qual v10 当前状态 | 需要补充的证据 | 实现方式 |
|------|------------------|--------------|---------|
| 多方法 reconcile 有记录 | `ValuationVerdict.reconciliation` 已实现 | **Reconciliation 详细日志**：记录每对方法的偏差值、偏差来源、仲裁理由 | `ValuationVerdict` 增加 `pairwise_deviations: list[PairwiseDeviation]`，`PairwiseDeviation` 含 `method_a`/`method_b`/`deviation_pct`/`deviation_source`/`arbitration_action` |
| 目标价与评级一致 | `_derive_rating()` 已实现 | **评级推导日志**：记录目标价→上行空间→评级的推导链 | `ValuationVerdict` 增加 `rating_derivation: RatingDerivation`，含 `target_price`/`current_price`/`upside_pct`/`rating`/`threshold_applied`/`rationale` |
| 跨报告一致性 | 无历史比较机制 | **纵向一致性检查**：同公司不同次运行的估值偏差监控 | 新增 `audit/consistency_tracker.py`，记录同 ticker 历次运行的目标价/方法/评级，偏差 > 20% 触发警告 |
| 审计日志不可篡改 | 无审计日志 | **审计日志锚定**：每次运行的审计日志写入后不可修改，支持回溯验证 | `audit/logger.py` 增加 `run_id`/`timestamp`/`content_hash`，日志文件写入后设为只读；未来可对接区块链锚定 |

**V-C 证据链产物**：`audit_trail_vc.json`：
```json
{
  "pairwise_deviations": [
    {"method_a": "EV/Revenue", "value_a": 45.0, "method_b": "PS", "value_b": 42.0, "deviation_pct": 6.9, "source": "乘数差异(EV含净债务调整)", "action": "等权平均"},
    {"method_a": "EV/Revenue", "value_a": 45.0, "method_b": "DCF", "value_b": 38.5, "deviation_pct": 15.5, "source": "DCF对WACC敏感(WACC=9.5% vs 隐含11%)", "action": "以EV/Rev为主,DCF作区间下限"}
  ],
  "rating_derivation": {
    "target_price": 45.0,
    "current_price": 46.52,
    "upside_pct": -3.3,
    "rating": "中性",
    "threshold_applied": "upside ∈ [-15%, +15%) → 中性",
    "rationale": "目标价45.0港元，当前价46.52港元，下行空间-3.3%，在中性区间内"
  },
  "reconciliation_summary": "EV/Revenue(45.0) + PS(42.0) 等权均值43.5，与DCF(38.5)偏差15.5%，以等权均值为基准上调至45.0(EV/Rev权重略高因含净债务调整更精确)",
  "consistency_check": {"vs_last_run": {"date": "2026-08-20", "target": 43.2, "deviation": 4.2, "status": "normal"}},
  "audit_log_hash": "sha256:a1b2c3d4e5f6...",
  "log_immutable": true
}
```

### 4.4 合规证据链总览

```
qual v10 单次运行 → 自动生成三份审计文件
                    ├── audit_trail_va.json   （V-A 勤勉：数据来源+假设依据+验证报告）
                    ├── audit_trail_vb.json   （V-B 适当：方法选择+敏感性+可比公司）
                    └── audit_trail_vc.json   （V-C 一致：Reconcile+评级推导+一致性+审计锚定）

报告输出 → 附加"合规声明"章节：
  "本报告估值数据来源：Wind MCP（详见 audit_trail_va.json）。
   估值方法选择依据：见 audit_trail_vb.json method_selection。
   多方法 Reconcile 记录：见 audit_trail_vc.json pairwise_deviations。
   本报告由 qual v10 自动化管线生成，未经人工分析师复核，
   所有估值结论仅供参考，不构成投资建议。"
```

---

## 五、回归股票池与测试方案（P0 整改第 2 项）

> 选择原则：覆盖 A 股/港股/美股、盈利/亏损、高增长/稳定/周期、大市值/中市值，确保 qual v10 在不同场景下的泛化能力可验证。

### 5.1 回归股票池（10 只）

| # | 场景 | 代表股票 | 代码 | 理由 | 验证重点 |
|---|------|---------|------|------|---------|
| 1 | 港股亏损（OCF 正） | 小鹏汽车 | 9868.HK | 已完成全流程验证，FY2024 净利=-11.39 亿，OCF=+82.59 亿 | EV/Rev 主方法 + DCF 辅助情景 + PS 交叉验证 |
| 2 | A 股盈利（稳定） | 协鑫能科 | 002015.SZ | 已完成全流程验证，FY2024 净利=正，营收稳定增长 | DCF + PE + PB 多方法 reconcile |
| 3 | 港股高增长（盈利） | 美团 | 3690.HK | 营收 YoY ≥ 20%，已扭亏为盈，大市值蓝筹 | DCF 主方法 + PE/PS 交叉；WACC 参数敏感性 |
| 4 | A 股周期 | 海螺水泥 | 600585.SH | 典型周期股，盈利随水泥周期剧烈波动 | PB 主方法 + 正常化 PE；周期位置判断 |
| 5 | 美股中概（亏损） | 蔚来 | NIO | 美股上市的中国亏损车企，与小鹏可比但 OCF 为负 | PS 主方法（OCF 负时最严格路径）；跨市场汇率处理 |
| 6 | 港股蓝筹（金融） | 汇丰控股 | 0005.HK | 港股金融蓝筹，PB+DDM 估值体系 | PB 主方法 + DDM 交叉；金融行业阈值 20% |
| 7 | A 股高增长（科技） | 宁德时代 | 300750.SZ | 新能源龙头，营收高增长+高利润率 | DCF 主方法 + PE/PS；高增长阈值 30% |
| 8 | 港股亏损（OCF 负） | 快手 | 1024.HK | 互联网亏损公司，OCF 曾为负转正的历史路径 | PS 主方法；OCF 状态判定逻辑 |
| 9 | A 股小市值 | 三人行 | 603999.SH | 中小市值广告公司，盈利稳定但规模较小 | 小市值参数校验（shares/price 量级）；估值乘数范围 |
| 10 | 港股地产（周期+高杠杆） | 华润置地 | 1109.HK | 地产周期+高杠杆，PB 适用但净资产质量需审视 | PB 主方法 + NAV 交叉；资产负债率 > 80% 的降级逻辑 |

### 5.2 验证矩阵：每只股票的预期行为

| 股票 | 预期主方法 | 预期偏差阈值 | 预期评级路径 | 关键 Fatal 防线 |
|------|-----------|------------|------------|----------------|
| 小鹏 9868 | EV/Revenue | ≤ 25% | 中性/增持（看上行空间） | DCF 负值不注入报告 |
| 协鑫能科 002015 | DCF | ≤ 30% | 增持 | WACC 参数来源可追溯 |
| 美团 3690 | DCF | ≤ 30% | 买入/增持 | 高增长假设敏感性矩阵 |
| 海螺水泥 600585 | PB | ≤ 30% | 中性（周期中部） | 正常化 PE 标注周期位置 |
| 蔚来 NIO | PS | ≤ 20% | 中性/减持 | OCF 负时 PS 唯一主方法 |
| 汇丰 0005 | PB | ≤ 20% | 中性 | 金融公司净资产质量分析 |
| 宁德时代 300750 | DCF | ≤ 30% | 买入 | 高增长 DCF vs PE 偏差 |
| 快手 1024 | PS | ≤ 20% | 增持（扭亏路径） | OCF 状态判定正确性 |
| 三人行 603999 | PE | ≤ 25% | 中性 | 小市值参数量级校验 |
| 华润置地 1109 | PB | ≤ 30% | 中性 | 高杠杆降级逻辑 |

### 5.3 回归测试执行规范

```python
# tests/test_regression_pool.py

REGRESSION_POOL = [
    # (ticker, market, expected_primary_method, deviation_threshold, fatal_checks)
    ("9868.HK",   "HK", "EV/Revenue", 0.25, ["no_negative_dcf_injection", "ocf_positive_dcf_auxiliary"]),
    ("002015.SZ", "A",  "DCF",        0.30, ["wacc_source_traceable", "rating_upside_consistent"]),
    ("3690.HK",   "HK", "DCF",        0.30, ["sensitivity_matrix_present", "high_growth_assumption_log"]),
    ("600585.SH", "A",  "PB",         0.30, ["normalized_pe_labeled", "cycle_position_noted"]),
    ("NIO",       "US", "PS",         0.20, ["ocf_negative_ps_primary", "cross_market_currency_ok"]),
    ("0005.HK",   "HK", "PB",         0.20, ["ddm_cross_validation", "net_asset_quality_analysis"]),
    ("300750.SZ", "A",  "DCF",        0.30, ["wacc_sensitivity_1pct", "revenue_growth_sensitivity"]),
    ("1024.HK",   "HK", "PS",         0.20, ["ocf_status_correct", "path_to_profitability_noted"]),
    ("603999.SH", "A",  "PE",         0.25, ["small_cap_parameter_sanity", "multiple_range_check"]),
    ("1109.HK",   "HK", "PB",         0.30, ["high_leverage_degradation", "nav_cross_validation"]),
]

@pytest.mark.parametrize("ticker,market,primary,threshold,fatal_checks", REGRESSION_POOL)
def test_regression_full_pipeline(ticker, market, primary, threshold, fatal_checks):
    """回归测试：验证完整 Gate 0-8 流水线。"""
    result = run_qual_full(ticker, mode="regression")
    # 1. Gate 8 零 fatal
    assert result.gate8_fatal_count == 0, f"{ticker} Gate8 fatal: {result.gate8_fatals}"
    # 2. 主方法匹配
    assert result.verdict.primary_method == primary, \
        f"{ticker} expected {primary}, got {result.verdict.primary_method}"
    # 3. 偏差不超阈值
    max_dev = max(result.verdict.pairwise_deviations, key=lambda d: d.deviation_pct)
    assert max_dev.deviation_pct <= threshold, \
        f"{ticker} deviation {max_dev.deviation_pct:.1%} > {threshold:.0%}"
    # 4. 逐项 fatal 检查
    for check in fatal_checks:
        assert getattr(result, check, False), f"{ticker} failed check: {check}"
```

### 5.4 CI/CD 接入方案

```yaml
# .github/workflows/qual-regression.yml
name: qual regression suite
on:
  push:
    paths: ['tools/finance/**', 'skills/finance/**']
  pull_request:
    paths: ['tools/finance/**', 'skills/finance/**']

jobs:
  regression:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run fatal regression tests
        run: |
          python -m pytest tests/test_regression.py -v --tb=short
        # 失败即阻断合并

      - name: Run multi-stock regression (MVP: 2 stocks)
        run: |
          python -m pytest tests/test_multi_stock.py -v -k "xpev or gxkn"
        # MVP 阶段只需小鹏+协鑫通过

      - name: Run full regression pool (Beta: 6 stocks)
        if: github.ref == 'refs/heads/main'
        run: |
          python -m pytest tests/test_regression_pool.py -v --timeout=600
        # main 分支需要 6 只股票通过
```

### 5.5 升级标准

| 阶段 | 要求 | 升级后能力 |
|------|------|-----------|
| **MVP** | 小鹏 + 协鑫 2 只通过 | 可交付港股亏损 + A 股盈利 |
| **Beta** | 前 6 只通过（+美团/海螺/蔚来/汇丰） | 覆盖 A 股/港股/美股 + 盈利/亏损/周期/金融 |
| **GA** | 全部 10 只通过 | 全场景泛化，可处理任意 A 股/港股/美股标的 |

---

## 六、实施路线图（P0 整改第 5 项，细化为可执行工作包）

| 天数 | 工作包 | 交付物 | 负责人 | 退出标准 | 回滚方案 |
|------|--------|--------|--------|---------|---------|
| D1 | WP-1.1 Wind 适配器强制化 | `data/wind_adapter.py` 全必填 fail-fast | qual 开发 | Wind→Financials 零静默降级（单测通过） | 回退到 v8 wind_adapter |
| D1 | WP-1.2 Canonical key 统一 | `canonical.py` 63 处别名映射 | qual 开发 | `grep -r` 旧 key 零残留 | git revert |
| D2 | WP-1.3 Financials 增溯源字段 | `contracts/financials.py` 增 `provenance` | qual 开发 | 每个字段有 source/fetch_time/fiscal_year | 纯新增，不影响现有逻辑 |
| D2 | WP-1.4 输入校验器扩展 | `valuation/validator.py` 12 项检查 | qual 开发 | 所有关键参数有范围校验 | 回退到 5 项检查 |
| D3 | WP-2.1 删 gate5 简化 DCF | `gate5.py` 统一消费 ValuationArbiter | qual 开发 | 全报告一套估值（集成测试） | 恢复 gate5 简化 DCF |
| D3 | WP-2.2 Arbiter 方向验证 | `valuation/arbiter.py` | qual 开发 | 数学公式无方向错误（单测） | git revert |
| D4 | WP-2.3 DCF 负值阻断 | `quality_enhancer.py` | qual 开发 | ch7 无负 DCF（集成测试） | git revert |
| D4 | WP-2.4 翻转阈值+敏感度 | `depth_enhancer.py` | qual 开发 | 无信息量时降级+敏感度矩阵输出 | git revert |
| D5 | WP-3.1 Gate5 估值一致性 | `gate5.py` 差异化阈值（§3） | CFA 分析 | 按公司类型阈值正确触发警告 | 回退到固定 40% |
| D5 | WP-3.2 Gate6 评级校验 | `gate6.py` | qual 开发 | 评级与上行空间不一致 → 警告 | git revert |
| D6 | WP-3.3 Gate7 跨章校验 | `gate7.py` | qual 开发 | 关键指标跨章不一致 → 警告 | git revert |
| D6 | WP-3.4 Gate8 降级确认 | `gate8.py` | qual 开发 | fatal 来自 Gate 5-7 warning | git revert |
| D7 | WP-4.1 Fatal 回归错题库 | `tests/test_regression.py` 8 个用例 | qual 开发 | 所有用例通过 | git revert |
| D7 | WP-4.2 多股票回归集 | `tests/test_multi_stock.py` 2 只 | qual 开发 | 小鹏+协鑫 Gate 0-7 通过 | git revert |
| D8 | WP-4.3 数据血缘审计 | `tests/test_data_trace.py` | qual 开发 | 所有关键数据可追溯 | git revert |
| D8 | WP-4.4 CI/CD 集成 | `.github/workflows/qual-regression.yml` | qual 开发 | fatal 失败阻断发布 | 移除 workflow |
| D9 | WP-5.1 CFA 合规证据链 | `audit/audit_trail_va.json` + `vb.json` + `vc.json` | qual 开发 | 三份审计文件自动生成且内容完整 | git revert |
| D9 | WP-5.2 回归股票池扩展 | 10 只股票回归集（§5.1） | 投资分析 | MVP 2 只 + Beta 6 只通过 | 回退到 2 只 |
| D10 | WP-E2E 端到端验证 | 全量回归报告 | HeavySkill | 10 只股票 Gate 8 零 fatal + 阈值验证通过 | 回退到上一个稳定版本 |

---

## 七、验收标准

| 标准 | 检查方法 | 升级条件 |
|------|---------|---------|
| Gate 8 零 fatal | 10 只股票连续 3 次 | 从"研究原型"升级为"可交付系统" |
| 数据可追溯 | 每个财务字段有 source/timestamp | 数据血缘审计通过 |
| 估值自洽 | 分类型差异化阈值（20-30%） | 估值仲裁器输出无矛盾 |
| 回归覆盖 | 8 个 fatal + 10 只股票回归 | 新增标的首过率 ≥95% |
| CFA 合规 | V-A/V-B/V-C 三份审计文件完整 | 人工复核通过 |
| CI/CD | fatal 失败阻断发布 | 主分支保护规则生效 |

---

## 八、执行级文档包清单（P0 整改第 6 项）

| 文档 | 说明 | 输出位置 | 交付阶段 | 状态 |
|------|------|---------|---------|------|
| **RCA（根因分析）** | 每个 P0 fatal 的完整根因链 | `docs/rca/` | 已完成（§一追溯矩阵） | ✅ |
| **数据字典** | Financials 契约 + Wind 字段映射 + Canonical key 对照表 | `docs/data-dictionary.md` | D2 (Phase 1) | 🔧 |
| **接口规范** | Wind MCP → wind_adapter → Financials → Arbiter → Verdict 全链路接口 | `docs/api-spec.md` | D4 (Phase 2) | 🔧 |
| **Runbook** | qual v10 部署/运行/故障排查手册 | `docs/runbook.md` | D8 (Phase 4) | 🔧 |
| **RACI 矩阵** | 每个 Phase 的负责人(R)/审批人(A)/咨询方(C)/知会方(I) | 见下方 | 本方案 | ✅ |
| **架构图** | 四层防线 + GateDAG + 数据流 | `docs/qual-architecture.md` | D1 (Phase 1) | 🔧 |
| **ADR（架构决策记录）** | 关键架构决策的理由与替代方案 | `docs/adr/` | 持续 | 🔧 |

### 8.1 RACI 矩阵

| 工作包 | R（负责执行） | A（审批验收） | C（咨询） | I（知会） |
|--------|-------------|-------------|---------|---------|
| Phase 1 数据契约强化（D1-D2） | qual 开发 | CFA 审查 + HeavySkill | Wind MCP 团队 | 投资研究 |
| Phase 2 估值引擎加固（D3-D4） | qual 开发 | CFA 审查 + HeavySkill | 量化研究 | 投资研究 |
| Phase 3 检查前移（D5-D6） | qual 开发 | Gate8 红队验证 | — | 投资研究 |
| Phase 4 回归测试+CI/CD（D7-D8） | qual 开发 | 全量回归通过（10/10） | DevOps | — |
| 证据链+回归扩展（D9） | qual 开发 + 投资分析 | CFA 审查 | 法律合规 | — |
| 端到端验证（D10） | HeavySkill | 投资研究 | — | 全团队 |
| 阈值细化（§三） | CFA 分析 | HeavySkill K8 复核 | — | qual 开发 |
| 合规证据链设计（§四） | CFA 分析 | HeavySkill K8 复核 | 法律合规 | qual 开发 |
| 回归股票池选择（§五） | 投资分析 | HeavySkill K8 复核 | — | qual 开发 |

---

## 九、与 dayu-agent 的差距收敛

| 维度 | dayu | qual v10 | 优化后 | 差距 |
|------|------|----------|--------|------|
| 数据控制 | 仓储协议 | PGNB regex | Financials 契约 | **基本对齐** |
| 估值仲裁 | 多方法 reconcile | ValuationArbiter | 唯一出口+差异化阈值 | **基本对齐** |
| Gate 依赖 | 无 Gate | GateDAG | HARD/SOFT 依赖 | **基本对齐** |
| 检查前移 | audit/confirm/repair | 后置检查 | Gate 5-7 前移 | **需实施** |
| 回归测试 | 完整测试集 | 4 个 fatal | 8+10 回归 + CI/CD | **需实施** |
| CFA 合规 | 隐式 | 无证据链 | V-A/V-B/V-C 三份审计文件 | **需实施** |
| 交付可靠性 | 生产级 | 研究原型 | Gate 8 零 fatal | **需验证** |

**结论**：Phase 1-4 + 附录实施后，qual v10 在架构层面将基本对齐 dayu-agent，在合规层面建立 CFA 标准的可审计证据链，在交付层面通过 10 只股票 Gate 8 零 fatal 验证。
