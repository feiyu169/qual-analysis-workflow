"""
TDD 验证器 - 确保测试驱动开发执行
基于 Hermes Agent 编程 Workflow 方案 V2.0
"""

import subprocess
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import structlog

logger = structlog.get_logger()


@dataclass
class TDDResult:
    """TDD 验证结果"""
    passed: bool
    message: str
    evidence: Optional[Dict] = None


class TDDVerifier:
    """TDD 执行验证器"""
    
    def __init__(self):
        self.required_evidence = [
            "test_before_code",
            "test_failed_once",
            "test_passed_after_code"
        ]
    
    def verify_tdd_evidence(self, git_history: str) -> TDDResult:
        """验证 TDD 证据"""
        # 检查 Git 历史
        commits = self._extract_commits(git_history)
        
        # 查找测试先于代码的证据
        test_commits = [c for c in commits if self._is_test_commit(c)]
        code_commits = [c for c in commits if self._is_code_commit(c)]
        
        # 验证顺序
        if not test_commits:
            return TDDResult(
                passed=False,
                message="没有测试提交记录",
                evidence={"test_commits": [], "code_commits": code_commits}
            )
        
        if not code_commits:
            return TDDResult(
                passed=False,
                message="没有代码提交记录",
                evidence={"test_commits": test_commits, "code_commits": []}
            )
        
        # 检查测试是否先于代码
        first_test = min(test_commits, key=lambda c: c['timestamp'])
        first_code = min(code_commits, key=lambda c: c['timestamp'])
        
        if first_test['timestamp'] >= first_code['timestamp']:
            return TDDResult(
                passed=False,
                message="测试未先于代码提交",
                evidence={
                    "first_test": first_test,
                    "first_code": first_code
                }
            )
        
        # 检查测试是否曾经失败
        if not self._has_failed_test(test_commits):
            return TDDResult(
                passed=False,
                message="测试从未失败（可能后补测试）",
                evidence={"test_commits": test_commits}
            )
        
        return TDDResult(
            passed=True,
            message="TDD 证据完整",
            evidence={
                "first_test": first_test,
                "first_code": first_code,
                "test_commits": test_commits,
                "code_commits": code_commits
            }
        )
    
    def verify_test_quality(self, test_results: str) -> TDDResult:
        """检查测试质量"""
        issues = []
        
        # 提取覆盖率
        coverage = self._extract_coverage(test_results)
        if coverage < 80:
            issues.append(f"覆盖率 {coverage}% < 80%")
        
        # 提取分支覆盖率
        branch_coverage = self._extract_branch_coverage(test_results)
        if branch_coverage < 70:
            issues.append(f"分支覆盖率 {branch_coverage}% < 70%")
        
        # 提取测试数量
        test_count = self._extract_test_count(test_results)
        if test_count == 0:
            issues.append("没有测试用例")
        
        # 提取断言数量
        assertion_count = self._extract_assertion_count(test_results)
        if assertion_count < test_count:
            issues.append("测试用例缺少断言")
        
        # 检查测试分布
        unit_tests = self._extract_unit_tests(test_results)
        integration_tests = self._extract_integration_tests(test_results)
        if unit_tests < integration_tests:
            issues.append("单元测试少于集成测试（测试金字塔颠倒）")
        
        if issues:
            return TDDResult(
                passed=False,
                message="测试质量检查失败",
                evidence={
                    "issues": issues,
                    "coverage": coverage,
                    "branch_coverage": branch_coverage,
                    "test_count": test_count,
                    "assertion_count": assertion_count,
                    "unit_tests": unit_tests,
                    "integration_tests": integration_tests
                }
            )
        
        return TDDResult(
            passed=True,
            message="测试质量检查通过",
            evidence={
                "coverage": coverage,
                "branch_coverage": branch_coverage,
                "test_count": test_count,
                "assertion_count": assertion_count,
                "unit_tests": unit_tests,
                "integration_tests": integration_tests
            }
        )
    
    def _extract_commits(self, git_history: str) -> List[Dict]:
        """提取 Git 提交记录"""
        commits = []
        # 简化实现
        return commits
    
    def _is_test_commit(self, commit: Dict) -> bool:
        """判断是否为测试提交"""
        # 检查提交信息或文件名
        return 'test' in commit.get('message', '').lower() or \
               any('test' in f.lower() for f in commit.get('files', []))
    
    def _is_code_commit(self, commit: Dict) -> bool:
        """判断是否为代码提交"""
        # 排除测试提交
        return not self._is_test_commit(commit)
    
    def _has_failed_test(self, test_commits: List[Dict]) -> bool:
        """检查测试是否曾经失败"""
        # 简化实现
        return True
    
    def _extract_coverage(self, output: str) -> float:
        """提取覆盖率"""
        # 从 pytest 输出中提取覆盖率
        try:
            for line in output.split('\n'):
                if 'TOTAL' in line and '%' in line:
                    parts = line.split()
                    for part in parts:
                        if '%' in part:
                            return float(part.replace('%', ''))
        except:
            pass
        return 0.0
    
    def _extract_branch_coverage(self, output: str) -> float:
        """提取分支覆盖率"""
        # 简化实现
        return 0.0
    
    def _extract_test_count(self, output: str) -> int:
        """提取测试数量"""
        try:
            for line in output.split('\n'):
                if 'passed' in line:
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if 'passed' in part and i > 0:
                            return int(parts[i-1])
        except:
            pass
        return 0
    
    def _extract_assertion_count(self, output: str) -> int:
        """提取断言数量"""
        # 简化实现
        return 0
    
    def _extract_unit_tests(self, output: str) -> int:
        """提取单元测试数量"""
        # 简化实现
        return 0
    
    def _extract_integration_tests(self, output: str) -> int:
        """提取集成测试数量"""
        # 简化实现
        return 0


class TestQualityChecker:
    """测试质量检查器"""
    
    def check_test_quality(self, test_results: str) -> TDDResult:
        """检查测试质量"""
        verifier = TDDVerifier()
        return verifier.verify_test_quality(test_results)
