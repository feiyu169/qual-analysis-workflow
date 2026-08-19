"""LLM 调用错误分类（统一契约，供 harness_llm / llm_caller / 上层消费）

v3.1 阶段 A 新增（docs/qual-loop-fix-design-v3.md P0-A/P0-B）。
核心：错误先分类后重试——瞬态可重试、确定性不重试（换策略）、
预算/墙钟耗尽不重试（fail-closed）。
"""
from enum import Enum


class LLMFailureKind(Enum):
    """LLM 失败分类（供熔断/重试/降级策略消费）"""
    TRANSIENT = "transient"          # 瞬态：网络/连接/超时/流中断 → 可重试
    DETERMINISTIC = "deterministic"  # 确定性：预算耗尽空输出/格式错误 → 不重试，换策略
    SEMANTIC = "semantic"            # 语义失败：ok 但内容不合格 → 走业务处理
    CIRCUIT_OPEN = "circuit_open"    # 熔断 → 跳过


class DeterministicLLMFailure(RuntimeError):
    """确定性失败：同一 prompt+model 必然复现，重试无意义。

    携带 finish_reason 与模型信息，供上层换模型/拆任务/降级。
    """
    def __init__(self, message: str, finish_reason=None, model: str | None = None):
        super().__init__(message)
        self.finish_reason = finish_reason
        self.model = model


class LLMCallBudgetExceeded(DeterministicLLMFailure):
    """LLM 调用次数预算耗尽（阶段 A：单 Gate 调用次数硬上限）。

    继承 DeterministicLLMFailure：不重试，fail-closed。
    """
    def __init__(self, message: str = "LLM 调用次数超预算"):
        super().__init__(message, finish_reason="budget")


class WallClockDeadlineExceeded(DeterministicLLMFailure):
    """墙钟截止时间耗尽（阶段 A：全局 deadline 硬上限）。

    继承 DeterministicLLMFailure：不重试，fail-closed。
    """
    def __init__(self, message: str = "墙钟预算耗尽"):
        super().__init__(message, finish_reason="deadline")
