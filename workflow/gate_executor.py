"""
门禁执行器 - V3.0 方案
插件架构，支持动态注册和按级别执行
"""

import os
import time

import yaml

try:
    from .gate_types import (
        GateConfig,
        GateExecutionReport,
        GateExecutionStatus,
        GateLevel,
        GateResult,
    )
except ImportError:
    from gate_types import (
        GateConfig,
        GateExecutionReport,
        GateExecutionStatus,
        GateLevel,
        GateResult,
    )

try:
    from .gate_plugin import GatePlugin
except ImportError:
    from gate_plugin import GatePlugin

try:
    from .gate_plugins import GATE_PLUGINS
except ImportError:
    from gate_plugins import GATE_PLUGINS

try:
    from .failure_handler import FailureHandler, FailureType
except ImportError:
    from failure_handler import FailureHandler, FailureType

import structlog

logger = structlog.get_logger()


class GateExecutorError(Exception):
    """门禁执行器错误"""


class GateExecutor:
    """门禁执行器（插件架构）

    V3.1 变更：
    - 删除 DEFAULT_CONFIG：配置缺失时 fail-closed（抛错），不再静默使用
      与项目无关的默认矩阵——门禁定义只允许来自配置文件，避免三处漂移。
    - 启动时校验：level_gates 引用的门禁名必须在 gates 定义中存在，
      且其 tool 必须已注册插件。
    """

    def __init__(
        self,
        config_path: str = ".mcp-gates.yaml",
        matrix_evidence_callback: callable | None = None,
    ):
        """初始化门禁执行器

        V3.3-R4（架构评审修复：矩阵-生命周期解耦）：执行层不再直接 import
        生命周期模块——DAG 接电改为**注入回调**（默认 None = 不接电）。
        调用方（CLI/bridge）如需要矩阵结果自动推进生命周期 gate，传入
        `matrix_evidence_callback`（接收 (working_dir, report_dict) → dict）。
        """
        self.config_path = config_path
        self.config = self._load_config(config_path)
        self.plugins: dict[str, GatePlugin] = {}
        # V3.3-R4：矩阵证据回调（默认关闭，消除执行层对生命周期的运行时依赖）
        self.matrix_evidence_callback = matrix_evidence_callback

        # 自动注册所有内置插件
        for name, plugin_class in GATE_PLUGINS.items():
            self.register_plugin(name, plugin_class)

        # 启动校验：配置引用必须可解析
        self._validate_config()

        # 失败处理器（V3.2 接线：可重试失败重试 + 连续失败升级）
        self.failure_handler = FailureHandler()

        # 误报/豁免检查器（V3.2.9 接线 C：此前定义了单例但从未在主流程调用，
        # 豁免机制"已实现未生效"。配置缺失时降级为"无豁免"——豁免是放行通道，
        # 缺失配置不应阻断门禁，但会记录到结果。)
        self.false_positive_checker = None
        try:
            from . import false_positive_checker as fpc_mod
        except ImportError:
            import false_positive_checker as fpc_mod
        try:
            self.false_positive_checker = fpc_mod.FalsePositiveChecker()
        except Exception as e:
            logger.warning("false_positive_checker_unavailable", error=str(e))

    def _load_config(self, path: str) -> dict:
        """加载门禁配置（配置缺失即失败，杜绝幽灵默认值）"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            # 深度合并项目级覆盖
            overrides = config.pop("project_overrides", {})
            if overrides:
                config = self._deep_merge(config, overrides)
            return config
        except FileNotFoundError:
            raise GateExecutorError(
                f"门禁配置文件不存在: {path}（门禁定义只允许来自配置，拒绝静默使用默认值）"
            )

    def _validate_config(self):
        """启动校验：门禁名可解析、工具已注册"""
        gates_config = self.config.get("gates", {})
        level_config = self.config.get("level_gates", {})
        for level, spec in level_config.items():
            for bucket in ("must_pass", "should_pass", "optional"):
                for gate_name in spec.get(bucket, []):
                    gate_def = self._find_gate_definition(gate_name, gates_config)
                    if gate_def is None:
                        raise GateExecutorError(
                            f"配置错误: 等级 {level} 引用的门禁 [{gate_name}] 在 gates 定义中不存在"
                        )
                    tool = gate_def.get("tool")
                    if tool not in self.plugins:
                        raise GateExecutorError(
                            f"配置错误: 门禁 [{gate_name}] 的工具 [{tool}] 未注册插件"
                        )

    def _deep_merge(self, base: dict, override: dict) -> dict:
        """深度合并两个字典"""
        result = base.copy()
        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def register_plugin(self, name: str, plugin_class: type, config: GateConfig = None):
        """注册门禁插件"""
        if config is None:
            config = GateConfig(name=name, tool=name, command="")
        self.plugins[name] = plugin_class(config)
        logger.info("plugin_registered", name=name)

    def get_gates_for_level(self, level: str) -> list[GateConfig]:
        """获取指定级别的门禁配置"""
        level_config = self.config.get("level_gates", {}).get(level, {})
        gates_config = self.config.get("gates", {})

        gate_configs = []

        # MUST_PASS
        for gate_name in level_config.get("must_pass", []):
            gate_def = self._find_gate_definition(gate_name, gates_config)
            if gate_def:
                gate_configs.append(
                    GateConfig(
                        name=gate_def["name"],
                        tool=gate_def["tool"],
                        command=gate_def.get("command", ""),
                        level=GateLevel.MUST_PASS,
                        timeout=gate_def.get("timeout", 60),
                        coverage_min=gate_def.get("coverage_min"),
                        incremental_coverage_min=gate_def.get(
                            "incremental_coverage_min"
                        ),
                        verification=gate_def.get("verification"),
                        applicable=gate_def.get("applicable"),
                        probes=gate_def.get("probes"),
                        evidence=gate_def.get("evidence"),
                    )
                )

        # SHOULD_PASS
        for gate_name in level_config.get("should_pass", []):
            gate_def = self._find_gate_definition(gate_name, gates_config)
            if gate_def:
                gate_configs.append(
                    GateConfig(
                        name=gate_def["name"],
                        tool=gate_def["tool"],
                        command=gate_def.get("command", ""),
                        level=GateLevel.SHOULD_PASS,
                        timeout=gate_def.get("timeout", 60),
                        coverage_min=gate_def.get("coverage_min"),
                        incremental_coverage_min=gate_def.get(
                            "incremental_coverage_min"
                        ),
                        verification=gate_def.get("verification"),
                        applicable=gate_def.get("applicable"),
                        probes=gate_def.get("probes"),
                        evidence=gate_def.get("evidence"),
                    )
                )

        # OPTIONAL
        for gate_name in level_config.get("optional", []):
            gate_def = self._find_gate_definition(gate_name, gates_config)
            if gate_def:
                gate_configs.append(
                    GateConfig(
                        name=gate_def["name"],
                        tool=gate_def["tool"],
                        command=gate_def.get("command", ""),
                        level=GateLevel.OPTIONAL,
                        timeout=gate_def.get("timeout", 60),
                        coverage_min=gate_def.get("coverage_min"),
                        incremental_coverage_min=gate_def.get(
                            "incremental_coverage_min"
                        ),
                        verification=gate_def.get("verification"),
                        applicable=gate_def.get("applicable"),
                        probes=gate_def.get("probes"),
                        evidence=gate_def.get("evidence"),
                    )
                )

        return gate_configs

    def _find_gate_definition(self, gate_name: str, gates_config: dict) -> dict | None:
        """查找门禁定义"""
        for level in ["must_pass", "should_pass", "optional"]:
            for gate in gates_config.get(level, []):
                if gate["name"] == gate_name:
                    return gate
        return None

    def execute_gates(
        self, level: str, files: list[str], working_dir: str = "."
    ) -> GateExecutionReport:
        """
        执行门禁

        Args:
            level: 任务等级
            files: 变更文件列表
            working_dir: 工作目录

        Returns:
            GateExecutionReport: 门禁执行报告
        """
        start_time = time.time()

        # 获取该级别的门禁配置
        gate_configs = self.get_gates_for_level(level)

        logger.info("executing_gates", level=level, gate_count=len(gate_configs))

        results = []
        must_pass_failed = []

        for gate_config in gate_configs:
            # 检查适用范围
            if gate_config.applicable and not self._is_applicable(
                files, gate_config.applicable
            ):
                logger.info(
                    "gate_skipped", gate=gate_config.name, reason="not_applicable"
                )
                results.append(
                    GateResult(
                        name=gate_config.name,
                        tool=gate_config.tool,
                        status=GateExecutionStatus.SKIPPED,
                        exit_code=0,
                        issues_count=0,
                        message="不适用于当前变更",
                        level=gate_config.level,
                    )
                )
                continue

            # 执行门禁
            result = self._execute_single_gate(gate_config, files, working_dir)
            results.append(result)

            # 检查 MUST_PASS：FAILED 与 ERROR 都必须阻断（V3.2 修复：
            # 此前只统计 FAILED，ERROR（如工具输出解析失败）会假绿灯）
            if gate_config.level == GateLevel.MUST_PASS and (
                result.failed or result.status == GateExecutionStatus.ERROR
            ):
                must_pass_failed.append(gate_config.name)
                logger.error("must_pass_failed", gate=gate_config.name)

        duration = time.time() - start_time

        # 失败自动记录（V3.1/V3.2：把"失败要记录"变成系统行为）。
        # 仅 MUST_PASS 阻断性失败进入纪律日志（failure_log 门禁要求根因）；
        # SHOULD_PASS/OPTIONAL 失败记入 runs.jsonl 历史与 failure_handler 计数。
        # V3.3.2（自审查 S1 修复）：failure_log 门禁自身的失败**不写入**
        # failures.jsonl——否则"记录不完整"失败被记录成新记录（且必然缺
        # root_cause/fix）→ 下次检查到更多不完整 → 自指循环指数爆炸
        # （实测 232 条/196 未解决的历史雪崩）。failure_log 是元门禁，
        # 它失败的原因（其他门禁的未闭环记录）已在检查结果中体现。
        try:
            from . import failure_log
        except ImportError:
            import failure_log
        for result in results:
            if result.failed and result.level == GateLevel.MUST_PASS:
                if result.name == "failure_log":
                    logger.warning(
                        "failure_log_self_failure_skipped",
                        detail="failure_log 门禁自身失败不入纪律日志（防自锁雪崩）",
                    )
                    continue
                failure_log.record_failure(
                    working_dir=working_dir,
                    gate=result.name,
                    level=result.level.value,
                    message=result.message,
                    output_tail=result.output,
                )

        # 复跑通过自动回填（V3.2.8-A）：本次通过的门禁若有历史失败记录，
        # 补 re_run_result 标记"已解决"（is_resolved 约定：re_run_result 非空）。
        # 让"失败要记录 → 复跑闭环"成为系统行为，无需手工维护 resolved 状态位。
        for result in results:
            if result.failed or result.level != GateLevel.MUST_PASS:
                continue
            if failure_log.update_failure(
                working_dir,
                result.name,
                re_run_result=f"复跑通过（{result.status.value}）",
            ):
                logger.info("failure_resolved", gate=result.name)

        # 生成报告
        tool_health = [
            {
                "gate": r.name,
                "tool": r.tool,
                "status": r.status.value,
                "message": r.message,
            }
            for r in results
            if r.status in (GateExecutionStatus.SKIPPED, GateExecutionStatus.ERROR)
        ]
        report = GateExecutionReport(
            level=level,
            total_gates=len(gate_configs),
            passed=sum(1 for r in results if r.passed),
            failed=sum(1 for r in results if r.failed),
            skipped=sum(1 for r in results if r.status == GateExecutionStatus.SKIPPED),
            must_pass_failed=must_pass_failed,
            results=results,
            duration=duration,
            tool_health=tool_health,
        )

        logger.info(
            "gates_executed",
            level=level,
            total=report.total_gates,
            passed=report.passed,
            failed=report.failed,
            success=report.success,
        )

        # 流水线失败计数（V3.2）
        if not report.success:
            self.failure_handler.record_pipeline_failure()

        # 运行历史（V3.2）：追加 .hgf/runs.jsonl
        try:
            from . import run_history
        except ImportError:
            import run_history
        try:
            run_history.append_run(working_dir, report.to_dict())
        except Exception as e:
            logger.warning("run_history_append_failed", error=str(e))

        # DAG 接电（V3.3-R4：改为注入回调，执行层不再 import lifecycle）
        # 此前 execute_gates 直接调用 lifecycle.record_matrix_evidence 造成
        # 运行时双向耦合（执行器依赖生命周期 + 生命周期推进依赖执行器输出）。
        if self.matrix_evidence_callback is not None:
            try:
                evidence = self.matrix_evidence_callback(working_dir, report.to_dict())
                if evidence and evidence.get("advanced"):
                    logger.info(
                        "lifecycle_auto_advanced",
                        gates=evidence["advanced"],
                    )
            except Exception as e:
                logger.warning("matrix_evidence_failed", error=str(e))

        # 基线存档（V3.2.0）：标准可复现——记录配置哈希/工具版本，漂移告警
        try:
            from . import baseline
        except ImportError:
            import baseline
        try:
            changes = baseline.update(
                working_dir, baseline.snapshot(self.config_path, self.plugins)
            )
            for change in changes:
                logger.warning("baseline_drift", change=change)
        except Exception as e:
            logger.warning("baseline_update_failed", error=str(e))

        return report

    def _execute_single_gate(
        self, gate_config: GateConfig, files: list[str], working_dir: str
    ) -> GateResult:
        """执行单个门禁"""
        # 获取插件
        plugin = self.plugins.get(gate_config.tool)
        if not plugin:
            logger.warning("plugin_not_found", tool=gate_config.tool)
            return GateResult(
                name=gate_config.name,
                tool=gate_config.tool,
                status=GateExecutionStatus.ERROR,
                exit_code=-1,
                issues_count=0,
                message=f"插件未找到: {gate_config.tool}",
                level=gate_config.level,
            )

        # 更新插件配置
        plugin.config = gate_config
        plugin.name = gate_config.name
        plugin.tool = gate_config.tool
        plugin.timeout = gate_config.timeout

        # 检查工具是否可用
        if not plugin.is_available():
            if gate_config.level == GateLevel.MUST_PASS:
                # MUST_PASS 工具不可用，拒绝
                raise GateExecutorError(
                    f"MUST_PASS 门禁工具 {gate_config.tool} 不可用，操作被拒绝"
                )
            else:
                # 非 MUST_PASS，跳过
                logger.warning(
                    "tool_not_available",
                    tool=gate_config.tool,
                    level=gate_config.level.value,
                )
                return GateResult(
                    name=gate_config.name,
                    tool=gate_config.tool,
                    status=GateExecutionStatus.SKIPPED,
                    exit_code=0,
                    issues_count=0,
                    message=f"工具不可用: {gate_config.tool}",
                    level=gate_config.level,
                )

        # 工具版本契约（V3.2.5）：版本越界 → ERROR（fail-loud，不猜）
        contract_error = plugin.check_version_contract()
        if contract_error:
            return GateResult(
                name=gate_config.name,
                tool=gate_config.tool,
                status=GateExecutionStatus.ERROR,
                exit_code=-1,
                issues_count=0,
                message=contract_error,
                level=gate_config.level,
            )

        # 执行门禁（V3.2：接入 failure_handler 的可重试失败重试 + 升级）
        # 重试仅对 MUST_PASS 生效（解阻流水线）；SHOULD_PASS/OPTIONAL 超时
        # 只记录，不重试（避免慢门禁 ×3 拖垮整个流水线）
        if gate_config.level == GateLevel.MUST_PASS:
            max_retries = self.failure_handler.gate_retry_config.max_retries
        else:
            max_retries = 1
        result = None
        failure_type = FailureType.TEMPORARY_FAILURE.value

        for attempt in range(1, max_retries + 1):
            result = self._run_plugin_once(plugin, gate_config, files, working_dir)

            # 仅对可重试失败（超时/网络/限流）重试
            if result.status != GateExecutionStatus.ERROR:
                break
            failure_type = self.failure_handler.classify_failure(
                result.message, result.exit_code
            )
            # 每次失败尝试都计数（连续失败用于升级判定）
            self.failure_handler.record_failure(
                gate_config.name,
                failure_type,
                result.message,
                result.exit_code,
                attempt,
            )
            if not self.failure_handler.should_retry_gate(
                gate_config.name, failure_type, attempt
            ):
                break
            delay = self.failure_handler.get_retry_delay(attempt)
            logger.warning(
                "gate_retry",
                gate=gate_config.name,
                attempt=attempt,
                failure_type=failure_type,
                delay=delay,
            )
            if delay > 0:
                time.sleep(delay)

        # FAILED（不可重试判定类失败）也记录一次
        if result is not None and result.failed:
            failure_type = self.failure_handler.classify_failure(
                result.message, result.exit_code
            )
            self.failure_handler.record_failure(
                gate_config.name,
                failure_type,
                result.message,
                result.exit_code,
                attempt,
            )

        # 连续失败升级
        escalation = self.failure_handler.should_escalate(gate_config.name)
        if escalation and result is not None and escalation not in result.suggestions:
            result.suggestions.append(f"升级: {escalation}")
        return result

    def _run_plugin_once(
        self, plugin, gate_config: GateConfig, files: list[str], working_dir: str
    ) -> GateResult:
        """执行一次插件（含验证级别契约检查）"""
        try:
            result = plugin.execute(files, working_dir)
        except Exception as e:
            logger.error("gate_execution_error", gate=gate_config.name, error=str(e))
            return GateResult(
                name=gate_config.name,
                tool=gate_config.tool,
                status=GateExecutionStatus.ERROR,
                exit_code=-1,
                issues_count=0,
                message=f"执行错误: {e!s}",
                level=gate_config.level,
            )

        # 验证级别契约（V3.1）：声明级别必须被插件能力覆盖
        declared = gate_config.verification
        if declared is not None and not result.failed:
            capability = getattr(type(plugin), "verification_levels", {"L1"})
            if not self._verification_covers(capability, declared):
                return GateResult(
                    name=gate_config.name,
                    tool=gate_config.tool,
                    status=GateExecutionStatus.ERROR,
                    exit_code=-1,
                    issues_count=0,
                    message=(
                        f"验证级别不匹配: 声明 {declared}，"
                        f"插件 {gate_config.tool} 仅支持 {sorted(capability)}"
                    ),
                    level=gate_config.level,
                )

        # L2-L5 证据机制（V3.2.4）：声明高级别验证且配置了证据时，证据必须存在且非空
        if result.passed and declared and gate_config.evidence:
            try:
                declared_num = int(declared.upper().lstrip("L"))
            except ValueError:
                declared_num = 0
            if declared_num >= 2:
                import glob as _glob

                for pattern in gate_config.evidence:
                    matched = _glob.glob(os.path.join(working_dir, pattern))
                    if not matched:
                        return GateResult(
                            name=gate_config.name,
                            tool=gate_config.tool,
                            status=GateExecutionStatus.ERROR,
                            exit_code=-1,
                            issues_count=0,
                            message=f"验证级别 {declared} 声明缺少证据: {pattern}",
                            level=gate_config.level,
                        )
                    empty = [p for p in matched if os.path.getsize(p) == 0]
                    if empty:
                        return GateResult(
                            name=gate_config.name,
                            tool=gate_config.tool,
                            status=GateExecutionStatus.ERROR,
                            exit_code=-1,
                            issues_count=0,
                            message=f"验证级别 {declared} 证据为空: {empty[0]}",
                            level=gate_config.level,
                        )
        # 误报过滤（V3.2.9 接线 C）：FAILED 结果的 issues 全部命中已知误报
        # （rule+file 精确匹配、未过期）→ 视为通过并说明；部分命中 → 保留失败
        # 但记录豁免数。豁免是显式配置的放行通道，不是默认行为。
        if result.failed and self.false_positive_checker is not None:
            fp_issues = [
                i
                for i in result.issues
                if self.false_positive_checker.is_false_positive(
                    i.rule or "", i.file or ""
                )
            ]
            if fp_issues and len(fp_issues) == len(result.issues):
                result = GateResult(
                    name=result.name,
                    tool=result.tool,
                    status=GateExecutionStatus.PASSED,
                    exit_code=0,
                    issues_count=len(result.issues),
                    issues=result.issues,
                    duration=result.duration,
                    message=f"{result.message}（{len(fp_issues)} 项命中已知误报豁免）",
                    output=result.output,
                    level=result.level,
                )
            elif fp_issues:
                result.suggestions.append(
                    f"{len(fp_issues)}/{len(result.issues)} 项命中已知误报，"
                    "其余为真实问题"
                )
        return result

    @staticmethod
    def _verification_covers(capability: set, declared: str) -> bool:
        """插件能力集合是否覆盖声明的验证级别（如 {"L1","L2"} 覆盖 L1、L2）"""

        def num(level: str) -> int:
            try:
                return int(level.upper().lstrip("L"))
            except ValueError:
                return 0

        required = num(declared)
        if required <= 0:
            return True
        return any(num(c) >= required for c in capability)

    def _is_applicable(self, files: list[str], pattern) -> bool:
        """检查文件是否适用"""
        import fnmatch

        if isinstance(pattern, str):
            return any(fnmatch.fnmatch(f, pattern) for f in files)
        elif isinstance(pattern, list):
            return any(fnmatch.fnmatch(f, p) for f in files for p in pattern)
        return False
