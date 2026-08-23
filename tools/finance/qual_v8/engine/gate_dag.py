"""
Gate 依赖有向无环图（v9 新增，对标 dayu host 生命周期管理）。

替代线性链 Gate0→1→2→...→8，支持：
- HARD 依赖：前置 Gate 必须 PASSED（如 Gate2 依赖 Gate1 数据）
- SOFT 依赖（降级）：前置 Gate FAILED 时仍执行，但标记 DEGRADED（如 Gate5 不依赖 Gate4）
- 发布门禁：最终报告是否可发布取决于 HARD 依赖全部 PASSED

设计原则（来自 HeavySkill K8 审查）：
- "数据依赖 vs 质量门禁分离"：Gate 间依赖应是"需要哪些数据"，而非"前一个 Gate 是否通过"
- "降级执行"：前置 Gate 失败时后续 Gate 应降级运行，而非完全跳过
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GateDependency:
    """Gate 依赖描述。

    Attributes:
        gate_num: Gate 编号。
        hard_deps: 硬依赖（前置 Gate 必须 PASSED）。
        soft_deps: 软依赖（前置 Gate FAILED 时降级运行）。
    """
    gate_num: int
    hard_deps: tuple[int, ...] = ()
    soft_deps: tuple[int, ...] = ()


# 默认依赖图（对标 dayu DAG + HeavySkill K8 审查建议）
# Phase 1: 数据准备（HARD 依赖）
# Phase 2: 内容生成（HARD 依赖 Gate2）
# Phase 3: 审计修复（HARD 依赖 Gate3）
# Phase 4: 增强决策（SOFT 依赖 Gate4，不阻塞）
# Phase 5: 终局验证（HARD 依赖 Gate3，SOFT 依赖 Gate4-7）
DEFAULT_GATE_DEPS: dict[int, GateDependency] = {
    0: GateDependency(gate_num=0),  # 无依赖
    1: GateDependency(gate_num=1, hard_deps=(0,)),
    2: GateDependency(gate_num=2, hard_deps=(1,)),
    3: GateDependency(gate_num=3, hard_deps=(2,)),
    4: GateDependency(gate_num=4, hard_deps=(3,)),  # 审计修复依赖章节内容
    5: GateDependency(gate_num=5, hard_deps=(3,), soft_deps=(4,)),  # 估值不依赖审计
    6: GateDependency(gate_num=6, hard_deps=(3,), soft_deps=(4, 5)),  # 结论不依赖审计
    7: GateDependency(gate_num=7, hard_deps=(3,), soft_deps=(4, 5, 6)),  # 问题转化
    8: GateDependency(gate_num=8, hard_deps=(3,), soft_deps=(4, 5, 6, 7)),  # 终局
}


@dataclass
class GateDAG:
    """Gate 依赖有向无环图。

    用法：
        dag = GateDAG()
        ready = dag.get_ready(completed={0, 1, 2})  # [3]
        degraded = dag.get_degraded_gate5(completed={0,1,2,3}, gate4_passed=False)  # 5 可降级
    """

    def __init__(self, deps: dict[int, GateDependency] | None = None) -> None:
        self._deps = deps or DEFAULT_GATE_DEPS

    def get_deps(self, gate_num: int) -> GateDependency:
        """获取某 Gate 的依赖描述。"""
        return self._deps.get(gate_num, GateDependency(gate_num=gate_num))

    def can_execute(self, gate_num: int, gate_results: dict[int, object]) -> tuple[bool, bool]:
        """判断 Gate 是否可执行。

        Args:
            gate_num: Gate 编号。
            gate_results: 已完成的 Gate 结果 {gate_num: GateResult}。

        Returns:
            (can_run, is_degraded):
                can_run: 是否可执行（hard deps 全 PASSED）
                is_degraded: 是否降级运行（有 soft dep FAILED/SKIPPED）
        """
        dep = self.get_deps(gate_num)

        # HARD 依赖：全部必须 PASSED
        for hard in dep.hard_deps:
            result = gate_results.get(hard)
            if result is None:
                return False, False  # 前置 Gate 未执行
            # 兼容 contracts.GateResult（state 属性）和 workflow dict（passed/score 字段）
            state = self._extract_state(result)
            if state != 'passed':
                return False, False

        # SOFT 依赖：有 FAILED/SKIPPED → 降级运行
        degraded = False
        for soft in dep.soft_deps:
            result = gate_results.get(soft)
            if result is None:
                continue
            state = self._extract_state(result)
            if hasattr(state, 'value'):
                state = state.value
            if str(state) not in ('passed', 'degraded'):
                degraded = True

        return True, degraded

    def _extract_state(self, result: object) -> str:
        """从 result 中提取状态字符串（兼容 GateResult 和 dict）。

        Args:
            result: GateResult 或 dict（workflow.py 中 gate_results 的值）。

        Returns:
            状态字符串（'passed'/'failed'/'degraded'/'blocked'/'skipped'）。
        """
        # contracts.GateResult: state 属性
        state = getattr(result, 'state', None)
        if state is not None:
            return state.value if hasattr(state, 'value') else str(state)
        # workflow dict: passed 字段
        if isinstance(result, dict):
            if result.get('state'):
                return str(result['state'])
            return 'passed' if result.get('passed', False) else 'failed'
        # 旧 GateResult: passed 字段
        return 'passed' if getattr(result, 'passed', False) else 'failed'

    def get_ready(self, gate_results: dict[int, object]) -> list[int]:
        """获取所有可执行的 Gate（HARD 依赖全满足）。"""
        ready = []
        for gate_num in sorted(self._deps.keys()):
            can_run, _ = self.can_execute(gate_num, gate_results)
            if can_run and gate_num not in gate_results:
                ready.append(gate_num)
        return ready

    def get_phase(self, gate_num: int) -> str:
        """获取 Gate 所属阶段。"""
        from ..contracts.types import GATE_PHASE_MAP, RunPhase
        phase = GATE_PHASE_MAP.get(gate_num, RunPhase.INIT)
        return phase.value if hasattr(phase, 'value') else str(phase)

    def is_publishable(self, gate_results: dict[int, object]) -> bool:
        """判断报告是否可发布（所有 HARD 依赖 PASSED）。

        Gate 8 的 hard_deps = (3,)，即 Gate3 必须 PASSED。
        Gate4-7 是 soft_deps，失败不阻断发布（标注降级）。
        """
        for gate_num in self._deps:
            dep = self._deps[gate_num]
            for hard in dep.hard_deps:
                result = gate_results.get(hard)
                if result is None:
                    return False
                state = self._extract_state(result)
                if state != 'passed':
                    return False
        return True
