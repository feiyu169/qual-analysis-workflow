"""
门禁插件实现 - V3.1 方案
6个核心插件：ruff, pytest, detect-secrets, semgrep, safety, checkov
3个纪律插件：test-quality（拒空桩）, integration-probe（集成验证）, failure-log（失败记录）

配置单一事实来源：命令模板一律从 GateConfig.command 读取（支持 {files}、
{coverage_min} 占位符），空则回退到插件默认；禁止在插件内硬编码完整命令。
"""

import os
import re

try:
    from .gate_types import GateResult, Issue
except ImportError:
    from gate_types import GateResult, Issue
try:
    from .gate_plugin import GatePlugin
except ImportError:
    from gate_plugin import GatePlugin


class RuffPlugin(GatePlugin):
    """Ruff 静态分析插件"""

    min_version = "0.16.0"  # 规则集按 0.16 固定（见 pyproject.toml）

    verification_levels: frozenset[str] = frozenset({"L1"})

    def execute(self, files: list[str], working_dir: str) -> GateResult:
        """执行 ruff 静态分析"""
        import time

        start_time = time.time()

        try:
            argv = self._build_argv(files, "ruff check {files}")
            result = self._run_command(argv, working_dir)

            duration = time.time() - start_time

            issues = self._parse_ruff_output(result.stdout)

            if result.returncode == 0:
                gate_result = self._create_success_result(
                    message="静态分析通过", output=result.stdout
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
        return self._check_tool_available("ruff")

    def get_version(self) -> str | None:
        try:
            result = self._run_command("ruff --version", ".")
            return result.stdout.strip()
        except Exception:
            return None

    def _parse_ruff_output(self, output: str) -> list[Issue]:
        """解析 ruff 输出（兼容新旧两种格式）"""
        issues = []
        # 旧格式: file.py:10:5: E501 line too long
        pattern = r"^(?P<file>.+?):(?P<line>\d+):(?P<column>\d+): (?P<rule>\w+) (?P<message>.+)$"
        for match in re.finditer(pattern, output, re.MULTILINE):
            issues.append(
                Issue(
                    severity="error",
                    message=match.group("message"),
                    file=match.group("file"),
                    line=int(match.group("line")),
                    column=int(match.group("column")),
                    rule=match.group("rule"),
                )
            )
        if issues:
            return issues

        # 新格式 (ruff 0.16+):
        #   F401 [*] `os` imported but unused
        #    --> a.py:1:8
        lines = output.splitlines()
        i = 0
        while i < len(lines):
            m = re.match(r"^(?P<rule>[A-Z]{1,6}\d*)\b(?P<message>.*)$", lines[i])
            if m and i + 1 < len(lines):
                loc = re.match(
                    r"\s*-->\s*(?P<file>.+?):(?P<line>\d+):(?P<column>\d+)",
                    lines[i + 1],
                )
                if loc:
                    issues.append(
                        Issue(
                            severity="error",
                            message=(m.group("message") or "").strip(),
                            file=loc.group("file"),
                            line=int(loc.group("line")),
                            column=int(loc.group("column")),
                            rule=m.group("rule"),
                        )
                    )
                    i += 2
                    continue
            i += 1
        return issues


class PytestPlugin(GatePlugin):
    """Pytest 单元测试插件（支持总覆盖率与增量覆盖率两种门槛）"""

    min_version = "7.0.0"  # pythonpath 配置项需要 pytest >= 7

    verification_levels: frozenset[str] = frozenset({"L1"})

    def execute(self, files: list[str], working_dir: str) -> GateResult:
        """执行 pytest 单元测试"""
        import time

        start_time = time.time()

        try:
            coverage_min = self.config.coverage_min or 80
            incremental_min = self.config.incremental_coverage_min

            default = (
                "pytest tests/ -v --cov=. --cov-report=term-missing "
                "--cov-fail-under={coverage_min}"
            )
            argv = self._build_argv(files, default, coverage_min=coverage_min)
            if incremental_min is not None:
                argv += ["--cov-report=xml"]
            result = self._run_command(argv, working_dir)

            duration = time.time() - start_time

            coverage = self._parse_coverage(result.stdout)

            # 增量覆盖率：总覆盖率不达标但变更文件覆盖率达标 → 放行
            if (
                incremental_min is not None
                and result.returncode != 0
                and "Required test coverage" in result.stdout
                and "FAILED" not in result.stdout
            ):
                changed = self._changed_files(working_dir)
                changed_cov = self._changed_coverage(working_dir, changed)
                if changed_cov is not None and changed_cov >= incremental_min:
                    gate_result = self._create_success_result(
                        message=(
                            f"测试通过（增量覆盖率 {changed_cov:.1f}% ≥ "
                            f"{incremental_min:.1f}%，豁免总覆盖率门槛）"
                        ),
                        output=result.stdout,
                    )
                    gate_result.coverage = changed_cov
                    gate_result.duration = duration
                    return gate_result

            if result.returncode == 0:
                gate_result = self._create_success_result(
                    message=f"测试通过，覆盖率 {coverage:.1f}%", output=result.stdout
                )
                gate_result.coverage = coverage
            else:
                gate_result = self._create_failure_result(
                    message="测试失败", output=result.stdout
                )

            gate_result.duration = duration
            return gate_result

        except Exception as e:
            return self._create_error_result(message=str(e))

    def is_available(self) -> bool:
        return self._check_tool_available("pytest")

    def get_version(self) -> str | None:
        try:
            result = self._run_command("pytest --version", ".")
            return result.stdout.strip()
        except Exception:
            return None

    def _parse_coverage(self, output: str) -> float:
        """解析覆盖率"""
        match = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", output)
        if match:
            return float(match.group(1))
        return 0.0

    def _changed_files(self, working_dir: str) -> list[str]:
        """git 变更的 .py 文件（无 git 仓库或出错时返回空列表）

        V3.3.1（复审共识 B）：shell=True 改 argv 数组 + tool_runner。
        """
        try:
            from . import tool_runner as _runner
        except ImportError:
            import tool_runner as _runner
        files: list[str] = []
        for argv in (
            ["git", "diff", "--name-only", "HEAD"],
            ["git", "diff", "--cached", "--name-only"],
        ):
            try:
                r = _runner.safe_run(argv, working_dir, timeout=30)
                files.extend(
                    line.strip()
                    for line in r.stdout.splitlines()
                    if line.strip().endswith(".py")
                )
            except Exception:
                continue
        return list(dict.fromkeys(files))

    def _changed_coverage(
        self, working_dir: str, changed_files: list[str]
    ) -> float | None:
        """从 coverage.xml 统计变更文件的覆盖率（百分比）"""
        import xml.etree.ElementTree as ET

        xml_path = os.path.join(working_dir, "coverage.xml")
        if not changed_files or not os.path.exists(xml_path):
            return None
        try:
            root = ET.parse(xml_path).getroot()
            covered = total = 0
            for cls in root.iter("class"):
                filename = cls.get("filename") or ""
                if not any(
                    fn.replace("\\", "/") in filename.replace("\\", "/")
                    for fn in changed_files
                ):
                    continue
                for line in cls.findall(".//line"):
                    total += 1
                    if line.get("hits") not in (None, "0"):
                        covered += 1
            return (covered / total * 100.0) if total else None
        except Exception:
            return None


class DetectSecretsPlugin(GatePlugin):
    """Detect-secrets 密钥扫描插件"""

    min_version = "1.0.0"

    verification_levels: frozenset[str] = frozenset({"L1"})

    def execute(self, files: list[str], working_dir: str) -> GateResult:
        """执行 detect-secrets 扫描"""
        import time

        start_time = time.time()

        try:
            argv = self._build_argv(files, "detect-secrets scan {files}")
            result = self._run_command(argv, working_dir)

            duration = time.time() - start_time

            issues, parse_error = self._safe_parse(
                self._parse_secrets_output, result.stdout
            )

            if parse_error is not None:
                gate_result = self._create_error_result(
                    message=parse_error, output=result.stdout
                )
            elif len(issues) == 0:
                gate_result = self._create_success_result(
                    message="未发现密钥", output=result.stdout
                )
            else:
                gate_result = self._create_failure_result(
                    message=f"发现 {len(issues)} 个潜在密钥",
                    output=result.stdout,
                    issues=issues,
                )

            gate_result.duration = duration
            return gate_result

        except Exception as e:
            return self._create_error_result(message=str(e))

    def is_available(self) -> bool:
        return self._check_tool_available("detect-secrets")

    def get_version(self) -> str | None:
        try:
            result = self._run_command("detect-secrets --version", ".")
            return result.stdout.strip()
        except Exception:
            return None

    def _parse_secrets_output(self, output: str) -> list[Issue]:
        """解析 detect-secrets 输出（fail-loud：畸形 JSON 抛异常，不静默 PASS）"""
        import json

        data = json.loads(output)
        issues = []
        for file, secrets in data.get("results", {}).items():
            for secret in secrets:
                issues.append(
                    Issue(
                        severity="high",
                        message=f"Potential secret: {secret.get('type', 'unknown')}",
                        file=file,
                        line=secret.get("line_number"),
                    )
                )
        return issues


class SemgrepPlugin(GatePlugin):
    """Semgrep 安全扫描插件"""

    min_version = "1.0.0"

    verification_levels: frozenset[str] = frozenset({"L1"})

    def execute(self, files: list[str], working_dir: str) -> GateResult:
        """执行 semgrep 安全扫描"""
        import time

        start_time = time.time()

        try:
            argv = self._build_argv(files, "semgrep --config=p/r2c-ci --json {files}")
            result = self._run_command(argv, working_dir)

            duration = time.time() - start_time

            issues, parse_error = self._safe_parse(
                self._parse_semgrep_output, result.stdout
            )

            if parse_error is not None:
                gate_result = self._create_error_result(
                    message=parse_error, output=result.stdout
                )
            elif len(issues) == 0:
                gate_result = self._create_success_result(
                    message="安全扫描通过", output=result.stdout
                )
            else:
                gate_result = self._create_failure_result(
                    message=f"发现 {len(issues)} 个安全问题",
                    output=result.stdout,
                    issues=issues,
                )

            gate_result.duration = duration
            return gate_result

        except Exception as e:
            return self._create_error_result(message=str(e))

    def is_available(self) -> bool:
        return self._check_tool_available("semgrep")

    def get_version(self) -> str | None:
        try:
            result = self._run_command("semgrep --version", ".")
            return result.stdout.strip()
        except Exception:
            return None

    def _parse_semgrep_output(self, output: str) -> list[Issue]:
        """解析 semgrep 输出（fail-loud：畸形 JSON 抛异常，不静默 PASS）"""
        import json

        data = json.loads(output)
        issues = []
        for result in data.get("results", []):
            issues.append(
                Issue(
                    severity=result.get("extra", {}).get("severity", "warning"),
                    message=result.get("extra", {}).get("message", ""),
                    file=result.get("path"),
                    line=result.get("start", {}).get("line"),
                    rule=result.get("check_id"),
                )
            )
        return issues


class SafetyPlugin(GatePlugin):
    """Safety 依赖扫描插件"""

    # 3.x 顶层为字典 {"vulnerabilities": [...]}；上限 4 防止未知格式漂移
    min_version = "2.0.0"
    max_version = "4.0.0"

    verification_levels: frozenset[str] = frozenset({"L1"})

    def execute(self, files: list[str], working_dir: str) -> GateResult:
        """执行 safety 依赖扫描"""
        import time

        start_time = time.time()

        try:
            argv = self._build_argv(files, "safety check --json")
            result = self._run_command(argv, working_dir)

            duration = time.time() - start_time

            issues, parse_error = self._safe_parse(
                self._parse_safety_output, result.stdout
            )

            if parse_error is not None:
                gate_result = self._create_error_result(
                    message=parse_error, output=result.stdout
                )
            elif len(issues) == 0:
                gate_result = self._create_success_result(
                    message="依赖扫描通过", output=result.stdout
                )
            else:
                gate_result = self._create_failure_result(
                    message=f"发现 {len(issues)} 个依赖漏洞",
                    output=result.stdout,
                    issues=issues,
                )

            gate_result.duration = duration
            return gate_result

        except Exception as e:
            return self._create_error_result(message=str(e))

    def is_available(self) -> bool:
        return self._check_tool_available("safety")

    def get_version(self) -> str | None:
        try:
            result = self._run_command("safety --version", ".")
            return result.stdout.strip()
        except Exception:
            return None

    def _parse_safety_output(self, output: str) -> list[Issue]:
        """解析 safety 输出（兼容新旧两种顶层结构）。

        - 旧版（pyup）: [{"package_name": ..., "vulnerability_id": ...}]
        - safety 3.x: {"vulnerabilities": [...], "remediations": {...}}
        V3.2 修复：此前仅支持列表结构，3.x 字典结构会被误判为解析失败
        （与 checkov 顶层结构变更同族）。
        """
        import json

        data = json.loads(output)
        if isinstance(data, dict):
            vulns = data.get("vulnerabilities", [])
        else:
            vulns = data
        issues = []
        for vuln in vulns:
            if not isinstance(vuln, dict):
                continue
            issues.append(
                Issue(
                    severity="high",
                    message=f"{vuln.get('package_name', 'unknown')}: {vuln.get('advisory', '')}",
                    rule=vuln.get("vulnerability_id"),
                )
            )
        return issues


class CheckovPlugin(GatePlugin):
    """Checkov IaC 扫描插件"""

    # 3.x 顶层为数组；上限 4 防止未知格式漂移
    min_version = "1.0.0"
    max_version = "4.0.0"

    verification_levels: frozenset[str] = frozenset({"L1"})

    def execute(self, files: list[str], working_dir: str) -> GateResult:
        """执行 checkov IaC 扫描"""
        import time

        start_time = time.time()

        try:
            argv = self._build_argv(files, "checkov -d . --output json")
            result = self._run_command(argv, working_dir)

            duration = time.time() - start_time

            issues, parse_error = self._safe_parse(
                self._parse_checkov_output, result.stdout
            )

            if parse_error is not None:
                gate_result = self._create_error_result(
                    message=parse_error, output=result.stdout
                )
            elif len(issues) == 0:
                gate_result = self._create_success_result(
                    message="IaC 扫描通过", output=result.stdout
                )
            else:
                gate_result = self._create_failure_result(
                    message=f"发现 {len(issues)} 个 IaC 问题",
                    output=result.stdout,
                    issues=issues,
                )

            gate_result.duration = duration
            return gate_result

        except Exception as e:
            return self._create_error_result(message=str(e))

    def is_available(self) -> bool:
        return self._check_tool_available("checkov")

    def get_version(self) -> str | None:
        try:
            result = self._run_command("checkov --version", ".")
            return result.stdout.strip()
        except Exception:
            return None

    def _parse_checkov_output(self, output: str) -> list[Issue]:
        """解析 checkov 输出（兼容新旧两种顶层结构）。

        - 旧版: {"results": {"terraform": {"failed_checks": [...]}}}
        - checkov 3.x: [{"check_type": "terraform", "results": {
            "passed_checks": [...], "failed_checks": [...], ...}}]
        V3.1 修复：此前仅支持旧版字典结构，新版顶层为数组 → .get() 抛
        AttributeError 被 except 吞掉 → 真实失败被误判为通过（P0 陷阱）。
        """
        issues = []
        import json

        data = json.loads(output)
        entries = data if isinstance(data, list) else [data]
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            results = entry.get("results", {})
            if not isinstance(results, dict):
                continue
            # 新格式: results 直接含 failed_checks 列表
            failed_lists = []
            if isinstance(results.get("failed_checks"), list):
                failed_lists.append(results["failed_checks"])
            else:
                # 旧格式: results 按 check_type 分组
                # {"terraform": {"failed_checks": [...]}}
                for value in results.values():
                    if isinstance(value, dict) and isinstance(
                        value.get("failed_checks"), list
                    ):
                        failed_lists.append(value["failed_checks"])
            for failed_list in failed_lists:
                for result in failed_list:
                    if not isinstance(result, dict):
                        continue
                    check = result.get("check") or {}
                    issues.append(
                        Issue(
                            severity="high",
                            message=(
                                result.get("check_name") or check.get("name") or ""
                            ),
                            file=result.get("file_path"),
                            line=(result.get("file_line_range") or [None])[0],
                            rule=result.get("check_id"),
                        )
                    )
        return issues


# ── 纪律插件（V3.1 新增：把 HGF 纪律变成可执行门禁）───────────────────────────


class TestQualityPlugin(GatePlugin):
    """测试质量门禁：拒绝空桩测试。

    规则（P20）：
    - 每个 `def test_*` 函数必须包含至少一个断言（assert / pytest.raises）。
    - 纯 `pass` 的测试函数视为空桩，FAIL。
    实现基于 AST 解析（V3.1 修复：原按缩进切分函数体，多行字符串
    内容行会提前截断函数体，导致误报/漏报）。
    """

    verification_levels: frozenset[str] = frozenset({"L1"})

    def execute(self, files: list[str], working_dir: str) -> GateResult:
        """扫描测试文件中的空桩测试"""
        import ast
        import time

        start_time = time.time()

        test_files = self._collect_test_files(files, working_dir)
        issues: list[Issue] = []
        total_tests = 0
        total_asserts = 0

        for path in test_files:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
            except (OSError, UnicodeDecodeError):
                continue

            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if not (
                    isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name.startswith("test_")
                ):
                    continue
                total_tests += 1
                assert_count = self._count_asserts(node)
                total_asserts += assert_count
                if assert_count == 0:
                    issues.append(
                        Issue(
                            severity="error",
                            message=f"空桩测试: {node.name} 无任何断言",
                            file=path,
                            rule="empty-test-stub",
                        )
                    )

        duration = time.time() - start_time

        if issues:
            gate_result = self._create_failure_result(
                message=f"发现 {len(issues)} 个空桩测试",
                output="\n".join(i.message for i in issues),
                issues=issues,
            )
        else:
            suggestion = None
            if total_tests > 0 and total_asserts < total_tests:
                suggestion = (
                    f"断言数({total_asserts}) < 测试数({total_tests})，建议补断言"
                )
            gate_result = self._create_success_result(
                message=f"测试质量通过（{total_tests} 个测试，{total_asserts} 个断言）",
            )
            if suggestion:
                gate_result.suggestions.append(suggestion)

        gate_result.duration = duration
        return gate_result

    @staticmethod
    def _count_asserts(node) -> int:
        """统计函数体中的断言数量（assert 语句 + pytest.raises / raises 调用）"""
        import ast

        count = 0
        for child in ast.walk(node):
            if isinstance(child, ast.Assert):
                count += 1
                continue
            if isinstance(child, ast.Call):
                func = child.func
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr == "raises"
                    or isinstance(func, ast.Name)
                    and func.id == "raises"
                ):
                    count += 1
        return count

    def is_available(self) -> bool:
        return True

    def _collect_test_files(self, files: list[str], working_dir: str) -> list[str]:
        """收集测试文件：变更列表中的测试 + working_dir 下的 tests/ 目录"""
        result = []
        for f in files:
            if f.endswith((".py",)) and ("test" in os.path.basename(f).lower()):
                p = os.path.join(working_dir, f)
                if os.path.exists(p):
                    result.append(p)
        tests_dir = os.path.join(working_dir, "tests")
        if os.path.isdir(tests_dir):
            for root, _dirs, names in os.walk(tests_dir):
                for n in names:
                    if n.startswith("test_") and n.endswith(".py"):
                        result.append(os.path.join(root, n))
        # 去重保序
        seen, out = set(), []
        for p in result:
            ap = os.path.abspath(p)
            if ap not in seen:
                seen.add(ap)
                out.append(p)
        return out


