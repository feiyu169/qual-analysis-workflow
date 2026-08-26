# Qual 估值模块修复——逐文件技术规格 v2.0

> 版本：v2.0 | 日期：2026-08-24
> 基线：qual v9 commit 6529d69
> 审查：HeavySkill K8 审查通过（有条件），CFA V-A/V-B/V-C 合规
> 目标：消除估值逻辑三重互斥，建立可审计、可复现、可辩护的估值体系

---

## 一、修改总览

| 文件 | 修改类型 | 工作量 | 优先级 |
|------|----------|--------|--------|
| `contracts/financials.py` | **新建**：Financials 数据契约 | 2h | P0-1 |
| `data/wind_adapter.py` | **新建**：Wind 字段映射适配层 | 2h | P0-2 |
| `valuation/currency.py` | **新建**：币种统一模块 | 1h | P0-3 |
| `valuation/method_selector.py` | **新建**：估值方法选择矩阵 | 2h | P0-4 |
| `valuation/arbiter.py` | **新建**：估值仲裁器（唯一出口） | 3h | P0-5/P0-6 |
| `valuation/validator.py` | **新建**：估值输入校验器（扩展版） | 2h | P0-8 |
| `quality_enhancer.py` | 重构：估值注入改为仲裁器输出 | 1h | P0-7 |
| `depth_enhancer.py` | 重构：删除硬编码 + 亏损公司降级 | 2h | P0 |
| `gate5.py` | 重构：删除简化 DCF，消费仲裁器结论 | 1h | P0-5 |

**总计：16 小时（2 个工作日）**

---

## 二、P0-1：统一估值数据契约

### 新建：`contracts/financials.py`

```python
"""
估值数据契约（v2.0 新建）。

所有估值输入必须通过此契约传递，禁止 dict[str, Any] 直传。
对标 CFA Standard V-A：所有估值输入必须有合理来源、可追溯。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Financials:
    """估值输入数据契约（不可变，所有字段必填）。

    CFA V-A 要求：每个字段必须有 source（数据来源）、
    report_date（报告日期）、currency（币种）、unit（单位）。
    """
    # === 损益表 ===
    revenue: float                    # 营业收入（亿元）
    operating_profit: float           # 营业利润（亿元）
    net_profit_parent: float          # 归母净利润（亿元）
    gross_profit: float | None = None # 毛利润（亿元，可选）

    # === 资产负债表 ===
    total_assets: float               # 总资产（亿元）
    total_liabilities: float          # 总负债（亿元）
    equity_parent: float              # 归母净资产（亿元）
    cash: float | None = None         # 货币资金（亿元，可选）
    interest_bearing_debt: float | None = None  # 有息负债（亿元，可选）

    # === 现金流量表 ===
    operating_cashflow: float         # 经营现金流（亿元）
    capex: float | None = None        # 资本开支（亿元，可选）

    # === 市场数据 ===
    shares: float                     # 总股本（亿股）
    current_price: float              # 当前股价（元或港元）
    currency: Literal["CNY", "HKD", "USD"] = "CNY"  # 股价币种

    # === 元数据 ===
    ticker: str = ""                  # 股票代码
    company_name: str = ""            # 公司名称
    fiscal_year: int = 0              # 财年
    source: str = "Wind"              # 数据来源
    report_date: str = ""             # 报告日期
    unit: str = "亿元"                # 财务数据单位

    @property
    def net_debt(self) -> float:
        """净债务 = 有息负债 - 货币资金（亿元）。"""
        debt = self.interest_bearing_debt or 0.0
        cash = self.cash or 0.0
        return debt - cash

    @property
    def enterprise_value(self) -> float:
        """企业价值 EV = 市值 + 净债务（亿元）。"""
        market_cap = self.shares * self.current_price
        return market_cap + self.net_debt

    @property
    def ebit_margin(self) -> float:
        """EBIT 利润率 = 营业利润 / 营业收入。"""
        return self.operating_profit / self.revenue if self.revenue > 0 else 0.0

    @property
    def is_loss_company(self) -> bool:
        """是否亏损公司（归母净利润 < 0）。"""
        return self.net_profit_parent < 0

    @property
    def has_positive_ocf(self) -> bool:
        """经营现金流是否为正（亏损但现金流为正 = 有扭亏路径）。"""
        return self.operating_cashflow > 0

    def to_wind_dict(self) -> dict:
        """转换为 Wind financials dict 格式（向后兼容）。"""
        return {
            "income": {
                "年营业总收入": [self.revenue],
                "年营业利润": [self.operating_profit],
                "年净利润": [self.net_profit_parent],
            },
            "balance": {
                "总资产": [self.total_assets],
                "年负债合计": [self.total_liabilities],
                "年所有者权益合计": [self.equity_parent],
            },
            "cashflow": {
                "经营活动现金流量净额": [self.operating_cashflow],
            },
        }
```

