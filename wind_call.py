#!/usr/bin/env python3
"""Wind CLI 调用助手：用 subprocess 列表参数调用 cli.mjs，绕开 PowerShell 引号问题。
用法: python wind_call.py <server_type> <tool> '<params_json>' [out_file]
"""
import json
import os
import subprocess
import sys

SKILL_DIR = os.path.expanduser(r"~\.hermes\skills\wind-mcp-skill")
ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", ".env")


def load_env():
    env = {}
    if os.path.exists(ENV_FILE):
        for line in open(ENV_FILE, encoding="utf-8"):
            line = line.strip()
            if line and "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def main():
    # 用法: wind_call.py <server_type> <tool> <params_json|params_file> [out_file]
    # 第三参数若指向存在的文件则按文件读取 JSON（推荐，绕开 shell 引号问题）
    if len(sys.argv) < 4:
        print("usage: wind_call.py <server_type> <tool> <params_json_or_file> [out_file]")
        return 2
    server_type, tool, params_arg = sys.argv[1], sys.argv[2], sys.argv[3]
    out_file = sys.argv[4] if len(sys.argv) > 4 else None
    if os.path.isfile(params_arg):
        with open(params_arg, "r", encoding="utf-8-sig") as f:
            params_json = f.read().strip()
    else:
        params_json = params_arg
    env = load_env()
    api_key = os.environ.get("WIND_API_KEY", "") or env.get("WIND_API_KEY", "")
    if not api_key:
        print("WIND_API_KEY 未配置")
        return 2
    # 校验 params 是合法 JSON
    json.loads(params_json)
    cmd = ["node", "scripts/cli.mjs", "call", server_type, tool, params_json]
    full_env = dict(os.environ)
    full_env["WIND_API_KEY"] = api_key
    if out_file:
        with open(out_file, "w", encoding="utf-8") as f:
            r = subprocess.run(cmd, cwd=SKILL_DIR, env=full_env, stdout=f, stderr=subprocess.STDOUT)
    else:
        r = subprocess.run(cmd, cwd=SKILL_DIR, env=full_env)
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
