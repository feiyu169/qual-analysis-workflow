# 估值模块修复模式 - 续 (2026-08-01 Part 2)

## 新增修复项

| # | 文件 | 函数 | 问题 | 修复 |
|---|------|------|------|------|
| 11 | run_yuewen_fix.py | WIND_DATA | 缺少"现金及等价物"字段 | 手动添加到balance字典 |
| 12 | valuation_engine.py | compute_dcf | 净负债用"年流动资产合计"而非"现金及等价物" | 优先用现金及等价物，fallback到流动资产 |
| 13 | depth_enhancer.py | run_scenario_analysis | FCF用简化公式(nopat*0.9)与主DCF不一致 | 改用完整公式: nopat+da-capex-wc_change |
| 14 | depth_enhancer.py | compute_flip_thresholds | current_price(HKD)与revenue(CNY)单位不匹配 | 用二分法直接搜索，避免单位换算 |
| 15 | depth_enhancer.py | compute_flip_thresholds | WACC翻转点用wacc*1.3(无逻辑) | 二分法搜索使EV=target的WACC |

## 情景分析FCF一致性

**问题**: `depth_enhancer.py`的`run_scenario_analysis()`使用简化FCF:
```python
fcf = nopat * 0.9  # 简化：假设DA-Capex-WC=10%
```

而主DCF(`valuation_engine.py`)使用完整公式:
```python
nopat = ebit * (1 - tax_rate)
da = revenue * 0.03
capex = revenue * 0.04
wc_change = revenue * growth * 0.02
fcf = nopat + da - capex - wc_change
```

**修复**: 情景分析必须使用与主DCF一致的FCF公式，否则每股价值不一致。

## 翻转阈值二分法

**原问题**: 旧代码用简单公式计算翻转点:
```python
target_fcf = current_price * shares * 0.05  # current_price是HKD!
required_revenue = target_fcf / (base_ebit_margin * 0.75 * 0.9)
```

**根因**: `current_price`单位是HKD(20.22)，`revenue`单位是CNY(80.07亿)，直接乘除导致荒谬结果(607.7亿)。

**修复**: 使用二分法搜索，固定其他变量找到使equity_value = target_equity_value的变量值:
```python
# 营收翻转点
low_rev, high_rev = base_revenue * 0.3, base_revenue * 3.0
for _ in range(50):
    mid_rev = (low_rev + high_rev) / 2
    # 用mid_rev计算FCF和EV
    if equity > target_equity_value:
        high_rev = mid_rev
    else:
        low_rev = mid_rev
flip_rev = (low_rev + high_rev) / 2
```

同理修复EBIT利润率和WACC翻转点。

## 现金及等价物字段

**问题**: Wind数据中没有"现金及等价物"字段，但估值模块需要用它计算净负债。

**解决方案**: 在`run_yuewen_fix.py`的WIND_DATA中手动添加:
```python
"balance": {
    "现金及等价物": [168.37, 168.37, 168.37],  # 从年报获取
    # ... 其他字段
}
```

**valuation_engine.py修复**: 优先使用"现金及等价物"，fallback到"年流动资产合计":
```python
cash_list = balance.get('现金及等价物', [])
if not cash_list:
    cash_list = balance.get('年流动资产合计', [])
```

## 修复后验证结果

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| DCF每股价值 | -7.3元 | 17.2元 |
| WACC | 10.0% | 8.1% |
| 目标价(牛/基/熊) | -25/-20.8/-16.7 | 20.7/17.2/13.8 |
| 可比公司 | 抖音/Meta/拼多多 | 掌阅/中文在线/迪士尼 |
| 情景分析基准 | 3.5元 | 2.9元 |
| 翻转阈值-营收 | 607.7 | 240.2 |
| 翻转阈值-EBIT | 38.9% | 30.0% |

## 仍存在的已知问题

1. **情景分析与DCF估值不一致** — 情景分析使用depth_enhancer的简化模型，DCF使用valuation_engine的完整模型，两者参数不同导致结果差异
2. **下行空间计算** — "下行空间58.6%"的计算公式可能有误（当前股价高于目标价时应显示"上行空间"）
3. **洞察评分100/100虚高** — 报告存在大量问题但洞察评分仍为满分，评分逻辑需要调整

## 系统性教训

1. **估值链有4个独立模块** — extract_dcf_params(workflow.py) → compute_dcf(valuation_engine.py) → run_scenario_analysis(depth_enhancer.py) → compute_flip_thresholds(depth_enhancer.py)，每步可能有独立bug
2. **单位一致性** — HKD/CNY混用会导致数量级错误，必须在计算前统一
3. **简化公式必须与完整公式一致** — 如果主DCF用完整FCF，情景分析也必须用完整FCF
4. **二分法优于解析公式** — 对于非线性DCF模型，二分法搜索翻转点比解析公式更可靠
