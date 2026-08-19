#!/usr/bin/env python3
"""
Wind MCP Server - 万得金融数据 MCP 服务（使用官方 CLI）

提供股票行情、财务数据、估值指标、行业数据、宏观经济、财经新闻等金融数据查询功能。
使用官方 wind-mcp-skill CLI 调用 Wind AIFin Market API。

股票代码格式: 600519.SH, 1810.HK, AAPL.OQ
日期格式: YYYY-MM-DD
"""

import asyncio
import json
import os
import subprocess
from pathlib import Path
from datetime import datetime, timedelta


# ─── Configuration ─────────────────────────────────────────────────────────────

SKILL_DIR = Path.home() / ".hermes" / "skills" / "wind-mcp-skill"


def _get_api_key() -> str:
    """读取 API Key，优先从环境变量，其次从配置文件。"""
    # 1. 环境变量
    key = os.environ.get("WIND_API_KEY", "").strip()
    if key:
        return key

    # 2. 配置文件 ~/.wind-aifinmarket/config
    config_path = Path.home() / ".wind-aifinmarket" / "config"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if "WIND_API_KEY" in line and "=" in line:
                        key = line.split("=", 1)[1].strip()
                        if key:
                            return key
        except Exception:
            pass

    return ""


def _call_wind_api(server_type: str, tool_name: str, params: dict) -> dict:
    """
    调用 Wind AIFin Market API（通过官方 CLI）。

    Args:
        server_type: 服务器类型（stock_data, fund_data, index_data 等）
        tool_name: 工具名称
        params: 工具参数

    Returns:
        dict: {"success": True, "data": ...} 或 {"success": False, "error": "..."}
    """
    api_key = _get_api_key()
    if not api_key:
        return {
            "success": False,
            "error": "未找到 Wind API Key。请设置环境变量 WIND_API_KEY 或在 ~/.wind-aifinmarket/config 文件中配置"
        }

    # 检查 CLI 脚本是否存在
    cli_path = SKILL_DIR / "scripts" / "cli.mjs"
    if not cli_path.exists():
        return {
            "success": False,
            "error": f"CLI 脚本不存在: {cli_path}"
        }

    # 构建 CLI 命令 - 使用 shell=True 避免 Node.js 输出缓冲问题
    import shlex
    cmd_str = f'cd {SKILL_DIR} && WIND_API_KEY={shlex.quote(api_key)} node scripts/cli.mjs call {server_type} {tool_name} {shlex.quote(json.dumps(params))}'

    try:
        result = subprocess.run(
            cmd_str,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                # CLI 返回 MCP 格式: {"content": [{"type": "text", "text": "..."}], "isError": false}
                # 需要解析 content[0].text 中的实际数据
                if isinstance(data, dict) and "content" in data:
                    inner_text = data.get("content", [{}])[0].get("text", "")
                    if inner_text:
                        try:
                            inner_data = json.loads(inner_text)
                            # 检查是否有业务错误
                            if isinstance(inner_data, dict):
                                if inner_data.get("error"):
                                    return {"success": False, "error": str(inner_data["error"])}
                                if inner_data.get("mcp_tool_error_code", 0) != 0:
                                    return {"success": False, "error": inner_data.get("mcp_tool_error_msg", "工具错误")}
                            return {"success": True, "data": inner_data}
                        except json.JSONDecodeError:
                            return {"success": True, "data": inner_text}
                # 非 MCP 格式，直接返回
                return {"success": True, "data": data}
            except json.JSONDecodeError:
                return {"success": True, "data": result.stdout}
        else:
            # 尝试解析错误
            try:
                error_data = json.loads(result.stdout)
                if "error" in error_data:
                    return {"success": False, "error": error_data["error"].get("message", result.stdout)}
            except:
                pass
            return {"success": False, "error": result.stderr or result.stdout or "未知错误"}

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "请求超时"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _get_server_type(tool_name: str) -> str:
    """根据工具名称确定 server_type"""
    if "stock" in tool_name:
        return "stock_data"
    elif "fund" in tool_name:
        return "fund_data"
    elif "index" in tool_name:
        return "index_data"
    elif "bond" in tool_name:
        return "bond_data"
    elif "financial" in tool_name or "news" in tool_name:
        return "financial_docs"
    elif "economic" in tool_name or "macro" in tool_name:
        return "economic_data"
    else:
        return "analytics_data"


def _format_date(date_str: str) -> str:
    """将 YYYY-MM-DD 格式转换为 yyyyMMdd 格式"""
    if not date_str:
        return date_str
    # 移除可能的连字符
    return date_str.replace("-", "")


def _build_financial_question(windcode: str, report_type: str, startdate: str = "", enddate: str = "") -> str:
    """将 windcode + type 参数转换为自然语言 question"""
    # 报表类型映射
    type_map = {
        "income": "利润表",
        "balance": "资产负债表",
        "cashflow": "现金流量表"
    }
    report_name = type_map.get(report_type, report_type)
    
    # 构建问题
    question = f"{windcode}{startdate[:4] if startdate else ''}年{report_name}"
    if enddate:
        question += f"至{enddate[:4]}年"
    return question


# ─── MCP Tool Definitions ──────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "wind_stock_quote",
        "description": "股票实时行情。获取指定股票的最新价格、涨跌幅、成交量、成交额等实时数据。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "windcode": {
                    "type": "string",
                    "description": "股票代码，如 600519.SH, 1810.HK, AAPL.OQ"
                }
            },
            "required": ["windcode"]
        }
    },
    {
        "name": "wind_stock_history",
        "description": "股票历史行情。获取指定股票在时间区间内的历史K线数据（开高低收、成交量、成交额等）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "windcode": {"type": "string", "description": "股票代码"},
                "startdate": {"type": "string", "description": "开始日期 (YYYY-MM-DD)"},
                "enddate": {"type": "string", "description": "结束日期 (YYYY-MM-DD)"},
                "period": {"type": "string", "enum": ["day", "week", "month"], "description": "K线周期：day=日K, week=周K, month=月K"}
            },
            "required": ["windcode", "startdate"]
        }
    },
    {
        "name": "wind_financial_data",
        "description": "财务数据。获取上市公司财务报表数据，包括利润表(income)、资产负债表(balance)、现金流量表(cashflow)。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "windcode": {"type": "string", "description": "股票代码"},
                "type": {"type": "string", "enum": ["income", "balance", "cashflow"], "description": "报表类型：income=利润表, balance=资产负债表, cashflow=现金流量表"},
                "startdate": {"type": "string", "description": "开始日期 (YYYY-MM-DD)，可选"},
                "enddate": {"type": "string", "description": "结束日期 (YYYY-MM-DD)，可选"}
            },
            "required": ["windcode", "type"]
        }
    },
    {
        "name": "wind_valuation",
        "description": "估值指标。获取股票的 PE(市盈率)、PB(市净率)、PS(市销率)、股息率、总市值、流通市值等估值数据。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "windcode": {"type": "string", "description": "股票代码"}
            },
            "required": ["windcode"]
        }
    },
    {
        "name": "wind_industry_data",
        "description": "行业数据。获取行业分类、行业指数行情、行业成分股列表等信息。action 可选: classify(行业分类), index(行业指数), members(成分股)。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["classify", "index", "members"], "description": "操作类型"},
                "industry": {"type": "string", "description": "行业名称或代码"},
                "market": {"type": "string", "description": "市场（可选）"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "wind_macro_data",
        "description": "宏观经济数据。获取 GDP、CPI、PPI、PMI、M2、社融、利率、汇率等宏观经济指标数据。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "indicator": {"type": "string", "description": "指标名称，如 GDP, CPI, PPI, PMI, M2"},
                "startdate": {"type": "string", "description": "开始日期"},
                "enddate": {"type": "string", "description": "结束日期"},
                "frequency": {"type": "string", "enum": ["day", "month", "quarter", "year"], "description": "数据频率"}
            },
            "required": ["indicator"]
        }
    },
    {
        "name": "wind_financial_news",
        "description": "财经新闻。获取最新的财经新闻、公司公告、研究报告等信息。可按关键词、股票代码、新闻类别筛选。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "关键词"},
                "windcode": {"type": "string", "description": "股票代码"},
                "category": {"type": "string", "description": "新闻类别"},
                "count": {"type": "integer", "description": "返回条数"}
            },
            "required": []
        }
    },
    {
        "name": "wind_health_check",
        "description": "健康检查。测试 Wind API 连接状态和 API Key 有效性。",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    }
]


