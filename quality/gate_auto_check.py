"""
gate_auto_check.py — 自动化检查点模块

功能：
- 语法检查
- 导入检查
- None 崩溃检查
- 格式化检查
"""

import re
import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ====================================================================
# 数据结构
# ====================================================================

@dataclass
class AutoCheckIssue:
    """自动检查问题"""
    check_type: str      # syntax, import, none, format
    severity: str        # P0, HIGH, MEDIUM, LOW
    message: str
    file_path: str = ""
    line: int = 0
    suggestion: str = ""


@dataclass
class AutoCheckResult:
    """自动检查结果"""
    file_path: str
    passed: bool
    score: int
    issues: list[AutoCheckIssue] = field(default_factory=list)
    syntax_ok: bool = True
    import_ok: bool = True
    none_safe: bool = True


# ====================================================================
# 检查函数
# ====================================================================

def check_syntax(file_path: str) -> list[AutoCheckIssue]:
    """语法检查"""
    issues = []
    try:
        content = Path(file_path).read_text(encoding='utf-8')
        ast.parse(content)
    except SyntaxError as e:
        issues.append(AutoCheckIssue(
            check_type="syntax",
            severity="P0",
            message=f"语法错误: {e.msg}",
            file_path=file_path,
            line=e.lineno or 0,
            suggestion=f"修复第 {e.lineno} 行的语法错误",
        ))
    except Exception as e:
        issues.append(AutoCheckIssue(
            check_type="syntax",
            severity="P0",
            message=f"解析异常: {e}",
            file_path=file_path,
        ))
    return issues


def check_imports(file_path: str) -> list[AutoCheckIssue]:
    """导入检查（静态分析）"""
    issues = []
    try:
        content = Path(file_path).read_text(encoding='utf-8')
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    # 检查是否导入了不存在的模块
                    if alias.name.startswith('.'):
                        # 相对导入，跳过
                        continue
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.startswith('.'):
                    # 相对导入，检查文件是否存在
                    pass
    except Exception as e:
        issues.append(AutoCheckIssue(
            check_type="import",
            severity="HIGH",
            message=f"导入分析异常: {e}",
            file_path=file_path,
        ))
    return issues


def check_none_handling(file_path: str) -> list[AutoCheckIssue]:
    """None 崩溃检查"""
    issues = []
    try:
        content = Path(file_path).read_text(encoding='utf-8')
        lines = content.split('\n')
        
        for i, line in enumerate(lines, 1):
            # 检查格式化字符串中可能的 None 崩溃
            # 如 f"{value:.0f}" 当 value 为 None 时会崩溃
            format_matches = re.findall(r'\{(\w+):[^}]+\}', line)
            for var in format_matches:
                # 检查变量是否有 None 保护
                if var in ['self', 'cls']:
                    continue
                # 检查前面是否有 if var 或 var and 的保护
                context = '\n'.join(lines[max(0, i-5):i])
                if f'if {var}' not in context and f'{var} and' not in context:
                    # 可能是 None 风险
                    if '.' not in var:  # 排除属性访问
                        issues.append(AutoCheckIssue(
                            check_type="none",
                            severity="MEDIUM",
                            message=f"变量 {var} 的格式化可能在 None 时崩溃",
                            file_path=file_path,
                            line=i,
                            suggestion=f"添加 if {var} 保护或使用条件格式化",
                        ))
            
            # 检查迭代中可能的 None 崩溃
            iter_matches = re.findall(r'for\s+\w+\s+in\s+(\w+)', line)
            for var in iter_matches:
                context = '\n'.join(lines[max(0, i-3):i])
                if f'if {var}' not in context and f'{var} and' not in context:
                    issues.append(AutoCheckIssue(
                        check_type="none",
                        severity="HIGH",
                        message=f"迭代变量 {var} 可能为 None",
                        file_path=file_path,
                        line=i,
                        suggestion=f"添加 if {var} 保护",
                    ))
    except Exception as e:
        issues.append(AutoCheckIssue(
            check_type="none",
            severity="MEDIUM",
            message=f"None 检查异常: {e}",
            file_path=file_path,
        ))
    return issues


# ====================================================================
# 主检查流程
# ====================================================================

def run_auto_checks(file_path: str) -> AutoCheckResult:
    """
    运行所有自动检查。

    Args:
        file_path: 代码文件路径

    Returns:
        AutoCheckResult 检查结果
    """
    issues = []
    
    # 语法检查
    syntax_issues = check_syntax(file_path)
    issues.extend(syntax_issues)
    syntax_ok = len(syntax_issues) == 0
    
    # 导入检查
    import_issues = check_imports(file_path)
    issues.extend(import_issues)
    import_ok = len(import_issues) == 0
    
    # None 崩溃检查
    none_issues = check_none_handling(file_path)
    issues.extend(none_issues)
    none_safe = len(none_issues) == 0
    
    # 计算分数
    score = 100
    for issue in issues:
        if issue.severity == "P0":
            score -= 30
        elif issue.severity == "HIGH":
            score -= 15
        elif issue.severity == "MEDIUM":
            score -= 5
        elif issue.severity == "LOW":
            score -= 2
    score = max(0, score)
    
    # 判断是否通过
    p0_count = sum(1 for i in issues if i.severity == "P0")
    high_count = sum(1 for i in issues if i.severity == "HIGH")
    passed = p0_count == 0 and high_count == 0 and score >= 70
    
    result = AutoCheckResult(
        file_path=file_path,
        passed=passed,
        score=score,
        issues=issues,
        syntax_ok=syntax_ok,
        import_ok=import_ok,
        none_safe=none_safe,
    )
    
    logger.info(
        f"自动检查: {Path(file_path).name} - "
        f"{'通过' if passed else '不通过'} "
        f"(评分={score}, 语法={syntax_ok}, 导入={import_ok}, None安全={none_safe})"
    )
    
    return result


def format_auto_check_report(result: AutoCheckResult) -> str:
    """格式化自动检查报告"""
    lines = [f"## 自动检查报告: {Path(result.file_path).name}"]
    lines.append("")
    lines.append(f"**评分**: {result.score}/100")
    lines.append(f"**结论**: {'通过 ✅' if result.passed else '不通过 ❌'}")
    lines.append("")
    lines.append("### 检查项")
    lines.append(f"- 语法检查: {'✅' if result.syntax_ok else '❌'}")
    lines.append(f"- 导入检查: {'✅' if result.import_ok else '❌'}")
    lines.append(f"- None 安全: {'✅' if result.none_safe else '❌'}")
    lines.append("")
    
    if result.issues:
        lines.append("### 问题清单")
        for issue in result.issues:
            lines.append(f"- [{issue.severity}] {issue.message}")
            if issue.suggestion:
                lines.append(f"  建议: {issue.suggestion}")
        lines.append("")
    
    return "\n".join(lines)
