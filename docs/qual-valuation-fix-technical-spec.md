# Qual 估值模块修复——逐文件技术规格

> 版本：v1.0 | 日期：2026-08-24
> 基线：qual v9 commit d8cf8d3
> 目标：消除估值逻辑三重互斥，达到 CFA 标准 V-A/V-B/V-C

---

## 修改总览

| 文件 | 修改类型 | 工作量 | 优先级 |
|------|----------|--------|--------|
| `depth_enhancer.py` | 重构：删除硬编码 fallback + 负利润率处理 | 2h | P0 |
| `quality_enhancer.py` | 重构：估值注入改为统一引擎输出 | 1h | P0 |
| `valuation_engine.py` | 新增：估值仲裁逻辑 | 3h | P1 |
| `valuation_arbiter.py` | 新建：估值仲裁器 | 3h | P1 |
| `valuation_validator.py` | 新建：估值输入校验器 | 2h | P2 |
| `gate5.py` | 重构：删除简化 DCF，改用统一引擎 | 1h | P1 |

**总计：12 小时（1.5 个工作日）**

---

## 文件 1：`depth_enhancer.py`

### 修改 1a：删除硬编码 fallback（L505-523）

**当前代码**：
```python
# L505-523
income = financials.get('income', {})
rev_list = income.get('年营业总收入', [])
op_list = income.get('年营业利润', [])
np_list = income.get('年净利润', [])

base_revenue = rev_list[-1] if rev_list else 1427.76  # ← 硬编码美团数据

if op_list and base_revenue:
    base_ebit_margin = op_list[-1] / base_revenue
    if base_ebit_margin < 0:
        base_ebit_margin = 0.05  # ← 负值替换为正值
elif np_list and base_revenue:
    base_ebit_margin = abs(np_list[-1] / base_revenue) * 0.5
else:
    base_ebit_margin = 0.13
```

**修改为**：
```python
# L505-530
import logging
logger = logging.getLogger(__name__)

income = financials.get('income', {})
rev_list = income.get('年营业总收入', [])
op_list = income.get('年营业利润', [])
np_list = income.get('年净利润', [])

# v9 P0：禁止硬编码 fallback，所有输入必须从 financials/DataAnchor 获取
base_revenue = rev_list[-1] if rev_list else None
if base_revenue is None:
    # 尝试从 DataAnchor 获取
    try:
        from .data_anchor import get_data_anchor
        anchor = get_data_anchor(financials)
        base_revenue = anchor.get_anchor("营业收入")
    except Exception:
        pass
if base_revenue is None:
    raise ValueError(
        "估值输入缺失：营业收入无法获取。"
        f"financials keys: {list(income.keys())[:5]}"
        "禁止使用硬编码默认值。"
    )

# v9 P0：负 EBIT 利润率不替换为正值——标记为不适用
base_ebit_margin = None
is_loss_company = False

if op_list and base_revenue:
    raw_margin = op_list[-1] / base_revenue
    if raw_margin < 0:
        is_loss_company = True
        base_ebit_margin = raw_margin  # 保留真实负值
        logger.warning(
            f"EBIT 利润率为负({raw_margin:.2%})，"
            f"DCF/情景分析不适用于亏损公司，将使用 PS 估值"
        )
    else:
        base_ebit_margin = raw_margin
elif np_list and base_revenue:
    raw_margin = np_list[-1] / base_revenue
    if raw_margin < 0:
        is_loss_company = True
        base_ebit_margin = raw_margin
        logger.warning(f"净利润利润率为负({raw_margin:.2%})，标记为亏损公司")
    else:
        base_ebit_margin = raw_margin
else:
    raise ValueError(
        "估值输入缺失：营业利润和净利润均无法获取。"
        f"op_list={len(op_list)}, np_list={len(np_list)}"
    )
```

### 修改 1b：情景分析亏损公司降级（L525-536）

**当前代码**：
```python
# L525-536
try:
    result.scenarios = run_scenario_analysis(
        base_revenue=base_revenue,
        base_ebit_margin=base_ebit_margin,
        base_wacc=base_wacc,
        base_terminal_growth=base_terminal_growth,
        shares=shares,
    )
except Exception as e:
    logger.warning(f"情景分析失败: {e}")
```

