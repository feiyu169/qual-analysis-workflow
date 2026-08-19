"""
Finance Tool Suite - 财报处理工具集

Phase 2: 财报处理
- downloaders: SEC/巨潮/披露易 下载器
- parsers: Docling/MinerU 解析器
- processors: 8个格式提取器 + 表格提取器
- rate_limiter: 速率限制器
- filing_service: 查询服务

Phase 3: 数据层集成
- data_context: 层间数据契约 (DataContext, WindData, FilingData, ...)
- data_collector: 双层数据收集器
- workflow: 投资分析工作流主入口

Phase 4: 质量层
- quality.structural_check: 结构化预检 (Gate 4.1)
- quality.auditor: 审计子代理 (Gate 4.2)
- quality.repairer: 修复子代理 (Gate 4.3)
- quality.checkpoint: 断点恢复 (Gate 4.4)

Phase 5: 记忆集成
- memory.gbrain_writer: GBrain 知识图谱集成 (Gate 5.1)
- memory.flomo_writer: flomo 笔记集成 (Gate 5.2)
- memory.nocturne_writer: nocturne 记忆集成 (Gate 5.3)
- memory.memory_manager: 三层记忆管理器 (Gate 5.4)
"""

__version__ = "5.0.0"
