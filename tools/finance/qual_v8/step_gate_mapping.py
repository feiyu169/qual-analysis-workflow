"""
Qual流程整合 - Step/Gate映射

将workflow.py的Step映射到qual_v8的Gate 0-8
"""

# Step/Gate映射表
STEP_GATE_MAPPING = {
    # workflow.py Step -> qual_v8 Gate
    "Step 1: 类型推断": {"gate": 1, "name": "类型推断 + 数据提取"},
    "Step 1.5: 自动获取财报": {"gate": 0, "name": "数据源验证"},
    "Step 1.6: 事实提取": {"gate": 1, "name": "类型推断 + 数据提取"},
    "Step 2: 数据收集": {"gate": 2, "name": "数据收集 + 参数提取"},
    "Step 2.5: DCF参数提取": {"gate": 2, "name": "数据收集 + 参数提取"},
    "Step 2.5: 投资论点锚定": {"gate": 2, "name": "数据收集 + 参数提取"},
    "Step 3: 逐章写作": {"gate": 3, "name": "逐章写作"},
    "Step 4: 审计修复": {"gate": 4, "name": "审计修复 + 深度审查"},
    "Step 4.5: 质量增强": {"gate": 5, "name": "质量增强 + 组件集成"},
    "Step 4.5b: v3组件集成": {"gate": 5, "name": "质量增强 + 组件集成"},
    "Step 4.5b: 压力测试": {"gate": 5, "name": "质量增强 + 组件集成"},
    "Step 4.6: Gate Checks": {"gate": 5, "name": "质量增强 + 组件集成"},
    "Step 4.7: 深度审查": {"gate": 4, "name": "审计修复 + 深度审查"},
    "Step 5: 综合结论": {"gate": 6, "name": "综合结论 + 决策章"},
    "Step 5: 决策章": {"gate": 6, "name": "综合结论 + 决策章"},
    "Step 5: 概览章": {"gate": 6, "name": "综合结论 + 决策章"},
    "Step 6: 记忆存储": {"gate": 7, "name": "问题转化 + 记忆存储"},
    "Step 7: 问题转化": {"gate": 7, "name": "问题转化 + 记忆存储"},
}

# Gate -> Step反向映射
GATE_STEP_MAPPING = {
    0: ["Step 1.5: 自动获取财报"],
    1: ["Step 1: 类型推断", "Step 1.6: 事实提取"],
    2: ["Step 2: 数据收集", "Step 2.5: DCF参数提取", "Step 2.5: 投资论点锚定"],
    3: ["Step 3: 逐章写作"],
    4: ["Step 4: 审计修复", "Step 4.7: 深度审查"],
    5: ["Step 4.5: 质量增强", "Step 4.5b: v3组件集成", "Step 4.5b: 压力测试", "Step 4.6: Gate Checks"],
    6: ["Step 5: 综合结论", "Step 5: 决策章", "Step 5: 概览章"],
    7: ["Step 6: 记忆存储", "Step 7: 问题转化"],
    8: [],  # 最终验证（人工确认）
}


def get_gate_for_step(step_name: str) -> int:
    """根据Step名称获取对应的Gate编号"""
    for step_prefix, mapping in STEP_GATE_MAPPING.items():
        if step_name.startswith(step_prefix):
            return mapping["gate"]
    return -1  # 未找到


def get_steps_for_gate(gate_num: int) -> list:
    """根据Gate编号获取对应的Step列表"""
    return GATE_STEP_MAPPING.get(gate_num, [])


def get_gate_name(gate_num: int) -> str:
    """获取Gate名称"""
    gate_names = {
        0: "数据源验证",
        1: "类型推断 + 数据提取",
        2: "数据收集 + 参数提取",
        3: "逐章写作",
        4: "审计修复 + 深度审查",
        5: "质量增强 + 组件集成",
        6: "综合结论 + 决策章",
        7: "问题转化 + 记忆存储",
        8: "最终验证",
    }
    return gate_names.get(gate_num, f"Gate {gate_num}")


def print_mapping():
    """打印映射表"""
    print("=" * 80)
    print("Step/Gate映射表")
    print("=" * 80)
    
    for gate_num in range(9):
        steps = get_steps_for_gate(gate_num)
        gate_name = get_gate_name(gate_num)
        print(f"\nGate {gate_num}: {gate_name}")
        for step in steps:
            print(f"  - {step}")


if __name__ == "__main__":
    print_mapping()