**修改为**：
```python
# v9 P0：亏损公司跳过情景分析（FCF 为负，DCF 模型崩溃）
if is_loss_company:
    logger.info("亏损公司：跳过情景分析（DCF 不适用），使用 PS 估值")
    result.scenarios = []
    result.warnings.append(
        f"亏损公司(EBIT={base_ebit_margin:.2%})，情景分析跳过，使用 PS 估值"
    )
else:
    try:
        result.scenarios = run_scenario_analysis(
            base_revenue=base_revenue,
            base_ebit_margin=base_ebit_margin,
            base_wacc=base_wacc,
            base_terminal_growth=base_terminal_growth,
            shares=shares,
        )
    except Exception as e:
        logger.warning(f"情景分析失败: {e}")
        result.warnings.append(f"情景分析失败: {e}")
```

### 修改 1c：翻转阈值亏损公司降级（L538-551）

**当前代码**：
```python
# L538-551
try:
    result.flip_thresholds = compute_flip_thresholds(...)
except Exception as e:
    logger.warning(f"翻转阈值计算失败: {e}")
```

**修改为**：
```python
# v9 P0：亏损公司跳过翻转阈值（DCF 模型输入为负，二分法不收敛）
if is_loss_company:
    logger.info("亏损公司：跳过翻转阈值（DCF 不适用），使用 PS 翻转分析")
    result.flip_thresholds = _compute_ps_flip_thresholds(
        base_revenue=base_revenue,
        current_price=current_price,
        shares=shares,
        ps_multiple=2.0,  # 行业中位数 PS
    )
    result.warnings.append("亏损公司，翻转阈值使用 PS 模型（非 DCF）")
else:
    try:
        result.flip_thresholds = compute_flip_thresholds(
            base_value=valuation_value,
            current_price=current_price,
            base_revenue=base_revenue,
            base_ebit_margin=base_ebit_margin,
            base_wacc=base_wacc,
            base_terminal_growth=base_terminal_growth,
            shares=shares,
        )
    except Exception as e:
        logger.warning(f"翻转阈值计算失败: {e}")
        result.warnings.append(f"翻转阈值失败: {e}")
```

### 修改 1d：新增 PS 翻转阈值函数（文件末尾）

```python
def _compute_ps_flip_thresholds(
    base_revenue: float,
    current_price: float,
    shares: float,
    ps_multiple: float = 2.0,
) -> list[FlipThreshold]:
    """亏损公司 PS 翻转阈值：当 PS 倍数降至 X 时，估值等于当前股价。"""
    thresholds = []

    # 当前 PS 倍数
    market_cap = current_price * shares
    current_ps = market_cap / base_revenue if base_revenue > 0 else 0

    # PS 翻转点：当 PS 降至 current_ps * 0.5 时
    flip_ps = current_ps * 0.5
    flip_revenue = market_cap / flip_ps if flip_ps > 0 else 0

    thresholds.append(FlipThreshold(
        variable="PS倍数",
        current_value=round(current_ps, 2),
        flip_value=round(flip_ps, 2),
        direction="down",
        impact=f"当PS倍数降至{flip_ps:.2f}时，估值等于当前股价",
    ))

    thresholds.append(FlipThreshold(
        variable="营收(亿)",
        current_value=round(base_revenue, 2),
        flip_value=round(flip_revenue, 2),
        direction="down",
        impact=f"当营收降至{flip_revenue:.1f}亿时，估值等于当前股价（PS={flip_ps:.2f}）",
    ))

    return thresholds
```

---

## 文件 2：`quality_enhancer.py`

### 修改 2a：估值注入改为统一引擎输出（L237-250）

**当前代码**：
```python
# L237-250
if result.valuation_result and result.valuation_result.get('dcf_value'):
    _ccy = "港元" if market == "hk" else "元"
    _dcf = result.valuation_result['dcf_value']
    if _dcf is not None and _dcf < 0:
        logger.info(f"[Quality] DCF 为负({_dcf:.2f})，不注入第7章")
    else:
        val_text = f"\n\n## 估值分析\n\n- DCF每股价值: {_dcf:.2f}{_ccy}\n"
        val_text += f"- 目标价区间: ...\n"
        val_text += f"- 上行空间: ...\n"
        if 7 in chapters:
            chapters[7] = chapters[7] + val_text
```

