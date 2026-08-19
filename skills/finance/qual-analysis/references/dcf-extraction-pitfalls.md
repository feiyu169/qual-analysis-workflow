# DCF 参数提取陷阱 (2026-06-30 实测发现)

## Bug 1: ctx.wind_data 不存在 (P0)

**错误代码**:
```python
if ctx.wind_data and isinstance(ctx.wind_data, dict):
    dcf_params = extract_dcf_params(ctx.wind_data)
```

**问题**: DataContext 的属性名是 `wind` (WindData 对象)，不是 `wind_data`。
访问 `ctx.wind_data` 触发 `AttributeError`，被 `except Exception` 静默捕获。

**正确代码**:
```python
if ctx.wind is not None:
    wind_dict = {}
    if ctx.wind.income:
        wind_dict["income"] = ctx.wind.income
    if ctx.wind.balance:
        wind_dict["balance"] = ctx.wind.balance
    if ctx.wind.cashflow:
        wind_dict["cashflow"] = ctx.wind.cashflow
    if len(wind_dict) == 3:
        dcf_params = extract_dcf_params(wind_dict)
```

**教训**: except Exception 会吞掉 AttributeError，导致测试"通过"但功能失效。

## Bug 2: WIND_FIELD_MAPPING 方向错误 (P0)

**错误方向**: `"年营业总收入": "营业收入"` (Wind名→内部名)
**正确方向**: `"营业收入": "年营业总收入"` (内部名→Wind名)

safe_get(data, "营业收入") 的查找顺序:
1. data["营业收入"] → 不存在
2. data[WIND_FIELD_MAPPING["营业收入"]] → data["年营业总收入"] → 找到

## Bug 3: extract_dcf_params 字段名不匹配 (P1)

代码期望 vs Wind 实际:
- "经营活动现金流量净额" → "过去三年每年经营活动产生的现金流量净额"
- "资本性支出" → 不存在(用投资活动现金流近似)
- "有息负债" → 不存在(用总负债近似)
- "货币资金" → 不存在
- "总股本" → 不存在

## Bug 4: 3年数组未取最新值 (P1)

Wind 返回3年数据数组如 [2023值, 2024值, 2025值]。
必须取最后一个元素(最新年份)。

```python
def latest_value(data, key, default=0):
    value = data.get(key)
    if isinstance(value, list) and value:
        for v in reversed(value):
            if v is not None:
                return float(v)
    return default
```

## Bug 5: comps_analysis 直接调用 MCP (P0)

**错误**: `mcp_wind_mcp_wind_industry_data(...)` 在 Python 层调用
**正确**: MCP 工具只能通过 Agent 层调用。comps_analysis 应为纯计算函数，接收预收集数据。

## 总股本参数化方案

Wind 不提供总股本。解决方案:
```python
def extract_dcf_params(wind_data: dict, shares: float = None) -> dict:
    if shares is not None and shares > 0:
        pass  # 使用 Agent 层传入的值
    else:
        shares = 1
        warnings.append("总股本未提供，使用默认值 1")
```

Agent 层从财报原文、用户输入等途径获取 shares 并传入。
