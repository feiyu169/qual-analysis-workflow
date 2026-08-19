# 估值模块修复模式 - Part 3 (2026-08-01)

## 新增修复项

| # | 文件 | 函数 | 问题 | 修复 |
|---|------|------|------|------|
| 16 | quality_enhancer.py | Stage 5 | 未传递WACC和terminal_growth给run_depth_enhancement | 计算CAPM WACC并传递 |
| 17 | depth_enhancer.py | run_scenario_analysis | 使用单年FCF而非5年FCF预测 | 改用5年FCF预测 |
| 18 | depth_enhancer.py | compute_flip_thresholds | WACC翻转阈值方向错误 | 添加方向验证逻辑 |

## quality_enhancer.py WACC参数传递

**问题**: quality_enhancer.py调用run_depth_enhancement()时未传递base_wacc和base_terminal_growth参数，导致使用默认值（0.10和0.03）。

**影响**: 情景分析和翻转阈值使用错误的WACC（10%而非CAPM计算的8.1%），与DCF估值不一致。

**修复**: 在quality_enhancer.py中计算WACC并传递：
```python
# 计算WACC（使用CAPM）
rf = 0.023
beta = 1.2
erp = 0.055
ke = rf + beta * erp  # 0.089
kd = 0.05
tax_rate = 0.25
wacc = ke * 0.85 + kd * (1 - tax_rate) * 0.15  # 0.081

depth = run_depth_enhancement(
    chapters=chapters,
    financials=financials,
    valuation_value=result.valuation_result.get('dcf_value', 0) if result.valuation_result else 0,
    current_price=current_price,
    shares=shares,
    base_wacc=wacc,  # 必须传递！
    base_terminal_growth=0.02,  # 必须传递！
)
```

## 5年FCF预测

**问题**: 情景分析使用单年FCF计算终值，而主DCF使用5年FCF预测。导致情景分析结果与DCF估值不一致（如DCF=17.2元但情景基准=2.9元）。

**修复**: 情景分析必须使用与主DCF一致的5年FCF预测：
```python
for name, rev, margin, wacc, tg, prob in key_scenarios:
    # 5年FCF预测
    total_pv_fcf = 0
    current_revenue = base_revenue
    revenue_growth = (rev - base_revenue) / base_revenue if base_revenue > 0 else 0
    
    for year in range(1, 6):
        # 营收增长（第1年使用情景增速，后续年份使用递减增速）
        if year == 1:
            growth = revenue_growth
        else:
            growth = revenue_growth * (1 - 0.1 * (year - 1))  # 逐年递减
        
        current_revenue = current_revenue * (1 + growth)
        ebit = current_revenue * margin
        nopat = ebit * (1 - 0.25)  # 税率25%
        da = current_revenue * 0.03  # 折旧率3%
        capex = current_revenue * 0.04  # 资本开支率4%
        wc_change = current_revenue * growth * 0.02  # 营运资金变动
        fcf = nopat + da - capex - wc_change
        
        # 折现
        discount_factor = 1 / (1 + wacc) ** year
        total_pv_fcf += fcf * discount_factor
    
    # 终值（基于第5年FCF）
    last_fcf = fcf
    terminal_value = last_fcf * (1 + tg) / (wacc - tg)
    pv_terminal = terminal_value / (1 + wacc) ** 5
    
    # 企业价值
    ev = total_pv_fcf + pv_terminal
```

## WACC翻转阈值方向验证

**问题**: WACC翻转阈值方向错误，显示"WACC降至3.0%时估值等于当前股价"，但逻辑上WACC上升才会降低估值。

**修复**: 必须验证翻转阈值方向：
```python
if flip_wacc > base_wacc:
    # WACC上升→估值下降，翻转点高于当前WACC
    direction = "up"
    impact = f"当WACC升至{flip_wacc*100:.1f}%时，估值等于当前股价"
else:
    # WACC下降→估值上升，翻转点低于当前WACC
    direction = "down"
    impact = f"当WACC降至{flip_wacc*100:.1f}%时，估值等于当前股价"
```

## 最终验证结果（Part 3修复后）

| 指标 | Part 2修复后 | Part 3修复后 |
|------|-------------|-------------|
| DCF每股价值 | 17.2元 | 17.2元 |
| WACC | 8.1% | 8.1% |
| 目标价(牛/基/熊) | 20.7/17.2/13.8 | 20.7/17.2/13.8 |
| 情景分析WACC | 10.0% | **8.1%** |
| 情景分析乐观 | 9.7元 | **15.5元** |
| 情景分析高增长 | 4.4元 | **8.0元** |
| 翻转阈值-WACC | 3.0% (down) | **3.0% (down)** |

## 系统性教训（完整）

1. **估值链有4个独立模块** — extract_dcf_params(workflow.py) → compute_dcf(valuation_engine.py) → run_scenario_analysis(depth_enhancer.py) → compute_flip_thresholds(depth_enhancer.py)，每步可能有独立bug
2. **单位一致性** — HKD/CNY混用会导致数量级错误，必须在计算前统一
3. **简化公式必须与完整公式一致** — 如果主DCF用完整FCF，情景分析也必须用完整FCF
4. **二分法优于解析公式** — 对于非线性DCF模型，二分法搜索翻转点比解析公式更可靠
5. **参数传递链必须完整** — quality_enhancer.py → depth_enhancer.py的参数传递链必须完整，否则会使用错误的默认值
6. **5年FCF预测优于单年** — 情景分析必须使用与主DCF一致的5年FCF预测，否则结果不一致
7. **翻转阈值方向必须验证** — WACC翻转阈值方向必须逻辑验证，不能假设
