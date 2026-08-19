"""
验证引擎 - 确保真实验证，禁止虚假通过
"""

import subprocess
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import structlog

logger = structlog.get_logger()


@dataclass
class VerificationResult:
    """验证结果"""
    passed: bool
    level: str
    message: str
    details: Optional[Dict] = None


class VerificationEngine:
    """验证引擎 - 确保真实验证"""
    
    # 禁止的验证方式
    FORBIDDEN_VERIFICATIONS = [
        "file_exists",
        "status_code_200",
        "output_not_empty"
    ]
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.coverage_min = self.config.get("coverage_min", 80)
        self.verifiers = {
            "L1": self.verify_unit_test,
            "L2": self.verify_integration,
            "L3": self.verify_external_api,
            "L4": self.verify_manual_trigger,
            "L5": self.verify_routing
        }
    
    def verify(self, level: str, command: str = None, expected: Any = None) -> VerificationResult:
        """执行验证 - 不可绕过"""
        # 检查命令中是否使用了禁止的验证方式
        if command:
            for forbidden in self.FORBIDDEN_VERIFICATIONS:
                if forbidden in command.lower():
                    raise ValueError(f"禁止的验证方式: {forbidden}")
        
        verifier = self.verifiers.get(level)
        if not verifier:
            raise ValueError(f"未知的验证级别: {level}")
        
        try:
            return verifier(command, expected)
        except NotImplementedError:
            # 未实现的验证器返回失败结果而非崩溃
            return VerificationResult(
                passed=False,
                level=level,
                message=f"验证器 {level} 尚未实现",
                details={"status": "not_implemented"}
            )
    
    def verify_unit_test(self, command: str = None, expected: Any = None) -> VerificationResult:
        """L1: 单元测试验证"""
        import shlex
        if not command:
            # 使用 --cov-report=json 输出 JSON 格式覆盖率
            command = "pytest tests/ -v --tb=short --cov-report=json:coverage.json --cov"
        
        try:
            # 安全执行：使用 shlex.split 避免 shell 注入
            cmd_args = shlex.split(command)
            result = subprocess.run(
                cmd_args,
                shell=False,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            # 检查测试结果
            if result.returncode != 0:
                return VerificationResult(
                    passed=False,
                    level="L1",
                    message=f"单元测试失败: {result.stderr}",
                    details={"stdout": result.stdout, "stderr": result.stderr}
                )
            
            # 尝试从 JSON 文件读取覆盖率
            coverage = self._extract_coverage_json()
            if coverage is None:
                # 回退到文本解析
                coverage = self._extract_coverage(result.stdout)
            
            if coverage is None:
                return VerificationResult(
                    passed=False,
                    level="L1",
                    message="无法解析覆盖率数据",
                    details={"stdout": result.stdout}
                )
            if coverage < self.coverage_min:
                return VerificationResult(
                    passed=False,
                    level="L1",
                    message=f"覆盖率 {coverage}% < {self.coverage_min}%",
                    details={"coverage": coverage}
                )
            
            # 提取测试数量
            test_count = self._extract_test_count(result.stdout)
            if test_count == 0:
                return VerificationResult(
                    passed=False,
                    level="L1",
                    message="没有测试用例",
                    details={"test_count": test_count}
                )
            
            return VerificationResult(
                passed=True,
                level="L1",
                message=f"单元测试通过，覆盖率 {coverage}%，测试数量 {test_count}",
                details={"coverage": coverage, "test_count": test_count}
            )
            
        except subprocess.TimeoutExpired:
            return VerificationResult(
                passed=False,
                level="L1",
                message="单元测试超时",
                details={"timeout": 300}
            )
        except Exception as e:
            return VerificationResult(
                passed=False,
                level="L1",
                message=f"单元测试执行失败: {str(e)}",
                details={"error": str(e)}
            )
    
    def verify_integration(self, command: str = None, expected: Any = None) -> VerificationResult:
        """L2: 真实数据端到端测试"""
        import shlex
        if not command:
            command = "pytest tests/integration/ -v --tb=short"
        
        try:
            # 安全执行：使用 shlex.split 避免 shell 注入
            cmd_args = shlex.split(command)
            result = subprocess.run(
                cmd_args,
                shell=False,
                capture_output=True,
                text=True,
                timeout=600
            )
            
            if result.returncode != 0:
                return VerificationResult(
                    passed=False,
                    level="L2",
                    message=f"集成测试失败: {result.stderr}",
                    details={"stdout": result.stdout, "stderr": result.stderr}
                )
            
            return VerificationResult(
                passed=True,
                level="L2",
                message="集成测试通过",
                details={"stdout": result.stdout}
            )
            
        except subprocess.TimeoutExpired:
            return VerificationResult(
                passed=False,
                level="L2",
                message="集成测试超时",
                details={"timeout": 600}
            )
        except Exception as e:
            return VerificationResult(
                passed=False,
                level="L2",
                message=f"集成测试执行失败: {str(e)}",
                details={"error": str(e)}
            )
    
    def verify_external_api(self, command: str = None, expected: Any = None) -> VerificationResult:
        """L3: 外部 API 真实数据验证"""
        raise NotImplementedError(
            "L3 外部 API 验证器需要项目级实现。"
            "请在子类中重写此方法，提供真实的 API 调用和验证逻辑。"
        )
    
    def verify_manual_trigger(self, command: str = None, *args, **kwargs) -> VerificationResult:
        """L4: 手动触发 + 输出检查"""
        raise NotImplementedError(
            "L4 手动触发验证器需要项目级实现。"
            "请在子类中重写此方法，提供真实的手动触发和输出检查逻辑。"
        )
    
    def verify_routing(self, command: str = None, expected: Any = None) -> VerificationResult:
        """L5: 路由/分发测试"""
        raise NotImplementedError(
            "L5 路由验证器需要项目级实现。"
            "请在子类中重写此方法，提供真实的路由分发测试逻辑。"
        )
    
    def _extract_coverage(self, output: str) -> Optional[float]:
        """从文本输出提取覆盖率（回退方案）"""
        try:
            for line in output.split('\n'):
                if 'TOTAL' in line and '%' in line:
                    parts = line.split()
                    for part in parts:
                        if '%' in part:
                            return float(part.replace('%', ''))
        except (ValueError, IndexError):
            pass
        return None
    
    def _extract_coverage_json(self, json_path: str = "coverage.json") -> Optional[float]:
        """从 JSON 文件提取覆盖率（推荐方案）"""
        import os
        try:
            if not os.path.exists(json_path):
                return None
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # pytest-cov JSON 格式: {"totals": {"percent_covered": 85.5, ...}}
            totals = data.get('totals', {})
            percent = totals.get('percent_covered')
            if percent is not None:
                return round(float(percent), 1)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            pass
        return None
    
    def _extract_test_count(self, output: str) -> int:
        """提取测试数量"""
        # 从 pytest 输出中提取测试数量
        # 简化实现
        try:
            for line in output.split('\n'):
                if 'passed' in line:
                    # 提取 passed 数量
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if 'passed' in part and i > 0:
                            return int(parts[i-1])
        except Exception:
            pass
        return 0
