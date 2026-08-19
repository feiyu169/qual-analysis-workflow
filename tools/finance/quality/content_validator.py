"""
内容验证器（语义一致性验证）

功能：
1. 模式匹配验证
2. 长度验证
3. 章节标记验证
4. 语义一致性验证
"""

import re
import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """验证结果"""
    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class ContentValidator:
    """内容验证器"""
    
    # 无效内容特征
    INVALID_PATTERNS = [
        "[Placeholder]",
        "XX亿元",
        "XX港元",
        "XX元",
        "具体数据待核实",
        "数据不足",
        "需要配置 LLM API",
        "TBD",
        "TK",
        "待补充",
        "待完善",
    ]
    
    # 最小内容长度
    MIN_CONTENT_LENGTH = 100
    
    # 必需章节标记
    REQUIRED_SECTIONS = ["## ", "### "]
    
    # 关键数字模式（用于语义验证）
    KEY_NUMBER_PATTERNS = [
        (r'(-?\d+\.?\d*)\s*亿元', '金额'),
        (r'(-?\d+\.?\d*)%', '百分比'),
        (r'PE\s*(\d+\.?\d*)x', 'PE倍数'),
        (r'PB\s*(\d+\.?\d*)x', 'PB倍数'),
        (r'PS\s*(\d+\.?\d*)x', 'PS倍数'),
    ]
    
    # 语义一致性规则
    SEMANTIC_RULES = [
        {
            "name": "营收增长与描述一致",
            "pattern": r'营收.*?增长.*?(-?\d+\.?\d*)%',
            "check": lambda m: float(m.group(1)) > 0,
            "error": "描述'增长'但百分比为负",
        },
        {
            "name": "营收下降与描述一致",
            "pattern": r'营收.*?下降.*?(-?\d+\.?\d*)%',
            "check": lambda m: float(m.group(1)) < 0,
            "error": "描述'下降'但百分比为正",
        },
        {
            "name": "净利润为正时不应描述亏损",
            "pattern": r'净利润.*?(-?\d+\.?\d*)\s*亿.*?亏损',
            "check": lambda m: float(m.group(1)) < 0,
            "error": "净利润为正但描述为亏损",
        },
    ]
    
    @classmethod
    def validate(cls, content: str, chapter_id: str = "unknown") -> ValidationResult:
        """验证内容"""
        errors = []
        warnings = []
        
        if not content:
            return ValidationResult(passed=False, errors=["内容为空"])
        
        # 1. 模式匹配验证
        for pattern in cls.INVALID_PATTERNS:
            if pattern in content:
                errors.append(f"包含无效模式: {pattern}")
        
        # 2. 长度验证
        if len(content) < cls.MIN_CONTENT_LENGTH:
            errors.append(f"内容过短: {len(content)}字符 (最小{cls.MIN_CONTENT_LENGTH})")
        
        # 3. 章节标记验证
        if not any(s in content for s in cls.REQUIRED_SECTIONS):
            warnings.append("缺少章节标记 (## 或 ###)")
        
        # 4. 语义一致性验证
        semantic_errors = cls._validate_semantic_consistency(content)
        errors.extend(semantic_errors)
        
        return ValidationResult(
            passed=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )
    
    @classmethod
    def _validate_semantic_consistency(cls, content: str) -> List[str]:
        """语义一致性验证"""
        errors = []
        
        # 应用语义规则
        for rule in cls.SEMANTIC_RULES:
            matches = re.finditer(rule["pattern"], content)
            for match in matches:
                try:
                    if not rule["check"](match):
                        errors.append(f"语义不一致: {rule['error']}")
                except (ValueError, AttributeError):
                    pass
        
        # 检查数字合理性
        for pattern, name in cls.KEY_NUMBER_PATTERNS:
            matches = re.finditer(pattern, content)
            for match in matches:
                try:
                    value = float(match.group(1))
                    
                    # 检查异常值
                    if name == '金额' and abs(value) > 10000:
                        errors.append(f"金额异常大: {value}亿元")
                    elif name == '百分比' and abs(value) > 100:
                        errors.append(f"百分比异常: {value}%")
                    elif name in ['PE倍数', 'PB倍数', 'PS倍数'] and value < 0:
                        errors.append(f"{name}为负值: {value}")
                except (ValueError, AttributeError):
                    pass
        
        return errors
    
    @classmethod
    def validate_for_checkpoint(cls, content: str, chapter_id: str) -> bool:
        """验证内容是否适合保存到checkpoint"""
        result = cls.validate(content, chapter_id)
        
        if not result.passed:
            logger.info(f"第{chapter_id}章内容验证失败: {result.errors}")
            return False
        
        if result.warnings:
            logger.warning(f"第{chapter_id}章内容有警告: {result.warnings}")
        
        return True
    
    @classmethod
    def get_invalid_patterns(cls) -> List[str]:
        """获取无效模式列表"""
        return cls.INVALID_PATTERNS.copy()
    
    @classmethod
    def add_invalid_pattern(cls, pattern: str):
        """添加无效模式"""
        if pattern not in cls.INVALID_PATTERNS:
            cls.INVALID_PATTERNS.append(pattern)
            logger.info(f"添加无效模式: {pattern}")
