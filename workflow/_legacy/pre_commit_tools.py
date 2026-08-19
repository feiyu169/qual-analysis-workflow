"""
编码前检查工具 - V3.0 方案
1. analyze_requirements: 需求分析
2. review_design: 设计评审
"""

import re
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict

import structlog
logger = structlog.get_logger()


@dataclass
class RequirementAnalysis:
    """需求分析结果"""
    completeness: Dict[str, bool]  # 完整性检查
    completeness_score: float      # 完整性分数
    features: List[str]            # 关键功能点
    acceptance_criteria: List[str] # 验收标准
    recommendations: List[str]     # 建议
    missing: List[str]             # 缺失项
    
    def to_dict(self) -> dict:
        return {
            "completeness": self.completeness,
            "completeness_score": self.completeness_score,
            "features": self.features,
            "acceptance_criteria": self.acceptance_criteria,
            "recommendations": self.recommendations,
            "missing": self.missing,
        }


@dataclass
class DesignReview:
    """设计评审结果"""
    coverage: Dict[str, bool]      # 需求覆盖
    coverage_score: float          # 覆盖分数
    issues: List[Dict]             # 问题列表
    suggestions: List[str]         # 建议
    passed: bool                   # 是否通过
    
    def to_dict(self) -> dict:
        return {
            "coverage": self.coverage,
            "coverage_score": self.coverage_score,
            "issues": self.issues,
            "suggestions": self.suggestions,
            "passed": self.passed,
        }


class RequirementsAnalyzer:
    """需求分析器"""
    
    # 完整性检查规则
    COMPLETENESS_RULES = {
        "has_goal": {
            "keywords": ["目标", "目的", "goal", "objective", "实现", "完成"],
            "description": "是否有明确目标"
        },
        "has_scope": {
            "keywords": ["范围", "边界", "scope", "boundary", "包含", "不包含"],
            "description": "是否有明确范围"
        },
        "has_acceptance": {
            "keywords": ["验收", "标准", "acceptance", "criteria", "成功", "通过"],
            "description": "是否有验收标准"
        },
        "has_priority": {
            "keywords": ["优先级", "紧急", "priority", "urgent", "重要", "必须"],
            "description": "是否有优先级"
        },
        "has_user_story": {
            "keywords": ["用户", "角色", "user", "role", "作为", "想要"],
            "description": "是否有用户故事"
        },
    }
    
    # 功能点识别规则
    FEATURE_PATTERNS = [
        r"(?:实现|添加|创建|支持|提供|增加)\s*(.+?)(?:功能|特性|能力)",
        r"(?:功能|特性|能力)[:：]\s*(.+)",
        r"(?:需要|应该|必须)\s*(.+?)(?:。|；|$)",
    ]
    
    def analyze(self, description: str, context: Dict = None) -> RequirementAnalysis:
        """
        分析需求
        
        Args:
            description: 需求描述
            context: 上下文信息
        
        Returns:
            RequirementAnalysis: 分析结果
        """
        logger.info("analyzing_requirements", description_length=len(description))
        
        # 检查完整性
        completeness = self._check_completeness(description)
        completeness_score = sum(completeness.values()) / len(completeness)
        
        # 识别功能点
        features = self._extract_features(description)
        
        # 生成验收标准
        acceptance_criteria = self._generate_acceptance_criteria(description, features)
        
        # 生成建议
        missing = [k for k, v in completeness.items() if not v]
        recommendations = self._generate_recommendations(missing, features)
        
        result = RequirementAnalysis(
            completeness=completeness,
            completeness_score=completeness_score,
            features=features,
            acceptance_criteria=acceptance_criteria,
            recommendations=recommendations,
            missing=missing,
        )
        
        logger.info(
            "requirements_analyzed",
            completeness_score=completeness_score,
            features_count=len(features),
            missing_count=len(missing)
        )
        
        return result
    
    def _check_completeness(self, description: str) -> Dict[str, bool]:
        """检查需求完整性"""
        description_lower = description.lower()
        results = {}
        
        for rule_name, rule in self.COMPLETENESS_RULES.items():
            has_keyword = any(
                keyword in description_lower
                for keyword in rule["keywords"]
            )
            results[rule_name] = has_keyword
        
        return results
    
    def _extract_features(self, description: str) -> List[str]:
        """识别关键功能点"""
        features = []
        
        for pattern in self.FEATURE_PATTERNS:
            matches = re.findall(pattern, description)
            features.extend(matches)
        
        # 去重
        return list(set(features))
    
    def _generate_acceptance_criteria(self, description: str, features: List[str]) -> List[str]:
        """生成验收标准"""
        criteria = []
        
        # 基于功能点生成验收标准
        for feature in features[:5]:  # 最多5个
            criteria.append(f"功能 '{feature}' 正常工作")
            criteria.append(f"功能 '{feature}' 有测试覆盖")
        
        # 通用验收标准
        criteria.append("所有单元测试通过")
        criteria.append("代码覆盖率 ≥ 80%")
        criteria.append("无安全漏洞")
        
        return criteria
    
    def _generate_recommendations(self, missing: List[str], features: List[str]) -> List[str]:
        """生成建议"""
        recommendations = []
        
        # 基于缺失项生成建议
        missing_descriptions = {
            "has_goal": "建议添加明确的目标描述",
            "has_scope": "建议明确需求范围和边界",
            "has_acceptance": "建议定义验收标准",
            "has_priority": "建议标注优先级",
            "has_user_story": "建议添加用户故事",
        }
        
        for m in missing:
            if m in missing_descriptions:
                recommendations.append(missing_descriptions[m])
        
        # 基于功能点生成建议
        if len(features) == 0:
            recommendations.append("建议明确列出关键功能点")
        elif len(features) > 10:
            recommendations.append("功能点较多，建议拆分为多个需求")
        
        return recommendations


