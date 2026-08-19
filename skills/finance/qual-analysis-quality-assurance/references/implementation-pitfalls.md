# 实施陷阱和解决方案

本文档记录qual-analysis-quality-assurance实施过程中发现的关键陷阱，避免未来重复踩坑。

## 1. DCFInputs接口字段名不匹配

**问题**: 现有`DCFCalculator`的`DCFInputs`字段名与直觉不同。

**错误用法**:
```python
# ❌ 错误 - 这些字段不存在
inputs = DCFInputs(
    wacc=0.10,
    terminal_growth=0.025,
    shares=10.0,
)
```

**正确用法**:
```python
# ✅ 正确 - 使用实际字段名
inputs = DCFInputs(
    fcf_projections=[100],
    risk_free_rate=0.023,
    equity_risk_premium=0.065,
    beta=1.0,
    cost_of_debt=0.05,
    tax_rate=0.25,
    debt_ratio=0.0,
    terminal_growth_rate=0.025,  # 不是 terminal_growth
    shares_outstanding=10.0,     # 不是 shares
)
```

**完整字段列表**:
- `fcf_projections: List[float]` - FCF预测列表
- `projection_years: int = 5`
- `risk_free_rate: float = 0.03` - 无风险利率
- `equity_risk_premium: float = 0.06` - 股权风险溢价
- `beta: float = 1.0`
- `cost_of_debt: float = 0.05`
- `tax_rate: float = 0.25`
- `debt_ratio: float = 0.0`
- `terminal_growth_rate: float = 0.02` - 永续增长率（不是terminal_growth）
- `terminal_method: str = "gordon"` - gordon | exit_multiple
- `terminal_ebitda_multiple: float = 10.0`
- `terminal_ebitda: float = 0.0`
- `shares_outstanding: float = 1.0` - 总股本（不是shares）
- `current_price: float = 0.0`
- `currency: str = "CNY"`

**DCFResult字段**:
- `equity_value` - 权益价值
- `per_share_value` - 每股价值
- `current_price` - 当前价格
- `upside` - 上行空间
- `wacc` - WACC
- `cost_of_equity` - Ke
- `terminal_value` - 终值
- `terminal_value_pv` - 终值现值
- `fcf_pv` - FCF现值
- `sensitivity` - 敏感性分析结果
- `yearly_data` - 年度数据
- `warnings` - 警告列表

**教训**: 实现新模块前，先用`inspect.signature()`或`__dataclass_fields__`检查现有接口。

## 2. 内容长度验证阈值

**问题**: `QualityPipeline`的结构化预检有200字符最小长度要求。

**症状**: 测试中构造的内容如果<200字符，会被判定为"内容过短，疑似Placeholder"并blocked。

**解决方案**:
```python
# ❌ 会失败 - 内容只有41字符
content = "结论要点: 顺丰控股是物流公司\n详细分析: ...\n证据与出处: ..."

# ✅ 通过 - 内容>200字符
content = "结论要点: 顺丰控股是物流公司\n详细分析: " + "详细内容" * 50 + "\n证据与出处: 年报数据"
```

**调试技巧**: 不确定内容长度时，先用`len(content)`检查。

## 3. unittest vs pytest

**问题**: WSL环境可能没有安装pytest。

**症状**: `ModuleNotFoundError: No module named 'pytest'`

**解决方案**: 使用标准库`unittest`替代pytest。

```python
# ❌ 需要pytest
import pytest
class TestFeature:
    def test_default(self):
        assert True

# ✅ 使用unittest
import unittest
class TestFeature(unittest.TestCase):
    def test_default(self):
        self.assertTrue(True)

if __name__ == "__main__":
    unittest.main(verbosity=2)
```

**运行命令**: `python3 tests/test_xxx.py` (不需要pytest)

## 4. 权威冲突解决器参数名

**问题**: `AuthorityResolver.resolve()`参数名是`l2_result`和`l3_result`，不是`l2`和`l3`。

```python
# ❌ 错误
result = resolver.resolve(l1, l2=l2, l3=l3)

# ✅ 正确
result = resolver.resolve(l1, l2_result=l2, l3_result=l3)
```

