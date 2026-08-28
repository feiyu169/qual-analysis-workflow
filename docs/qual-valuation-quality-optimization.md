# 估值模块输出质量优化——CFA 专家级方案

> 日期：2026-08-27
> 基于：小鹏 9868.HK（v10b）+ 协鑫能科 002015.SZ（v10c5）两轮全流程实测
> 标准：CFA Institute Standards of Practice (V-A/V-B/V-C) + 买方研究报告质量底线

---

## 一、当前估值模块的核心缺陷

### 1.1 实测暴露的问题

| 问题 | 小鹏 | 协鑫能科 | 根因 |
|------|------|---------|------|
| DCF 目标价与正文结论矛盾 | DCF=-43.53 港元 vs 中性评级 | DCF=2.96 元 vs 增持评级 | 亏损公司 DCF 负值未正确处理 |
| 翻转阈值方向错误 | 营收 767→1534（应降非升） | 净现比 4.04 vs 4.6 | 数学公式错误 |
| 数据引用不一致 | ch5 净利润=94.0（幻觉） | ch0 净现比 vs ch3-7 不一致 | LLM 跨章引用未统一 |
| 红队致命：估值矛盾 | DCF -43.53 vs 中性 | DCF 2.96 vs 增持 | 估值仲裁未生效 |

### 1.2 CFA 标准视角的缺陷分类

| CFA 标准 | 缺陷 | 严重度 |
|----------|------|--------|
| **V-A 合理基础** | 翻转阈值用硬编码参数（1427.76） | 已修复 |
| **V-A 合理基础** | DCF 对亏损公司不适用但未标注 | 部分修复 |
| **V-B 适当方法** | 亏损公司应以 EV/Revenue 为主，非 DCF | 已实现 |
| **V-B 适当方法** | 缺少敏感性分析和情景加权 | 未实现 |
| **V-C 一致性** | 多套估值结论未 reconciled | ValuationArbiter 已实现 |
| **V-C 一致性** | 目标价与评级逻辑未显式关联 | 未实现 |

---

## 二、优化方案：三层架构

### 第一层：估值输入标准化（CFA V-A）

**原则**：所有估值输入必须有明确来源、可追溯、可验证。

```
Wind MCP → Financials 契约 → 输入校验器 → 估值引擎
         ↓                    ↓              ↓
    source/date/currency   范围检查       可追溯
```

**具体措施**：

1. **Financials 契约强制化**（已实现）：所有估值输入通过 `Financials` frozen dataclass 传递
2. **输入校验器扩展**（已实现）：WACC/g/PS/PB/EV-Rev 范围检查
3. **缺失数据显式标注**（待实现）：当某指标缺失时，在报告中标注"⚠️ 数据不足，估值基于有限信息"

### 第二层：估值方法矩阵（CFA V-B）

**原则**：估值方法必须适当——亏损公司不用 DCF，高增长公司不用 PE。

```
公司特征 → 方法选择器 → 主方法 + 交叉验证 + 辅助
   ↓           ↓              ↓
亏损？      EV/Revenue      PS 交叉验证
盈利？      DCF + PE        PB 辅助
高增长？    EV/Revenue      DCF 辅助
```

**具体措施**：

1. **方法选择矩阵**（已实现）：`select_valuation_methods()` 根据公司特征自动选择
2. **DCF 适用性判断**（已实现）：亏损公司 + OCF 为负 → DCF 不适用
3. **目标价区间推导**（待实现）：基于主方法 ±20%（悲观/乐观）

### 第三层：估值仲裁与输出（CFA V-C）

**原则**：多套方法结论不一致时，必须明确仲裁规则并说明理由。

```
主方法估值 + 交叉验证估值 → 仲裁器 → 最终目标价 + 区间 + 说明
   ↓              ↓           ↓
DCF/PS/EV-Rev   PE/PB      分档偏差处理
```

**具体措施**：

