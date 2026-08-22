"""HGF L1 测试：v3.1 阶段 A P0-A 三项（签名保留章节号 / 豁免 fail-closed / 单调守卫）

对应 docs/qual-loop-fix-design-v3.md P0-A-1/2/3 与 v3.1 清单 P0-1..7。
"""
import sys
from unittest.mock import MagicMock

sys.path.insert(0, r'D:\OneDrive\文档\deepseek harness workspace\tools')

import pytest

from finance.quality.review_repair_loop import (
    _issue_signature,
    review_and_repair_loop,
)

# ============ P0-A-1: _issue_signature 三段式 ============

def test_signature_keeps_chapter():
    """跨章同形问题签名必须不同（v3.1 P0-A-1，v2 缺陷16 修复）"""
    s4 = _issue_signature("第4章营收增长100亿无解释")
    s5 = _issue_signature("第5章营收增长100亿无解释")
    assert s4 != s5, f"跨章签名应不同: {s4} == {s5}"


def test_signature_multidigit_chapter():
    """多数字节（第12章）不破损"""
    s = _issue_signature("第12章总资产827.06亿元")
    assert "第@12章" in s, f"多数字节应保留: {s}"


def test_signature_same_chapter_same_signature():
    """同章不同数字应同签（数字归一化）"""
    s1 = _issue_signature("第4章营收增长100亿无解释")
    s2 = _issue_signature("第4章营收增长99亿无解释")
    assert s1 == s2, "同章不同数字应同签"


def test_signature_multi_chapter_preserve_order():
    """多章节号按顺序还原（防 str.replace 全量替换）"""
    s = _issue_signature("第4章与第5章营收不一致100亿")
    assert s == "第@4章与第@5章营收不一致N亿", f"多章节应保序: {s}"


def test_signature_literal_chapter_placeholder():
    """字面"第N章"（无数字）不崩溃"""
    s = _issue_signature("第N章占位符无数字")
    assert s == "第N章占位符无数字"


# ============ P0-A-2: 豁免 fail-closed ============

def _make_fake_caller():
    """假 LLM caller：返回空 patch（无修复能力），记录调用"""
    calls = []

    def caller(name, prompt):
        calls.append(name)
        return '{"patches": []}'

    return caller, calls


def test_exemption_failclosed_empty_round(monkeypatch):
    """豁免问题在后续轮不再上报时，passed 必须为 False（v3.1 P0-A-2）

    场景：前几轮报同签名问题（被豁免），最后一轮审查返回空 →
    若按 v2 逻辑会 passed=True 静默放行；v3.1 要求豁免非空即 fail。
    """
    caller, _ = _make_fake_caller()

    chapters = {1: "第1章内容", 5: "第5章内容"}

    # 模拟审查总是报同一个问题（跨轮同签名）
    def fake_deep_review(ch, wd):
        return ["第5章营收增长100亿无解释"]

    def fake_substantive(ch, caller, wd, industry, **kwargs):
        return ["第5章营收增长100亿无解释"]  # 每轮都报

    import finance.quality.review_repair_loop as m
    monkeypatch.setattr(m, "_run_deep_review", fake_deep_review)
    monkeypatch.setattr(m, "_run_substantive_review", fake_substantive)

    result = review_and_repair_loop(
        chapters=chapters,
        ctx=MagicMock(),
        llm_caller=caller,
        max_rounds=4,
    )

    # 豁免问题存在 → 不得静默通过
    assert result.passed is False, "豁免问题存在时不得 passed=True"
    assert result.exempted_count >= 1, "应有豁免记录"
    assert result.remaining_issues, "豁免问题应留在 remaining_issues"


# ============ P0-A-3: 单调守卫 ============

def test_monotonic_guard_rollback(monkeypatch):
    """修复引入新问题 → 回滚本轮，issues_fixed 不虚增（v3.1 P0-A-3）"""
    import finance.quality.review_repair_loop as m

    original_chapters = {1: "第1章原始内容", 5: "第5章原始内容"}

    # 假 LLM：第一次修复"成功"但引入了新问题
    def fake_repair(chapters, issues, caller, wd):
        chapters[5] = chapters[5] + "\n新增内容引入了新矛盾"
        return 1  # 修复 1 处

    # 修复前审查报问题 A；修复后重审报新问题 B（未在修复前清单中）
    calls = {"phase": "before"}

    def fake_deep_review(ch, wd):
        if calls["phase"] == "before":
            return ["第5章营收增长100亿无解释"]
        return ["第1章总资产900亿无解释"]  # 新问题

    monkeypatch.setattr(m, "_repair_chapters", fake_repair)
    monkeypatch.setattr(m, "_run_deep_review", fake_deep_review)
    monkeypatch.setattr(m, "_run_substantive_review", lambda *a, **k: [])

    def fake_caller(name, prompt):
        return '{"patches": []}'

    # 修复前审查报问题 A；修复后重审报新问题 B（用 phase 切换）
    phase = {"n": 0}

    def phased_deep(ch, wd):
        phase["n"] += 1
        if phase["n"] <= 1:
            return ["第5章营收增长100亿无解释"]
        return ["第1章总资产900亿无解释"]

    monkeypatch.setattr(m, "_run_deep_review", phased_deep)

    chapters = dict(original_chapters)
    result = review_and_repair_loop(
        chapters=chapters,
        ctx=MagicMock(),
        llm_caller=fake_caller,
        max_rounds=2,
    )

    # 单调守卫触发回滚：chapters 恢复原始
    assert chapters[5] == original_chapters[5], "回滚后章节应恢复原始"
    # issues_fixed 不虚增（回滚后应为 0 或未增）
    assert result.issues_fixed == 0, f"回滚后 issues_fixed 应不虚增，实为 {result.issues_fixed}"