class IntegrationProbePlugin(GatePlugin):
    """集成验证门禁：验证"已声明接入"的符号确实有调用点。

    probes 配置示例（来自 mcp-gates.yaml）：
      probes:
        - name: "discount 已接入测试"
          module: "calc"
          symbol: "apply_discount"
          usage_pattern: "apply_discount"
    规则：usage_pattern 必须在 module 定义文件之外的至少一个 .py 文件中出现，
    否则判 FAIL——对应"文件存在 ≠ 已接入"（P0 / 90% 陷阱）。
    """

    verification_levels: frozenset[str] = frozenset({"L1", "L2", "L3"})

    def execute(self, files: list[str], working_dir: str) -> GateResult:
        """按探针扫描调用点"""
        import time

        start_time = time.time()

        probes = self.config.probes or []
        issues: list[Issue] = []
        checked = 0

        for probe in probes:
            module = (probe.get("module") or "").replace(".py", "")
            symbol = probe.get("symbol") or ""
            pattern = probe.get("usage_pattern") or symbol
            if not pattern:
                continue
            checked += 1
            usage = self._find_usage(working_dir, module, pattern)
            if usage == 0:
                issues.append(
                    Issue(
                        severity="error",
                        message=(
                            f"集成探针 [{probe.get('name', pattern)}]: "
                            f"{module}.{symbol} 除定义文件外无任何调用点（仅存在≠已接入）"
                        ),
                        file=module,
                        rule="integration-probe",
                    )
                )

        duration = time.time() - start_time

        if not probes:
            gate_result = self._create_success_result(
                message="未配置集成探针（跳过）",
            )
        elif issues:
            gate_result = self._create_failure_result(
                message=f"{len(issues)} 个集成探针未通过",
                output="\n".join(i.message for i in issues),
                issues=issues,
            )
        else:
            gate_result = self._create_success_result(
                message=f"集成验证通过（{checked} 个探针均有真实调用点）",
            )

        gate_result.duration = duration
        return gate_result

    def is_available(self) -> bool:
        return True

    def _find_usage(self, working_dir: str, module: str, pattern: str) -> int:
        """统计 usage_pattern 在模块定义文件之外的出现次数"""
        module_file = os.path.join(working_dir, module + ".py")
        count = 0
        for root, _dirs, names in os.walk(working_dir):
            # 跳过缓存目录
            if any(part.startswith(".") for part in root.split(os.sep)):
                continue
            for n in names:
                if not n.endswith(".py"):
                    continue
                path = os.path.join(root, n)
                if os.path.abspath(path) == os.path.abspath(module_file):
                    continue
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read()
                except (OSError, UnicodeDecodeError):
                    continue
                count += len(re.findall(re.escape(pattern), content))
        return count