1. **ValuationArbiter**（已实现）：分档偏差处理（<20% 等权 / 20-40% 披露 / >40% 主方法）
2. **目标价区间**（待实现）：悲观/基准/乐观 + 对应假设
3. **评级-目标价映射**（待实现）：显式关联目标价与投资评级

---

## 三、具体优化措施

### 3.1 目标价区间推导（P0）

**问题**：当前只输出单一目标价，无区间。

**方案**：基于估值乘数/假设的变化推导区间。

```python
# 亏损公司（EV/Revenue 为主）
base_ev_rev = enterprise_value / revenue
bear_ev_rev = base_ev_rev * 0.80  # 20% 下降
bull_ev_rev = base_ev_rev * 1.20  # 20% 上升

target_base = base_ev_rev * revenue / shares
target_bear = bear_ev_rev * revenue / shares
target_bull = bull_ev_rev * revenue / shares

# 盈利公司（DCF 为主）
target_base = dcf_value
target_bear = dcf_value * 0.80
target_bull = dcf_value * 1.20
```

**CFA 依据**：CFA V-C 要求"当使用多种估值方法时，必须 reconcile 结果并给出区间"。

### 3.2 评级-目标价映射（P0）

**问题**：当前评级（中性/增持/减持）与目标价无显式关联。

**方案**：定义评级与上行/下行空间的映射规则。

```python
RATING_THRESHOLDS = {
    "买入": {"upside_min": 0.30, "description": "上行空间 ≥30%"},
    "增持": {"upside_min": 0.15, "description": "上行空间 15-30%"},
    "中性": {"upside_min": -0.15, "upside_max": 0.15, "description": "上行/下行空间 ±15%"},
    "减持": {"downside_min": 0.15, "description": "下行空间 15-30%"},
    "卖出": {"downside_min": 0.30, "description": "下行空间 ≥30%"},
}

def derive_rating(target_price: float, current_price: float) -> str:
    """根据目标价与当前价的偏离推导投资评级。"""
    upside = (target_price - current_price) / current_price
    if upside >= 0.30:
        return "买入"
    elif upside >= 0.15:
        return "增持"
    elif upside >= -0.15:
        return "中性"
    elif upside >= -0.30:
        return "减持"
    else:
        return "卖出"
```

**CFA 依据**：CFA V-B 要求"估值结论必须与投资建议一致"。

### 3.3 敏感性分析（P1）

**问题**：当前无敏感性分析，投资者无法判断关键假设变化对估值的影响。

**方案**：对 WACC、永续增长率、营收增速做 ±1% 敏感性矩阵。

```python
def sensitivity_matrix(base_value, wacc, growth, revenue_growth):
    """敏感性分析矩阵。"""
    wacc_range = [wacc - 0.01, wacc, wacc + 0.01]
    growth_range = [growth - 0.01, growth, growth + 0.01]
    
    matrix = {}
    for w in wacc_range:
        for g in growth_range:
            value = compute_dcf_value(w, g, revenue_growth)
            matrix[(w, g)] = value
    
    return matrix
```

**CFA 依据**：CFA V-B 要求"估值应包含关键假设的敏感性分析"。

### 3.4 可比公司分析标准化（P1）

**问题**：当前可比公司分析为静态快照，无动态更新。

**方案**：定义可比公司选择标准 + 估值乘数中位数 + 溢价/折价分析。

```python
COMPARABLE_SELECTION_CRITERIA = {
    "行业": ["新能源汽车", "智能驾驶", "电动汽车"],
    "市值范围": [100, 10000],  # 亿元
    "上市时间": "≥2年",
    "盈利能力": "不要求（亏损公司可比）",
}

def comparable_analysis(target_company, comparables):
    """可比公司分析。"""
    pe_multiples = [c.pe for c in comparables if c.pe and c.pe > 0]
    ps_multiples = [c.ps for c in comparables if c.ps and c.ps > 0]
    
    median_pe = median(pe_multiples) if pe_multiples else None
    median_ps = median(ps_multiples) if ps_multiples else None
    
    return {
        "median_pe": median_pe,
        "median_ps": median_ps,
        "target_pe": target_company.market_cap / target_company.net_profit if target_company.net_profit > 0 else None,
        "target_ps": target_company.market_cap / target_company.revenue,
        "premium_discount": (target_ps - median_ps) / median_ps if median_ps else None,
    }
```

