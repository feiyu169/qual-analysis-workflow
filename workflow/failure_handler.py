"""
失败处理器 - V5 方案实现
失败分类、重试策略、升级机制、审计日志
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

import structlog

logger = structlog.get_logger()


class FailureType(Enum):
    """失败类型"""

    # 可重试失败
    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    TEMPORARY_FAILURE = "temporary_failure"

    # 不可重试失败
    CODE_ERROR = "code_error"
    TEST_FAILURE = "test_failure"
    SECURITY_VULNERABILITY = "security_vulnerability"
    LINT_ERROR = "lint_error"
    DEPENDENCY_VULNERABILITY = "dependency_vulnerability"


@dataclass
class FailureRecord:
    """失败记录"""

    gate_name: str
    failure_type: str
    error_message: str
    exit_code: int
    timestamp: str
    attempt: int
    retryable: bool


@dataclass
class RetryConfig:
    """重试配置"""

    max_retries: int
    retry_delay: int  # 秒
    backoff: str  # exponential, linear, fixed
    scope: str  # single_gate, full_pipeline


@dataclass
class TimeoutConfig:
    """超时配置"""

    L0: str = "1h"
    L1: str = "2h"
    L2: str = "4h"
    L3: str = "24h"
    L3_LITE: str = "4h"
    IAC: str = "2h"
    CONFIG: str = "1h"
    DOCS: str = "1h"


@dataclass
class EscalationRule:
    """升级规则"""

    condition: str
    action: str


class FailureHandlerError(Exception):
    """失败处理错误"""


class FailureHandler:
    """失败处理器"""

    # 可重试失败类型
    RETRYABLE_FAILURES = {
        FailureType.NETWORK_ERROR.value,
        FailureType.TIMEOUT.value,
        FailureType.RATE_LIMIT.value,
        FailureType.TEMPORARY_FAILURE.value,
    }

    # 不可重试失败类型
    NON_RETRYABLE_FAILURES = {
        FailureType.CODE_ERROR.value,
        FailureType.TEST_FAILURE.value,
        FailureType.SECURITY_VULNERABILITY.value,
        FailureType.LINT_ERROR.value,
        FailureType.DEPENDENCY_VULNERABILITY.value,
    }

    # 超时配置
    TIMEOUT_CONFIG = {
        "L0": 3600,  # 1h
        "L1": 7200,  # 2h
        "L2": 14400,  # 4h
        "L3": 86400,  # 24h
        "L3_LITE": 14400,  # 4h
        "IAC": 7200,  # 2h
        "CONFIG": 3600,  # 1h
        "DOCS": 3600,  # 1h
    }

    # 升级规则
    ESCALATION_RULES = [
        EscalationRule(condition="单个门禁连续失败 2 次", action="通知技术负责人"),
        EscalationRule(condition="单个门禁连续失败 3 次", action="冻结流程，人工介入"),
        EscalationRule(condition="整个流水线失败", action="添加 do-not-merge 标签"),
        EscalationRule(condition="超时", action="自动取消，记录原因"),
    ]

    def __init__(self, config: dict = None):
        """初始化失败处理器"""
        self.gate_retry_config = RetryConfig(
            max_retries=config.get("gate_max_retries", 3) if config else 3,
            retry_delay=config.get("gate_retry_delay", 5) if config else 5,
            backoff=config.get("gate_backoff", "exponential")
            if config
            else "exponential",
            scope="single_gate",
        )

        self.pipeline_retry_config = RetryConfig(
            max_retries=config.get("pipeline_max_retries", 1) if config else 1,
            retry_delay=config.get("pipeline_retry_delay", 60) if config else 60,
            backoff="fixed",
            scope="full_pipeline",
        )

        # 失败记录
        self.failure_records: list[FailureRecord] = []

        # 门禁失败计数
        self.gate_failure_counts: dict[str, int] = {}

        # 流水线失败计数
        self.pipeline_failure_count: int = 0

    def classify_failure(self, error_message: str, exit_code: int) -> str:
        """
        分类失败类型

        Args:
            error_message: 错误消息
            exit_code: 退出码

        Returns:
            str: 失败类型
        """
        error_lower = error_message.lower()

        # 网络错误
        if any(
            keyword in error_lower
            for keyword in ["network", "connection", "timeout", "dns"]
        ):
            return FailureType.NETWORK_ERROR.value

        # 超时
        if "timeout" in error_lower or exit_code == -1:
            return FailureType.TIMEOUT.value

        # 限流
        if "rate limit" in error_lower or "429" in error_message:
            return FailureType.RATE_LIMIT.value

        # 测试失败
        if "test" in error_lower and ("fail" in error_lower or "error" in error_lower):
            return FailureType.TEST_FAILURE.value

        # 安全漏洞
        if "vulnerability" in error_lower or "security" in error_lower:
            return FailureType.SECURITY_VULNERABILITY.value

        # lint 错误
        if "lint" in error_lower or "style" in error_lower:
            return FailureType.LINT_ERROR.value

        # 依赖漏洞
        if "dependency" in error_lower or "package" in error_lower:
            return FailureType.DEPENDENCY_VULNERABILITY.value

        # 代码错误
        if exit_code != 0:
            return FailureType.CODE_ERROR.value

        # 默认为临时失败
        return FailureType.TEMPORARY_FAILURE.value

    def is_retryable(self, failure_type: str) -> bool:
        """判断是否可重试"""
        return failure_type in self.RETRYABLE_FAILURES

    def record_failure(
        self,
        gate_name: str,
        failure_type: str,
        error_message: str,
        exit_code: int,
        attempt: int,
    ) -> FailureRecord:
        """
        记录一次失败尝试（**内存态**，V3.2.9 职责澄清）。

        注意与 failure_log.record_failure 的区别：
        - 本方法：进程内计数（重试/升级决策用），进程结束即失；
        - failure_log.record_failure：持久化到 .hgf/failures.jsonl
          （failure-log 纪律门禁的数据层，要求 root_cause/fix）。
        两者互补：本方法管"这次要不要重试/升级"，failure_log 管"这次失败
        有没有被复盘"。不要混用。

        Args:
            gate_name: 门禁名称
            failure_type: 失败类型
            error_message: 错误消息
            exit_code: 退出码
            attempt: 尝试次数

        Returns:
            FailureRecord: 失败记录
        """
        record = FailureRecord(
            gate_name=gate_name,
            failure_type=failure_type,
            error_message=error_message,
            exit_code=exit_code,
            timestamp=datetime.now().isoformat(),
            attempt=attempt,
            retryable=self.is_retryable(failure_type),
        )

        self.failure_records.append(record)

        # 更新门禁失败计数
        if gate_name not in self.gate_failure_counts:
            self.gate_failure_counts[gate_name] = 0
        self.gate_failure_counts[gate_name] += 1

        logger.warning(
            "failure_recorded",
            gate=gate_name,
            failure_type=failure_type,
            attempt=attempt,
            retryable=record.retryable,
        )

        return record

    def should_retry_gate(
        self, gate_name: str, failure_type: str, attempt: int
    ) -> bool:
        """
        判断是否应该重试门禁

        Args:
            gate_name: 门禁名称
            failure_type: 失败类型
            attempt: 当前尝试次数

        Returns:
            bool: 是否应该重试
        """
        # 不可重试的失败类型
        if not self.is_retryable(failure_type):
            logger.info("not_retryable", gate=gate_name, failure_type=failure_type)
            return False

        # 超过最大重试次数
        if attempt >= self.gate_retry_config.max_retries:
            logger.info("max_retries_exceeded", gate=gate_name, attempt=attempt)
            return False

        return True

    def get_retry_delay(self, attempt: int) -> int:
        """
        获取重试延迟时间

        Args:
            attempt: 当前尝试次数

        Returns:
            int: 延迟秒数
        """
        base_delay = self.gate_retry_config.retry_delay

        if self.gate_retry_config.backoff == "exponential":
            return base_delay * (2 ** (attempt - 1))
        elif self.gate_retry_config.backoff == "linear":
            return base_delay * attempt
        else:
            return base_delay

    def should_escalate(self, gate_name: str) -> str | None:
        """
        判断是否应该升级

        Args:
            gate_name: 门禁名称

        Returns:
            Optional[str]: 升级动作，None 表示不需要升级
        """
        failure_count = self.gate_failure_counts.get(gate_name, 0)

        if failure_count >= 3:
            return "冻结流程，人工介入"
        elif failure_count >= 2:
            return "通知技术负责人"

        return None

    def record_pipeline_failure(self):
        """记录流水线失败"""
        self.pipeline_failure_count += 1
        logger.warning("pipeline_failure", count=self.pipeline_failure_count)

    def should_retry_pipeline(self) -> bool:
        """判断是否应该重试流水线"""
        return self.pipeline_failure_count < self.pipeline_retry_config.max_retries

    def get_timeout(self, level: str) -> int:
        """
        获取超时时间

        Args:
            level: 任务等级

        Returns:
            int: 超时秒数
        """
        return self.TIMEOUT_CONFIG.get(level, 3600)

    def format_timeout(self, level: str) -> str:
        """
        格式化超时时间

        Args:
            level: 任务等级

        Returns:
            str: 格式化的超时时间
        """
        seconds = self.get_timeout(level)
        hours = seconds // 3600
        if hours > 0:
            return f"{hours}h"
        minutes = seconds // 60
        return f"{minutes}m"

    def get_failure_summary(self) -> dict:
        """
        获取失败摘要

        Returns:
            Dict: 失败摘要
        """
        total_failures = len(self.failure_records)
        retryable_failures = sum(1 for r in self.failure_records if r.retryable)
        non_retryable_failures = total_failures - retryable_failures

        return {
            "total_failures": total_failures,
            "retryable_failures": retryable_failures,
            "non_retryable_failures": non_retryable_failures,
            "gate_failure_counts": self.gate_failure_counts,
            "pipeline_failure_count": self.pipeline_failure_count,
        }

    def format_failure_report(self) -> str:
        """
        格式化失败报告

        Returns:
            str: 失败报告
        """
        summary = self.get_failure_summary()

        output = []
        output.append("=" * 60)
        output.append("失败处理报告")
        output.append("=" * 60)
        output.append(f"总失败次数: {summary['total_failures']}")
        output.append(f"可重试失败: {summary['retryable_failures']}")
        output.append(f"不可重试失败: {summary['non_retryable_failures']}")
        output.append(f"流水线失败次数: {summary['pipeline_failure_count']}")
        output.append("")

        if summary["gate_failure_counts"]:
            output.append("门禁失败统计:")
            for gate, count in summary["gate_failure_counts"].items():
                output.append(f"  - {gate}: {count} 次")
            output.append("")

        if self.failure_records:
            output.append("失败记录:")
            for record in self.failure_records[-10:]:  # 最近10条
                output.append(f"  [{record.timestamp}] {record.gate_name}")
                output.append(f"    类型: {record.failure_type}")
                output.append(f"    消息: {record.error_message[:100]}")
                output.append(f"    尝试: {record.attempt}")
                output.append(f"    可重试: {record.retryable}")
            output.append("")

        output.append("升级规则:")
        for rule in self.ESCALATION_RULES:
            output.append(f"  - {rule.condition} → {rule.action}")

        output.append("=" * 60)

        return "\n".join(output)

    def reset(self):
        """重置失败处理器"""
        self.failure_records.clear()
        self.gate_failure_counts.clear()
        self.pipeline_failure_count = 0
        logger.info("failure_handler_reset")
