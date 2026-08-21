"""
YearAnchor模块

功能:
- YearPromptBuilder: 生成prompt注入
- YearErrorDetector: 检测年份错标
- YearTextFixer: 修正年份表述

解决: S01 年份锚点错误
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class YearError:
    """年份错误"""
    pattern: str
    message: str
    location: str = ""


class YearPromptBuilder:
    """年份Prompt注入器"""

    def __init__(self, fiscal_year: int = 2025):
        self.fiscal_year = fiscal_year

    def build(self) -> str:
        """生成年份锚点prompt"""
        return f"""
【强制年份锚点】
- 本报告分析的财年为FY{self.fiscal_year}
- "最近一年"指FY{self.fiscal_year}
- "同比"指FY{self.fiscal_year} vs FY{self.fiscal_year - 1}
- "三年CAGR"指FY{self.fiscal_year - 2}到FY{self.fiscal_year}
- 禁止使用"2024财年"表述FY{self.fiscal_year}的数据
- 所有财务数据必须标注具体财年(FY{self.fiscal_year-2}/FY{self.fiscal_year-1}/FY{self.fiscal_year})
"""


class YearErrorDetector:
    """年份错误检测器"""

    # 已知错误模式
    ERROR_PATTERNS = [
        (r'2024财年.*?3,?082', '年份错标: 3082亿是FY2025数据'),
        (r'2024财年.*?111', '年份错标: 111亿是FY2025数据'),
        (r'2024财年.*?8\.4%', '年份错标: 8.4%是FY2025增速'),
        (r'2024财年.*?9\.3%', '年份错标: 9.3%是FY2025增速'),
    ]

    def __init__(self, fiscal_year: int = 2025):
        self.fiscal_year = fiscal_year

    def detect(self, content: str) -> list[str]:
        """检测年份错标"""
        errors = []

        for pattern, msg in self.ERROR_PATTERNS:
            if re.search(pattern, content):
                errors.append(msg)

        return errors

    def detect_detailed(self, content: str) -> list[YearError]:
        """检测年份错标（详细版本）"""
        errors = []

        for pattern, msg in self.ERROR_PATTERNS:
            match = re.search(pattern, content)
            if match:
                errors.append(YearError(
                    pattern=pattern,
                    message=msg,
                    location=f"位置: {match.start()}-{match.end()}"
                ))

        return errors


class YearTextFixer:
    """年份文本修正器"""

    def __init__(self, target_year: int = 2025):
        self.target_year = target_year

    def fix(self, content: str) -> str:
        """修正年份表述"""
        # 修正"2024财年"为"2025财年"（如果包含2025年数据）
        if '2024财年' in content and self._contains_current_year_data(content):
            content = content.replace('2024财年', f'{self.target_year}财年')

        return content

    def _contains_current_year_data(self, content: str) -> bool:
        """检查是否包含当前财年数据"""
        # 检查是否包含2025年的标志性数据
        current_year_indicators = ['3,082', '111', '8.4%', '9.3%']
        return any(indicator in content for indicator in current_year_indicators)

    def fix_all_patterns(self, content: str) -> str:
        """修正所有年份错误模式"""
        # 通用修正: 将错误的年份替换为正确的年份
        replacements = [
            ('2024财年', f'{self.target_year}财年'),
            ('FY2024', f'FY{self.target_year}'),
        ]

        for old, new in replacements:
            if old in content and self._contains_current_year_data(content):
                content = content.replace(old, new)

        return content


@dataclass
class YearAnchorResult:
    """年份锚点完整结果"""
    prompt: str
    errors: list[str]
    fixed_content: str
    has_errors: bool = False


class YearAnchor:
    """年份锚点管理器（组合三个子模块）"""

    def __init__(self, fiscal_year: int = 2025):
        self.fiscal_year = fiscal_year
        self.prompt_builder = YearPromptBuilder(fiscal_year)
        self.error_detector = YearErrorDetector(fiscal_year)
        self.text_fixer = YearTextFixer(fiscal_year)

    def process(self, content: str) -> YearAnchorResult:
        """完整处理流程: 检测→修正→生成prompt"""
        # 1. 生成prompt
        prompt = self.prompt_builder.build()

        # 2. 检测错误
        errors = self.error_detector.detect(content)

        # 3. 修正内容
        fixed_content = content
        if errors:
            fixed_content = self.text_fixer.fix(content)

        return YearAnchorResult(
            prompt=prompt,
            errors=errors,
            fixed_content=fixed_content,
            has_errors=len(errors) > 0
        )
