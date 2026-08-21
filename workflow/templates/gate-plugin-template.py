"""
HGF Gate 插件模板（V3.2.0）
==========================

新增一个门禁插件的三步：
1. 复制本文件为 workflow/gate_plugins.py 中的新类（或独立模块注册）。
2. 实现 execute()（真实执行验证，禁止"文件存在即通过"）与 is_available()。
3. 在 GATE_PLUGINS 注册表登记，并在 config/mcp-gates.yaml 定义门禁与等级矩阵。

约定（V3.1/V3.2 强制）：
- 命令模板从 self.config.command 读取（支持 {files} 占位符），空则回退默认——
  禁止在插件内硬编码完整命令（配置单一事实来源）。
- 声明 verification_levels 能力集合；执行器校验声明级别必须被覆盖。
- 解析工具输出必须 fail-loud：解析失败返回 parse_error（经 _safe_parse），
  绝不静默 PASS（假通过防线）。
"""

import time

from gate_plugin import GatePlugin
from gate_types import GateResult, Issue


class ExamplePlugin(GatePlugin):
    """示例门禁：演示模板约定（替换为实际检查逻辑）"""

    # 该插件能覆盖的验证级别（L1=单元测试级；L2-L5 需要证据机制配合）
    verification_levels: frozenset = frozenset({"L1"})

    def execute(self, files: list[str], working_dir: str) -> GateResult:
        start_time = time.time()
        try:
            # 1. 从配置构造命令（配置单一事实来源）
            command = self._build_command(files, "your-tool {files}")

            # 2. 真实执行
            result = self._run_command(command, working_dir)
            duration = time.time() - start_time

            # 3. 解析输出（fail-loud：解析失败 → ERROR，绝不静默 PASS）
            issues, parse_error = self._safe_parse(self._parse_output, result.stdout)
            if parse_error is not None:
                return self._create_error_result(
                    message=f"输出解析失败，拒绝判定: {parse_error}",
                    output=result.stdout,
                )

            # 4. 按准出条件判定（必须基于真实执行结果）
            if result.returncode == 0 and not issues:
                gate_result = self._create_success_result(
                    message="检查通过", output=result.stdout
                )
            else:
                gate_result = self._create_failure_result(
                    message=f"发现 {len(issues)} 个问题",
                    output=result.stdout,
                    issues=issues,
                )
            gate_result.duration = duration
            return gate_result
        except Exception as e:
            return self._create_error_result(message=str(e))

    def is_available(self) -> bool:
        """工具是否可用（MUST_PASS 不可用 → 执行器拒绝）"""
        return self._check_tool_available("your-tool")

    def _parse_output(self, output: str) -> list[Issue]:
        """解析工具输出；畸形输入必须抛异常（由 _safe_parse 转 ERROR）"""
        issues = []
        # TODO: 实现真实解析，如
        #   for line in output.splitlines():
        #       issues.append(Issue(severity="error", message=line))
        return issues


# 在 gate_plugins.py 的 GATE_PLUGINS 注册：
#   "example": ExamplePlugin,
# 在 config/mcp-gates.yaml 定义：
#   - name: "example_check"
#     tool: "example"
#     command: "your-tool {files}"
#     verification: "L1"
#     timeout: 60
