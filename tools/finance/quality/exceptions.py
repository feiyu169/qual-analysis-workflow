"""
quality/exceptions.py — 异常体系模块

定义推理引擎的异常层次结构：
- InferenceError: 根异常
- BudgetExceededError: 预算耗尽
- CircuitOpenError: 熔断触发
- CalculationError: 计算失败
- DataQualityError: 数据质量不足
- ModelInferenceError: 模型推理失败
- MarketNotSupportedError: 市场不支持
"""


class InferenceError(Exception):
    """推理系统根异常"""
    pass


class BudgetExceededError(InferenceError):
    """预算耗尽异常
    
    当ReasoningBudget的remaining_time/calls/tokens不足时抛出
    """
    def __init__(self, message: str = "推理预算耗尽", budget_info: dict = None):
        super().__init__(message)
        self.budget_info = budget_info or {}


class CircuitOpenError(InferenceError):
    """熔断触发异常
    
    当CircuitBreaker状态为OPEN时抛出
    """
    def __init__(self, message: str = "熔断器已触发", failure_count: int = 0):
        super().__init__(message)
        self.failure_count = failure_count


class CalculationError(InferenceError):
    """计算失败异常
    
    通用计算错误，如数值溢出、除零等
    """
    pass


class DataQualityError(InferenceError):
    """数据质量不足异常
    
    当数据完整性、时效性不满足要求时抛出
    """
    def __init__(self, message: str = "数据质量不足", missing_fields: list = None):
        super().__init__(message)
        self.missing_fields = missing_fields or []


class ModelInferenceError(InferenceError):
    """模型推理失败异常
    
    当LLM调用失败、超时、返回格式错误时抛出
    """
    def __init__(self, message: str = "模型推理失败", model_name: str = None):
        super().__init__(message)
        self.model_name = model_name


class MarketNotSupportedError(InferenceError):
    """市场不支持异常
    
    当请求的市场不在支持列表中时抛出
    """
    def __init__(self, message: str = "市场不支持", market: str = None):
        super().__init__(message)
        self.market = market