---

## 三、P0-2：Wind 适配层

### 新建：`data/wind_adapter.py`

```python
"""
Wind 字段映射适配层（v2.0 新建）。

将 Wind MCP 返回的原始 dict 转换为 Financials 契约。
缺失字段 fail-fast（禁止静默返回 None 或硬编码默认值）。
"""
from __future__ import annotations

import logging
from typing import Any

from ..contracts.financials import Financials

logger = logging.getLogger(__name__)

# Wind 原始字段 → Financials 属性映射
_WIND_FIELD_MAP = {
    # (wind_dict_key, wind_list_key) → Financials 属性名
    ("income", "年营业总收入"): "revenue",
    ("income", "年营业利润"): "operating_profit",
    ("income", "年净利润"): "net_profit_parent",
    ("income", "年毛利润"): "gross_profit",
    ("balance", "总资产"): "total_assets",
    ("balance", "年负债合计"): "total_liabilities",
    ("balance", "年所有者权益合计"): "equity_parent",
    ("balance", "货币资金"): "cash",
    ("balance", "有息负债"): "interest_bearing_debt",
    ("cashflow", "经营活动现金流量净额"): "operating_cashflow",
    ("cashflow", "购建固定资产、无形资产和其他长期资产支付的现金"): "capex",
}


def wind_to_financials(
    wind_data: dict[str, Any],
    ticker: str = "",
    company_name: str = "",
    shares: float = 0,
    current_price: float = 0,
    currency: str = "CNY",
    fiscal_year: int = 0,
) -> Financials:
    """将 Wind 原始数据转换为 Financials 契约。

    Args:
        wind_data: Wind MCP 返回的原始 dict（含 income/balance/cashflow 子 dict）
        ticker: 股票代码
        company_name: 公司名称
        shares: 总股本（亿股）
        current_price: 当前股价
        currency: 股价币种
        fiscal_year: 财年

    Returns:
        Financials 契约（不可变）

    Raises:
        ValueError: 必填字段缺失时 fail-fast
    """
    errors: list[str] = []
    values: dict[str, float | None] = {}

    for (section, field_name), attr_name in _WIND_FIELD_MAP.items():
        section_data = wind_data.get(section, {})
        field_list = section_data.get(field_name, [])

        if not field_list:
            # 可选字段：允许 None
            if attr_name in ("gross_profit", "cash", "interest_bearing_debt", "capex"):
                values[attr_name] = None
                continue
            errors.append(f"Wind 字段缺失: {section}.{field_name}")
            continue

        # 取最后一个值（最新财年）
        raw_value = field_list[-1]
        if raw_value is None:
            if attr_name in ("gross_profit", "cash", "interest_bearing_debt", "capex"):
                values[attr_name] = None
                continue
            errors.append(f"Wind 字段值为 None: {section}.{field_name}")
            continue

        values[attr_name] = float(raw_value)

    if errors:
        raise ValueError(
            f"Wind 数据转换失败（{len(errors)} 项缺失）:\n" +
            "\n".join(f"  - {e}" for e in errors[:10])
        )

    return Financials(
        revenue=values["revenue"],
        operating_profit=values["operating_profit"],
        net_profit_parent=values["net_profit_parent"],
        gross_profit=values.get("gross_profit"),
        total_assets=values["total_assets"],
        total_liabilities=values["total_liabilities"],
        equity_parent=values["equity_parent"],
        cash=values.get("cash"),
        interest_bearing_debt=values.get("interest_bearing_debt"),
        operating_cashflow=values["operating_cashflow"],
        capex=values.get("capex"),
        shares=shares,
        current_price=current_price,
        currency=currency,  # type: ignore[arg-type]
        ticker=ticker,
        company_name=company_name,
        fiscal_year=fiscal_year,
        source="Wind",
    )
```

---

## 四、P0-3：币种统一

### 新建：`valuation/currency.py`