# ============ v3.1 P0-B-1/P0-B-7: 预算/墙钟双重护栏（loop 级） ============

def test_loop_budget_deadline(monkeypatch):
    """预算与墙钟在 loop 级生效（v3.1 P0-B-1/P0-B-7，对应 v3-code test_budget_deadline）

    (a) 预算：llm_call_budget=2 → 第 3 次包装调用抛 LLMCallBudgetExceeded →
        fail-closed 上抛（v3.1 P0-A-3 白名单：预算/墙钟不降级），审查调用 S5 计入；
    (b) 墙钟：deadline=已过期 → 轮首检查终止 → wall_clock_exceeded=True、passed=False。
    """
    import time

    import pytest

    import finance.quality.review_repair_loop as m
    from finance.llm_errors import LLMCallBudgetExceeded

    # (a) 预算
    calls = []

    def fake_caller(name, prompt):
        calls.append(name)
        return '{"patches": []}'

    def fake_deep_review(ch, wd):
        return ["第5章营收增长100亿无解释"]

    def fake_substantive(ch, caller, wd, industry, **kwargs):
        # 审查调用真实走传入的 caller（即 budgeted 包装）→ 计入预算（S5）
        # 每轮 3 次调用：预算=2 → 第 1 轮内即触发超限
        caller("审查深度", "请评估")
        caller("审查结论", "请评估")
        caller("审查假设", "请评估")
        return ["第5章营收增长100亿无解释"]

    monkeypatch.setattr(m, "_run_deep_review", fake_deep_review)
    monkeypatch.setattr(m, "_run_substantive_review", fake_substantive)

    # v3.1 P0-A-3：预算耗尽 fail-closed 上抛（不被 except Exception 吞成"审查不完整"）
    with pytest.raises(LLMCallBudgetExceeded):
        review_and_repair_loop(
            chapters={1: "第1章内容", 5: "第5章内容"},
            ctx=MagicMock(),
            llm_caller=fake_caller,
            max_rounds=4,
            llm_call_budget=2,
        )
    # S5 计入：审查调用均经 budgeted 包装计数；第 3 次调用在预算检查处被拦截（未达底层 caller）
    assert len(calls) == 2, f"前 2 次应到达底层 caller，第 3 次被预算拦截，实为 {len(calls)}"

    # (b) 墙钟：deadline 已过期 → 轮首终止（返回 result，非上抛——轮首检查早于任何 LLM 调用）
    calls2 = []

    def fake_caller2(name, prompt):
        calls2.append(name)
        return '{"patches": []}'

    result2 = review_and_repair_loop(
        chapters={1: "第1章内容"},
        ctx=MagicMock(),
        llm_caller=fake_caller2,
        max_rounds=4,
        deadline=time.monotonic() - 1,  # 已过期
    )
    assert result2.wall_clock_exceeded is True, "墙钟耗尽应标记 wall_clock_exceeded"
    assert result2.passed is False, "墙钟耗尽不得通过"


# ============ v3.1 P0-B-10: shadow 模式跳过修复 ============

def test_shadow_skip_repair(monkeypatch):
    """skip_repair=True（shadow 模式）→ 修复分支调用 0 次、passed=False、remaining 非空

    对应 v3-code 缺陷 10 / P0-B-10（gate4 消费 workflow 注入的 shadow_skip_repair）。
    """
    import finance.quality.review_repair_loop as m

    repair_calls = {"n": 0}
    original_repair = m._repair_chapters

    def counting_repair(chapters, issues, caller, wd):
        repair_calls["n"] += 1
        return original_repair(chapters, issues, caller, wd)

    def fake_deep_review(ch, wd):
        return ["第5章营收增长100亿无解释"]

    monkeypatch.setattr(m, "_repair_chapters", counting_repair)
    monkeypatch.setattr(m, "_run_deep_review", fake_deep_review)
    monkeypatch.setattr(m, "_run_substantive_review", lambda *a, **k: [])

    def fake_caller(name, prompt):
        return '{"patches": []}'

    result = review_and_repair_loop(
        chapters={1: "第1章内容", 5: "第5章内容"},
        ctx=MagicMock(),
        llm_caller=fake_caller,
        max_rounds=3,
        skip_repair=True,
    )
    assert repair_calls["n"] == 0, "shadow 模式不得调用修复"
    assert result.passed is False, "shadow 模式未修复不得通过"
    assert result.remaining_issues, "未修复问题应留在 remaining_issues"


# ============ 双专家 P0：review_incomplete 不得静默通过 ============

def test_review_incomplete_fail_closed(monkeypatch):
    """双专家 P0（2026-08-22）：审查不完整（检查器异常 → review_incomplete=True）
    时，即使无新问题也不得 passed=True——击穿 fail-closed 的漏洞修复"""
    import finance.quality.review_repair_loop as m

    def fake_caller(name, prompt):
        return '{"patches": []}'

    # 深度审查抛异常 → 置 review_incomplete=True（真实路径：cross_chapter/fact_checker 崩溃）
    def crashing_deep_review(ch, wd):
        raise RuntimeError("检查器崩溃")

    monkeypatch.setattr(m, "_run_deep_review", crashing_deep_review)
    monkeypatch.setattr(m, "_run_substantive_review", lambda *a, **k: [])

    result = review_and_repair_loop(
        chapters={1: "第1章内容"},
        ctx=MagicMock(),
        llm_caller=fake_caller,
        max_rounds=2,
    )

    # 审查不完整 → 必须 fail-closed（不得静默通过）
    assert result.review_incomplete is True, "异常应置 review_incomplete"
    assert result.passed is False, "审查不完整不得 passed=True（双专家 P0 修复）"
    assert result.remaining_issues, "应记录审查不完整原因"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
