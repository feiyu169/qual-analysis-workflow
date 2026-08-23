"""
Qual v9 轻量存储协议层。

3 个窄 Protocol（参照 dayu-agent fins/storage/repository_protocols.py 的窄 Protocol 设计）：
- AuditLogProtocol: 审计日志
- SnapshotProtocol: 输入快照
- ReportVersionProtocol: 报告版本

默认实现：文件系统（JSON 文件），不引入 SQLite/数据库依赖。
"""
from .audit_log import AuditLogProtocol, FileAuditLog
from .report_version import FileReportVersion, ReportVersionProtocol
from .snapshot import FileSnapshot, SnapshotProtocol

__all__ = [
    "AuditLogProtocol",
    "FileAuditLog",
    "FileReportVersion",
    "FileSnapshot",
    "ReportVersionProtocol",
    "SnapshotProtocol",
]