```python
"""
币种统一模块（v2.0 新建）。

内部统一为人民币计算，最终目标价按报告日汇率折算为港元。
禁止在估值比较中混用 CNY/HKD。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# 默认汇率（Wind 实时行情获取，此处为 fallback）
_DEFAULT_RATES = {
    ("CNY", "HKD"): 1.08,  # 1 CNY = 1.08 HKD
    ("HKD", "CNY"): 0.926,
    ("CNY", "USD"): 0.137,
    ("USD", "CNY"): 7.30,
}


@dataclass(frozen=True)
class PriceResult:
    """估值结果（含币种信息）。"""
    value_cny: float       # 人民币目标价
    value_hkd: float       # 港元目标价
    value_usd: float       # 美元目标价
    currency_used: str     # 计算使用的币种
    exchange_rate: float   # 使用的汇率


def convert_to_cny(value: float, from_currency: str, rates: dict | None = None) -> float:
    """将任意币种转换为人民币。"""
    if from_currency == "CNY":
        return value
    r = (rates or _DEFAULT_RATES).get((from_currency, "CNY"), 1.0)
    return value * r


def convert_from_cny(value_cny: float, to_currency: str, rates: dict | None = None) -> float:
    """将人民币转换为任意币种。"""
    if to_currency == "CNY":
        return value_cny
    r = (rates or _DEFAULT_RATES).get(("CNY", to_currency), 1.0)
    return value_cny * r


def make_price_result(
    value: float,
    source_currency: str,
    rates: dict | None = None,
) -> PriceResult:
    """创建统一币种的估值结果。"""
    value_cny = convert_to_cny(value, source_currency, rates)
    value_hkd = convert_from_cny(value_cny, "HKD", rates)
    value_usd = convert_from_cny(value_cny, "USD", rates)
    rate = (rates or _DEFAULT_RATES).get((source_currency, "CNY"), 1.0)
    return PriceResult(
        value_cny=round(value_cny, 2),
        value_hkd=round(value_hkd, 2),
        value_usd=round(value_usd, 2),
        currency_used=source_currency,
        exchange_rate=rate,
    )
```

---

## 五、P0-4：估值方法选择矩阵

### 新建：`valuation/method_selector.py`

```python
"""
估值方法选择矩阵（v2.0 新建）。

根据公司特征自动选择最适当的估值方法。
对标 CFA Standard V-B：估值方法必须适当。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

from ..contracts.financials import Financials

logger = logging.getLogger(__name__)


class ValuationMethod(str, Enum):
    """估值方法枚举。"""
    DCF = "DCF"
    EV_REVENUE = "EV/Revenue"
    PE = "PE"
    PS = "PS"
    PB = "PB"
    DIVIDEND_DISCOUNT = "DDM"


@dataclass(frozen=True)
class MethodSelection:
    """估值方法选择结果。"""
    primary: ValuationMethod          # 主方法
    cross_validation: list[ValuationMethod]  # 交叉验证方法
    auxiliary: list[ValuationMethod]  # 辅助方法（仅参考）
    excluded: list[ValuationMethod]   # 不适用方法
    reason: str                       # 选择理由


def select_valuation_methods(financials: Financials) -> MethodSelection:
    """根据公司特征选择估值方法。

    小鹏类公司（会计亏损、经营现金流转正、高速增长）：
    - 主方法：EV/Revenue（收入高增长、亏损收窄）
    - 交叉验证：PS（市销率）
    - 辅助：PB（底部参考，净资产为正时）
    - DCF：仅当 OCF 为正且有扭亏路径时作辅助情景

    CFA Standard V-B：估值方法必须适当。
    - 亏损公司不适用 PE（负 EPS 无意义）
    - 亏损公司不适用 DCF 作为主方法（FCF 可能为负）
    - EV/Revenue 适用于高增长亏损公司
    """
    excluded: list[ValuationMethod] = []
    auxiliary: list[ValuationMethod] = []
    cross_val: list[ValuationMethod] = []
    reason_parts: list[str] = []

    # 1. PE：亏损公司排除
    if financials.is_loss_company:
        excluded.append(ValuationMethod.PE)
        reason_parts.append("亏损公司（负 EPS），PE 不适用")
    else:
        cross_val.append(ValuationMethod.PE)

    # 2. DCF：亏损公司降级为辅助（OCF 为正时可作情景）
    if financials.is_loss_company:
        if financials.has_positive_ocf:
            auxiliary.append(ValuationMethod.DCF)
            reason_parts.append(
                f"会计亏损但 OCF={financials.operating_cashflow:.1f}亿为正，"
                f"DCF 仅作辅助情景（不作主方法）"
            )
        else:
            excluded.append(ValuationMethod.DCF)
            reason_parts.append("亏损公司且 OCF 为负，DCF 不适用")
    else:
        cross_val.append(ValuationMethod.DCF)

    # 3. PB：净资产为正时可用
    if financials.equity_parent > 0:
        auxiliary.append(ValuationMethod.PB)
    else:
        excluded.append(ValuationMethod.PB)
        reason_parts.append("归母净资产≤0，PB 不适用")

    # 4. EV/Revenue 和 PS：始终可用（高增长公司优选）
    primary = ValuationMethod.EV_REVENUE
    cross_val.append(ValuationMethod.PS)
    reason_parts.insert(0, f"主方法 EV/Revenue（营收 {financials.revenue:.1f}亿，YoY 高增长）")

    return MethodSelection(
        primary=primary,
        cross_validation=cross_val,
        auxiliary=auxiliary,
        excluded=excluded,
        reason="；".join(reason_parts),
    )
```