**CFA 依据**：CFA V-B 要求"可比公司选择必须有明确标准"。

### 3.5 估值输出标准化（P0）

**问题**：当前估值输出格式不统一，红队审查难以判断。

**方案**：定义标准估值输出格式。

```python
@dataclass(frozen=True)
class ValuationOutput:
    """估值标准输出（CFA V-C 一致性要求）。"""
    # 主方法
    primary_method: str           # "EV/Revenue" | "DCF" | "PE"
    primary_value: float          # 主方法目标价
    
    # 交叉验证
    cross_validation: dict[str, float]  # {"PS": 42.0, "PB": 38.0}
    
    # 目标价区间
    target_bear: float            # 悲观目标价
    target_base: float            # 基准目标价
    target_bull: float            # 乐观目标价
    target_assumptions: str       # 区间假设说明
    
    # 评级
    rating: str                   # "买入" | "增持" | "中性" | "减持" | "卖出"
    rating_rationale: str         # 评级理由
    
    # 仲裁
    reconciliation: str           # 多方法仲裁说明
    excluded_methods: list[str]   # 不适用方法及理由
    
    # 元数据
    currency: str                 # "CNY" | "HKD"
    data_as_of: str               # 数据截止日
    analyst: str                  # 分析师（默认 "qual v10"）
```

---

## 四、实施优先级

| 优先级 | 措施 | 工作量 | 影响 |
|--------|------|--------|------|
| **P0** | 目标价区间推导 | 1 天 | 消除"单一目标价"问题 |
| **P0** | 评级-目标价映射 | 0.5 天 | 消除"评级与目标价矛盾" |
| **P0** | 估值输出标准化 | 1 天 | 统一格式，便于红队审查 |
| **P1** | 敏感性分析 | 1 天 | 提供假设变化影响 |
| **P1** | 可比公司标准化 | 1 天 | 提供相对估值基准 |
| **P2** | 估值审计日志 | 0.5 天 | 可追溯性 |

**总计：5 天**

---

## 五、验收标准

| 标准 | 检查方法 |
|------|---------|
| 目标价区间包含悲观/基准/乐观 | ch7 估值分析输出三档目标价 |
| 评级与目标价一致 | 评级 = f(上行空间)，偏差 ≤5% |
| DCF 负值不输出到报告 | ch7 无负 DCF 值 |
| 多方法仲裁有说明 | ch7 含"主方法：EV/Revenue，交叉验证：PS" |
| 红队无"估值矛盾"致命 | Gate8 passed |

---

## 六、与 dayu-agent 的差距分析

| 维度 | dayu-agent | qual v10 | 差距 | 优化后 |
|------|-----------|----------|------|--------|
| 估值方法矩阵 | 6 种方法自动选择 | 5 种方法（EV/Rev/DCF/PE/PS/PB） | 小 | 对齐 |
| 目标价区间 | 悲观/基准/乐观 | 单一目标价 | **大** | P0 修复 |
| 敏感性分析 | WACC/g/增速 ±1% | 无 | **大** | P1 修复 |
| 可比公司 | 动态选择 + 中位数 | 静态快照 | 中 | P1 修复 |
| 评级映射 | 显式规则 | 隐式（LLM 判断） | **大** | P0 修复 |
| 仲裁逻辑 | 多方法 reconcile | ValuationArbiter | 小 | 对齐 |
| 输出格式 | 标准化 JSON | 非结构化文本 | **大** | P0 修复 |

**结论**：qual v10 在估值方法选择和仲裁逻辑上已接近 dayu 水平，但在目标价区间、敏感性分析、评级映射、输出格式上差距较大。P0 修复（3.5 天）可消除核心差距。