class FailureLogPlugin(GatePlugin):
    """失败记录门禁：每次门禁失败必须留有带根因分析的记录。

    记录由 GateExecutor 自动写入 `.hgf/failures.jsonl`；agent 复跑前必须用
    failure_log.update_failure 补充 root_cause / fix，否则本门禁 FAIL——
    把"失败要记录"（P4）从口头纪律变成可执行检查。
    """

    verification_levels: frozenset[str] = frozenset({"L1"})

    def execute(self, files: list[str], working_dir: str) -> GateResult:
        """检查失败日志一致性"""
        import time

        start_time = time.time()

        try:
            from . import failure_log
        except ImportError:
            import failure_log

        ok, issues_text = failure_log.check_failure_log(working_dir)
        duration = time.time() - start_time

        if ok:
            entries = failure_log.load_failures(working_dir)
            msg = (
                f"失败记录完整（{len(entries)} 条）" if entries else "无失败记录，通过"
            )
            gate_result = self._create_success_result(message=msg)
        else:
            gate_result = self._create_failure_result(
                message=f"{len(issues_text)} 条失败记录不完整",
                output="\n".join(issues_text),
                issues=[
                    Issue(severity="error", message=t, rule="failure-log")
                    for t in issues_text
                ],
            )

        gate_result.duration = duration
        return gate_result

    def is_available(self) -> bool:
        return True