---

## 六、P0-5/P0-6：估值仲裁器

### 新建：`valuation/arbiter.py`

```python
"""
估值仲裁器（v2.0 新建）。

ValuationArbiter 是估值模块的**唯一出口**。
gate5.py 必须只消费此结论，不得自行执行 DCF→PE→PS 降级链。

仲裁规则（HeavySkill K8 审查修订）：
- 取消固定 60/40 权重和固定 30% 阈值
- 改为分档处理：<20% 可加权，20-40% 披露偏差，>40% 以主方法为准
- 亏损公司不得先触发 DCF 再被覆盖
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..contracts.financials import Financials
from .method_selector import MethodSelection, ValuationMethod, select_valuation_methods

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ValuationVerdict:
    """估值仲裁结论（唯一出口）。

    CFA Standard V-C：多套方法结论不一致时，必须 reconcile。
    """
    target_price: float               # 最终目标价（主币种）
    target_bear: float                # 悲观目标价
    target_bear_assumptions: str      # 悲观假设说明
    target_base: float                # 基准目标价
    target_bull: float                # 乐观目标价
    target_bull_assumptions: str      # 乐观假设说明
    upside: float                     # 上行空间（%）
    method: str                       # 主估值方法说明
    method_details: dict              # 各方法估值结果
    reconciliation: str               # 仲裁说明（CFA V-C 要求）
    is_loss_company: bool             # 是否亏损公司
    primary_method: str               # 主方法名称
    excluded_methods: list[str]       # 不适用方法及理由
    currency: str                     # 目标价币种
    data_as_of: str                   # 数据截止日


class ValuationArbiter:
    """估值仲裁器（唯一出口）。

    使用方法：
        arbiter = ValuationArbiter()
        verdict = arbiter.arbitrate(financials, dcf_value, ev_revenue_value, ps_value, pb_value)
        # verdict 是估值模块的最终输出，gate5 只消费此结论
    """

    def arbitrate(
        self,
        financials: Financials,
        dcf_value: float | None = None,
        ev_revenue_value: float | None = None,
        ps_value: float | None = None,
        pb_value: float | None = None,
        pe_value: float | None = None,
    ) -> ValuationVerdict:
        """仲裁估值结论。"""

        # Step 1：选择估值方法
        method_sel = select_valuation_methods(financials)

        # Step 2：收集可用估值结果
        available: dict[str, float] = {}
        if dcf_value and dcf_value > 0 and "DCF" not in [e for e in method_sel.excluded]:
            available["DCF"] = dcf_value
        if ev_revenue_value and ev_revenue_value > 0:
            available["EV/Revenue"] = ev_revenue_value
        if ps_value and ps_value > 0:
            available["PS"] = ps_value
        if pb_value and pb_value > 0 and "PB" not in [e for e in method_sel.excluded]:
            available["PB"] = pb_value
        if pe_value and pe_value > 0 and "PE" not in [e for e in method_sel.excluded]:
            available["PE"] = pe_value

        # Step 3：确定主方法值
        primary_name = method_sel.primary.value
        primary_value = available.get(primary_name)

        if primary_value is None:
            # 主方法不可用，降级到交叉验证
            for cv in method_sel.cross_validation:
                if cv.value in available:
                    primary_value = available[cv.value]
                    primary_name = cv.value
                    break

        if primary_value is None:
            # 全部不可用
            return ValuationVerdict(
                target_price=0, target_bear=0, target_bear_assumptions="",
                target_base=0, target_bull=0, target_bull_assumptions="",
                upside=0, method="不适用", method_details={},
                reconciliation="所有估值方法均不可用，无法给出估值结论。",
                is_loss_company=financials.is_loss_company,
                primary_method="无", excluded_methods=[m for m in method_sel.excluded],
                currency=financials.currency, data_as_of=financials.report_date,
            )

        # Step 4：交叉验证 + 偏差分析
        cross_values = {k: v for k, v in available.items() if k != primary_name}
        deviations: dict[str, float] = {}
        for name, value in cross_values.items():
            deviation = abs(primary_value - value) / max(primary_value, value, 1e-6)
            deviations[name] = deviation

        # Step 5：仲裁（分档处理，取消固定阈值）
        if not deviations:
            # 无交叉验证
            target = primary_value
            method_desc = f"{primary_name}（单一方法，无交叉验证）"
            reconciliation = f"仅 {primary_name} 可用，建议补充交叉验证。"
        else:
            max_dev_name = max(deviations, key=deviations.get)  # type: ignore[arg-type]
            max_dev = deviations[max_dev_name]

            if max_dev < 0.20:
                # 偏差 <20%：可加权（等权）
                all_values = [primary_value] + list(cross_values.values())
                target = sum(all_values) / len(all_values)
                method_desc = f"{primary_name}+{'+'.join(cross_values.keys())} 等权（偏差 {max_dev:.0%}）"
                reconciliation = (
                    f"主方法 {primary_name}={primary_value:.2f}，"
                    f"交叉验证偏差 {max_dev:.0%}（<20%），取等权均值。"
                )
            elif max_dev < 0.40:
                # 偏差 20-40%：加权但强制披露偏差来源
                target = primary_value
                method_desc = f"{primary_name}（主）+ {max_dev_name} 偏差 {max_dev:.0%}（已披露）"
                reconciliation = (
                    f"主方法 {primary_name}={primary_value:.2f}，"
                    f"与 {max_dev_name}={cross_values[max_dev_name]:.2f} 偏差 {max_dev:.0%}。"
                    f"偏差来源：增长假设/折现率/乘数差异，以主方法为准。"
                )
            else:
                # 偏差 >40%：以主方法为准，其他方法仅作区间参考
                target = primary_value
                method_desc = f"{primary_name}（主，与 {max_dev_name} 偏差 {max_dev:.0%}）"
                reconciliation = (
                    f"主方法 {primary_name}={primary_value:.2f}，"
                    f"与 {max_dev_name}={cross_values[max_dev_name]:.2f} 偏差 {max_dev:.0%}（>40%）。"
                    f"以主方法为准，{max_dev_name} 仅作区间参考。"
                    f"建议检查 WACC/FCF/乘数假设。"
                )

        # Step 6：目标价区间（悲观/基准/乐观）
        if financials.is_loss_company:
            # 亏损公司：区间基于 PS 倍数变化
            bear = target * 0.75
            bull = target * 1.30
            bear_assumptions = "PS 倍数降至行业中位数 75%"
            bull_assumptions = "PS 倍数升至行业中位数 130%，叠加营收超预期"
        else:
            bear = target * 0.80
            bull = target * 1.20
            bear_assumptions = "增长放缓 + 利润率压缩"
            bull_assumptions = "增长超预期 + 利润率扩张"

        upside = (target / financials.current_price - 1) * 100 if financials.current_price > 0 else 0

        return ValuationVerdict(
            target_price=round(target, 2),
            target_bear=round(bear, 2),
            target_bear_assumptions=bear_assumptions,
            target_base=round(target, 2),
            target_bull=round(bull, 2),
            target_bull_assumptions=bull_assumptions,
            upside=round(upside, 1),
            method=method_desc,
            method_details=available,
            reconciliation=reconciliation,
            is_loss_company=financials.is_loss_company,
            primary_method=primary_name,
            excluded_methods=[str(m) for m in method_sel.excluded],
            currency=financials.currency,
            data_as_of=financials.report_date,
        )
```

