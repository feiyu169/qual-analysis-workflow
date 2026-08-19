"""numeric_guard 前端闸门测试（HGF L1 单元测试）"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from finance.quality.numeric_guard import (
    NumericGuard,
    check_chapter_gates,
    pre_assembly_gate,
)


@pytest.fixture
def wind_data():
    path = os.path.join(ROOT, ".pip-tmp", "wind_data.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)["wind_data"]
    return {
        "income": {"营业收入": [70.12, 81.21, 73.66], "归母净利润": [8.05, -2.09, -7.76]},
        "balance": {"总资产": [231.88, 229.45, 215.83]},
        "cashflow": {"经营活动现金流量净额": [11.31, 25.27, -2.77]},
        "_year_labels": {"财年": [2023, 2024, 2025]},
    }


class TestNumericGuard:
    def test_template_residue(self, wind_data):
        """T1: 模板残留 1427.8 应拦截（估值章 5 倍）"""
        g = NumericGuard()
        r = g.check_numeric(7, "当前营收1427.8亿元，翻转点428.3亿元。", wind_data)
        assert not r.passed
        assert "1427.8" in r.violations[0].message

    def test_normal_values(self, wind_data):
        """T2: 正常锚点值通过"""
        g = NumericGuard()
        r = g.check_numeric(1, "营业收入73.66亿元，归母净利润-7.76亿元。", wind_data)
        assert r.passed

    def test_whitelist(self, wind_data):
        """T3: 白名单（股本/PE/年份/发行价）不误伤"""
        g = NumericGuard()
        r = g.check_numeric(7, "总股本10.2亿股，PE 16.4倍，2025年营收，发行价55港元。", wind_data)
        assert r.passed

    def test_industry_scale_whitelist(self, wind_data):
        """T3b: 行业规模（非公司财务）不误伤"""
        g = NumericGuard()
        r = g.check_numeric(2, "IP改编全产业链市场规模超2600亿元。", wind_data)
        assert r.passed

    def test_count_words_skip(self, wind_data):
        """T3c: 计数词（100万次）非金额跳过"""
        g = NumericGuard()
        r = g.check_numeric(3, "一部小说100万次阅读比10万次多1倍。", wind_data)
        assert r.passed

    def test_empty_chapter(self, wind_data):
        """T4: 空章拦截"""
        g = NumericGuard()
        r = g.check_empty(8, "## 结论要点\n\n（空）")
        assert not r.passed

    def test_shell_chapter(self, wind_data):
        """T5: 空壳章（长度达标无数值）拦截"""
        g = NumericGuard()
        content = ("本集团财务状况良好，资产负债稳健，流动性充裕，资本结构合理，风险可控。"
                   "经营稳健，盈利质量良好，现金流充沛，偿债能力较强。" * 20)
        r = g.check_shell(6, content)
        assert not r.passed

    def test_fiscal_misalignment(self, wind_data):
        """T6: 财年错位（ch5 用 2024 无 2025）拦截"""
        g = NumericGuard()
        r = g.check_fiscal(5, "2024年度公司实现收入81.2亿元，经营表现良好。", wind_data)
        assert not r.passed

    def test_fiscal_correct(self, wind_data):
        """T6b: 财年正确（ch5 锚 2025）通过"""
        g = NumericGuard()
        r = g.check_fiscal(5, "2025财年公司收入73.66亿元，2024年作对比。", wind_data)
        assert r.passed

    def test_currency_hk(self, wind_data):
        """T7: 港股每股价值人民币未标注 → 拦截"""
        g = NumericGuard()
        r = g.check_currency(7, "基准每股价值187.2元，上行空间大。", "hk")
        assert not r.passed

    def test_currency_cny_labeled(self, wind_data):
        """T7b: 有人民币标注 → warning 非违规"""
        g = NumericGuard()
        r = g.check_currency(7, "基准每股价值187.2元人民币，港股需换算。", "hk")
        assert r.passed
        assert len(r.warnings) == 1

    def test_pre_assembly_gate(self, wind_data):
        """T8: 组装闸门标注失败章"""
        chapters = {
            1: "阅文集团营业收入73.66亿元，归母净利润-7.76亿元，经营现金流-2.77亿元。" * 40,
            8: "## 结论要点\n（空）",
        }
        failures = pre_assembly_gate(chapters, wind_data)
        assert list(failures.keys()) == [8]

    def test_check_chapter_gates(self, wind_data):
        """T9: 单章全闸门汇总"""
        r = check_chapter_gates(1, "营业收入73.66亿元，归母净利润-7.76亿元。" * 50, wind_data, "hk")
        assert r.passed