# ── V3.2 生态门禁：格式 / 依赖固定 / 文档结构 ────────────────────────────────


class FormatCheckPlugin(GatePlugin):
    """格式门禁：`ruff format --check`（真实执行，禁止'存在即通过'）"""

    verification_levels: frozenset[str] = frozenset({"L1"})

    def execute(self, files: list[str], working_dir: str) -> GateResult:
        import time

        start_time = time.time()
        try:
            argv = self._build_argv(files, "ruff format --check {files}")
            result = self._run_command(argv, working_dir)
            duration = time.time() - start_time

            if result.returncode == 0:
                gate_result = self._create_success_result(
                    message="代码格式通过", output=result.stdout
                )
            else:
                lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
                gate_result = self._create_failure_result(
                    message=f"发现 {len(lines)} 处格式问题（ruff format 可自动修复）",
                    output=result.stdout,
                    issues=[
                        Issue(severity="warning", message=ln, rule="format")
                        for ln in lines[:20]
                    ],
                )
            gate_result.duration = duration
            return gate_result
        except Exception as e:
            return self._create_error_result(message=str(e))

    def is_available(self) -> bool:
        return self._check_tool_available("ruff")


class PinCheckPlugin(GatePlugin):
    """依赖固定门禁：requirements.txt 必须固定版本（==），拒绝浮动版本"""

    verification_levels: frozenset[str] = frozenset({"L1"})

    def execute(self, files: list[str], working_dir: str) -> GateResult:
        import time

        start_time = time.time()
        req_path = os.path.join(working_dir, "requirements.txt")
        issues: list[Issue] = []
        if not os.path.exists(req_path):
            gate_result = self._create_success_result(
                message="无 requirements.txt（跳过）"
            )
        else:
            with open(req_path, encoding="utf-8") as f:
                for lineno, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line or line.startswith("#") or line.startswith("-"):
                        continue
                    if "==" not in line:
                        issues.append(
                            Issue(
                                severity="error",
                                message=f"依赖未固定版本: {line}",
                                file="requirements.txt",
                                line=lineno,
                                rule="unpinned-dependency",
                            )
                        )
            if issues:
                gate_result = self._create_failure_result(
                    message=f"{len(issues)} 个依赖未固定版本",
                    output="\n".join(i.message for i in issues),
                    issues=issues,
                )
            else:
                gate_result = self._create_success_result(message="依赖版本全部固定")
        gate_result.duration = time.time() - start_time
        return gate_result

    def is_available(self) -> bool:
        return True


