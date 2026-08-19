"""with_fallback 降级模块测试（v3.1 P0-2/4/5）

覆盖：
- test_fallback_deterministic_switch：确定性失败 → 换路由单次逃生（带 marker）；恢复后不再切
- test_fallback_wallclock_no_switch（P0-4）：墙钟/预算耗尽 → 逃生 0 次、异常原样上抛
- test_fallback_escape_deadline_guard（P0-5）：deadline 已过期时 primary 失败 → 逃生调用被拒
- test_fallback_transient_window_switch：瞬态失败窗口阈值 → 切直连
"""
import pytest

from finance.llm_errors import (
    DeterministicLLMFailure,
    LLMCallBudgetExceeded,
    WallClockDeadlineExceeded,
)
from finance.llm_fallback import with_fallback


def test_fallback_deterministic_switch():
    """确定性失败 → 直连文本带 marker；恢复后不再切（v3-code 缺陷 5/11）"""
    calls = {"primary": 0, "direct": 0}

    def primary(name, prompt):
        calls["primary"] += 1
        if calls["primary"] <= 2:
            raise DeterministicLLMFailure("预算耗尽空输出", finish_reason="max-tokens")
        return "primary-ok"

    def direct(name, prompt):
        calls["direct"] += 1
        return "direct-ok"

    fb = with_fallback(primary, lambda: direct, degrade_marker="<!-- 直连 -->")

    # 第 1、2 次：确定性失败 → 逃生直连（带 marker）
    out1 = fb("ch", "p")
    assert out1 == "direct-ok<!-- 直连 -->"
    assert calls["direct"] == 1
    out2 = fb("ch", "p")
    assert out2 == "direct-ok<!-- 直连 -->"
    assert calls["direct"] == 2

    # 第 3 次：primary 恢复 → 返回 primary 文本（窗口不清零，但成功不清零语义下不再切）
    out3 = fb("ch", "p")
    assert out3 == "primary-ok"
    assert calls["direct"] == 2  # 未再触发逃生


def test_fallback_wallclock_no_switch():
    """P0-4：墙钟/预算耗尽 → 逃生 0 次、异常原样上抛（白名单前置，不被父类遮蔽）"""
    direct_calls = {"n": 0}

    def primary(name, prompt):
        raise WallClockDeadlineExceeded("墙钟预算耗尽")

    def direct(name, prompt):
        direct_calls["n"] += 1
        return "direct-ok"

    fb = with_fallback(primary, lambda: direct)
    with pytest.raises(WallClockDeadlineExceeded):
        fb("ch", "p")
    assert direct_calls["n"] == 0  # 逃生调用数为 0

    # 预算耗尽同族：同样不逃生
    def primary_budget(name, prompt):
        raise LLMCallBudgetExceeded("调用超预算")

    fb2 = with_fallback(primary_budget, lambda: direct)
    with pytest.raises(LLMCallBudgetExceeded):
        fb2("ch", "p")
    assert direct_calls["n"] == 0


def test_fallback_escape_deadline_guard():
    """P0-5：deadline 已过期时 primary 失败 → 逃生调用被拒（monotonic()>deadline → raise）"""
    import time

    direct_calls = {"n": 0}

    def primary(name, prompt):
        raise ConnectionError("网络瞬态失败")

    def direct(name, prompt):
        direct_calls["n"] += 1
        return "direct-ok"

    # deadline 已过期（monotonic()-1）
    fb = with_fallback(primary, lambda: direct, fail_threshold=1, deadline=time.monotonic() - 1)
    with pytest.raises(WallClockDeadlineExceeded):
        fb("ch", "p")
    assert direct_calls["n"] == 0  # 逃生调用 0 次


def test_fallback_transient_window_switch():
    """瞬态失败窗口达阈值 → 切直连；未达阈值 → 原样上抛"""
    calls = {"primary": 0, "direct": 0}

    def primary(name, prompt):
        calls["primary"] += 1
        if calls["primary"] <= 3:
            raise ConnectionError("网络瞬态失败")
        return "primary-ok"

    def direct(name, prompt):
        calls["direct"] += 1
        return "direct-ok"

    fb = with_fallback(primary, lambda: direct, fail_threshold=3, window=4)

    # 前 2 次：未达阈值 → 原样上抛
    with pytest.raises(ConnectionError):
        fb("ch", "p")
    with pytest.raises(ConnectionError):
        fb("ch", "p")
    assert calls["direct"] == 0

    # 第 3 次：sum(hist)==3>=3 → 切换直连
    out = fb("ch", "p")
    assert out == "direct-ok"
    assert calls["direct"] == 1

    # 已切换后：primary 恢复成功 → 仍返回 primary 文本（K4：成功不清零，direct 仅失败时介入）
    out4 = fb("ch", "p")
    assert out4 == "primary-ok"
    assert calls["direct"] == 1


def test_fallback_transient_below_threshold_rethrows():
    """瞬态失败未达阈值 → 原样上抛（不切换）"""
    calls = {"primary": 0, "direct": 0}

    def primary(name, prompt):
        calls["primary"] += 1
        raise TimeoutError("超时")

    def direct(name, prompt):
        calls["direct"] += 1
        return "direct-ok"

    fb = with_fallback(primary, lambda: direct, fail_threshold=4, window=8)
    for _ in range(3):
        with pytest.raises(TimeoutError):
            fb("ch", "p")
    assert calls["direct"] == 0  # 未达阈值，不切换
