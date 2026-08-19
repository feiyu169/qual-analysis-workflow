"""run 脚本 with_fallback 一致性测试（v3.1 P0-2）

验收：两 run 脚本（run_qual_full.py / run_xpev_full.py）不再内联 _llm_with_fallback，
统一 import finance.llm_fallback.with_fallback，且调用参数一致（防双维护漂移）。
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # workspace 根（tests 在 tools/finance/ 下）
RUN_SCRIPTS = ["run_qual_full.py", "run_xpev_full.py"]


def _script_tree(name: str) -> ast.Module:
    path = ROOT / name
    assert path.exists(), f"{name} 不存在: {path}"
    src = path.read_text(encoding="utf-8")
    return ast.parse(src, filename=name)


def _collect_imports(tree: ast.Module) -> set[tuple[str, str]]:
    """收集 (模块, 名字) 导入对：from X import Y / import X"""
    out: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.add((alias.name, alias.asname or alias.name.split(".")[-1]))
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                out.add((f"{mod}.{alias.name}", alias.asname or alias.name))
    return out


def _find_with_fallback_calls(tree: ast.Module) -> list[ast.Call]:
    """收集 with_fallback(...) 调用节点"""
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "with_fallback":
            calls.append(node)
    return calls


def test_run_scripts_consistent():
    """两脚本用同一 with_fallback 模块，无内联 _llm_with_fallback"""
    for name in RUN_SCRIPTS:
        tree = _script_tree(name)

        # 1. 内联 _llm_with_fallback 函数定义不存在（v3.1 P0-2：幽灵内联已移除）
        func_defs = {
            n.name for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert "_llm_with_fallback" not in func_defs, f"{name} 仍含内联 _llm_with_fallback"

        # 2. 从 finance.llm_fallback import with_fallback
        imports = _collect_imports(tree)
        assert ("finance.llm_fallback.with_fallback", "with_fallback") in imports, \
            f"{name} 未从 finance.llm_fallback 导入 with_fallback"

        # 3. 调用点存在且传 fail_threshold/window
        calls = _find_with_fallback_calls(tree)
        assert calls, f"{name} 未调用 with_fallback"
        for call in calls:
            kwargs = {kw.arg: kw.value for kw in call.keywords if kw.arg}
            assert "fail_threshold" in kwargs and "window" in kwargs, \
                f"{name} with_fallback 调用缺少 fail_threshold/window 参数"


def _lit(node):
    """AST 节点 → 字面量（仅 Constant 支持）"""
    if isinstance(node, ast.Constant):
        return node.value
    return None


def test_run_scripts_same_module_and_params():
    """两脚本 with_fallback 参数一致（防双维护漂移）"""
    params_per_script = {}
    for name in RUN_SCRIPTS:
        tree = _script_tree(name)
        calls = _find_with_fallback_calls(tree)
        assert calls, f"{name} 未调用 with_fallback"
        call = calls[0]  # 每脚本仅一处调用
        kwargs = {kw.arg: _lit(kw.value) for kw in call.keywords if kw.arg and _lit(kw.value) is not None}
        params_per_script[name] = kwargs

    qual, xpev = RUN_SCRIPTS
    assert params_per_script[qual]["fail_threshold"] == params_per_script[xpev]["fail_threshold"]
    assert params_per_script[qual]["window"] == params_per_script[xpev]["window"]