class DocsCheckPlugin(GatePlugin):
    """文档结构门禁：README.md 必须存在、非空、包含关键章节。

    必需章节通过 GateConfig.probes 配置（[{"name": "安装"}]）；
    未配置时检查 README 非空（>200 字符）。
    """

    verification_levels: frozenset[str] = frozenset({"L1"})

    def execute(self, files: list[str], working_dir: str) -> GateResult:
        import time

        start_time = time.time()
        readme = os.path.join(working_dir, "README.md")
        issues: list[Issue] = []
        if not os.path.exists(readme):
            issues.append(
                Issue(severity="error", message="README.md 不存在", rule="docs")
            )
        else:
            with open(readme, encoding="utf-8") as f:
                content = f.read()
            if len(content.strip()) < 200:
                issues.append(
                    Issue(
                        severity="error",
                        message=f"README.md 内容过短（{len(content.strip())} 字符）",
                        rule="docs",
                    )
                )
            required = [
                p.get("name") for p in (self.config.probes or []) if p.get("name")
            ]
            for section in required:
                if section not in content:
                    issues.append(
                        Issue(
                            severity="error",
                            message=f"README.md 缺少必需章节: {section}",
                            rule="docs",
                        )
                    )

        if issues:
            gate_result = self._create_failure_result(
                message=f"文档检查失败（{len(issues)} 项）",
                output="\n".join(i.message for i in issues),
                issues=issues,
            )
        else:
            gate_result = self._create_success_result(message="文档结构通过")
        gate_result.duration = time.time() - start_time
        return gate_result

    def is_available(self) -> bool:
        return True


# 插件注册表（必须位于所有插件类定义之后）
GATE_PLUGINS = {
    "ruff": RuffPlugin,
    "pytest": PytestPlugin,
    "detect-secrets": DetectSecretsPlugin,
    "semgrep": SemgrepPlugin,
    "safety": SafetyPlugin,
    "checkov": CheckovPlugin,
    "test-quality": TestQualityPlugin,
    "integration-probe": IntegrationProbePlugin,
    "failure-log": FailureLogPlugin,
    "format-check": FormatCheckPlugin,
    "pin-check": PinCheckPlugin,
    "docs-check": DocsCheckPlugin,
}
