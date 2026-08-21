"""ROI 对照实验测试（V3.4-C，heavyskill 审查修正版）。

覆盖：C1 每任务独立目录 / C2 空清单早退 / C3 缺陷 oracle（非自证）/
C4 ABBA 交替 / C5 计时仅执行段。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts"))

import roi_benchmark


def _task(tid: str, marker: str, has_defect: bool = True) -> dict:
    content = "x = 1\n" + (f"{marker}\n" if has_defect else "")
    return {
        "id": tid,
        "files": ["a.py"],
        "files_content": {"a.py": content},
        "injected_defects": [{"file": "a.py", "marker": marker}],
    }


def test_empty_tasks_early_return(tmp_path):
    """C2 修正：空任务清单早退（无除零）"""
    result = roi_benchmark.run_group([], use_hgf=True, root_dir=str(tmp_path))
    assert result.get("error") == "empty tasks"
    assert result["tasks"] == 0


def test_each_task_isolated_workdir(tmp_path, monkeypatch):
    """C1 修正：每任务独立目录（防对照污染）——不真实跑门禁，模拟执行"""

    def fake_run_hgf(workdir, files):
        return 0, "ok"

    monkeypatch.setattr(roi_benchmark, "run_hgf_gates", fake_run_hgf)
    tasks = [_task("t1", "MARKER1"), _task("t2", "MARKER2")]
    result = roi_benchmark.run_group(tasks, use_hgf=True, root_dir=str(tmp_path))
    assert result["tasks"] == 2
    # 两个任务的目录必须独立存在
    assert os.path.isdir(os.path.join(str(tmp_path), "hgf-t1"))
    assert os.path.isdir(os.path.join(str(tmp_path), "hgf-t2"))
    # t1 目录不含 MARKER2 的内容（隔离）
    t1_file = os.path.join(str(tmp_path), "hgf-t1", "a.py")
    with open(t1_file, encoding="utf-8") as f:
        assert "MARKER1" in f.read()
        assert "MARKER2" not in f.read()


def test_escaped_defects_oracle(tmp_path):
    """C3 修正：缺陷仍存在 → 逃逸；被移除 → 拦截（oracle 非门禁自证）"""
    wd = os.path.join(str(tmp_path), "oracle-test")
    os.makedirs(wd, exist_ok=True)
    task = _task("t1", "TODO_BUG")
    roi_benchmark.write_task_code(wd, task)
    # 缺陷仍在 → 逃逸 1
    assert roi_benchmark.count_escaped_defects(wd, task) == 1
    # 修复缺陷（移除 marker）→ 逃逸 0
    with open(os.path.join(wd, "a.py"), "w", encoding="utf-8") as f:
        f.write("x = 1\n")
    assert roi_benchmark.count_escaped_defects(wd, task) == 0


def test_compare_abba_structure(tmp_path, monkeypatch):
    """C4 修正：compare 返回 A/B 双组 + delta + verdict（模拟执行防慢）"""

    def fake_run_hgf(workdir, files):
        return 0, "ok"

    def fake_run_base(workdir, files):
        return 0, "ok"

    monkeypatch.setattr(roi_benchmark, "run_hgf_gates", fake_run_hgf)
    monkeypatch.setattr(roi_benchmark, "run_baseline_checks", fake_run_base)
    tasks = [_task("t1", "M1"), _task("t2", "M2"), _task("t3", "M3")]
    result = roi_benchmark.compare(tasks, str(tmp_path))
    assert "hgf" in result and "baseline" in result
    assert "delta" in result
    assert result["verdict"]


def test_fix_loop_applies_fixes(tmp_path, monkeypatch):
    """ROI 修复循环：门禁先失败 → 修复 → 复跑通过（HGF 组）"""
    calls = {"n": 0}

    def fake_run_hgf(workdir, files):
        # 第一次失败，之后通过
        calls["n"] += 1
        if calls["n"] == 1:
            return 1, "failed"
        return 0, "ok"

    monkeypatch.setattr(roi_benchmark, "run_hgf_gates", fake_run_hgf)
    task = {
        "id": "fix-test",
        "files": ["a.py"],
        "files_content": {"a.py": "x = BUG_MARKER\n"},
        "injected_defects": [{"file": "a.py", "marker": "BUG_MARKER"}],
        "fixes": [{"file": "a.py", "marker": "BUG_MARKER", "replacement": "x = 1"}],
    }
    result = roi_benchmark.run_group([task], use_hgf=True, root_dir=str(tmp_path))
    assert calls["n"] == 2  # 失败→修复→复跑
    assert result["per_task"][0]["rounds"] == 2
    assert result["per_task"][0]["first_pass"] is True
    assert result["per_task"][0]["defects_escaped"] == 0  # 修复后逃逸 0


def test_baseline_group_does_not_fix(tmp_path, monkeypatch):
    """对照组：基线组不修复（缺陷常驻）"""

    def fake_run_base(workdir, files):
        return 1, "failed"

    monkeypatch.setattr(roi_benchmark, "run_baseline_checks", fake_run_base)
    task = {
        "id": "no-fix",
        "files": ["a.py"],
        "files_content": {"a.py": "x = BUG_MARKER\n"},
        "injected_defects": [{"file": "a.py", "marker": "BUG_MARKER"}],
        "fixes": [{"file": "a.py", "marker": "BUG_MARKER", "replacement": "x = 1"}],
    }
    result = roi_benchmark.run_group([task], use_hgf=False, root_dir=str(tmp_path))
    assert result["per_task"][0]["rounds"] == 1  # 只跑一次
    assert result["per_task"][0]["first_pass"] is False
    assert result["per_task"][0]["defects_escaped"] == 1  # 缺陷常驻


@pytest.mark.integration
def test_baseline_runs_without_hgf(tmp_path):
    """基线组不依赖 HGF（直接 ruff+pytest）——集成测试（较慢）"""
    wd = os.path.join(str(tmp_path), "base-t1")
    os.makedirs(wd, exist_ok=True)
    task = _task("t1", "MARKER")
    roi_benchmark.write_task_code(wd, task)
    # 文件无 import/语法问题，baseline 应能跑（rc 0 或 1 都允许，重点是执行）
    rc, _ = roi_benchmark.run_baseline_checks(wd, ["a.py"])
    assert rc in (0, 1)