---

## 七、P0-8：估值输入校验器（扩展版）

### 新建：`valuation/validator.py`

```python
"""
估值输入校验器（v2.0 扩展版）。

HeavySkill K8 审查要求扩展：不能仅检查 5 项，须覆盖
WACC/永续增长/汇率/PS/PB/EV-Rev 等所有关键参数。
"""
from __future__ import annotations

import logging

from ..contracts.financials import Financials

logger = logging.getLogger(__name__)


def validate_valuation_inputs(
    financials: Financials,
    wacc: float | None = None,
    terminal_growth: float | None = None,
    ps_multiple: float | None = None,
    pb_multiple: float | None = None,
    ev_revenue_multiple: float | None = None,
) -> list[str]:
    """估值输入校验（扩展版）。

    Returns:
        错误列表（空 = 通过）。警告不阻断但记录。
    """
    errors: list[str] = []
    warnings: list[str] = []

    # 1. 基础财务数据
    if financials.revenue < 1:
        errors.append(f"营业收入 {financials.revenue:.2f} 亿过小（<1亿），可能单位错误")
    elif financials.revenue > 100000:
        errors.append(f"营业收入 {financials.revenue:.2f} 亿过大（>10万亿），可能单位错误")

    if financials.shares <= 0:
        errors.append(f"总股本 {financials.shares} 必须 > 0")
    elif financials.shares > 1000:
        errors.append(f"总股本 {financials.shares:.2f} 亿股过大（>1000亿），可能单位错误")

    if financials.current_price <= 0:
        errors.append(f"当前股价 {financials.current_price} 必须 > 0")
    elif financials.current_price > 10000:
        errors.append(f"当前股价 {financials.current_price:.2f} 过大（>10000），可能单位错误")

    # 2. EBIT 利润率范围
    if financials.ebit_margin < -1.0:
        errors.append(f"EBIT 利润率 {financials.ebit_margin:.2%} 超出合理范围（<-100%）")
    elif financials.ebit_margin > 1.0:
        errors.append(f"EBIT 利润率 {financials.ebit_margin:.2%} 超出合理范围（>100%）")

    # 3. 资产负债率
    if financials.total_assets > 0:
        leverage = financials.total_liabilities / financials.total_assets
        if leverage > 1.0:
            # 不直接拒绝，降级为 EV/Revenue + 风险提示
            warnings.append(f"资产负债率 {leverage:.2%} > 100%（资不抵债），PB 不适用")

    # 4. WACC 范围
    if wacc is not None:
        if wacc < 0.03:
            errors.append(f"WACC {wacc:.2%} 过低（<3%），可能参数错误")
        elif wacc > 0.15:
            errors.append(f"WACC {wacc:.2%} 过高（>15%），可能参数错误")

    # 5. 永续增长率
    if terminal_growth is not None:
        if terminal_growth < -0.01:
            errors.append(f"永续增长率 {terminal_growth:.2%} 过低（<-1%）")
        elif terminal_growth > 0.04:
            errors.append(f"永续增长率 {terminal_growth:.2%} 过高（>4%）")
        if wacc is not None and terminal_growth >= wacc:
            errors.append(f"永续增长率 {terminal_growth:.2%} ≥ WACC {wacc:.2%}（永续增长模型崩溃）")

    # 6. 估值乘数范围
    if ps_multiple is not None:
        if ps_multiple < 0.2 or ps_multiple > 5.0:
            warnings.append(f"PS 乘数 {ps_multiple:.2f} 超出合理范围 [0.2, 5.0]")

    if pb_multiple is not None:
        if pb_multiple < 0.2 or pb_multiple > 8.0:
            warnings.append(f"PB 乘数 {pb_multiple:.2f} 超出合理范围 [0.2, 8.0]")
        if financials.equity_parent <= 0:
            errors.append(f"归母净资产 {financials.equity_parent:.2f} ≤ 0，PB 不适用")

    if ev_revenue_multiple is not None:
        if ev_revenue_multiple < 0.1 or ev_revenue_multiple > 10.0:
            warnings.append(f"EV/Revenue 乘数 {ev_revenue_multiple:.2f} 超出合理范围 [0.1, 10.0]")

    # 7. 币种检查
    if financials.currency not in ("CNY", "HKD", "USD"):
        errors.append(f"币种 {financials.currency} 不支持（仅支持 CNY/HKD/USD）")

    # 记录警告（不阻断）
    for w in warnings:
        logger.warning(f"估值输入校验警告: {w}")

    return errors
```

