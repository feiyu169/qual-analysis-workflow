"""
Qual流程整合 - 渐进式激活

支持三种模式：
- shadow：仅记录，不阻断
- soft：告警，不阻断
- enforce：阻断
"""

from enum import Enum
from typing import Dict, Any, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


class QualMode(Enum):
    """Qual流程模式"""
    SHADOW = "shadow"  # 仅记录，不阻断
    SOFT = "soft"      # 告警，不阻断
    ENFORCE = "enforce"  # 阻断


@dataclass
class ModeConfig:
    """模式配置"""
    mode: QualMode
    
    # 各组件的行为
    state_machine_enabled: bool
    audit_logger_enabled: bool
    supervisor_enabled: bool
    supervisor_blocking: bool  # 是否阻断
    circuit_breaker_enabled: bool
    monitoring_enabled: bool


# 模式配置
MODE_CONFIGS = {
    QualMode.SHADOW: ModeConfig(
        mode=QualMode.SHADOW,
        state_machine_enabled=True,
        audit_logger_enabled=True,
        supervisor_enabled=True,
        supervisor_blocking=False,  # 不阻断
        circuit_breaker_enabled=False,  # 不启用
        monitoring_enabled=True,
    ),
    QualMode.SOFT: ModeConfig(
        mode=QualMode.SOFT,
        state_machine_enabled=True,
        audit_logger_enabled=True,
        supervisor_enabled=True,
        supervisor_blocking=False,  # 不阻断，但告警
        circuit_breaker_enabled=True,
        monitoring_enabled=True,
    ),
    QualMode.ENFORCE: ModeConfig(
        mode=QualMode.ENFORCE,
        state_machine_enabled=True,
        audit_logger_enabled=True,
        supervisor_enabled=True,
        supervisor_blocking=True,  # 阻断
        circuit_breaker_enabled=True,
        monitoring_enabled=True,
    ),
}


class ModeManager:
    """模式管理器"""
    
    def __init__(self, initial_mode: QualMode = QualMode.SHADOW):
        self.current_mode = initial_mode
        self.mode_history = []
    
    def get_config(self) -> ModeConfig:
        """获取当前模式配置"""
        return MODE_CONFIGS[self.current_mode]
    
    def switch_mode(self, new_mode: QualMode):
        """切换模式"""
        old_mode = self.current_mode
        self.current_mode = new_mode
        self.mode_history.append({
            "from": old_mode.value,
            "to": new_mode.value,
            "timestamp": __import__('datetime').datetime.now().isoformat(),
        })
        logger.info(f"[Qual] 模式切换: {old_mode.value} -> {new_mode.value}")
    
    def is_shadow(self) -> bool:
        """是否为shadow模式"""
        return self.current_mode == QualMode.SHADOW
    
    def is_soft(self) -> bool:
        """是否为soft模式"""
        return self.current_mode == QualMode.SOFT
    
    def is_enforce(self) -> bool:
        """是否为enforce模式"""
        return self.current_mode == QualMode.ENFORCE
    
    def should_block(self) -> bool:
        """是否应该阻断"""
        return self.current_mode == QualMode.ENFORCE


# 环境变量控制
QUAL_MODE_ENV_VAR = "QUAL_MODE"


def get_initial_mode() -> QualMode:
    """从环境变量获取初始模式"""
    import os
    mode_str = os.environ.get(QUAL_MODE_ENV_VAR, "shadow").lower()
    
    try:
        return QualMode(mode_str)
    except ValueError:
        logger.warning(f"[Qual] 未知的QUAL_MODE: {mode_str}，使用默认shadow模式")
        return QualMode.SHADOW
