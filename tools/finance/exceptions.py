"""
Finance Exceptions - 金融工具异常定义

所有金融工具的自定义异常类。
"""


class DataCollectionError(Exception):
    """数据收集失败异常
    
    当数据源（披露易、Wind MCP、搜索等）无法提供数据时抛出。
    不允许静默降级返回假数据。
    """
    pass


class FilingDownloadError(DataCollectionError):
    """财报下载失败异常"""
    pass


class FilingParseError(Exception):
    """财报解析失败异常"""
    pass


class WindMCPError(DataCollectionError):
    """Wind MCP 调用失败异常"""
    pass


class DataContextError(Exception):
    """DataContext 数据不完整异常"""
    pass
