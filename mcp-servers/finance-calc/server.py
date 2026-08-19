#!/usr/bin/env python3
"""finance_calc MCP Server — 金融计算引擎

提供 WACC/DCF/敏感性分析等金融计算工具。
基于 ~/.hermes/tools/investment/finance_calc.py
"""

import sys
from pathlib import Path

# 添加 investment 模块路径
sys.path.insert(0, str(Path.home() / ".hermes" / "tools"))

from mcp.server.fastmcp import FastMCP
from investment.register import register_finance_calc_tools


def main():
    """启动 finance_calc MCP Server"""
    mcp_server = FastMCP(
        "Finance Calculator",
        instructions="金融计算引擎 MCP Server - 提供 WACC 计算、DCF 估值、敏感性分析等金融计算工具"
    )

    # 注册所有 tools
    register_finance_calc_tools(mcp_server)

    print("Finance Calc MCP Server 已启动")
    print("Tools: finance_calc_wacc, finance_calc_dcf, finance_calc_sensitivity, finance_calc_validate")

    mcp_server.run()


if __name__ == "__main__":
    main()
