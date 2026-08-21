"""金丝雀版本回归（V3.2.8）。

背景：工具升级会静默改变门禁语义（ruff 0.16 规则集、safety/checkov JSON
结构漂移都是实证）。金丝雀 = 一组轻量快速检查；当 baseline 检测到工具版本
漂移时，运行金丝雀并报告——把"工具升级后门禁是否仍可信"变成可验证动作。

用法：
    python workflow_cli.py --canary [--dir .]
"""

import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

CONFIG_PATH = os.path.join(_HERE, "config", "mcp-gates.yaml")

# 金丝雀覆盖的 Python 核心文件（快速 ruff 检查）
CANARY_FILES = [
    "gate_executor.py",
    "gate_plugins.py",
    "gate_types.py",
    "gate_plugin.py",
    "lifecycle.py",
    "risk_assessor.py",
    "task_classifier.py",
    "failure_log.py",
]
# 金丝雀快速测试子集（秒级）
CANARY_TESTS = ["tests/test_baseline.py", "tests/test_failure_log.py"]


def current_tool_versions() -> dict:
    """当前各门禁工具版本（供漂移比较）"""
    try:
        import baseline
        from gate_executor import GateExecutor

        executor = GateExecutor(CONFIG_PATH)
        snap = baseline.snapshot(executor.config_path, executor.plugins)
        return snap["tool_versions"]
    except Exception:
        return {}


def drift_from_baseline(working_dir: str) -> list[str]:
    """当前工具版本 vs .hgf/baseline.json 记录的版本 → 漂移列表。

    V3.3.2（自审查 S2 修复）：baseline.load 对损坏文件返回 None（容错），
    此处若 prev 为 None（文件缺失或损坏），自动重建基线快照——把"损坏
    状态"收敛为"已重建"，而不是每次运行都重复告警/当作漂移。
    """
    import baseline

    prev = baseline.load(working_dir)
    if prev is None:
        # 文件缺失或损坏：重建基线（以当前快照为准），返回"重建"信息
        try:
            from gate_executor import GateExecutor

            executor = GateExecutor(CONFIG_PATH)
            snap = baseline.snapshot(executor.config_path, executor.plugins)
            baseline.save(working_dir, snap)
            return ["基线缺失或损坏，已重建基线快照"]
        except Exception as e:
            return [f"基线重建失败（{e}），按无基线处理"]
    current = {
        "config_sha256": prev.get("config_sha256") if prev else None,
        "tool_versions": current_tool_versions(),
    }
    return baseline.drift(prev, current)


def run_canary(working_dir: str) -> dict:
    """运行金丝雀集（真实执行：ruff + 快速测试子集）"""
    import time

    start = time.time()

    ruff = subprocess.run(
        ["ruff", "check"] + CANARY_FILES,
        cwd=_HERE,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    pytest = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"] + CANARY_TESTS,
        cwd=_HERE,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )
    return {
        "ruff": {
            "ok": ruff.returncode == 0,
            "output": (ruff.stdout or ruff.stderr)[-500:],
        },
        "pytest": {
            "ok": pytest.returncode == 0,
            "output": (pytest.stdout or pytest.stderr)[-500:],
        },
        "duration_s": round(time.time() - start, 1),
    }


def check(working_dir: str = ".", force: bool = False) -> dict:
    """入口：检测漂移（可选强制）→ 跑金丝雀 → 返回结果"""
    drift = drift_from_baseline(working_dir)
    if not force and not drift:
        return {"drift": [], "skipped": True, "message": "无工具版本漂移，金丝雀跳过"}
    result = run_canary(working_dir)
    result["drift"] = drift
    result["skipped"] = False
    all_ok = result["ruff"]["ok"] and result["pytest"]["ok"]
    result["ok"] = all_ok
    return result