## 5. 规模溢价上限配置

**问题**: 测试中需要启用`governance_premium_enabled=True`才能测试治理溢价。

```python
# ❌ 会失败 - governance_premium_enabled默认为False
config = CAPMConfig(total_alpha_cap=0.06)
calc = CAPMCalculator(config=config)
alpha_result = calc.calculate_alpha(
    size_premium=0.04,
    liquidity_premium=0.03,
    governance_premium=0.02  # 会被忽略
)
# alpha_result.total = 0.07 (不是0.09)

# ✅ 正确 - 显式启用
config = CAPMConfig(
    total_alpha_cap=0.06,
    size_premium_enabled=True,
    size_premium_cap=0.05,  # 放宽单项上限
    liquidity_premium_enabled=True,
    liquidity_premium_value=0.03,
    governance_premium_enabled=True,  # 启用
    governance_premium_value=0.02
)
```

## 6. Gate-Driven实施模式

**有效模式**:
1. 先列出完整计划（Gate 0-7）
2. 每个Gate有明确交付物和通过标准
3. 实施后立即运行测试验证
4. 使用`[CHECKPOINT]`跟踪进度
5. 测试失败时快速修复，不绕过

**测试驱动**:
- 每个模块先写测试（定义接口）
- 实现模块使测试通过
- 所有测试通过后才进入下一个Gate

**累计测试跟踪**:
```
Gate 0: 26个测试
Gate 1: +30 = 56
Gate 2: +27 = 83
Gate 3: +25 = 108
Gate 4: +23 = 131
Gate 5: +25 = 156
Gate 6: +29 = 185
```

## 7. Mock DCFResult时字段完整性

**问题**: DCFResult是dataclass，所有非Optional字段都是必需的。Mock时不能省略。

```python
# ❌ 错误 - 缺少必需字段
from finance.quality.dcf import DCFResult
mock = DCFResult(equity_value=900, per_share_value=90.0, wacc=0.10, g=0.025)
# TypeError: missing required positional arguments

# ✅ 正确 - 提供所有必需字段
mock = DCFResult(
    equity_value=900,
    per_share_value=90.0,
    current_price=40.0,
    upside=1.25,
    wacc=0.10,
    cost_of_equity=0.12,
    terminal_value=1000,
    terminal_value_pv=600,
    fcf_pv=400,
)
```

**教训**: Mock复杂dataclass时，先用`inspect.signature()`检查所有必需参数。

## 8. CAPMConfig子项启用开关

**问题**: `governance_premium_enabled`默认为False，即使传入`governance_premium`参数也会被忽略。

```python
# ❌ 会失败 - governance_premium被忽略
config = CAPMConfig(total_alpha_cap=0.06)
alpha = calc.calculate_alpha(governance_premium=0.02)
# alpha.governance_premium = 0 (不是0.02)

# ✅ 正确 - 显式启用
config = CAPMConfig(
    governance_premium_enabled=True,
    governance_premium_value=0.02
)
```

## 9. E2E测试设计原则

**有效模式**: 顺丰控股完整分析E2E测试串联所有模块：
1. CAPM计算WACC → 2. FCF计算 → 3. 终值计算 → 4. 敏感性分析 → 5. DCF完整计算 → 6. 结论综合 → 7. 审计验证

**关键检查**:
- 每步输出作为下一步输入
- 最终检查无FATAL级别问题
- 不检查具体数值（会变），只检查结构正确性

## 10. Mock策略三层定义

| 层级 | 用途 | 粒度 | 示例 |
|------|------|------|------|
| L1精确 | 单元测试 | 固定返回值 | WindMock返回固定财务数据 |
| L2行为 | 集成测试 | 调用序列 | LLMMock按序返回不同响应 |
| L3异常 | 降级测试 | 注入失败 | ErrorMock抛出TimeoutError |

**测试Mock时**: 测试Mock本身的行为，不测试Mock与复杂模块的集成（会因接口不匹配失败）。
