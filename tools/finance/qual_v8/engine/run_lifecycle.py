"""
执行生命周期管理（v9 新增，对标 dayu host RunPhase 生命周期）。

管理 Run 从 INIT 到 FINALIZE 的阶段流转，每个阶段对应一组 Gate。
"""
from __future__ import annotations

import logging
from datetime import datetime

from ..contracts.types import GATE_PHASE_MAP, RunPhase

logger = logging.getLogger(__name__)


class RunLifecycle:
    """执行生命周期管理。

    对标 dayu host 的 RunPhase 生命周期，管理 Gate0-8 的阶段流转。

    用法：
        lifecycle = RunLifecycle()
        lifecycle.advance(0)  # Gate0 完成，进入 DATA 阶段
        lifecycle.advance(3)  # Gate3 完成，进入 AUDIT 阶段
    """

    def __init__(self) -> None:
        self._phase: RunPhase = RunPhase.INIT
        self._phase_history: list[dict[str, str]] = []
        self._gate_completion: dict[int, str] = {}  # gate_num -> completion_time

    @property
    def phase(self) -> RunPhase:
        """当前阶段。"""
        return self._phase

    def advance(self, gate_num: int) -> RunPhase:
        """Gate 完成后推进生命周期阶段。

        Args:
            gate_num: 完成的 Gate 编号。

        Returns:
            新的 RunPhase。
        """
        target_phase = GATE_PHASE_MAP.get(gate_num, RunPhase.INIT)
        if self._should_advance(target_phase):
            old = self._phase
            self._phase = target_phase
            self._phase_history.append({
                "from": old.value,
                "to": target_phase.value,
                "gate": str(gate_num),
                "timestamp": datetime.now().isoformat(),
            })
            logger.info(f"RunLifecycle: {old.value} → {target_phase.value} (Gate {gate_num})")
        self._gate_completion[gate_num] = datetime.now().isoformat()
        return self._phase

    def _should_advance(self, target: RunPhase) -> bool:
        """判断是否应该推进到目标阶段。"""
        phase_order = list(RunPhase)
        current_idx = phase_order.index(self._phase)
        target_idx = phase_order.index(target)
        return target_idx > current_idx

    def is_complete(self) -> bool:
        """是否已进入 FINALIZE 阶段。"""
        return self._phase == RunPhase.FINALIZE

    def get_history(self) -> list[dict[str, str]]:
        """获取阶段流转历史。"""
        return list(self._phase_history)

    def get_summary(self) -> dict[str, str]:
        """获取生命周期摘要。"""
        return {
            "current_phase": self._phase.value,
            "gates_completed": str(len(self._gate_completion)),
            "phase_transitions": str(len(self._phase_history)),
        }
