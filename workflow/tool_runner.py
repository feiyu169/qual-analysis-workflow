"""共享工具执行路径（V3.3-R2，架构评审修复 D/E）。

架构专家评审共识：同一工具（ruff/pytest/semgrep/safety/checkov）在
gate_plugins.py（GatePlugin._run_command，argv 数组 + shell=False）与
lifecycle.py（_check_tool_scan/_check_static，shell=True 字符串拼接）各实现
一次，判定标准与安全属性不一致——V3.2.9 修了插件层但漏了检查器层。

本模块提供统一的工具执行原语：
- safe_run(argv, cwd, timeout)：argv 数组 + shell=False（无 shell 解释、
  Windows 路径含空格安全、无注入面），统一 encoding/errors/timeout 处理；
- split_command(cmd)：把配置中的命令字符串（如 "semgrep --config=... --json ."）
  用 shlex 拆成 argv 数组（保留引号语义）；
- check_tool_available(tool)：PATH 中是否存在工具。

gate_plugin.py 的 _run_command 与 lifecycle 的检查器都可通过本模块统一。
"""

import shlex
import shutil
import subprocess


def check_tool_available(tool: str) -> bool:
    """检查工具是否在 PATH 中。"""
    return shutil.which(tool) is not None


def split_command(command: str) -> list[str]:
    """把命令字符串拆成 argv 数组（posix=True 去引号，argv 语义正确）。

    - 有引号（如 `--config "p/r2c-ci"`）时去引号还原为参数值；
    - 空串返回空列表；
    - Windows 路径含空格时由调用方传入 argv 数组而非字符串
      （safe_run 接受数组，不经过 split_command）。
    """
    command = (command or "").strip()
    if not command:
        return []
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        # 引号不闭合等异常：退化为按空白拆分（尽量执行而非崩溃）
        return command.split()


def safe_run(
    argv: list[str],
    cwd: str,
    timeout: int = 120,
) -> subprocess.CompletedProcess:
    """统一工具执行：argv 数组 + shell=False。

    Args:
        argv: 可执行程序 + 参数（[0] 为程序）
        cwd: 工作目录
        timeout: 超时秒数

    Returns:
        CompletedProcess（returncode/stdout/stderr，encoding=utf-8）

    Raises:
        subprocess.TimeoutExpired: 超时（调用方负责分类处理）
    """
    return subprocess.run(
        argv,
        shell=False,
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
