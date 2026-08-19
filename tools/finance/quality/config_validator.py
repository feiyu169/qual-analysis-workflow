"""
ConfigValidator模块

功能:
- WACC参数验证
- Ke参数验证
- 永续增长率验证
- YAML配置验证

解决: WACC数据源指定问题

"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ValidationResult:
    """验证结果"""
    passed: bool
    message: str
    details: Optional[dict] = None


class ConfigValidator:
    """配置验证器
    
    验证规则:
    - WACC: 6%-18%范围
    - Ke: 5%-25%范围
    - g: 1.5%-3.5%范围
    - g < WACC (数学约束)
    """
    
    # 参数范围
    WACC_RANGE = (0.06, 0.18)
    KE_RANGE = (0.05, 0.25)
    G_RANGE = (0.015, 0.035)
    
    def validate_wacc(self, value: float) -> ValidationResult:
        """验证WACC值"""
        if not isinstance(value, (int, float)):
            return ValidationResult(
                passed=False,
                message=f"WACC必须是数字，当前类型: {type(value).__name__}"
            )
        
        if value < self.WACC_RANGE[0] or value > self.WACC_RANGE[1]:
            return ValidationResult(
                passed=False,
                message=f"WACC={value:.2%}超出合理范围[{self.WACC_RANGE[0]:.0%}, {self.WACC_RANGE[1]:.0%}]"
            )
        
        return ValidationResult(
            passed=True,
            message=f"WACC={value:.2%}验证通过"
        )
    
    def validate_ke(self, value: float) -> ValidationResult:
        """验证Ke值"""
        if not isinstance(value, (int, float)):
            return ValidationResult(
                passed=False,
                message=f"Ke必须是数字，当前类型: {type(value).__name__}"
            )
        
        if value < self.KE_RANGE[0] or value > self.KE_RANGE[1]:
            return ValidationResult(
                passed=False,
                message=f"Ke={value:.2%}超出合理范围[{self.KE_RANGE[0]:.0%}, {self.KE_RANGE[1]:.0%}]"
            )
        
        return ValidationResult(
            passed=True,
            message=f"Ke={value:.2%}验证通过"
        )
    
    def validate_g(self, value: float, wacc: Optional[float] = None) -> ValidationResult:
        """验证永续增长率g"""
        if not isinstance(value, (int, float)):
            return ValidationResult(
                passed=False,
                message=f"g必须是数字，当前类型: {type(value).__name__}"
            )
        
        # 数学约束: g < WACC (优先检查，因为这是硬约束)
        if wacc is not None and value >= wacc:
            return ValidationResult(
                passed=False,
                message=f"g={value:.2%}必须小于WACC={wacc:.2%}（数学约束）"
            )
        
        if value < self.G_RANGE[0] or value > self.G_RANGE[1]:
            return ValidationResult(
                passed=False,
                message=f"g={value:.2%}超出合理范围[{self.G_RANGE[0]:.1%}, {self.G_RANGE[1]:.1%}]"
            )
        
        return ValidationResult(
            passed=True,
            message=f"g={value:.2%}验证通过"
        )
    
    def validate_dcf_params(
        self,
        wacc: float,
        ke: float,
        g: float,
        kd: Optional[float] = None,
        tax_rate: Optional[float] = None,
        debt_ratio: Optional[float] = None
    ) -> List[ValidationResult]:
        """验证DCF参数组合"""
        results = []
        
        # 验证WACC
        results.append(self.validate_wacc(wacc))
        
        # 验证Ke
        results.append(self.validate_ke(ke))
        
        # 验证g (带WACC约束)
        results.append(self.validate_g(g, wacc))
        
        # 验证Kd (如果提供)
        if kd is not None:
            if kd < 0.01 or kd > 0.20:
                results.append(ValidationResult(
                    passed=False,
                    message=f"Kd={kd:.2%}超出合理范围[1%, 20%]"
                ))
            else:
                results.append(ValidationResult(
                    passed=True,
                    message=f"Kd={kd:.2%}验证通过"
                ))
        
        # 验证税率 (如果提供)
        if tax_rate is not None:
            if tax_rate < 0 or tax_rate > 0.50:
                results.append(ValidationResult(
                    passed=False,
                    message=f"税率={tax_rate:.2%}超出合理范围[0%, 50%]"
                ))
            else:
                results.append(ValidationResult(
                    passed=True,
                    message=f"税率={tax_rate:.2%}验证通过"
                ))
        
        # 验证负债比率 (如果提供)
        if debt_ratio is not None:
            if debt_ratio < 0 or debt_ratio > 0.50:
                results.append(ValidationResult(
                    passed=False,
                    message=f"负债比率={debt_ratio:.2%}超出合理范围[0%, 50%]"
                ))
            else:
                results.append(ValidationResult(
                    passed=True,
                    message=f"负债比率={debt_ratio:.2%}验证通过"
                ))
        
        # 验证WACC计算一致性 (如果提供所有参数)
        if kd is not None and tax_rate is not None and debt_ratio is not None:
            # WACC = Ke * (1 - D/(D+E)) + Kd * (1-T) * D/(D+E)
            expected_wacc = ke * (1 - debt_ratio) + kd * (1 - tax_rate) * debt_ratio
            if abs(wacc - expected_wacc) > 0.001:
                results.append(ValidationResult(
                    passed=False,
                    message=f"WACC={wacc:.2%}与计算值{expected_wacc:.2%}不一致",
                    details={
                        'ke': ke,
                        'kd': kd,
                        'tax_rate': tax_rate,
                        'debt_ratio': debt_ratio,
                        'expected_wacc': expected_wacc
                    }
                ))
            else:
                results.append(ValidationResult(
                    passed=True,
                    message=f"WACC计算一致性验证通过"
                ))
        
        return results
    
    def validate_yaml_config(self, config_path: str) -> ValidationResult:
        """验证YAML配置文件"""
        try:
            import yaml
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            if not isinstance(config, dict):
                return ValidationResult(
                    passed=False,
                    message=f"配置文件格式错误: 期望dict，得到{type(config).__name__}"
                )
            
            # 检查必要字段
            required_fields = ['wacc', 'ke', 'g']
            missing_fields = [f for f in required_fields if f not in config]
            
            if missing_fields:
                return ValidationResult(
                    passed=False,
                    message=f"配置文件缺少必要字段: {missing_fields}"
                )
            
            # 验证参数
            results = self.validate_dcf_params(
                wacc=config['wacc'],
                ke=config['ke'],
                g=config['g'],
                kd=config.get('kd'),
                tax_rate=config.get('tax_rate'),
                debt_ratio=config.get('debt_ratio')
            )
            
            # 检查是否有失败
            failed = [r for r in results if not r.passed]
            if failed:
                return ValidationResult(
                    passed=False,
                    message=f"配置验证失败: {[r.message for r in failed]}",
                    details={'results': results}
                )
            
            return ValidationResult(
                passed=True,
                message="配置文件验证通过",
                details={'results': results}
            )
            
        except FileNotFoundError:
            return ValidationResult(
                passed=False,
                message=f"配置文件不存在: {config_path}"
            )
        except yaml.YAMLError as e:
            return ValidationResult(
                passed=False,
                message=f"YAML解析错误: {e}"
            )
        except Exception as e:
            return ValidationResult(
                passed=False,
                message=f"配置验证异常: {e}"
            )