**修改为**：
```python
# v9 P1：估值注入改为统一引擎输出（含仲裁结论）
if result.valuation_result:
    _ccy = "港元" if market == "hk" else "元"
    _vr = result.valuation_result

    # 从 valuation_arbiter 获取仲裁结论
    from .valuation_arbiter import ValuationArbiter
    arbiter = ValuationArbiter()
    verdict = arbiter.arbitrate(
        dcf_value=_vr.get('dcf_value'),
        comparable_value=_vr.get('comparable_ps_value'),
        is_loss_company=_vr.get('is_loss_company', False),
        market_cap=current_price * shares if shares else 0,
        revenue=financials.get('income', {}).get('年营业总收入', [None])[-1],
    )

    val_text = f"\n\n## 估值分析\n\n"
    val_text += f"- **主估值方法**: {verdict.method}\n"
    val_text += f"- **目标价**: {verdict.target_price:.2f}{_ccy}\n"
    if verdict.dcf_value and verdict.dcf_value > 0:
        val_text += f"- DCF每股价值: {verdict.dcf_value:.2f}{_ccy}\n"
    if verdict.comparable_value:
        val_text += f"- 可比公司每股价值: {verdict.comparable_value:.2f}{_ccy}\n"
    val_text += f"- 目标价区间: {verdict.target_bear:.2f} - {verdict.target_bull:.2f}{_ccy}\n"
    val_text += f"- 上行空间: {verdict.upside:.1%}\n"
    if verdict.is_loss_company:
        val_text += f"- ⚠️ 亏损公司，DCF 不适用，以 PS（市销率）为主估值方法\n"

    if 7 in chapters:
        chapters[7] = chapters[7] + val_text
        logger.info(f"[Quality] 估值结果已注入第7章（方法={verdict.method}）")
```

---

## 文件 3：`valuation_arbiter.py`（新建）

```python
"""
估值仲裁器（v9 新建）。

当多套估值方法结论不一致时，选择最可靠的方法并说明理由。
对标 CFA Standard V-C：当使用多种估值方法时，必须 reconcile 结果。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ValuationVerdict:
    """估值仲裁结论。"""
    target_price: float        # 最终目标价
    target_bear: float         # 悲观目标价
    target_bull: float         # 乐观目标价
    upside: float              # 上行空间（%）
    method: str                # 主估值方法说明
    dcf_value: float | None    # DCF 值（可能为 None）
    comparable_value: float | None  # 可比公司值
    is_loss_company: bool      # 是否亏损公司
    reconciliation: str        # 仲裁说明（CFA V-C 要求）


class ValuationArbiter:
    """估值仲裁器。

    仲裁规则：
    1. 亏损公司（EBIT<0）：DCF 不适用，以 PS 为主
    2. 盈利公司 + DCF 与可比偏差 <30%：取加权均值（DCF 60% + 可比 40%）
    3. 盈利公司 + DCF 与可比偏差 >30%：以 DCF 为主，标注偏差
    4. 只有 DCF 或只有可比：用单一方法，标注局限性
    """

    def arbitrate(
        self,
        dcf_value: float | None,
        comparable_value: float | None,
        is_loss_company: bool,
        market_cap: float = 0,
        revenue: float | None = None,
    ) -> ValuationVerdict:
        """仲裁估值结论。"""

        # Case 1：亏损公司 → PS 为主
        if is_loss_company:
            if comparable_value and comparable_value > 0:
                target = comparable_value
                method = "PS（市销率）——亏损公司 DCF 不适用"
                reconciliation = (
                    f"DCF 不适用于亏损公司（FCF 为负），"
                    f"以可比公司 PS 估值为主。"
                    f"可比公司 PS 估值 {comparable_value:.2f} 元/股。"
                )
            elif revenue and revenue > 0 and market_cap > 0:
                # 用行业中位数 PS 估算
                ps_multiple = 2.0  # 新能源汽车行业中位数
                target = ps_multiple * revenue / (market_cap / (comparable_value or 1))
                method = f"PS（市销率，行业中位数 {ps_multiple}x）"
                reconciliation = (
                    f"亏损公司，DCF/可比均不可用，"
                    f"使用行业中位数 PS={ps_multiple}x 估算。"
                    f"结果仅供参考，建议使用卖方一致预期。"
                )
            else:
                target = 0
                method = "不适用（亏损公司+无可比数据）"
                reconciliation = "亏损公司且无可比数据，无法给出估值结论。"

            return ValuationVerdict(
                target_price=target,
                target_bear=target * 0.8,
                target_bull=target * 1.2,
                upside=0,
                method=method,
                dcf_value=dcf_value,
                comparable_value=comparable_value,
                is_loss_company=True,
                reconciliation=reconciliation,
            )

        # Case 2：盈利公司 + 双方法可用
        if dcf_value and dcf_value > 0 and comparable_value and comparable_value > 0:
            deviation = abs(dcf_value - comparable_value) / max(dcf_value, comparable_value)

            if deviation < 0.30:
                # 偏差 <30%：加权均值
                target = dcf_value * 0.6 + comparable_value * 0.4
                method = f"DCF+可比加权（偏差 {deviation:.0%}，DCF 60% + 可比 40%）"
                reconciliation = (
                    f"DCF 估值 {dcf_value:.2f}，可比公司估值 {comparable_value:.2f}，"
                    f"偏差 {deviation:.0%}（<30%），取加权均值。"
                )
            else:
                # 偏差 >30%：以 DCF 为主
                target = dcf_value
                method = f"DCF（与可比公司偏差 {deviation:.0%}，以 DCF 为主）"
                reconciliation = (
                    f"DCF 估值 {dcf_value:.2f}，可比公司估值 {comparable_value:.2f}，"
                    f"偏差 {deviation:.0%}（>30%），以 DCF 为主。"
                    f"偏差原因：增长假设/折现率差异，建议检查 WACC 和 FCF 假设。"
                )

            return ValuationVerdict(
                target_price=target,
                target_bear=target * 0.8,
                target_bull=target * 1.2,
                upside=0,
                method=method,
                dcf_value=dcf_value,
                comparable_value=comparable_value,
                is_loss_company=False,
                reconciliation=reconciliation,
            )

        # Case 3：只有 DCF
        if dcf_value and dcf_value > 0:
            return ValuationVerdict(
                target_price=dcf_value,
                target_bear=dcf_value * 0.8,
                target_bull=dcf_value * 1.2,
                upside=0,
                method="DCF（单一方法）",
                dcf_value=dcf_value,
                comparable_value=None,
                is_loss_company=False,
                reconciliation="仅 DCF 可用，可比公司数据缺失。建议补充可比公司分析。",
            )

        # Case 4：只有可比
        if comparable_value and comparable_value > 0:
            return ValuationVerdict(
                target_price=comparable_value,
                target_bear=comparable_value * 0.8,
                target_bull=comparable_value * 1.2,
                upside=0,
                method="可比公司（单一方法）",
                dcf_value=None,
                comparable_value=comparable_value,
                is_loss_company=False,
                reconciliation="仅可比公司可用，DCF 计算失败。建议检查财务数据。",
            )

        # Case 5：全部不可用
        return ValuationVerdict(
            target_price=0,
            target_bear=0,
            target_bull=0,
            upside=0,
            method="不适用",
            dcf_value=None,
            comparable_value=None,
            is_loss_company=is_loss_company,
            reconciliation="所有估值方法均不可用，无法给出估值结论。",
        )
```