# ─── MCP Server Implementation ─────────────────────────────────────────────────

async def handle_tool_call(tool_name: str, arguments: dict) -> dict:
    """处理工具调用"""
    
    # 特殊处理 wind_health_check
    if tool_name == "wind_health_check":
        api_key = _get_api_key()
        if not api_key:
            return {"success": False, "error": "未配置 API Key"}
        
        # 测试调用
        result = _call_wind_api("stock_data", "get_stock_quote", {"windcode": "600519.SH"})
        if result["success"]:
            return {"success": True, "data": {"status": "ok", "api_key_configured": True, "detail": "Wind API 正常工作"}}
        else:
            return {"success": False, "error": result["error"]}
    
    # 工具名映射
    tool_mapping = {
        "wind_stock_quote": ("stock_data", "get_stock_quote"),
        "wind_stock_history": ("stock_data", "get_stock_kline"),
        "wind_financial_data": ("stock_data", "get_stock_fundamentals"),
        "wind_valuation": ("stock_data", "get_stock_price_indicators"),
        "wind_industry_data": ("analytics_data", "get_financial_data"),
        "wind_macro_data": ("economic_data", "get_economic_data"),
        "wind_financial_news": ("financial_docs", "search_news"),
        # 直接工具名映射
        "get_stock_quote": ("stock_data", "get_stock_quote"),
        "get_stock_kline": ("stock_data", "get_stock_kline"),
        "get_stock_fundamentals": ("stock_data", "get_stock_fundamentals"),
        "get_stock_price_indicators": ("stock_data", "get_stock_price_indicators"),
        "search_stocks": ("stock_data", "search_stocks"),
        "get_stock_basicinfo": ("stock_data", "get_stock_basicinfo"),
        "get_stock_equity_holders": ("stock_data", "get_stock_equity_holders"),
        "get_stock_events": ("stock_data", "get_stock_events"),
        "get_stock_technicals": ("stock_data", "get_stock_technicals"),
        "get_risk_metrics": ("stock_data", "get_risk_metrics"),
    }
    
    if tool_name in tool_mapping:
        server_type, mapped_tool = tool_mapping[tool_name]
        
        # 参数转换：wind_stock_history
        if tool_name == "wind_stock_history":
            # 转换日期格式：YYYY-MM-DD -> yyyyMMdd
            converted_args = {
                "windcode": arguments.get("windcode", ""),
                "begin_date": _format_date(arguments.get("startdate", "")),
                "end_date": _format_date(arguments.get("enddate", "")),
            }
            # period 转换
            period = arguments.get("period", "day")
            period_map = {"day": "10", "week": "11", "month": "12"}
            converted_args["period"] = period_map.get(period, "10")
            arguments = converted_args
        
        # 参数转换：wind_financial_data
        elif tool_name == "wind_financial_data":
            # 转换为 question 格式
            question = _build_financial_question(
                arguments.get("windcode", ""),
                arguments.get("type", "income"),
                arguments.get("startdate", ""),
                arguments.get("enddate", "")
            )
            arguments = {"question": question}
        
        # 参数转换：wind_macro_data
        elif tool_name == "wind_macro_data":
            # 转换日期格式
            converted_args = {
                "metricIdsStr": arguments.get("indicator", ""),
            }
            if arguments.get("startdate"):
                converted_args["beginDate"] = _format_date(arguments["startdate"])
            if arguments.get("enddate"):
                converted_args["endDate"] = _format_date(arguments["enddate"])
            if arguments.get("frequency"):
                freq_map = {"day": "日", "month": "月", "quarter": "季", "year": "年"}
                converted_args["freq"] = freq_map.get(arguments["frequency"], "月")
            arguments = converted_args
        
        # 参数转换：wind_industry_data
        elif tool_name == "wind_industry_data":
            action = arguments.get("action", "classify")
            industry = arguments.get("industry", "")
            market = arguments.get("market", "")
            action_map = {
                "classify": "行业分类",
                "index": "行业指数行情",
                "members": "行业成分股列表"
            }
            action_name = action_map.get(action, action)
            question = f"{industry}{action_name}" if industry else action_name
            if market:
                question += f"（{market}）"
            arguments = {"question": question}
        
        return _call_wind_api(server_type, mapped_tool, arguments)
    else:
        # 尝试自动路由
        server_type = _get_server_type(tool_name)
        return _call_wind_api(server_type, tool_name, arguments)


