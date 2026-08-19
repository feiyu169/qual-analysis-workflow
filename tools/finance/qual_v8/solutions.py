"""
Qual流程整合 - 解决方案

问题1: Gate状态未更新
问题2: 审查修复循环修复能力不足
问题3: enforce模式未验证
"""

# Step/Gate映射
STEP_GATE_MAP = {
    "Step 1": {"step_num": "1", "gate_num": 1},
    "Step 1.5": {"step_num": "1.5", "gate_num": 0},
    "Step 1.6": {"step_num": "1.6", "gate_num": 1},
    "Step 2": {"step_num": "2", "gate_num": 2},
    "Step 2.5": {"step_num": "2.5", "gate_num": 2},
    "Step 3": {"step_num": "3", "gate_num": 3},
    "Step 4": {"step_num": "4", "gate_num": 4},
    "Step 4.5": {"step_num": "4.5", "gate_num": 5},
    "Step 4.5b": {"step_num": "4.5b", "gate_num": 5},
    "Step 4.6": {"step_num": "4.6", "gate_num": 5},
    "Step 4.7": {"step_num": "4.7", "gate_num": 4},
    "Step 5": {"step_num": "5", "gate_num": 6},
    "Step 6": {"step_num": "6", "gate_num": 7},
    "Step 7": {"step_num": "7", "gate_num": 7},
}


def get_gate_for_step(step_name: str) -> int:
    """根据Step名称获取对应的Gate编号"""
    for prefix, mapping in STEP_GATE_MAP.items():
        if step_name.startswith(prefix):
            return mapping["gate_num"]
    return -1