---

## 文件 4：`valuation_validator.py`（新建）

```python
"""
估值输入校验器（v9 新建）。

在估值计算前校验所有输入参数是否在合理范围内。
防止硬编码/错误参数进入估值计算。
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def validate_valuation_inputs(
    financials: dict,
    shares: float,
    current_price: float,
) -> list[str]:
    """估值输入校验：返回错误列表（空 = 通过）。

    Args:
        financials: Wind 财务数据
        shares: 总股本（亿股）
        current_price: 当前股价（港元/元）

    Returns:
        错误列表（空 = 通过）
    """
    errors = []

    income = financials.get('income', {})
    balance = financials.get('balance', {})

    # 1. 营业收入
    rev_list = income.get('年营业总收入', [])
    if not rev_list:
        errors.append("营业收入缺失（income dict 无 '年营业总收入' key）")
    else:
        rev = rev_list[-1]
        if rev < 1:
            errors.append(f"营业收入 {rev:.2f} 亿过小（<1亿），可能单位错误")
        elif rev > 100000:
            errors.append(f"营业收入 {rev:.2f} 亿过大（>10万亿），可能单位错误")

    # 2. 总股本
    if shares <= 0:
        errors.append(f"总股本 {shares} 必须 > 0")
    elif shares > 1000:
        errors.append(f"总股本 {shares:.2f} 亿股过大（>1000亿），可能单位错误")

    # 3. 当前股价
    if current_price <= 0:
        errors.append(f"当前股价 {current_price} 必须 > 0")
    elif current_price > 10000:
        errors.append(f"当前股价 {current_price:.2f} 过大（>10000），可能单位错误")

    # 4. EBIT 利润率范围
    op_list = income.get('年营业利润', [])
    if op_list and rev_list:
        margin = op_list[-1] / rev_list[-1]
        if margin < -1.0:
            errors.append(f"EBIT 利润率 {margin:.2%} 超出合理范围（<-100%）")
        elif margin > 1.0:
            errors.append(f"EBIT 利润率 {margin:.2%} 超出合理范围（>100%）")

    # 5. 资产负债率
    debt_list = balance.get('年负债合计', [])
    asset_list = balance.get('总资产', [])
    if debt_list and asset_list:
        leverage = debt_list[-1] / asset_list[-1]
        if leverage > 1.0:
            errors.append(f"资产负债率 {leverage:.2%} > 100%，资不抵债")

    return errors
```

