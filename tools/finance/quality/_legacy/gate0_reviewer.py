"""
gate0_reviewer.py — Gate 0: 设计预审模块

在编码前识别架构级风险，减少 Gate 1 和 Gate 5+6 的返工。

检查清单：
- A-01: 模块接口是否清晰（函数签名、docstring、类型注解）
- A-02: 数据流是否完整（输入来源、输出去向）
- A-03: 错误处理是否完善（try/except 覆盖率）
- T-01: 测试策略是否明确
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
class FunctionInfo:
    """函数信息"""
    name: str
    line: int
    has_docstring: bool
    has_type_hints: bool
    params: list[str]
    return_annotation: Optional[str]


@dataclass
class Gate0Issue:
    """Gate 0 问题"""
    id: str              # A-01, A-02, A-03, T-01
    severity: str        # P0, P1, P2
    message: str
    file_path: str = ""
    line: int = 0
    suggestion: str = ""


@dataclass
class Gate0Result:
    """Gate 0 评估结果"""
    module_name: str
    passed: bool
    score: int
    issues: list[Gate0Issue] = field(default_factory=list)
    function_count: int = 0
    functions_with_docstring: int = 0
    functions_with_type_hints: int = 0
    try_except_count: int = 0
    external_call_count: int = 0
    has_test_file: bool = False


# ====================================================================
# 检查清单
# ====================================================================

CHECKLIST = {
    "A-01": {
        "question": "模块接口是否清晰？",
        "severity": "P0",
        "check_points": [
            "函数签名是否有类型注解",
            "函数是否有 docstring",
            "类是否有 docstring",
        ],
    },
    "A-02": {
        "question": "数据流是否完整？",
        "severity": "P0",
        "check_points": [
            "输入参数是否有明确来源",
            "返回值是否有明确去向",
            "是否有数据丢失风险",
        ],
    },
    "A-03": {
        "question": "错误处理是否完善？",
        "severity": "P1",
        "check_points": [
            "外部调用是否有 try/except",
            "失败时是否有降级路径",
            "错误信息是否足够诊断",
        ],
    },
    "T-01": {
        "question": "测试策略是否明确？",
        "severity": "P1",
        "check_points": [
            "是否有对应的测试文件",
            "测试覆盖了哪些场景",
        ],
    },
}


# ====================================================================
# 代码分析
# ====================================================================

def extract_function_info(file_path: str) -> list[FunctionInfo]:
    """提取文件中的函数信息"""
    functions = []
    
    try:
        content = Path(file_path).read_text(encoding='utf-8')
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # 检查 docstring
                has_docstring = (
                    node.body
                    and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, (ast.Str, ast.Constant))
                )
                
                # 检查类型注解
                has_type_hints = False
                if node.returns:
                    has_type_hints = True
                for arg in node.args.args:
                    if arg.annotation:
                        has_type_hints = True
                        break
                
                # 提取参数
                params = [arg.arg for arg in node.args.args if arg.arg != 'self']
                
                # 返回注解
                return_annotation = None
                if node.returns:
                    if isinstance(node.returns, ast.Name):
                        return_annotation = node.returns.id
                    elif isinstance(node.returns, ast.Constant):
                        return_annotation = str(node.returns.value)
                
                functions.append(FunctionInfo(
                    name=node.name,
                    line=node.lineno,
                    has_docstring=has_docstring,
                    has_type_hints=has_type_hints,
                    params=params,
                    return_annotation=return_annotation,
                ))
    except Exception as e:
        logger.warning(f"提取函数信息失败: {e}")
    
    return functions


def count_try_except(file_path: str) -> int:
    """统计 try/except 数量"""
    try:
        content = Path(file_path).read_text(encoding='utf-8')
        tree = ast.parse(content)
        return sum(1 for node in ast.walk(tree) if isinstance(node, ast.TryExcept))
    except:
        return 0


def count_external_calls(file_path: str) -> int:
    """统计外部调用数量（近似）"""
    try:
        content = Path(file_path).read_text(encoding='utf-8')
        # 匹配 llm_caller(), terminal(), 等外部调用
        patterns = [
            r'llm_caller\(',
            r'terminal\(',
            r'requests\.',
            r'subprocess\.',
            r'open\(',
            r'Path\(.*\)\.read',
            r'Path\(.*\)\.write',
        ]
        count = 0
        for pattern in patterns:
            count += len(re.findall(pattern, content))
        return count
    except:
        return 0


def check_test_file(file_path: str) -> bool:
    """检查是否有对应的测试文件"""
    path = Path(file_path)
    test_patterns = [
        path.parent / f"test_{path.name}",
        path.parent / f"{path.stem}_test.py",
        path.parent / "tests" / f"test_{path.name}",
    ]
    return any(p.exists() for p in test_patterns)


# ====================================================================
# Gate 0 预审
# ====================================================================

def run_gate0_review(
    file_path: str,
    module_name: Optional[str] = None,
) -> Gate0Result:
    """
    运行 Gate 0 设计预审。

    Args:
        file_path: 代码文件路径
        module_name: 模块名称（可选）

    Returns:
        Gate0Result 预审结果
    """
    if module_name is None:
        module_name = Path(file_path).stem
    
    issues = []
    
    # === A-01: 接口清晰度 ===
    functions = extract_function_info(file_path)
    functions_with_docstring = sum(1 for f in functions if f.has_docstring)
    functions_with_type_hints = sum(1 for f in functions if f.has_type_hints)
    
    for func in functions:
        if not func.has_docstring:
            issues.append(Gate0Issue(
                id="A-01",
                severity="P1",
                message=f"函数 {func.name}() 缺少 docstring",
                file_path=file_path,
                line=func.line,
                suggestion=f"为 {func.name}() 添加 docstring，说明参数和返回值",
            ))
        if not func.has_type_hints:
            issues.append(Gate0Issue(
                id="A-01",
                severity="P2",
                message=f"函数 {func.name}() 缺少类型注解",
                file_path=file_path,
                line=func.line,
                suggestion=f"为 {func.name}() 添加参数和返回值类型注解",
            ))
    
    # === A-03: 错误处理 ===
    try_except_count = count_try_except(file_path)
    external_call_count = count_external_calls(file_path)
    
    if external_call_count > 0:
        coverage = try_except_count / external_call_count
        if coverage < 0.5:
            issues.append(Gate0Issue(
                id="A-03",
                severity="P1",
                message=f"外部调用 {external_call_count} 个，但 try/except 仅 {try_except_count} 个（覆盖率 {coverage:.0%}）",
                file_path=file_path,
                suggestion="为外部调用添加 try/except 和降级策略",
            ))
    
    # === T-01: 测试策略 ===
    has_test_file = check_test_file(file_path)
    if not has_test_file:
        issues.append(Gate0Issue(
            id="T-01",
            severity="P1",
            message=f"缺少对应的测试文件",
            file_path=file_path,
            suggestion=f"创建 test_{Path(file_path).name} 或 {Path(file_path).stem}_test.py",
        ))
    
    # === 计算分数 ===
    score = 100
    for issue in issues:
        if issue.severity == "P0":
            score -= 20
        elif issue.severity == "P1":
            score -= 10
        elif issue.severity == "P2":
            score -= 3
    score = max(0, score)
    
    # === 判断是否通过 ===
    p0_count = sum(1 for i in issues if i.severity == "P0")
    high_count = sum(1 for i in issues if i.severity == "P1")
    passed = p0_count == 0 and high_count <= 2 and score >= 60
    
    result = Gate0Result(
        module_name=module_name,
        passed=passed,
        score=score,
        issues=issues,
        function_count=len(functions),
        functions_with_docstring=functions_with_docstring,
        functions_with_type_hints=functions_with_type_hints,
        try_except_count=try_except_count,
        external_call_count=external_call_count,
        has_test_file=has_test_file,
    )
    
    logger.info(
        f"Gate 0 预审: {module_name} - "
        f"{'通过' if passed else '不通过'} "
        f"(评分={score}, P0={p0_count}, HIGH={high_count})"
    )
    
    return result


def format_gate0_report(result: Gate0Result) -> str:
    """格式化 Gate 0 报告"""
    lines = [f"## Gate 0 预审报告: {result.module_name}"]
    lines.append("")
    lines.append(f"**评分**: {result.score}/100")
    lines.append(f"**结论**: {'通过 ✅' if result.passed else '不放行 ❌'}")
    lines.append("")
    
    lines.append("### 代码质量")
    lines.append(f"- 函数数量: {result.function_count}")
    lines.append(f"- 有 docstring: {result.functions_with_docstring}/{result.function_count}")
    lines.append(f"- 有类型注解: {result.functions_with_type_hints}/{result.function_count}")
    lines.append(f"- try/except: {result.try_except_count}")
    lines.append(f"- 外部调用: {result.external_call_count}")
    lines.append(f"- 有测试文件: {'是' if result.has_test_file else '否'}")
    lines.append("")
    
    if result.issues:
        lines.append("### 问题清单")
        for issue in result.issues:
            lines.append(f"- [{issue.severity}] {issue.message}")
            if issue.suggestion:
                lines.append(f"  建议: {issue.suggestion}")
        lines.append("")
    
    return "\n".join(lines)