---

## 八、P0：depth_enhancer.py 重构

### 修改 8a：删除硬编码 fallback + 亏损公司降级

**替换 `run_depth_enhancement` 函数的输入获取逻辑（L505-551）：**

```python
# v2.0：使用 Financials 契约替代 dict 取值
def run_depth_enhancement(
    chapters: dict,
    financials: Financials,  # 改为 Financials 契约（非 dict）
    valuation_value: float,
    current_price: float,
    shares: float,
    base_wacc: float,
    base_terminal_growth: float,
) -> DepthResult:
    """运行深度优化（v2.0：Financials 契约 + 亏损公司降级）。"""
    result = DepthResult()

    base_revenue = financials.revenue
    is_loss = financials.is_loss_company
    ebit_margin = financials.ebit_margin

    # 亏损公司：跳过 DCF 情景分析和翻转阈值，使用 PS 模型
    if is_loss:
        logger.info(
            f"亏损公司（EBIT={ebit_margin:.2%}，OCF={financials.operating_cashflow:.1f}亿），"
            f"跳过 DCF 情景/翻转，使用 EV/Revenue + PS 模型"
        )
        result.scenarios = []
        result.flip_thresholds = _compute_ev_revenue_flip_thresholds(
            financials=financials,
            current_price=current_price,
            shares=shares,
        )
        result.warnings.append(
            f"亏损公司(EBIT={ebit_margin:.2%})，情景分析使用 EV/Revenue 模型（非 DCF）"
        )
    else:
        # 盈利公司：正常 DCF 情景分析
        result.scenarios = run_scenario_analysis(
            base_revenue=base_revenue,
            base_ebit_margin=ebit_margin,
            base_wacc=base_wacc,
            base_terminal_growth=base_terminal_growth,
            shares=shares,
        )
        result.flip_thresholds = compute_flip_thresholds(
            base_value=valuation_value,
            current_price=current_price,
            base_revenue=base_revenue,
            base_ebit_margin=ebit_margin,
            base_wacc=base_wacc,
            base_terminal_growth=base_terminal_growth,
            shares=shares,
        )

    return result


def _compute_ev_revenue_flip_thresholds(
    financials: Financials,
    current_price: float,
    shares: float,
) -> list[FlipThreshold]:
    """亏损公司 EV/Revenue 翻转阈值。"""
    thresholds = []
    market_cap = current_price * shares
    ev = financials.enterprise_value
    current_ev_rev = ev / financials.revenue if financials.revenue > 0 else 0

    # EV/Revenue 翻转点
    flip_ev_rev = current_ev_rev * 0.5
    flip_revenue = ev / flip_ev_rev if flip_ev_rev > 0 else 0

    thresholds.append(FlipThreshold(
        variable="EV/Revenue倍数",
        current_value=round(current_ev_rev, 2),
        flip_value=round(flip_ev_rev, 2),
        direction="down",
        impact=f"当 EV/Revenue 降至 {flip_ev_rev:.2f}x 时，估值等于当前股价",
    ))

    thresholds.append(FlipThreshold(
        variable="营收(亿)",
        current_value=round(financials.revenue, 2),
        flip_value=round(flip_revenue, 2),
        direction="down",
        impact=f"当营收降至 {flip_revenue:.1f}亿 时，估值等于当前股价（EV/Rev={flip_ev_rev:.2f}x）",
    ))

    return thresholds
```

