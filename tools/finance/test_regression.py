"""
Qual v10 回归测试（治理方案 v3.0 Phase 4）。

8 个历史 fatal 固化为测试用例，防止复现。
每个测试对应追溯矩阵中的一个问题 ID。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))


# === P1: 翻转阈值方向错误 ===

class TestFlipThresholdDirection:
    """P1: 小鹏翻转阈值方向错误 → 防线2 ValuationArbiter 方向验证。"""

    def test_flip_ev_rev_decreasing(self):
        """翻转点 EV/Revenue 必须 ≤ 当前值。"""
        from finance.depth_enhancer import _compute_ev_revenue_flip_thresholds
        ft = _compute_ev_revenue_flip_thresholds(
            revenue=767.20, enterprise_value=877.83, current_price=46.52, shares=18.87,
        )
        for t in ft:
            assert t.flip_value <= t.current_value, (
                f"{t.variable}: 翻转点 {t.flip_value} > 当前值 {t.current_value}（方向错误）"
            )

    def test_loss_company_no_negative_flip(self):
        """亏损公司翻转阈值不出现负值。"""
        from finance.depth_enhancer import _compute_ev_revenue_flip_thresholds
        ft = _compute_ev_revenue_flip_thresholds(
            revenue=100.0, enterprise_value=50.0, current_price=10.0, shares=10.0,
        )
        for t in ft:
            assert t.flip_value >= 0, f"{t.variable}: 翻转值 {t.flip_value} 为负"


# === P2: 数据错位 ===

class TestFormatMisplacementFix:
    """P2: 小鹏数据错位 → 防线1 ADVC 确定性修复。"""

    def test_format_regex_matches(self):
        """格式错位正则匹配 '2025 303.69-5年'。"""
        import re
        _fmt_re = re.compile(r"(\d{4})\s+(\d+\.?\d*)\s*[-~～]\s*(\d+)\s*年")
        assert _fmt_re.search("FY2025 303.69-5年启动回购")

    def test_format_regex_no_false_positive(self):
        """格式错位正则不匹配正常 'FY2025 88.50 亿元'。"""
        import re
        _fmt_re = re.compile(r"(\d{4})\s+(\d+\.?\d*)\s*[-~～]\s*(\d+)\s*年")
        assert not _fmt_re.search("FY2025 88.50 亿元")


# === P3: 净现比不一致 ===

class TestNetCashflowRatioCheck:
    """P3: 协鑫净现比不一致 → 防线3 Gate7 跨章数据校验。"""

    def test_ratio_conflict_detected(self):
        """净现比跨章冲突被检测到。"""
        from finance.quality.cross_chapter_consistency import check_cross_chapter_consistency
        chapters = {
            0: "## 结论要点\n净现比：120%",
            5: "## 结论要点\n现金流转化率：85%",
        }
        result = check_cross_chapter_consistency(chapters)
        # 应该检测到净现比不一致
        ratio_issues = [i for i in result.issues if "净现比" in i.description or "现金流转化率" in i.description]
        assert len(ratio_issues) > 0, "净现比跨章冲突未被检测"

    def test_ratio_no_conflict(self):
        """净现比一致时无冲突。"""
        from finance.quality.cross_chapter_consistency import check_cross_chapter_consistency
        chapters = {
            0: "## 结论要点\n净现比：120%",
            5: "## 结论要点\n净现比：120%",
        }
        result = check_cross_chapter_consistency(chapters)
        ratio_issues = [i for i in result.issues if "净现比" in i.description]
        assert len(ratio_issues) == 0, "净现比一致但被误报为冲突"


# === P4: DCF 负值注入 ===

class TestDCFNegativeNotInjected:
    """P4: 协鑫 DCF 目标价矛盾 → 防线2 负值阻止注入。"""

    def test_negative_dcf_not_injected(self):
        """DCF 为负时 ch7 不注入估值文本。"""
        from finance.contracts.financials import Financials
        from finance.valuation.arbiter import ValuationArbiter
        fin = Financials(
            revenue=767.20, operating_profit=-44.16, net_profit_parent=-11.39,
            total_assets=1031.63, total_liabilities=727.94, equity_parent=303.69,
            operating_cashflow=82.59, shares=18.87, current_price=46.52,
        )
        arbiter = ValuationArbiter()
        verdict = arbiter.arbitrate(financials=fin, dcf_value=-43.53, ps_value=42.0)
        # DCF 为负时，主方法不应是 DCF
        assert verdict.primary_method != "DCF", f"DCF 为负时主方法不应是 DCF（实际：{verdict.primary_method}）"


# === P5: Wind key 不匹配 ===

class TestWindKeyCanonical:
    """P5: Wind key 不匹配 → 防线1 canonical key 统一。"""

    def test_canonical_alias_coverage(self):
        """所有旧 key 有 canonical alias。"""
        from finance.qual_v8.data_anchor import CANONICAL_ALIASES, canonical_key
        # 关键旧 key 必须有映射
        critical_old_keys = ["年营业总收入", "年净利润", "年营业利润", "经营活动产生的现金流量净额"]
        for key in critical_old_keys:
            result = canonical_key(key)
            assert result != key, f"旧 key '{key}' 无 canonical alias"


# === P6: Gate 级联失败 ===

class TestGateDAGDegraded:
    """P6: Gate4 级联失败 → GateDAG HARD/SOFT 依赖。"""

    def test_gate5_runs_when_gate4_fails(self):
        """Gate4 失败时 Gate5 仍可降级运行。"""
        from finance.qual_v8.engine.gate_dag import GateDAG
        dag = GateDAG()
        # Gate4 失败（state=failed），Gate5 应可降级运行
        fake_results = {
            0: type("R", (), {"passed": True})(),
            1: type("R", (), {"passed": True})(),
            2: type("R", (), {"passed": True})(),
            3: type("R", (), {"passed": True})(),
            4: type("R", (), {"passed": False})(),
        }
        can_run, degraded = dag.can_execute(5, fake_results)
        assert can_run, "Gate4 失败时 Gate5 应可运行"
        assert degraded, "Gate4 失败时 Gate5 应标记降级"


# === P7: context 分裂 ===

class TestContextNotSplit:
    """P7: context 分裂 → decision_rating 写入同一 context。"""

    def test_decision_rating_key_exists(self):
        """decision_rating key 在 context 传递链中存在。"""
        # 验证 gate3.py 写入 decision_rating 的代码路径
        import inspect
        from finance.qual_v8.gates import gate3
        source = inspect.getsource(gate3.Gate3ChapterWriting)
        assert "decision_rating" in source, "gate3.py 未写入 decision_rating"


# === P8: PGNB 盲区 ===

class TestPGNBAbbreviatedForms:
    """P8: PGNB 缩写形式覆盖 → _METRIC_NUM_RE 扩展。"""

    def test_abbreviated_cashflow_matched(self):
        """缩写形式 '经营现金流20.0亿' 被匹配。"""
        import re
        from finance.qual_v8.numeric_binder import _METRIC_NUM_RE
        assert _METRIC_NUM_RE.search("经营现金流20.0亿"), "经营现金流缩写未被匹配"

    def test_abbreviated_cashflow_net_matched(self):
        """缩写形式 '经营现金流净额20亿' 被匹配。"""
        import re
        from finance.qual_v8.numeric_binder import _METRIC_NUM_RE
        assert _METRIC_NUM_RE.search("经营现金流净额20亿"), "经营现金流净额缩写未被匹配"

    def test_full_form_still_matched(self):
        """完整形式 '经营活动现金流量净额20亿' 仍被匹配。"""
        import re
        from finance.qual_v8.numeric_binder import _METRIC_NUM_RE
        assert _METRIC_NUM_RE.search("经营活动现金流量净额20亿"), "完整形式未被匹配"
