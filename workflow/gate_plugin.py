"""
门禁插件基类 - V3.0 方案
所有门禁插件必须继承此基类
"""

import re
import shutil
import subprocess
from abc import ABC, abstractmethod

try:
    from .gate_types import (
        GateConfig,
        GateExecutionStatus,
        GateResult,
        Issue,
    )
except ImportError:
    from gate_types import GateConfig, GateExecutionStatus, GateResult, Issue


class GatePlugin(ABC):
    """门禁插件基类"""

    # 工具版本契约（V3.2.5）：get_version() 解析出的版本必须满足
    # [min_version, max_version)。工具大版本升级常改变输出契约
    # （safety/checkov 顶层结构漂移即实证），越界时执行器报 ERROR，
    # 提示升级 HGF 解析器，而不是猜。
    min_version: str | None = None
    max_version: str | None = None

    def __init__(self, config: GateConfig):
        self.config = config
        self.name = config.name
        self.tool = config.tool
        self.timeout = config.timeout

    @abstractmethod
    def execute(self, files: list[str], working_dir: str) -> GateResult:
        """
        执行门禁

        Args:
            files: 变更文件列表
            working_dir: 工作目录

        Returns:
            GateResult: 门禁执行结果
        """
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        """
        检查工具是否可用

        Returns:
            bool: 工具是否可用
        """
        raise NotImplementedError

    def get_version(self) -> str | None:
        """
        获取工具版本

        Returns:
            Optional[str]: 版本号，不可用时返回 None
        """
        return None

    def _run_command(
        self, command: str | list[str], working_dir: str
    ) -> subprocess.CompletedProcess:
        """
        执行命令（V3.2.9 修复 F / V3.3.1 统一闭环：委托 tool_runner.safe_run）。

        - 传 str 时用 shlex.split 拆成 argv（兼容旧调用，如 get_version）；
        - 传 list 时直接作为 argv 传递；
        - 实际执行统一走 tool_runner.safe_run（argv + shell=False），
          消除与 lifecycle 检查器层的双实现漂移（V3.3.0 复审共识 B）。

        Args:
            command: 命令字符串或 argv 参数数组
            working_dir: 工作目录

        Returns:
            subprocess.CompletedProcess: 命令执行结果
        """
        try:
            from . import tool_runner as _runner
        except ImportError:
            import tool_runner as _runner
        if isinstance(command, str):
            command = _runner.split_command(command)
        return _runner.safe_run(command, working_dir, timeout=self.timeout)

    def _build_command(self, files: list[str], default: str, **kwargs) -> str:
        """
        从配置构造命令（配置单一事实来源）：
        - GateConfig.command 有值时作为模板（支持 {files} 等占位符）；
        - 为空时回退到插件默认命令。
        """
        template = (self.config.command or "").strip() or default
        kwargs.setdefault("files", " ".join(files))
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return template

    def _build_argv(self, files: list[str], default: str, **kwargs) -> list[str]:
        """
        从配置构造 argv 参数数组（V3.2.9 修复 F：{files} 展开为独立参数，
        路径含空格安全，不经过 shell）。

        与 _build_command 的差异：{files} 不是空格拼接成一个字符串，
        而是展开为每个文件一个 argv 元素（shlex 无法正确拆分含空格路径）。
        """
        import shlex as _shlex

        template = (self.config.command or "").strip() or default
        marker = "__HGF_FILES__"
        kwargs.setdefault("files", marker)
        try:
            rendered = template.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            rendered = template
        argv: list[str] = []
        for part in _shlex.split(rendered, posix=False):
            if part == marker:
                argv.extend(files)
            else:
                argv.append(part)
        return argv

    @staticmethod
    def _parse_version(version: str | None) -> tuple | None:
        """从任意版本串提取 (major, minor, patch)；失败返回 None"""
        if not version:
            return None
        m = re.search(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", version)
        if not m:
            return None
        return tuple(int(x or 0) for x in m.groups())

    def check_version_contract(self) -> str | None:
        """
        校验工具版本是否在声明的支持区间内（V3.2.5 工具版本契约）。

        Returns:
            None=通过；否则返回 ERROR 消息（fail-loud，不猜）。
        """
        if self.min_version is None and self.max_version is None:
            return None
        try:
            version = self.get_version()
        except Exception:
            return f"无法获取工具 [{self.tool}] 版本，无法校验版本契约"
        current = self._parse_version(version)
        if current is None:
            return None  # 无法解析版本不阻塞（避免误伤）
        if self.min_version:
            floor = self._parse_version(self.min_version)
            if floor and current < floor:
                return (
                    f"工具版本过低: [{self.tool}] {version} < 支持下限 "
                    f"{self.min_version}（门禁契约未覆盖该版本行为）"
                )
        if self.max_version:
            ceiling = self._parse_version(self.max_version)
            if ceiling and current >= ceiling:
                return (
                    f"工具版本超出支持范围: [{self.tool}] {version} ≥ 上限 "
                    f"{self.max_version}（工具升级可能改变输出契约，请升级 HGF 解析器后再跑）"
                )
        return None

    @staticmethod
    def _safe_parse(parser, output: str) -> tuple:
        """
        Fail-loud 解析辅助（V3.2 假通过防线）：
        解析工具输出；畸形输入必须抛异常并返回 parse_error，绝不静默 PASS。
        checkov 假通过教训：解析失败 → ERROR 拒绝判定，而不是当成"0 问题"。

        Returns:
            (issues, parse_error): parse_error 为 None 表示解析成功。
        """
        try:
            return parser(output), None
        except Exception as e:
            return [], f"工具输出解析失败，拒绝判定: {e}"

    def _check_tool_available(self, tool_name: str) -> bool:
        """
        检查工具是否在 PATH 中

        Args:
            tool_name: 工具名称

        Returns:
            bool: 工具是否可用
        """
        return shutil.which(tool_name) is not None

    def _parse_issues_from_output(self, output: str, pattern: str) -> list[Issue]:
        """
        从输出中解析问题

        Args:
            output: 工具输出
            pattern: 正则表达式模式

        Returns:
            List[Issue]: 问题列表
        """
        issues = []
        for match in re.finditer(pattern, output):
            groups = match.groupdict()
            issues.append(
                Issue(
                    severity=groups.get("severity", "error"),
                    message=groups.get("message", ""),
                    file=groups.get("file"),
                    line=int(groups["line"]) if groups.get("line") else None,
                    column=int(groups["column"]) if groups.get("column") else None,
                    rule=groups.get("rule"),
                )
            )
        return issues

    def _create_success_result(self, message: str = "", output: str = "") -> GateResult:
        """创建成功结果"""
        return GateResult(
            name=self.name,
            tool=self.tool,
            status=GateExecutionStatus.PASSED,
            exit_code=0,
            issues_count=0,
            issues=[],
            message=message,
            output=output,
            level=self.config.level,
        )

    def _create_failure_result(
        self, message: str, output: str = "", issues: list[Issue] = None
    ) -> GateResult:
        """创建失败结果"""
        return GateResult(
            name=self.name,
            tool=self.tool,
            status=GateExecutionStatus.FAILED,
            exit_code=1,
            issues_count=len(issues) if issues else 0,
            issues=issues or [],
            message=message,
            output=output,
            level=self.config.level,
        )

    def _create_error_result(self, message: str, output: str = "") -> GateResult:
        """创建错误结果"""
        return GateResult(
            name=self.name,
            tool=self.tool,
            status=GateExecutionStatus.ERROR,
            exit_code=-1,
            issues_count=0,
            issues=[],
            message=message,
            output=output,
            level=self.config.level,
        )

    def _create_skipped_result(self, message: str) -> GateResult:
        """创建跳过结果"""
        return GateResult(
            name=self.name,
            tool=self.tool,
            status=GateExecutionStatus.SKIPPED,
            exit_code=0,
            issues_count=0,
            issues=[],
            message=message,
            level=self.config.level,
        )
