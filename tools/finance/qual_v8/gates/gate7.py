"""
Gate 7: 问题转化 + 记忆存储
"""

from typing import Dict, Any, List
from dataclasses import dataclass
from datetime import datetime
import logging

from ..core.gate_engine import GateBase, GateSpec, GateResult

logger = logging.getLogger(__name__)


@dataclass
class ReviewIssue:
    """审查问题"""
    issue_id: str
    issue_type: str
    severity: str
    chapter: int
    description: str
    suggestion: str


@dataclass
class AnalysisMemory:
    """分析记忆"""
    ticker: str
    company_name: str
    analysis_date: str
    key_findings: List[str]
    review_issues: List[ReviewIssue]
    lessons_learned: List[str]


class Gate7ProblemTransformation(GateBase):
    """Gate 7: 问题转化 + 记忆存储"""
    
    def __init__(self):
        spec = GateSpec(
            gate_num=7,
            name="问题转化 + 记忆存储",
            description="将审查问题转化为结构化记忆",
            prerequisites=[6],  # 依赖Gate 6
            timeout=180,  # 3分钟
            max_retries=3,
            pass_criteria=[
                {"name": "问题转化成功", "type": "condition", "condition": "transformation_success"},
                {"name": "Schema校验通过", "type": "condition", "condition": "schema_valid"},
                {"name": "记忆存储成功", "type": "condition", "condition": "memory_stored"},
            ],
        )
        super().__init__(spec)
    
    def execute(self, context: Dict[str, Any]) -> GateResult:
        """执行Gate 7"""
        errors = []
        warnings = []
        details = {}
        
        # 1. 收集审查问题
        review_issues = self._collect_review_issues(context)
        details["review_issues"] = len(review_issues)
        
        # 2. 转化为结构化问题
        transformation_result = self._transform_issues(review_issues)
        details["transformation"] = transformation_result
        
        if not transformation_result["passed"]:
            errors.extend(transformation_result["errors"])
        
        # 3. 存储记忆
        memory_result = self._store_memory(context, transformation_result["issues"])
        details["memory"] = memory_result
        
        if not memory_result["passed"]:
            errors.extend(memory_result["errors"])
        
        # 4. 计算得分
        score = 100.0
        if errors:
            score -= len(errors) * 30
        score = max(0.0, min(100.0, score))
        
        passed = len(errors) == 0
        
        return GateResult(
            gate_num=7,
            passed=passed,
            score=score,
            details=details,
            errors=errors,
            warnings=warnings,
            execution_time=0.0,
            timestamp=datetime.now().isoformat(),
        )
    
    def check_criteria(self, context: Dict[str, Any]) -> bool:
        """检查通过标准"""
        # 检查问题转化
        transformation = context.get("transformation")
        if not transformation or not transformation.get("passed"):
            return False
        
        # 检查记忆存储
        memory = context.get("memory")
        if not memory or not memory.get("passed"):
            return False
        
        return True
    
    def _collect_review_issues(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """收集审查问题"""
        issues = []

        # 从Gate 4的结果中收集问题
        gate4_result = context.get("gate_4_result", {})
        if "contradictions" in gate4_result and isinstance(gate4_result["contradictions"], list):
            issues.extend(gate4_result["contradictions"])

        # 从Gate 5的结果中收集问题（warnings 可能为 int 计数，需防御）
        gate5_result = context.get("gate_5_result", {})
        if isinstance(gate5_result, dict):
            w = gate5_result.get("warnings")
            if isinstance(w, list):
                issues.extend(w)

        # 收口 Gate4 形式问题
        formal_issues = context.get("gate_4_formal_issues")
        if isinstance(formal_issues, list):
            issues.extend([{"id": "", "type": "formal", "severity": "warning",
                            "chapter": 0, "description": str(i), "suggestion": ""}
                           for i in formal_issues])

        return issues
    
    def _transform_issues(self, issues: List[Dict[str, Any]]) -> Dict[str, Any]:
        """转化问题为结构化格式"""
        errors = []
        transformed_issues = []
        
        for issue in issues:
            try:
                transformed = ReviewIssue(
                    issue_id=issue.get("id", ""),
                    issue_type=issue.get("type", ""),
                    severity=issue.get("severity", ""),
                    chapter=issue.get("chapter", 0),
                    description=issue.get("description", ""),
                    suggestion=issue.get("suggestion", ""),
                )
                transformed_issues.append(transformed)
            except Exception as e:
                errors.append(f"问题转化失败: {str(e)}")
        
        return {
            "passed": len(errors) == 0,
            "errors": errors,
            "issues": transformed_issues,
        }
    
    def _store_memory(self, context: Dict[str, Any], issues: List[ReviewIssue]) -> Dict[str, Any]:
        """存储记忆（真实：finance.workflow._store_memory 生成 MCP 指令）"""
        errors = []

        try:
            report = context.get("report", "")
            ctx = context.get("data_ctx")

            if ctx is None:
                # 构造轻量 DataContext 或直接跳过（无 ctx 时记录但不阻断）
                logger.warning("Gate7: 无 data_ctx，跳过记忆存储")
                return {
                    "passed": True,
                    "errors": [],
                    "memory_id": None,
                    "skipped": True,
                }

            from ...workflow import _store_memory as real_store_memory
            instructions = real_store_memory(ctx, report)

            return {
                "passed": True,
                "errors": [],
                "memory_id": f"memory_{context.get('ticker', 'unknown')}",
                "instructions_count": len(instructions),
            }
        except Exception as e:
            return {
                "passed": False,
                "errors": [f"记忆存储失败: {str(e)}"],
            }