---

## 文件 5：`gate5.py`

### 修改 5a：删除简化 DCF，改用统一引擎（L148-165）

**当前代码**：
```python
# L148-165
try:
    _dcf_p = context.get("dcf_params")
    _shares = context.get("shares")
    if _dcf_p is not None and _shares:
        _fcf = getattr(_dcf_p, "fcf", None) or 0
        _wacc = getattr(_dcf_p, "wacc", 0.10) or 0.10
        _g = getattr(_dcf_p, "terminal_growth", 0.03) or 0.03
        if _fcf and _wacc > _g and _shares > 0:
            dcf_value = (_fcf / (_wacc - _g)) / _shares
            if dcf_value < 0:
                valuation["dcf_value"] = None
                ...
            else:
                valuation["dcf_value"] = round(dcf_value, 2)
```

**修改为**：
```python
# v9 P1：删除简化 DCF，统一使用 valuation_engine（含降级链）
try:
    from ..valuation_engine import compute_full_valuation
    from ..valuation_validator import validate_valuation_inputs
    from ..valuation_arbiter import ValuationArbiter

    financials = context.get("financials", {})
    _shares = context.get("shares")
    _price = context.get("current_price", 0)

    # 输入校验
    input_errors = validate_valuation_inputs(financials, _shares, _price)
    if input_errors:
        logger.warning(f"Gate5 估值输入校验失败: {input_errors}")
        valuation["input_errors"] = input_errors

    if financials and _shares and _price:
        val_result = compute_full_valuation(
            ticker=context.get("ticker", ""),
            company_name=context.get("company_name", ""),
            financials=financials,
            shares=_shares,
            current_price=_price,
        )

        # 估值仲裁
        arbiter = ValuationArbiter()
        verdict = arbiter.arbitrate(
            dcf_value=val_result.dcf.value_per_share if val_result.dcf else None,
            comparable_value=val_result.value_per_share,
            is_loss_company=val_result.degraded and "亏损" in (val_result.degradation_reason or ""),
            market_cap=_price * _shares,
            revenue=financials.get('income', {}).get('年营业总收入', [None])[-1],
        )

        valuation["dcf_value"] = verdict.dcf_value
        valuation["comparable_value"] = verdict.comparable_value
        valuation["target_price"] = verdict.target_price
        valuation["method"] = verdict.method
        valuation["reconciliation"] = verdict.reconciliation
        valuation["is_loss_company"] = verdict.is_loss_company
        logger.info(f"Gate5 估值完成: method={verdict.method}, target={verdict.target_price:.2f}")
except Exception as e:
    logger.warning(f"Gate5 统一估值失败（非阻断）: {e}")
```

---

## 验收标准

修复后重跑小鹏 9868.HK，必须满足：

| # | 标准 | 检查方法 |
|---|------|---------|
| 1 | 翻转阈值营收与 Wind 锚点偏差 ≤1% | Gate8 红队审查无"翻转阈值参数偏差" |
| 2 | EBIT 利润率与实际值一致 | Gate8 红队审查无"EBIT 矛盾" |
| 3 | 全报告只有一套 DCF 值 | ch7 估值分析只出现一个目标价 |
| 4 | 估值仲裁明确说明主方法 | ch7 含"主估值方法：PS/DCF" |
| 5 | Gate8 红队无"估值矛盾"致命问题 | Gate8 passed |

## 测试用例

```python
# test_valuation_arbiter.py
def test_loss_company_uses_ps():
    arbiter = ValuationArbiter()
    verdict = arbiter.arbitrate(
        dcf_value=-43.53,
        comparable_value=45.0,
        is_loss_company=True,
    )
    assert verdict.method.startswith("PS")
    assert verdict.target_price == 45.0
    assert "亏损公司" in verdict.reconciliation

def test_profitable_company_weighted():
    arbiter = ValuationArbiter()
    verdict = arbiter.arbitrate(
        dcf_value=50.0,
        comparable_value=55.0,
        is_loss_company=False,
    )
    assert "加权" in verdict.method
    assert abs(verdict.target_price - (50*0.6 + 55*0.4)) < 0.1

def test_validator_rejects_hardcoded():
    errors = validate_valuation_inputs(
        financials={"income": {"年营业总收入": []}},
        shares=18.87,
        current_price=46.52,
    )
    assert any("营业收入缺失" in e for e in errors)
```
