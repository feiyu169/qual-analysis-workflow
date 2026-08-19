"""
插件输出标准化协议 - V3.0 方案
定义门禁执行结果的标准格式
"""

import json
from dataclasses import asdict, dataclass, field
from enum import Enum


class GateExecutionStatus(Enum):
    """门禁执行状态（与 state_machine.GateStatus 区分）"""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


class GateLevel(Enum):
    """门禁级别"""

    MUST_PASS = "MUST_PASS"
    SHOULD_PASS = "SHOULD_PASS"
    OPTIONAL = "OPTIONAL"


@dataclass
class Issue:
    """问题详情"""

    severity: str  # error/warning/info
    message: str  # 问题描述
    file: str | None = None
    line: int | None = None
    column: int | None = None
    rule: str | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class GateResult:
    """门禁执行结果（标准化输出）"""

    name: str  # 门禁名称
    tool: str  # 工具名称
    status: GateExecutionStatus  # 状态
    exit_code: int  # 退出码
    issues_count: int  # 问题数量
    issues: list[Issue] = field(default_factory=list)  # 问题详情
    duration: float = 0.0  # 耗时（秒）
    message: str = ""  # 消息
    output: str = ""  # 原始输出
    level: GateLevel = GateLevel.MUST_PASS  # 门禁级别
    coverage: float | None = None  # 覆盖率（可选）
    suggestions: list[str] = field(default_factory=list)  # 建议
    parse_error: str | None = None  # 工具输出解析失败信息（fail-loud，V3.2）

    def to_dict(self) -> dict:
        """转换为字典"""
        result = {
            "name": self.name,
            "tool": self.tool,
            "status": self.status.value,
            "exit_code": self.exit_code,
            "issues_count": self.issues_count,
            "issues": [i.to_dict() for i in self.issues],
            "duration": self.duration,
            "message": self.message,
            "level": self.level.value,
        }
        if self.coverage is not None:
            result["coverage"] = self.coverage
        if self.suggestions:
            result["suggestions"] = self.suggestions
        if self.parse_error:
            result["parse_error"] = self.parse_error
        return result

    def to_json(self) -> str:
        """转换为 JSON"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @property
    def passed(self) -> bool:
        """是否通过"""
        return self.status == GateExecutionStatus.PASSED

    @property
    def failed(self) -> bool:
        """是否失败"""
        return self.status == GateExecutionStatus.FAILED


@dataclass
class GateConfig:
    """门禁配置"""

    name: str  # 门禁名称
    tool: str  # 工具名称
    command: str  # 命令模板（支持 {files} 占位符；空则用插件默认）
    level: GateLevel = GateLevel.MUST_PASS  # 门禁级别
    severity: str = "error"  # 严重级别
    timeout: int = 60  # 超时（秒）
    coverage_min: float | None = None  # 最小覆盖率
    incremental_coverage_min: float | None = None  # 增量覆盖率门槛（仅统计变更文件）
    verification: str | None = None  # 声明的验证级别（L1-L5）
    applicable: str | None = None  # 适用文件模式（如 "**/*.py"）
    probes: list[dict] | None = None  # integration-probe 门禁的探针配置
    evidence: list[str] | None = None  # L2-L5 声明的证据文件（glob），V3.2

    def to_dict(self) -> dict:
        """转换为字典"""
        result = {
            "name": self.name,
            "tool": self.tool,
            "command": self.command,
            "level": self.level.value,
            "severity": self.severity,
            "timeout": self.timeout,
        }
        if self.coverage_min is not None:
            result["coverage_min"] = self.coverage_min
        if self.incremental_coverage_min is not None:
            result["incremental_coverage_min"] = self.incremental_coverage_min
        if self.verification is not None:
            result["verification"] = self.verification
        if self.applicable is not None:
            result["applicable"] = self.applicable
        if self.probes is not None:
            result["probes"] = self.probes
        if self.evidence is not None:
            result["evidence"] = self.evidence
        return result


@dataclass
class GateExecutionReport:
    """门禁执行报告"""

    level: str  # 任务等级
    total_gates: int  # 总门禁数
    passed: int  # 通过数
    failed: int  # 失败数
    skipped: int  # 跳过数
    must_pass_failed: list[str]  # MUST_PASS 失败列表
    results: list[GateResult]  # 门禁结果列表
    duration: float  # 总耗时
    tool_health: list[dict] = field(default_factory=list)  # V3.2.5 环境维度（SKIPPED/ERROR）

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "level": self.level,
            "total_gates": self.total_gates,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "must_pass_failed": self.must_pass_failed,
            "success": len(self.must_pass_failed) == 0,
            "exit_code": self.exit_code,
            "tool_health": self.tool_health,
            "results": [r.to_dict() for r in self.results],
            "duration": self.duration,
        }

    def to_json(self) -> str:
        """转换为 JSON"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @property
    def exit_code(self) -> int:
        """进程退出码：0=全部 MUST_PASS 通过，1=存在失败"""
        return 0 if self.success else 1

    @property
    def success(self) -> bool:
        """是否成功（无 MUST_PASS 失败）"""
        return len(self.must_pass_failed) == 0

    def format_report(self) -> str:
        """格式化报告"""
        lines = []
        lines.append("=" * 60)
        lines.append("质量门禁执行报告")
        lines.append("=" * 60)
        lines.append(f"任务等级: {self.level}")
        lines.append(f"总门禁数: {self.total_gates}")
        lines.append(f"通过: {self.passed}")
        lines.append(f"失败: {self.failed}")
        lines.append(f"跳过: {self.skipped}")
        lines.append(f"总耗时: {self.duration:.2f}s")
        lines.append("")

        for result in self.results:
            icon = "✅" if result.passed else "❌" if result.failed else "⏭️"
            lines.append(f"{icon} {result.name} ({result.tool})")
            lines.append(f"   状态: {result.status.value}")
            lines.append(f"   级别: {result.level.value}")
            if result.issues_count > 0:
                lines.append(f"   问题数: {result.issues_count}")
            if result.coverage is not None:
                lines.append(f"   覆盖率: {result.coverage:.1f}%")
            if result.message:
                lines.append(f"   消息: {result.message}")
            lines.append("")

        # 工具健康度（V3.2.5 环境维度：SKIPPED/ERROR ≠ 代码质量问题）
        if self.tool_health:
            lines.append("工具健康度（SKIPPED/ERROR：环境维度，非代码质量）")
            for h in self.tool_health:
                lines.append(f"  - {h['gate']} ({h['tool']}): {h['status']} — {h['message']}")
            lines.append("")

        lines.append("=" * 60)
        if self.success:
            lines.append("✅ 所有 MUST_PASS 门禁通过")
        else:
            lines.append(f"❌ MUST_PASS 门禁失败: {', '.join(self.must_pass_failed)}")
        lines.append("=" * 60)

        return "\n".join(lines)