class DesignReviewer:
    """设计评审器"""
    
    # 设计检查规则
    DESIGN_RULES = {
        "has_architecture": {
            "keywords": ["架构", "architecture", "模块", "组件", "分层"],
            "description": "是否有架构设计"
        },
        "has_interface": {
            "keywords": ["接口", "interface", "API", "协议", "格式"],
            "description": "是否有接口设计"
        },
        "has_data_model": {
            "keywords": ["数据", "模型", "data", "model", "表", "字段"],
            "description": "是否有数据模型"
        },
        "has_error_handling": {
            "keywords": ["错误", "异常", "error", "exception", "处理", "恢复"],
            "description": "是否有错误处理"
        },
        "has_security": {
            "keywords": ["安全", "security", "认证", "授权", "加密"],
            "description": "是否有安全设计"
        },
        "has_performance": {
            "keywords": ["性能", "performance", "缓存", "优化", "并发"],
            "description": "是否有性能考虑"
        },
    }
    
    def review(self, design_doc: str, requirements: Dict = None) -> DesignReview:
        """
        评审设计
        
        Args:
            design_doc: 设计文档
            requirements: 需求分析结果
        
        Returns:
            DesignReview: 评审结果
        """
        logger.info("reviewing_design", design_doc_length=len(design_doc))
        
        # 检查设计覆盖
        coverage = self._check_coverage(design_doc)
        coverage_score = sum(coverage.values()) / len(coverage)
        
        # 识别问题
        issues = self._identify_issues(design_doc, requirements)
        
        # 生成建议
        suggestions = self._generate_suggestions(coverage, issues)
        
        # 判断是否通过
        passed = coverage_score >= 0.5 and len(issues) == 0
        
        result = DesignReview(
            coverage=coverage,
            coverage_score=coverage_score,
            issues=issues,
            suggestions=suggestions,
            passed=passed,
        )
        
        logger.info(
            "design_reviewed",
            coverage_score=coverage_score,
            issues_count=len(issues),
            passed=passed
        )
        
        return result
    
    def _check_coverage(self, design_doc: str) -> Dict[str, bool]:
        """检查设计覆盖"""
        design_doc_lower = design_doc.lower()
        results = {}
        
        for rule_name, rule in self.DESIGN_RULES.items():
            has_keyword = any(
                keyword in design_doc_lower
                for keyword in rule["keywords"]
            )
            results[rule_name] = has_keyword
        
        return results
    
    def _identify_issues(self, design_doc: str, requirements: Dict = None) -> List[Dict]:
        """识别设计问题"""
        issues = []
        
        # 检查设计覆盖
        coverage = self._check_coverage(design_doc)
        
        for rule_name, covered in coverage.items():
            if not covered:
                rule = self.DESIGN_RULES[rule_name]
                issues.append({
                    "severity": "warning",
                    "message": f"设计文档缺少 {rule['description']}",
                    "rule": rule_name,
                })
        
        # 检查需求覆盖
        if requirements:
            features = requirements.get("features", [])
            design_doc_lower = design_doc.lower()
            
            for feature in features:
                if feature.lower() not in design_doc_lower:
                    issues.append({
                        "severity": "warning",
                        "message": f"设计文档未覆盖功能点: {feature}",
                        "rule": "requirement_coverage",
                    })
        
        return issues
    
    def _generate_suggestions(self, coverage: Dict[str, bool], issues: List[Dict]) -> List[str]:
        """生成建议"""
        suggestions = []
        
        # 基于覆盖生成建议
        uncovered = [k for k, v in coverage.items() if not v]
        if uncovered:
            suggestions.append("建议补充设计文档中缺失的部分")
        
        # 基于问题生成建议
        if len(issues) > 3:
            suggestions.append("设计问题较多，建议重新评审")
        
        return suggestions


# 全局实例
requirements_analyzer = RequirementsAnalyzer()
design_reviewer = DesignReviewer()


def analyze_requirements(description: str, context: Dict = None) -> dict:
    """需求分析（对外接口）"""
    result = requirements_analyzer.analyze(description, context)
    return result.to_dict()


def review_design(design_doc: str, requirements: Dict = None) -> dict:
    """设计评审（对外接口）"""
    result = design_reviewer.review(design_doc, requirements)
    return result.to_dict()
