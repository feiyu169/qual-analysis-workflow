"""
参数传递强制检查装饰器

功能：
1. 强制检查参数是否传递
2. 值域校验
3. 参数约束配置
"""

from functools import wraps
import inspect
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Set, List

logger = logging.getLogger(__name__)


@dataclass
class ParamConstraint:
    """参数约束"""
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    allowed_values: Optional[Set] = None
    validator: Optional[Callable] = None
    description: str = ""


class ParamRegistry:
    """参数注册表"""
    
    # 参数约束配置
    PARAM_CONSTRAINTS: Dict[str, ParamConstraint] = {
        "base_wacc": ParamConstraint(
            min_value=0.03,
            max_value=0.25,
            description="加权平均资本成本"
        ),
        "base_terminal_growth": ParamConstraint(
            min_value=0.01,
            max_value=0.05,
            description="永续增长率"
        ),
        "shares": ParamConstraint(
            min_value=0,
            description="总股本"
        ),
        "current_price": ParamConstraint(
            min_value=0,
            description="当前股价"
        ),
        "tax_rate": ParamConstraint(
            min_value=0,
            max_value=0.5,
            description="税率"
        ),
    }
    
    @classmethod
    def validate_param(cls, name: str, value: Any) -> Optional[str]:
        """验证参数值"""
        constraint = cls.PARAM_CONSTRAINTS.get(name)
        if not constraint:
            return None
        
        if constraint.min_value is not None and value < constraint.min_value:
            return f"参数'{name}'值{value}小于最小值{constraint.min_value}"
        
        if constraint.max_value is not None and value > constraint.max_value:
            return f"参数'{name}'值{value}大于最大值{constraint.max_value}"
        
        if constraint.allowed_values is not None and value not in constraint.allowed_values:
            return f"参数'{name}'值{value}不在允许值{constraint.allowed_values}中"
        
        if constraint.validator is not None:
            error = constraint.validator(value)
            if error:
                return f"参数'{name}'验证失败: {error}"
        
        return None
    
    @classmethod
    def add_constraint(cls, name: str, constraint: ParamConstraint):
        """添加参数约束"""
        cls.PARAM_CONSTRAINTS[name] = constraint


def require_params(*param_names, validate_values: bool = True):
    """
    装饰器：强制检查参数是否传递+值域校验
    
    使用示例：
        @require_params('base_wacc', 'base_terminal_growth')
        def run_depth_enhancement(
            chapters,
            financials,
            valuation_value,
            current_price,
            shares,
            base_wacc,  # 无默认值
            base_terminal_growth,  # 无默认值
        ):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 获取函数签名
            sig = inspect.signature(func)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            
            # 检查必需参数
            for name in param_names:
                if name not in bound.arguments:
                    raise ValueError(
                        f"参数'{name}'未传递，不允许使用默认值。"
                        f"函数: {func.__name__}, 参数列表: {list(bound.arguments.keys())}"
                    )
                
                # 检查是否为默认值
                param = sig.parameters.get(name)
                if param and param.default is not inspect.Parameter.empty:
                    if bound.arguments[name] == param.default:
                        raise ValueError(
                            f"参数'{name}'使用了默认值{param.default}，必须显式传递。"
                            f"函数: {func.__name__}"
                        )
                
                # 值域校验
                if validate_values:
                    value = bound.arguments[name]
                    error = ParamRegistry.validate_param(name, value)
                    if error:
                        raise ValueError(f"{error}。函数: {func.__name__}")
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


def require_params_async(*param_names, validate_values: bool = True):
    """
    异步版本装饰器
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 获取函数签名
            sig = inspect.signature(func)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            
            # 检查必需参数
            for name in param_names:
                if name not in bound.arguments:
                    raise ValueError(
                        f"参数'{name}'未传递，不允许使用默认值。"
                        f"函数: {func.__name__}, 参数列表: {list(bound.arguments.keys())}"
                    )
                
                # 检查是否为默认值
                param = sig.parameters.get(name)
                if param and param.default is not inspect.Parameter.empty:
                    if bound.arguments[name] == param.default:
                        raise ValueError(
                            f"参数'{name}'使用了默认值{param.default}，必须显式传递。"
                            f"函数: {func.__name__}"
                        )
                
                # 值域校验
                if validate_values:
                    value = bound.arguments[name]
                    error = ParamRegistry.validate_param(name, value)
                    if error:
                        raise ValueError(f"{error}。函数: {func.__name__}")
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator
