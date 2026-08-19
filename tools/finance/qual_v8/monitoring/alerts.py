"""
监控告警模块

实现监控指标收集和告警规则
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """告警级别"""
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Alert:
    """告警"""
    name: str
    level: AlertLevel
    message: str
    timestamp: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Metrics:
    """监控指标"""
    gate_pass_rate: Dict[int, float] = field(default_factory=dict)
    gate_avg_duration: Dict[int, float] = field(default_factory=dict)
    gate_failure_count: Dict[int, int] = field(default_factory=dict)
    gate_retry_count: Dict[int, int] = field(default_factory=dict)
    circuit_break_count: int = 0
    human_response_time: float = 0.0
    sla_violation_count: int = 0
    pending_count: int = 0
    api_latency: float = 0.0
    error_rate: float = 0.0
    queue_depth: int = 0


class AlertManager:
    """告警管理器"""
    
    def __init__(self):
        self.alerts: List[Alert] = []
        self.metrics = Metrics()
        self.alert_rules = self._init_alert_rules()
    
    def _init_alert_rules(self) -> List[Dict[str, Any]]:
        """初始化告警规则"""
        return [
            {
                "name": "Gate通过率过低",
                "condition": lambda m: any(rate < 0.80 for rate in m.gate_pass_rate.values()),
                "level": AlertLevel.WARNING,
                "message": "Gate通过率低于80%",
            },
            {
                "name": "Gate连续失败",
                "condition": lambda m: any(count >= 3 for count in m.gate_failure_count.values()),
                "level": AlertLevel.CRITICAL,
                "message": "Gate连续失败3次以上",
            },
            {
                "name": "人工SLA违规",
                "condition": lambda m: m.sla_violation_count >= 5,
                "level": AlertLevel.WARNING,
                "message": "人工SLA违规次数过多",
            },
            {
                "name": "熔断器打开",
                "condition": lambda m: m.circuit_break_count > 0,
                "level": AlertLevel.CRITICAL,
                "message": "熔断器已打开",
            },
            {
                "name": "API延迟过高",
                "condition": lambda m: m.api_latency > 1000,
                "level": AlertLevel.WARNING,
                "message": "API延迟超过1000ms",
            },
            {
                "name": "队列积压",
                "condition": lambda m: m.queue_depth > 100,
                "level": AlertLevel.WARNING,
                "message": "队列积压超过100",
            },
        ]
    
    def update_metrics(self, metrics: Metrics):
        """更新指标"""
        self.metrics = metrics
        self._check_alerts()
    
    def _check_alerts(self):
        """检查告警规则"""
        for rule in self.alert_rules:
            try:
                if rule["condition"](self.metrics):
                    alert = Alert(
                        name=rule["name"],
                        level=rule["level"],
                        message=rule["message"],
                        timestamp=datetime.now().isoformat(),
                    )
                    self.alerts.append(alert)
                    self._send_alert(alert)
            except Exception as e:
                logger.warning(f"告警规则检查失败: {rule['name']}, 错误: {e}")
    
    def _send_alert(self, alert: Alert):
        """发送告警"""
        # 这里应该实现实际的告警发送逻辑
        # 发送到钉钉、邮件、短信等
        logger.warning(f"告警: [{alert.level.value}] {alert.name} - {alert.message}")
    
    def get_alerts(self, level: Optional[AlertLevel] = None) -> List[Alert]:
        """获取告警"""
        if level:
            return [a for a in self.alerts if a.level == level]
        return self.alerts.copy()
    
    def clear_alerts(self):
        """清除告警"""
        self.alerts.clear()


class MetricsCollector:
    """指标收集器"""
    
    def __init__(self):
        self.gate_results: Dict[int, List[Dict[str, Any]]] = {}
        self.execution_times: Dict[int, List[float]] = {}
    
    def record_gate_result(self, gate_num: int, result: Dict[str, Any]):
        """记录Gate结果"""
        if gate_num not in self.gate_results:
            self.gate_results[gate_num] = []
        self.gate_results[gate_num].append(result)
    
    def record_execution_time(self, gate_num: int, duration: float):
        """记录执行时间"""
        if gate_num not in self.execution_times:
            self.execution_times[gate_num] = []
        self.execution_times[gate_num].append(duration)
    
    def get_metrics(self) -> Metrics:
        """获取指标"""
        metrics = Metrics()
        
        # 计算Gate通过率
        for gate_num, results in self.gate_results.items():
            if results:
                passed_count = sum(1 for r in results if r.get("passed", False))
                metrics.gate_pass_rate[gate_num] = passed_count / len(results)
        
        # 计算平均执行时间
        for gate_num, times in self.execution_times.items():
            if times:
                metrics.gate_avg_duration[gate_num] = sum(times) / len(times)
        
        return metrics