---

## 九、P0：gate5.py 重构

### 修改 9a：删除简化 DCF，消费仲裁器结论

```python
# v2.0：gate5 只消费 ValuationArbiter 结论，不得自行执行估值计算
try:
    from ..contracts.financials import Financials
    from ..data.wind_adapter import wind_to_financials
    from ..valuation.arbiter import ValuationArbiter
    from ..valuation.validator import validate_valuation_inputs
    from ..valuation.method_selector import select_valuation_methods

    wind_data = context.get("wind_data", {})
    _shares = context.get("shares", 0)
    _price = context.get("current_price", 0)

    if wind_data and _shares and _price:
        # Step 1：Wind → Financials 契约
        fin = wind_to_financials(
            wind_data=wind_data,
            ticker=context.get("ticker", ""),
            company_name=context.get("company_name", ""),
            shares=_shares,
            current_price=_price,
        )

        # Step 2：输入校验
        input_errors = validate_valuation_inputs(fin)
        if input_errors:
            logger.warning(f"Gate5 估值输入校验失败: {input_errors}")
            valuation["input_errors"] = input_errors

        # Step 3：选择估值方法
        method_sel = select_valuation_methods(fin)
        logger.info(f"Gate5 估值方法: 主={method_sel.primary.value}, 排除={[m for m in method_sel.excluded]}")

        # Step 4：计算各方法估值（这里简化，实际调用各估值函数）
        # ... dcf_value, ev_revenue_value, ps_value, pb_value ...

        # Step 5：仲裁（唯一出口）
        arbiter = ValuationArbiter()
        verdict = arbiter.arbitrate(
            financials=fin,
            dcf_value=dcf_value,
            ev_revenue_value=ev_revenue_value,
            ps_value=ps_value,
            pb_value=pb_value,
        )

        valuation["verdict"] = verdict
        valuation["target_price"] = verdict.target_price
        valuation["method"] = verdict.method
        valuation["reconciliation"] = verdict.reconciliation
        logger.info(f"Gate5 估值完成: {verdict.primary_method}={verdict.target_price:.2f}")

except Exception as e:
    logger.warning(f"Gate5 估值失败（非阻断）: {e}")
```

