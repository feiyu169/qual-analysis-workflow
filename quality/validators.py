"""
quality/validators.py — 自动校验机制

定义投资分析中的自动校验规则，避免计算错误和口径不一致。

原则：
1. 每个校验规则有明确的检查逻辑
2. 校验失败有明确的错误信息
3. 校验结果可追溯
4. 支持自定义校验规则
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .formulas import FormulaResult

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """校验结果"""
    is_valid: bool
    checks: list[CheckResult]
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def passed_count(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def failed_count(self) -> int:
        return sum(1 for c in self.checks if not c.passed)

    @property
    def pass_rate(self) -> float:
        if not self.checks:
            return 1.0
        return self.passed_count / len(self.checks)


@dataclass
class CheckResult:
    """单个检查结果"""
    name: str
    passed: bool
    expected: Any = None
    actual: Any = None
    message: str = ""
    severity: str = "error"  # "error" | "warning" | "info"


class Validators:
    """自动校验器"""
    
    # ─────────────────────────────────────────────────
    # 估值校验
    # ─────────────────────────────────────────────────
    
    @staticmethod
    def validate_pe(
        pe_value: float,
        net_income_type: str,
        market_cap: float,
        net_income: float,
        tolerance: float = 0.01
    ) -> ValidationResult:
        """校验PE计算
        
        Args:
            pe_value: 报告中的PE值
            net_income_type: 净利润口径
            market_cap: 市值
            net_income: 净利润
            tolerance: 允许误差（默认1%）
        
        Returns:
            ValidationResult: 校验结果
        """
        checks = []
        warnings = []
        errors = []
        
        # 检查1: PE计算是否正确
        if net_income > 0:
            expected_pe = market_cap / net_income
            deviation = abs(pe_value - expected_pe) / expected_pe
            
            checks.append(CheckResult(
                name="PE计算正确性",
                passed=deviation <= tolerance,
                expected=round(expected_pe, 2),
                actual=round(pe_value, 2),
                message=f"PE计算偏差: {deviation:.2%} (允许: {tolerance:.2%})",
                severity="error" if deviation > tolerance else "info"
            ))
        
        # 检查2: 口径标注
        if net_income_type not in ["GAAP", "adjusted", "core", "deducted"]:
            warnings.append(f"净利润口径'{net_income_type}'非标准口径，请确认")
        
        # 检查3: PE合理性
        if pe_value < 0:
            errors.append(f"PE为负值({pe_value})，无意义")
        elif pe_value > 100:
            warnings.append(f"PE过高({pe_value}倍)，请确认是否使用了正确的净利润口径")
        
        is_valid = all(c.passed for c in checks) and not errors
        
        return ValidationResult(
            is_valid=is_valid,
            checks=checks,
            warnings=warnings,
            errors=errors
        )
    
    @staticmethod
    def validate_pb(
        pb_value: float,
        equity_type: str,
        market_cap: float,
        equity: float,
        tolerance: float = 0.01
    ) -> ValidationResult:
        """校验PB计算
        
        ⚠️ 关键校验：必须使用归母净资产，而非总权益
        
        Args:
            pb_value: 报告中的PB值
            equity_type: 净资产口径
            market_cap: 市值
            equity: 净资产
            tolerance: 允许误差
        
        Returns:
            ValidationResult: 校验结果
        """
        checks = []
        warnings = []
        errors = []
        
        # 检查1: 口径是否正确
        if equity_type == "total":
            errors.append("PB计算使用了总权益，应使用归母净资产")
        elif equity_type != "parent":
            warnings.append(f"净资产口径'{equity_type}'非标准，请确认")
        
        # 检查2: PB计算是否正确
        if equity > 0:
            expected_pb = market_cap / equity
            deviation = abs(pb_value - expected_pb) / expected_pb
            
            checks.append(CheckResult(
                name="PB计算正确性",
                passed=deviation <= tolerance,
                expected=round(expected_pb, 2),
                actual=round(pb_value, 2),
                message=f"PB计算偏差: {deviation:.2%} (允许: {tolerance:.2%})",
                severity="error" if deviation > tolerance else "info"
            ))
        
        # 检查3: PB合理性
        if pb_value < 0:
            errors.append(f"PB为负值({pb_value})，无意义")
        elif pb_value > 10:
            warnings.append(f"PB过高({pb_value}倍)，请确认")
        
        is_valid = all(c.passed for c in checks) and not errors
        
        return ValidationResult(
            is_valid=is_valid,
            checks=checks,
            warnings=warnings,
            errors=errors
        )
    
    @staticmethod
    def validate_market_cap(
        market_cap: float,
        share_price: float,
        total_shares: float,
        tolerance: float = 0.01
    ) -> ValidationResult:
        """校验市值计算
        
        ⚠️ 关键校验：总股本单位必须是亿股
        
        Args:
            market_cap: 报告中的市值
            share_price: 股价
            total_shares: 总股本（亿股）
            tolerance: 允许误差
        
        Returns:
            ValidationResult: 校验结果
        """
        checks = []
        warnings = []
        errors = []
        
        # 检查1: 总股本单位
        if total_shares < 1:
            warnings.append(f"总股本={total_shares}亿股，小于1亿股，请确认单位是否正确（可能是万股）")
        
        # 检查2: 市值计算
        expected_cap = share_price * total_shares
        deviation = abs(market_cap - expected_cap) / max(expected_cap, 0.01)
        
        checks.append(CheckResult(
            name="市值计算正确性",
            passed=deviation <= tolerance,
            expected=round(expected_cap, 2),
            actual=round(market_cap, 2),
            message=f"市值计算偏差: {deviation:.2%} (允许: {tolerance:.2%})",
            severity="error" if deviation > tolerance else "info"
        ))
        
        is_valid = all(c.passed for c in checks) and not errors
        
        return ValidationResult(
            is_valid=is_valid,
            checks=checks,
            warnings=warnings,
            errors=errors
        )
    
    # ─────────────────────────────────────────────────
    # 增长率校验
    # ─────────────────────────────────────────────────
    
    @staticmethod
    def validate_growth_rate(
        growth_value: float,
        current: float,
        previous: float,
        tolerance: float = 0.01
    ) -> ValidationResult:
        """校验增长率计算
        
        Args:
            growth_value: 报告中的增长率（%）
            current: 当期值
            previous: 上期值
            tolerance: 允许误差
        
        Returns:
            ValidationResult: 校验结果
        """
        checks = []
        warnings = []
        errors = []
        
        # 检查1: 增长率计算
        if previous != 0:
            expected_growth = (current - previous) / abs(previous) * 100
            deviation = abs(growth_value - expected_growth) / max(abs(expected_growth), 0.01)
            
            checks.append(CheckResult(
                name="增长率计算正确性",
                passed=deviation <= tolerance,
                expected=round(expected_growth, 2),
                actual=round(growth_value, 2),
                message=f"增长率计算偏差: {deviation:.2%} (允许: {tolerance:.2%})",
                severity="error" if deviation > tolerance else "info"
            ))
        
        # 检查2: 增长率合理性
        if abs(growth_value) > 100:
            warnings.append(f"增长率过高({growth_value}%)，请确认")
        
        is_valid = all(c.passed for c in checks) and not errors
        
        return ValidationResult(
            is_valid=is_valid,
            checks=checks,
            warnings=warnings,
            errors=errors
        )
    
    # ─────────────────────────────────────────────────
    # 财务指标校验
    # ─────────────────────────────────────────────────
    
    @staticmethod
    def validate_financial_consistency(
        revenue: float,
        net_income: float,
        operating_cashflow: float,
        total_assets: float,
        total_equity: float
    ) -> ValidationResult:
        """校验财务指标一致性
        
        Args:
            revenue: 营业收入
            net_income: 净利润
            operating_cashflow: 经营现金流
            total_assets: 总资产
            total_equity: 总权益
        
        Returns:
            ValidationResult: 校验结果
        """
        checks = []
        warnings = []
        errors = []
        
        # 检查1: 净利率合理性
        if revenue > 0:
            net_margin = net_income / revenue * 100
            if net_margin > 50:
                warnings.append(f"净利率过高({net_margin:.1f}%)，请确认")
            elif net_margin < -50:
                warnings.append(f"净利率过低({net_margin:.1f}%)，请确认")
        
        # 检查2: 现金流转化率
        if net_income > 0:
            cash_ratio = operating_cashflow / net_income
            if cash_ratio < 0.5:
                warnings.append(f"现金流转化率过低({cash_ratio:.2f})，盈利质量存疑")
            elif cash_ratio > 2:
                warnings.append(f"现金流转化率过高({cash_ratio:.2f})，请确认")
        
        # 检查3: 资产负债表平衡
        # 注意：这里简化处理，实际应检查 资产 = 负债 + 权益
        
        is_valid = all(c.passed for c in checks) and not errors
        
        return ValidationResult(
            is_valid=is_valid,
            checks=checks,
            warnings=warnings,
            errors=errors
        )
    
    # ─────────────────────────────────────────────────
    # 数据来源校验
    # ─────────────────────────────────────────────────
    
    @staticmethod
    def validate_data_source(
        data_value: float,
        source_name: str,
        source_value: float,
        tolerance: float = 0.05
    ) -> ValidationResult:
        """校验数据来源一致性
        
        Args:
            data_value: 报告中的数据值
            source_name: 数据来源名称（如"Wind"、"年报"）
            source_value: 来源中的数据值
            tolerance: 允许误差（默认5%）
        
        Returns:
            ValidationResult: 校验结果
        """
        checks = []
        warnings = []
        errors = []
        
        # 检查: 数据一致性
        if source_value != 0:
            deviation = abs(data_value - source_value) / abs(source_value)
            
            checks.append(CheckResult(
                name=f"数据来源一致性({source_name})",
                passed=deviation <= tolerance,
                expected=round(source_value, 2),
                actual=round(data_value, 2),
                message=f"与{source_name}数据偏差: {deviation:.2%} (允许: {tolerance:.2%})",
                severity="error" if deviation > tolerance else "info"
            ))
        
        is_valid = all(c.passed for c in checks) and not errors
        
        return ValidationResult(
            is_valid=is_valid,
            checks=checks,
            warnings=warnings,
            errors=errors
        )


class ReportValidator:
    """报告校验器"""
    
    def __init__(self):
        self.validators = Validators()
    
    def validate_report(self, report_data: dict) -> ValidationResult:
        """校验整个报告
        
        Args:
            report_data: 报告数据
                {
                    "company": str,
                    "market_cap": float,
                    "share_price": float,
                    "total_shares": float,
                    "pe": float,
                    "net_income_type": str,
                    "net_income": float,
                    "pb": float,
                    "equity_type": str,
                    "equity": float,
                    ...
                }
        
        Returns:
            ValidationResult: 校验结果
        """
        all_checks = []
        all_warnings = []
        all_errors = []
        
        # 校验市值
        if "market_cap" in report_data and "share_price" in report_data and "total_shares" in report_data:
            result = self.validators.validate_market_cap(
                report_data["market_cap"],
                report_data["share_price"],
                report_data["total_shares"]
            )
            all_checks.extend(result.checks)
            all_warnings.extend(result.warnings)
            all_errors.extend(result.errors)
        
        # 校验PE
        if "pe" in report_data and "net_income" in report_data:
            result = self.validators.validate_pe(
                report_data["pe"],
                report_data.get("net_income_type", "GAAP"),
                report_data.get("market_cap", 0),
                report_data["net_income"]
            )
            all_checks.extend(result.checks)
            all_warnings.extend(result.warnings)
            all_errors.extend(result.errors)
        
        # 校验PB
        if "pb" in report_data and "equity" in report_data:
            result = self.validators.validate_pb(
                report_data["pb"],
                report_data.get("equity_type", "parent"),
                report_data.get("market_cap", 0),
                report_data["equity"]
            )
            all_checks.extend(result.checks)
            all_warnings.extend(result.warnings)
            all_errors.extend(result.errors)
        
        # 校验增长率
        if "growth_value" in report_data and "growth_current" in report_data and "growth_previous" in report_data:
            result = self.validators.validate_growth_rate(
                report_data["growth_value"],
                report_data["growth_current"],
                report_data["growth_previous"]
            )
            all_checks.extend(result.checks)
            all_warnings.extend(result.warnings)
            all_errors.extend(result.errors)
        
        is_valid = all(c.passed for c in all_checks) and not all_errors
        
        return ValidationResult(
            is_valid=is_valid,
            checks=all_checks,
            warnings=all_warnings,
            errors=all_errors
        )
