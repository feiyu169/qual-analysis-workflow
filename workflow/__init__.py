"""
Hermes Gate Flow (HGF) - 门禁驱动开发工作流（DSH 接入版，V3.3.2）

模块地图（核心可执行部分）：
- task_classifier / risk_assessor：任务分级与风险评估
- gate_executor / gate_plugin / gate_plugins / gate_types：门禁执行（插件架构）
- lifecycle（lifecycle_dag / lifecycle_checkers / lifecycle_metrics）：生命周期 DAG
- tool_runner / state_io：共享工具执行与原子写入（V3.3-R1/R2）
- failure_log：结构化失败记录（HGF 纪律门禁的数据层；V3.3.2 含归档机制）
- false_positive_checker：已知误报/豁免
- workflow_cli：命令行入口（分级+风评+门禁+生命周期）
- mcp_server：MCP 服务入口（hermes 兼容）
- _legacy/：已归档的未接线模块（见 _legacy/README.md）
"""

__version__ = "3.4.0"