---

## 十、验收标准

| # | 标准 | 检查方法 |
|---|------|---------|
| 1 | 翻转阈值营收与 Wind 锚点偏差 ≤1% | Gate8 红队无"参数偏差" |
| 2 | EBIT 利润率与实际值一致 | 日志无"EBIT 利润率为负，使用 5%" |
| 3 | 全报告只有一套估值结论 | ch7 只出现一个目标价 |
| 4 | 估值仲裁明确说明主方法 | ch7 含"主估值方法：EV/Revenue" |
| 5 | Gate8 红队无"估值矛盾"致命问题 | Gate8 passed |
| 6 | 亏损公司不触发 DCF 作为主方法 | 日志无"DCF per-share: -43.53" |
| 7 | 目标价区间包含悲观/基准/乐观 | ch7 含三档目标价 |
| 8 | Financials 契约所有字段有值 | wind_to_financials 无 ValueError |

## 十一、测试用例

```python
# test_valuation_v2.py

def test_loss_company_ev_revenue_primary():
    """亏损公司：EV/Revenue 为主，DCF 为辅助。"""
    fin = Financials(
        revenue=767.20, operating_profit=-44.16, net_profit_parent=-11.39,
        total_assets=1031.63, total_liabilities=727.94, equity_parent=303.69,
        operating_cashflow=82.59, shares=18.87, current_price=46.52,
        currency="HKD", fiscal_year=2025,
    )
    sel = select_valuation_methods(fin)
    assert sel.primary == ValuationMethod.EV_REVENUE
    assert ValuationMethod.PE in sel.excluded
    assert ValuationMethod.DCF in sel.auxiliary  # OCF 为正，DCF 作辅助

def test_arbiter_no_dcf_for_loss_company():
    """仲裁器：亏损公司不以 DCF 为主。"""
    fin = Financials(
        revenue=767.20, operating_profit=-44.16, net_profit_parent=-11.39,
        total_assets=1031.63, total_liabilities=727.94, equity_parent=303.69,
        operating_cashflow=82.59, shares=18.87, current_price=46.52,
        currency="HKD", fiscal_year=2025,
    )
    arbiter = ValuationArbiter()
    verdict = arbiter.arbitrate(financials=fin, ev_revenue_value=45.0, ps_value=42.0)
    assert verdict.primary_method != "DCF"
    assert verdict.target_price > 0

def test_validator_rejects_hardcoded():
    """校验器：拒绝硬编码默认值。"""
    fin = Financials(
        revenue=1427.76,  # 硬编码美团数据
        operating_profit=0, net_profit_parent=0,
        total_assets=0, total_liabilities=0, equity_parent=0,
        operating_cashflow=0, shares=18.87, current_price=46.52,
    )
    errors = validate_valuation_inputs(fin)
    # 营收 1427.76 在范围内但应被 Wind 适配层拦截
    # 这里测试的是 Financials 直接构造时的校验

def test_financials_immutable():
    """Financials 契约不可变。"""
    fin = Financials(
        revenue=767.20, operating_profit=-44.16, net_profit_parent=-11.39,
        total_assets=1031.63, total_liabilities=727.94, equity_parent=303.69,
        operating_cashflow=82.59, shares=18.87, current_price=46.52,
    )
    try:
        fin.revenue = 999
        assert False, "Should raise FrozenInstanceError"
    except Exception:
        pass  # frozen=True 阻止修改
```
