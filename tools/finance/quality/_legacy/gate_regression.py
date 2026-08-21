"""
gate_regression.py — 回归测试流程模块

功能：
- 运行回归测试
- 验证修复不引入新问题
- 生成回归测试报告
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ====================================================================
# 数据结构
# ====================================================================

@dataclass
class RegressionResult:
    """回归测试结果"""
    test_file: str
    passed: bool
    output: str = ""
    error: str = ""
    duration: float = 0.0


@dataclass
class FixVerification:
    """修复验证结果"""
    issue_id: str
    fix_description: str
    verified: bool
    verification_method: str
    message: str = ""


@dataclass
class RegressionReport:
    """回归测试报告"""
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    results: list[RegressionResult] = field(default_factory=list)
    fix_verifications: list[FixVerification] = field(default_factory=list)


# ====================================================================
# 回归测试
# ====================================================================

class GateRegressionTester:
    """Gate 回归测试器"""
    
    def __init__(self, test_dir: Optional[str] = None):
        self.test_dir = Path(test_dir) if test_dir else None
    
    def run_test(self, test_file: str) -> RegressionResult:
        """
        运行单个测试文件。

        Args:
            test_file: 测试文件路径

        Returns:
            RegressionResult 测试结果
        """
        import time
        start = time.time()
        
        try:
            import subprocess
            result = subprocess.run(
                ["python3", test_file],
                capture_output=True,
                text=True,
                timeout=60,
            )
            
            duration = time.time() - start
            
            return RegressionResult(
                test_file=test_file,
                passed=result.returncode == 0,
                output=result.stdout,
                error=result.stderr,
                duration=duration,
            )
        except subprocess.TimeoutExpired:
            return RegressionResult(
                test_file=test_file,
                passed=False,
                error="测试超时 (60s)",
                duration=time.time() - start,
            )
        except Exception as e:
            return RegressionResult(
                test_file=test_file,
                passed=False,
                error=str(e),
                duration=time.time() - start,
            )
    
    def run_all_tests(self) -> RegressionReport:
        """
        运行所有测试文件。

        Returns:
            RegressionReport 测试报告
        """
        results = []
        
        if self.test_dir and self.test_dir.exists():
            test_files = list(self.test_dir.glob("test_*.py"))
            for test_file in test_files:
                result = self.run_test(str(test_file))
                results.append(result)
        
        passed = sum(1 for r in results if r.passed)
        failed = sum(1 for r in results if not r.passed)
        
        return RegressionReport(
            total_tests=len(results),
            passed_tests=passed,
            failed_tests=failed,
            results=results,
        )
    
    def verify_fix(
        self,
        issue_id: str,
        fix_description: str,
        test_file: str,
        verification_method: str = "run_test",
    ) -> FixVerification:
        """
        验证修复。

        Args:
            issue_id: 问题 ID
            fix_description: 修复描述
            test_file: 测试文件
            verification_method: 验证方法

        Returns:
            FixVerification 验证结果
        """
        if verification_method == "run_test":
            result = self.run_test(test_file)
            return FixVerification(
                issue_id=issue_id,
                fix_description=fix_description,
                verified=result.passed,
                verification_method=verification_method,
                message=result.output if result.passed else result.error,
            )
        elif verification_method == "syntax":
            # 语法验证
            try:
                content = Path(test_file).read_text(encoding='utf-8')
                import ast
                ast.parse(content)
                return FixVerification(
                    issue_id=issue_id,
                    fix_description=fix_description,
                    verified=True,
                    verification_method=verification_method,
                    message="语法验证通过",
                )
            except Exception as e:
                return FixVerification(
                    issue_id=issue_id,
                    fix_description=fix_description,
                    verified=False,
                    verification_method=verification_method,
                    message=f"语法验证失败: {e}",
                )
        else:
            return FixVerification(
                issue_id=issue_id,
                fix_description=fix_description,
                verified=False,
                verification_method=verification_method,
                message=f"未知验证方法: {verification_method}",
            )


def format_regression_report(report: RegressionReport) -> str:
    """格式化回归测试报告"""
    lines = ["## 回归测试报告"]
    lines.append("")
    lines.append(f"- 总测试数: {report.total_tests}")
    lines.append(f"- 通过: {report.passed_tests}")
    lines.append(f"- 失败: {report.failed_tests}")
    lines.append("")
    
    if report.results:
        lines.append("### 测试结果")
        for result in report.results:
            status = "✅" if result.passed else "❌"
            name = Path(result.test_file).name
            lines.append(f"- {status} {name} ({result.duration:.1f}s)")
            if not result.passed and result.error:
                lines.append(f"  错误: {result.error[:100]}")
        lines.append("")
    
    if report.fix_verifications:
        lines.append("### 修复验证")
        for fix in report.fix_verifications:
            status = "✅" if fix.verified else "❌"
            lines.append(f"- {status} [{fix.issue_id}] {fix.fix_description}")
        lines.append("")
    
    return "\n".join(lines)
