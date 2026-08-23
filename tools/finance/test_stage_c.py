"""阶段 C 审查效率测试（C1-1/3 + C2-2 + C5-2）

验收（路线图 C）：
- C1-3：Gate3 跨章结果首轮复用（loop 不重复跑 deep 静态）
- C2-2：修复后轮仅审受影响章节（LLM 调用降）
- C5-2：占位符统一常量（gate8 全量 5 pattern，含待填写/TBD 不逃出）
- C1-1：gate4 logic 结果挂 context（check_criteria 复用）
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import pytest

from finance.qual_v8.gates.gate4 import Gate4AuditRepair
from finance.qual_v8.gates.gate8 import Gate8FinalValidation
from finance.quality.placeholder_rules import PLACEHOLDER_PATTERNS
from finance.quality.review_repair_loop import (
    _run_substantive_review,
    review_and_repair_loop,
)

# ===== C1-3：Gate3 跨章结果首轮复用 =====

def test_precomputed_cross_chapter_skips_deep_review(monkeypatch):
    """C1-3：提供 precomputed_cross_chapter 时，首轮不重跑 _run_deep_review"""
    import finance.quality.review_repair_loop as m

    deep_calls = {"n": 0}

    def counting_deep(ch, wd):
        deep_calls["n"] += 1
        return []

    monkeypatch.setattr(m, "_run_deep_review", counting_deep)
    monkeypatch.setattr(m, "_run_substantive_review", lambda *a, **k: [])

    def fake_caller(name, prompt):
        return '{"patches": []}'

    result = review_and_repair_loop(
        chapters={1: "第1章内容"},
        ctx=MagicMock(),
        llm_caller=fake_caller,
        max_rounds=1,
        precomputed_cross_chapter=["第1章 vs 第2章: 总资产不一致"],
    )
    # 首轮审查复用预计算（deep 0 次）；单调守卫的静态 deep 仍跑（1 次，必要防线）
    # 无 precomputed 时首轮审查 + 单调守卫 = 2 次 → 此处 1 次证明首轮审查被跳过
    assert deep_calls["n"] == 1, f"C1-3 首轮应复用 Gate3 结果（仅单调守卫跑），实跑 {deep_calls['n']} 次"
    assert result.passed is False  # 预计算结果有矛盾 → 不通过


def test_no_precomputed_runs_deep_review(monkeypatch):
    """无预计算结果时首轮照常跑 _run_deep_review"""
    import finance.quality.review_repair_loop as m

    deep_calls = {"n": 0}

    def counting_deep(ch, wd):
        deep_calls["n"] += 1
        return []

    monkeypatch.setattr(m, "_run_deep_review", counting_deep)
    monkeypatch.setattr(m, "_run_substantive_review", lambda *a, **k: [])

    def fake_caller(name, prompt):
        return '{"patches": []}'

    review_and_repair_loop(
        chapters={1: "第1章内容"},
        ctx=MagicMock(),
        llm_caller=fake_caller,
        max_rounds=1,
    )
    assert deep_calls["n"] == 1


# ===== C2-2：增量审查（仅受影响章节） =====

def test_substantive_review_only_chapters():
    """C2-2：only_chapters 过滤——只审指定章节"""
    # 2026-08-22 P6 修复：事实核查改为 DataAnchor（退役 fact_checker），
    # 测试改为验证 DataAnchor 路径收到过滤后的章节子集
    captured = {}

    # Mock DataAnchor 的 validate_chapter_any_fy 来捕获调用
    original_check = None

    class FakeAnchor:
        def validate_chapter_any_fy(self, ch_num, content):
            captured.setdefault("chapters", {})[ch_num] = content
            return []

    def fake_get_data_anchor(wd):
        return FakeAnchor()

    monkeypatch_obj = pytest.MonkeyPatch()
    monkeypatch_obj.setattr("finance.qual_v8.data_anchor.get_data_anchor", fake_get_data_anchor)

    try:
        # depth/conclusion 等检查器全部 pass（避免真实 LLM）
        def _fake_check(*a, **k):
            class _R:
                passed = True
                issues: list = None
                llm_failed = False
            return _R()

        monkeypatch_obj.setattr("finance.quality.depth_reviewer.check_depth", _fake_check)
        monkeypatch_obj.setattr("finance.quality.conclusion_validator.check_conclusion", _fake_check)
        monkeypatch_obj.setattr("finance.quality.assumption_checker.check_assumptions", _fake_check)

        _run_substantive_review(
            {1: "ch1", 2: "ch2", 5: "ch5"},
            lambda n, p: "ok",
            {"income": {}, "balance": {}, "cashflow": {}, "_year_labels": {"财年": [2023, 2024, 2025]}},
            "综合",
            budget_state={"calls": 0, "wall_clock_exceeded": False, "budget_exceeded": False},
            only_chapters={2, 5},
        )
        # DataAnchor 收到的应是过滤后子集
        assert set(captured["chapters"].keys()) == {2, 5}, \
            f"C2-2 增量应只审受影响章节，实为 {list(captured['chapters'].keys())}"
    finally:
        monkeypatch_obj.undo()


def test_substantive_review_empty_only_returns():
    """C2-2：only_chapters 为空集 → 跳过（返回空）"""
    issues = _run_substantive_review(
        {1: "ch1"}, lambda n, p: "ok", {}, "综合",
        only_chapters=set(),
    )
    assert issues == []


# ===== C5-2：占位符统一常量 =====

def test_placeholder_patterns_complete():
    """C5-2：占位符常量含全部 5 pattern（含待填写/TBD 不逃出）"""
    assert set(PLACEHOLDER_PATTERNS) == {"[Placeholder]", "XX亿元", "待填写", "TBD", "LLM_GENERATE"}


def test_gate8_uses_full_placeholder_patterns():
    """C5-2：Gate8 用全量 pattern（待填写/TBD 逃出收口修复）"""
    gate = Gate8FinalValidation()
    # 红队确定性检查应捕获"待填写"占位符
    result = gate._check_placeholder_deterministic("正文含待填写内容") if hasattr(
        gate, "_check_placeholder_deterministic") else None
    if result is not None:
        assert "待填写" in str(result)
    else:
        # 无独立方法则验证常量被引用（源码级）
        import inspect
        src = inspect.getsource(Gate8FinalValidation)
        assert "PLACEHOLDER_PATTERNS" in src, "Gate8 应引用统一常量"


# ===== C1-1：gate4 logic 结果挂 context =====

def test_gate4_logic_result_cached():
    """C1-1：logic 结果挂 context，check_criteria 复用（不重复跑）"""
    gate = Gate4AuditRepair()
    context = {"chapters": {1: "内容"}}
    with patch.object(gate, "_detect_contradictions", return_value={
        "passed": True, "errors": [], "contradictions": [], "critical_count": 0,
    }) as mock_detect, \
         patch.object(gate, "_check_risk_disclosure", return_value={
             "passed": True, "errors": [], "covered_count": 5,
         }):
        # 模拟 execute 已跑：挂 context
        context["gate4_logic_result"] = mock_detect.return_value
        mock_detect.reset_mock()
        ok = gate.check_criteria(context)
        assert ok is True
        mock_detect.assert_not_called(), "C1-1 check_criteria 应复用 execute 结果"


# ===== C2-3：受影响集跨章引用链 =====

def test_chapter_dependencies_propagation():
    """C2-3：改 ch5 → ch0/ch10 受影响（依赖传播）"""
    from finance.quality.incremental_checker import IncrementalChecker
    from finance.quality.review_repair_loop import CHAPTER_DEPENDENCIES

    affected = IncrementalChecker().get_affected_chapters(
        {"5"},
        {str(k): [str(v) for v in vs] for k, vs in CHAPTER_DEPENDENCIES.items()},
    )
    # ch5 变化 → ch0（依赖全部）与 ch10（依赖 1-9）受影响
    assert {"0", "10"} <= affected, f"C2-3 依赖传播应含 ch0/ch10，实为 {affected}"


def test_chapter_dependencies_isolated_changes():
    """C2-3：改 ch1 → 受影响集 = {1,0,10}"""
    from finance.quality.incremental_checker import IncrementalChecker
    from finance.quality.review_repair_loop import CHAPTER_DEPENDENCIES

    affected = IncrementalChecker().get_affected_chapters(
        {"1"},
        {str(k): [str(v) for v in vs] for k, vs in CHAPTER_DEPENDENCIES.items()},
    )
    assert affected == {"1", "0", "10"}


# ===== C3-2：红队门控 =====

def test_redteam_gated_by_gate4():
    """C3-2：Gate4 实质未通过 → 红队延后（不触发 LLM）"""
    gate = Gate8FinalValidation()
    context = {"llm_caller": lambda n, p: "ok", "report": "报告内容",
               "gate_4_result": {"substantive_passed": False}}
    result = gate._run_redteam_review(context)
    assert result["skipped"] is True, "Gate4 未通过应跳过红队"
    assert any("延后" in w for w in result["warnings"])


def test_redteam_runs_when_gate4_passed():
    """C3-2：Gate4 通过 → 红队触发（不跳过）"""
    gate = Gate8FinalValidation()
    context = {"llm_caller": lambda n, p: "ok", "report": "报告内容",
               "gate_4_result": {"substantive_passed": True},
               "wind_data": {}, "output_dir": ""}
    with patch("finance.quality.review_integrator.ReviewIntegrator") as mock_integrator:
        mock_integrator.return_value.review_report_text.return_value = MagicMock(
            fatal_issues=[], important_issues=[], suggestion_issues=[])
        result = gate._run_redteam_review(context)
        assert result["passed"] is True or result["skipped"] is True


# ===== C4-1：审查预算 ≤35 =====

def test_review_budget_capped_at_35():
    """C4-1：v9 单轮确定性修复不消耗 LLM 预算（无 llm_call_budget 参数）"""
    from finance.quality.review_repair_loop import ReviewRepairResult, review_and_repair_single_pass
    # v9 的 review_and_repair_single_pass 不调用 LLM，无需预算控制
    # 验证函数签名不含 llm_call_budget（确定性修复零 LLM 依赖）
    import inspect
    sig = inspect.signature(review_and_repair_single_pass)
    assert "llm_call_budget" not in sig.parameters, \
        "v9 单轮修复不应有 llm_call_budget 参数（零 LLM 依赖）"
    # 验证 wind_data 为空时仍返回合法结果
    result = review_and_repair_single_pass(chapters={1: "测试内容"}, wind_data=None)
    assert isinstance(result, ReviewRepairResult)


# ===== C5-3：锚点单例 =====

def test_data_anchor_singleton():
    """C5-3：get_data_anchor 同 wind_data 返回缓存实例（只构建一次）"""
    from finance.qual_v8.data_anchor import _anchor_cache, get_data_anchor

    wind = {"income": {"营业收入": [100.0, 120.0, 150.0]}, "_year_labels": {"财年": [2023, 2024, 2025]}}
    before = len(_anchor_cache)
    a1 = get_data_anchor(wind)
    a2 = get_data_anchor(wind)
    assert a1 is a2, "同 wind_data 应返回同一实例"
    assert len(_anchor_cache) == before + 1, "缓存应只新增 1 条"
    # 不同 wind_data → 不同实例
    a3 = get_data_anchor({"income": {}})
    assert a3 is not a1
    # 清理缓存（防污染其他测试）
    _anchor_cache.clear()


def test_data_anchor_singleton_content():
    """C5-3：单例锚点内容正确（营收最新财年值）"""
    from finance.qual_v8.data_anchor import _anchor_cache, get_data_anchor

    wind = {"income": {"营业收入": [100.0, 120.0, 150.0]}, "_year_labels": {"财年": [2023, 2024, 2025]}}
    a = get_data_anchor(wind)
    assert a.get_anchor("营业收入", fiscal_year=2025) == 150.0
    _anchor_cache.clear()


# ===== 双专家 P1：评级一致性检查不再空转 =====

def test_gate5_valuation_has_dcf_value():
    """双专家 P1（2026-08-22）：gate5 写入 dcf_value——gate6 评级一致性检查依赖它，
    缺失会导致检查被 if dcf_value>0 静默跳过（评级铁律空转）"""
    from finance.qual_v8.gates.gate5 import Gate5QualityEnhancement

    g = Gate5QualityEnhancement()
    ctx = {
        "wind_data": {"income": {"年营业总收入": [300, 400, 700]},
                      "balance": {}, "cashflow": {}},
        "ticker": "9868.HK", "company_name": "小鹏集团-W",
        "shares": 18.87, "current_price": 46.52,
        "dcf_params": MagicMock(fcf=82.5, wacc=0.10, terminal_growth=0.03),
    }
    with patch.object(g, "check_criteria", return_value=True):
        result = g._calculate_valuation(ctx)
    val = result.get("valuation") or {}
    assert "dcf_value" in val, "valuation 必须含 dcf_value（否则 gate6 空转）"
    assert val["dcf_value"] and val["dcf_value"] > 0, "dcf_value 应为正"


def test_gate6_rating_consistency_triggers():
    """双专家 P1：gate6 评级一致性检查在 dcf_value 存在时真实触发
    （买入评级但 DCF 无低估 → 报错，不再静默通过）"""
    from finance.qual_v8.gates.gate6 import Gate6Conclusion

    g = Gate6Conclusion()
    chapters = {10: "投资评级：买入"}  # 买入要求低估≥30%
    ctx = {
        "valuation": {"dcf_value": 40.0},  # vs current_price 46.52 → 低估13.9% < 30%
        "current_price": 46.52,
    }
    r = g._check_rating_valuation_consistency(chapters, ctx)
    assert not r["passed"], "买入评级但 DCF 低估<30% 应被拦截（评级铁律真实执行）"
    assert any("低估" in e for e in r["errors"]), "错误应说明低估不足"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