async def main():
    """MCP 服务器主循环"""
    import sys
    
    # 简单的 JSON-RPC 服务器
    for line in sys.stdin:
        try:
            request = json.loads(line.strip())
            method = request.get("method")
            params = request.get("params", {})
            request_id = request.get("id")
            
            # 处理通知（没有 id 的请求不需要响应）
            if request_id is None:
                if method == "notifications/initialized":
                    # MCP 初始化完成通知，无需响应
                    continue
                elif method == "notifications/cancelled":
                    # 取消通知，无需响应
                    continue
                else:
                    # 其他通知，无需响应
                    continue
            
            if method == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "wind-mcp", "version": "1.0.0"}
                    }
                }
            elif method == "tools/list":
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"tools": TOOLS}
                }
            elif method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                result = await handle_tool_call(tool_name, arguments)
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                        "isError": not result.get("success", False)
                    }
                }
            else:
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"}
                }
            
            print(json.dumps(response, ensure_ascii=False))
            sys.stdout.flush()
            
        except json.JSONDecodeError:
            continue
        except Exception as e:
            error_response = {
                "jsonrpc": "2.0",
                "id": request_id if 'request_id' in dir() else None,
                "error": {"code": -32603, "message": str(e)}
            }
            print(json.dumps(error_response, ensure_ascii=False))
            sys.stdout.flush()


if __name__ == "__main__":
    asyncio.run(main())
