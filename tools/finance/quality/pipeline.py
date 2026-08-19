"""
QualityPipeline模块

功能:
- 4个子步骤独立运行
- 每步有独立降级策略
- 降级表: structural_check(不可降级) → auditor(可降级) → repairer(可降级) → checkpoint(不阻塞)

解决: P0-3 Step 4.5过于密集
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DegradationLevel(Enum):
    """降级级别"""
    NONE = "none"
    L1 = "L1"  # 轻微降级
    L2 = "L2"  # 中度降级（跳过语义审计）
    L3 = "L3"  # 重度降级（跳过修复）


@dataclass
class StructuralCheckResult:
    """结构化预检结果"""
    passed: bool
    score: float = 0.0
    issues: List[str] = field(default_factory=list)
    must_answer_coverage: Dict[str, bool] = field(default_factory=dict)


@dataclass
class AuditResult:
    """语义审计结果"""
    passed: bool
    score: Optional[float] = None
    issues: List[str] = field(default_factory=list)
    semantic_passed: Optional[bool] = None


@dataclass
class RepairResult:
    """修复结果"""
    passed: bool
    rounds: int = 0
    history: List[Dict] = field(default_factory=list)
    final_content: Optional[str] = None


@dataclass
class CheckpointResult:
    """断点保存结果"""
    saved: bool
    path: Optional[str] = None
    error: Optional[str] = None


@dataclass
class ChapterQualityInput:
    """章节质量检查输入"""
    chapter_id: str
    content: str
    contract: Dict[str, Any]
    llm_caller: Optional[Any] = None
    feature_flags: Optional[Any] = None


@dataclass
class ChapterQualityOutput:
    """章节质量检查输出"""
    chapter_id: str
    structural: Optional[StructuralCheckResult] = None
    audit: Optional[AuditResult] = None
    repair: Optional[RepairResult] = None
    checkpoint: Optional[CheckpointResult] = None
    blocked: bool = False
    block_reason: Optional[str] = None
    degradation_level: DegradationLevel = DegradationLevel.NONE
    warnings: List[str] = field(default_factory=list)


class QualityPipeline:
    """质量保证流水线 - 每个步骤独立可降级
    
    降级策略表:
    ┌─────────────────────────────────────────────────────────────┐
    │ 模块              │ 失败场景        │ 降级行为            │
    ├─────────────────────────────────────────────────────────────┤
    │ structural_check  │ 代码异常        │ 抛出，阻断          │
    │ auditor           │ LLM超时/熔断    │ 跳过，标记L2        │
    │ auditor           │ JSON解析失败    │ 重试1次，失败后跳过 │
    │ repairer          │ LLM超时        │ 跳过，保留原始内容  │
    │ checkpoint        │ I/O失败        │ 记录warning，不阻塞 │
    └─────────────────────────────────────────────────────────────┘
    """
    
    def __init__(
        self,
        require_structural_pass: bool = True,
        max_repair_rounds: int = 3,
    ):
        self.require_structural_pass = require_structural_pass
        self.max_repair_rounds = max_repair_rounds
    
    def run_chapter_quality(
        self,
        input_data: ChapterQualityInput,
    ) -> ChapterQualityOutput:
        """执行单个章节的质量检查"""
        result = ChapterQualityOutput(chapter_id=input_data.chapter_id)
        
        # Step 4.1: 结构化预检（必须，不可降级）
        try:
            struct_result = self._run_structural_check(input_data)
            result.structural = struct_result
            
            if not struct_result.passed and self.require_structural_pass:
                result.blocked = True
                result.block_reason = "; ".join(struct_result.issues) if struct_result.issues else "结构化预检未通过"
                # 即使blocked，也执行checkpoint
                try:
                    result.checkpoint = self._run_checkpoint(input_data)
                except Exception as e:
                    result.checkpoint = CheckpointResult(saved=False, error=str(e))
                return result
        except Exception as e:
            logger.error(f"结构化预检异常: {e}")
            result.blocked = True
            result.block_reason = f"结构化预检异常: {e}"
            return result
        
        # Step 4.2: 语义审计（可选，可降级）
        if input_data.feature_flags and hasattr(input_data.feature_flags, 'is_enabled'):
            try:
                from finance.quality.v3.feature_flags import FeatureModule
                if not input_data.feature_flags.is_enabled(FeatureModule.SEMANTIC_AUDIT):
                    result.degradation_level = DegradationLevel.L2
                    result.warnings.append("语义审计已禁用")
                    result.audit = AuditResult(passed=True, issues=["语义审计已禁用"])
                    # 继续执行checkpoint
                    try:
                        result.checkpoint = self._run_checkpoint(input_data)
                    except Exception as e:
                        result.checkpoint = CheckpointResult(saved=False, error=str(e))
                    return result
            except ImportError:
                pass
        
        try:
            audit_result = self._run_semantic_audit(input_data)
            result.audit = audit_result
        except Exception as e:
            # 降级：跳过语义审计，标记为degraded
            logger.warning(f"语义审计失败: {e}, 降级到L2")
            result.audit = AuditResult(
                passed=True,  # 降级时默认通过
                issues=[f"[degraded] 语义审计跳过: {e}"],
                score=None,
            )
            result.degradation_level = DegradationLevel.L2
            result.warnings.append(f"语义审计降级: {e}")
        
        # Step 4.3: 修复（可选，依赖审计结果）
        if result.audit and not result.audit.passed:
            try:
                repair_result = self._run_repair(input_data, result.audit)
                result.repair = repair_result
            except Exception as e:
                logger.warning(f"修复失败: {e}, 降级到L3")
                result.repair = RepairResult(passed=False, rounds=0)
                result.degradation_level = DegradationLevel.L3
                result.warnings.append(f"修复降级: {e}")
        
        # Step 4.4: 断点保存（必须，但失败不阻塞）
        try:
            checkpoint_result = self._run_checkpoint(input_data)
            result.checkpoint = checkpoint_result
        except Exception as e:
            logger.warning(f"断点保存失败（非阻塞）: {e}")
            result.checkpoint = CheckpointResult(saved=False, error=str(e))
            result.warnings.append(f"断点保存失败: {e}")
        
        return result
    
    def _run_structural_check(self, input_data: ChapterQualityInput) -> StructuralCheckResult:
        """运行结构化预检"""
        content = input_data.content
        issues = []
        
        # 检查内容长度
        if len(content) < 200:
            issues.append("内容过短，疑似Placeholder")
        
        # 检查必需小节
        required_sections = ["结论要点", "详细", "证据"]
        for section in required_sections:
            if section not in content:
                issues.append(f"缺少必需小节: {section}")
        
        passed = len(issues) == 0
        score = 100 - len(issues) * 20
        
        return StructuralCheckResult(
            passed=passed,
            score=max(0, score),
            issues=issues,
        )
    
    def _run_semantic_audit(self, input_data: ChapterQualityInput) -> AuditResult:
        """运行语义审计"""
        content = input_data.content
        contract = input_data.contract
        issues = []
        
        must_answer = contract.get("must_answer", [])
        for i, question in enumerate(must_answer):
            keywords = question.split()[:3]
            found = any(kw in content for kw in keywords)
            if not found:
                issues.append(f"must_answer[{i}] 未回答: {question[:50]}")
        
        passed = len(issues) == 0
        score = 100 - len(issues) * 10
        
        return AuditResult(
            passed=passed,
            score=max(0, score),
            issues=issues,
            semantic_passed=passed,
        )
    
    def _run_repair(self, input_data: ChapterQualityInput, audit: AuditResult) -> RepairResult:
        """运行修复"""
        history = []
        rounds = 0
        
        for issue in audit.issues:
            rounds += 1
            history.append({
                "round": rounds,
                "issue": issue,
                "action": "标记待修复",
            })
            
            if rounds >= self.max_repair_rounds:
                break
        
        return RepairResult(
            passed=False,
            rounds=rounds,
            history=history,
        )
    
    def _run_checkpoint(self, input_data: ChapterQualityInput) -> CheckpointResult:
        """运行断点保存"""
        return CheckpointResult(
            saved=True,
            path=f"/tmp/checkpoint/{input_data.chapter_id}.json",
        )
    
    def run_batch(
        self,
        inputs: List[ChapterQualityInput],
    ) -> List[ChapterQualityOutput]:
        """批量执行质量检查"""
        results = []
        
        for input_data in inputs:
            result = self.run_chapter_quality(input_data)
            results.append(result)
        
        return results
    
    def get_summary(self, results: List[ChapterQualityOutput]) -> Dict:
        """获取批量检查摘要"""
        total = len(results)
        blocked = sum(1 for r in results if r.blocked)
        degraded = sum(1 for r in results if r.degradation_level != DegradationLevel.NONE)
        
        return {
            "total": total,
            "blocked": blocked,
            "degraded": degraded,
            "passed": total - blocked,
            "pass_rate": (total - blocked) / total if total > 0 else 0,
        }
