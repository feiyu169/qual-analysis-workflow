"""
numeric_guard.py — 前端数值闸门（HGF 驱动，L2）

按 HeavySkill K=6 评审修订（v2）：6 道闸门合一
  闸门1 数值量级校验（类别锚点，非全局 closest；普通10倍/估值5倍）
  闸门2 空章检测（去空白 < 800 字符）
  闸门3 财年一致性校验（ch5 必须锚 FY2025，程序化强制）
  闸门4 币值/单位语义校验（估值章每股价值币种对齐市场）
  闸门5 空壳检测（财务章长度达标但小数数字计数=0 → 空壳）
  闸门6 组装前调用（全过才组装 + 无锚点数字标注）

核心：LLM 模板残留（1427.8 vs 实际73.66）是确定性的量级违规，机器校验无法绕过。
"""

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ====================================================================
# 数据模型
# ====================================================================

@dataclass
class GateViolation:
    """闸门违规"""
    gate: str                 # "numeric" / "empty" / "fiscal" / "currency" / "shell"
    chapter: int
    message: str
    severity: str = "critical"   # critical=阻断 / warning=提示


@dataclass
class GateResult:
    """闸门结果"""
    passed: bool
    violations: list[GateViolation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def __bool__(self):
        return self.passed


# ====================================================================
# 常量
# ====================================================================

# 空章阈值：去空白后最小有效字符数
MIN_CHAPTER_CHARS = 800
# 财务章编号
FINANCIAL_CHAPTERS = {5, 6}
# 空壳阈值分级（P12 诊断 2026-08-22：ch5 是运营章（交付量/门店），财务小数天然少；
# ch6 纯财务章，小数数字应充足）
MIN_FINANCIAL_NUMBERS_BY_CH = {5: 1, 6: 3}  # ch5≥1, ch6≥3
MIN_FINANCIAL_NUMBERS = 3  # 默认值（向后兼容）
# 估值章编号
VALUATION_CHAPTERS = {7}
# 财年铁律章节（B1-1 修订：ch5 经营表现 / ch7 估值 从严——当期锚断言）
FISCAL_STRICT_CHAPTERS = {5, 7}
# 放行章节（B1-1 修订：ch6 财务分析 / ch4 最近变化——历史引用宽松豁免，不阻断）
FISCAL_LENIENT_CHAPTERS = {4, 6}
# 历史引用豁免语境词（对比/趋势语境：引用处附近出现即豁免）
FISCAL_HISTORICAL_CONTEXT = [
    "对比", "历史", "上年", "同期", "趋势", "同比", "较上年", "相较于", "回顾", "此前",
    "较", "下降", "上升", "增长", "回落", "变化", "低于", "高于",
]
# 币值敏感章节
CURRENCY_CHAPTERS = {7}

# 量级阈值
GENERAL_RATIO = 10.0     # 普通章：数字与锚点差 >10 倍 → 模板残留
VALUATION_RATIO = 5.0    # 估值章：>5 倍

# 白名单：这些上下文中的数字不参与量级校验
WHITELIST_CONTEXT = [
    r"\d{4}年",                 # 年份（2025年）
    r"^\d+\.?\d*\s*%$",         # 纯百分数
    r"股本|总股本|亿股|万股|股$",   # 股本
    r"发行价|上市价|招股价|港元|港币|每股收益|价格带|价格区间|售价|定价|价格$|细分市场|市场$|纯电|新能源",  # 价格/币种/市场定位
    r"ARPU|ARPPU|MAU|DAU|MPU|付费用户|用户数",  # 运营指标
    r"市盈率|市净率|PE\b|PB\b|PS\b|EV\b|ROE|ROIC|毛利率|净利率",  # 比率
    r"汇率|折算",
    # 行业/市场规模等外部数据（非公司财务，如"IP改编市场超2600亿元"）
    r"市场规模|行业规模|全产业链|产业链产值|市场空间|行业产值|总规模|市场规模达",
    # 比例/示例/倍数（如"100万次阅读比10万次多1倍"中的 0.01/0.001）
    r"倍$|次$|比例|示例|举例|每\S{0,4}就|相当于|约为.{0,4}倍",
    # 小额科目/非锚点财务项（P12 诊断 2026-08-22：0.1-1.14 亿数字被判"无同量级锚点"
    # 导致 gate_issues=1 不消——减值/拨备/补助/汇兑/回购/分红/少数股东/利息等）
    r"减值|拨备|补助|补贴|奖励|汇兑|利息|回购|分红|派息|股利|少数股东|少数权益|"
    r"政府补助|递延收益|商誉|无形资产|使用权资产|租赁负债|股份支付|股权激励|"
    r"员工持股|期权|认股权|信托|理财|存款|保证金|押金|预付款|预收款|应收|应付|"
    r"递延|摊销|折旧|资本化|研发投入|研发费用|管理费用|销售费用|财务费用",
]

# 币值关键词
_CURRENCY_CNY = ["人民币", "元", "CNY", "RMB"]
_CURRENCY_HKD = ["港元", "港币", "HKD", "HK$"]


# ====================================================================
# 闸门类
# ====================================================================

class NumericGuard:
    """前端数值闸门合集"""

    # ------------------------------------------------------------
    # 闸门1：数值量级校验（类别锚点）
    # ------------------------------------------------------------
    def check_numeric(
        self,
        chapter_num: int,
        content: str,
        wind_data: dict,
    ) -> GateResult:
        """校验章节数字与 Wind 锚点量级一致性（类别锚点：营收对营收、净利对净利）"""
        result = GateResult(passed=True)

        anchors = self._category_anchors(wind_data)
        if not anchors:
            return result  # 无锚点跳过（wind 不可用）

        threshold = VALUATION_RATIO if chapter_num in VALUATION_CHAPTERS else GENERAL_RATIO

        for value, ctx in self._extract_amounts(content):
            if value == 0:
                continue
            # 白名单过滤
            if any(re.search(p, ctx) for p in WHITELIST_CONTEXT):
                continue
            # 万元级数字（<1000万 = <0.1亿）：价格/单价/运营数据（如"25万-40万纯电车型"、
            # "30万元以上"），不属于亿级财务锚点量级，不参与模板残留校验
            # （模板残留指亿级财务数字错位：1427.8 vs 73.66；万元级写错也不构成模板残留）
            if abs(value) < 0.1:
                continue
            # 类别锚点：找与该数字**同类别**的锚点（按数量级就近，但要求可解释）
            # 简化：找所有锚点中与 value 比值在 [1/threshold, threshold] 内的
            # 若无任何锚点与之同量级 → 模板残留嫌疑
            matched = any(
                1.0 / threshold <= abs(value) / max(abs(a), 1e-9) <= threshold
                for a in anchors
            )
            if not matched:
                closest = min(anchors, key=lambda a: abs(abs(value) - abs(a)))
                result.violations.append(GateViolation(
                    gate="numeric",
                    chapter=chapter_num,
                    message=(
                        f"数字 {value} 与 Wind 锚点（最近 {closest}）量级不匹配"
                        f"（ratio={abs(value)/max(abs(closest),1e-9):.1f} > {threshold}），"
                        f"疑似模板残留：'{ctx[:40]}...'"
                    ),
                ))
                result.passed = False
        return result

    def _category_anchors(self, wind_data: dict) -> list[float]:
        """收集 Wind canonical 锚点数值（各类别指标绝对值）"""
        anchors: list[float] = []
        for section in ("income", "balance", "cashflow"):
            table = wind_data.get(section) or {}
            for v in table.values():
                if isinstance(v, list):
                    for x in v:
                        if isinstance(x, (int, float)) and x is not None:
                            anchors.append(abs(float(x)))
        return [a for a in anchors if a > 0]

    def _extract_amounts(self, content: str) -> list[tuple[float, str]]:
        """提取 "数字+万亿/亿元/亿/万元/万" 及上下文（排除计数词如"100万次/万人/万部"）"""
        out = []
        # 万亿 必须单独列在 亿 之前（否则 "1.5万亿" 会被切成 "1.5万" → 0.00015 亿 的假数字）
        for m in re.finditer(r"(-?\d+\.?\d*)\s*(万亿|亿元|亿|万元|万)", content):
            value = float(m.group(1))
            unit = m.group(2)
            # 单位后跟计数词（次/人/户/部/家/字/本/篇/首/条/个/起/辆/用户…）→ 非金额，跳过
            after = content[m.end():m.end() + 4]
            if re.match(r"(次|人|户|部|家|字|本|篇|首|条|个|章|册|张|场|款|项|起|辆|台|位|名|岁|用户|人次|下载|安装|门店|公里|小时|分钟|天|月|年|款车|车型)", after):
                continue
            if unit == "万亿":
                value = value * 10000.0
            elif unit in ("万元", "万"):
                value = value / 10000.0
            # ctx 前后各放宽一些，确保"市场规模/行业规模"等白名单词能被捕获
            ctx = content[max(0, m.start() - 25):m.end() + 12].replace("\n", " ")
            out.append((value, ctx))
        return out

    # ------------------------------------------------------------
    # 闸门2：空章检测
    # ------------------------------------------------------------
    def check_empty(self, chapter_num: int, content: str) -> GateResult:
        result = GateResult(passed=True)
        stripped = re.sub(r"\s", "", content or "")
        if len(stripped) < MIN_CHAPTER_CHARS:
            result.passed = False
            result.violations.append(GateViolation(
                gate="empty", chapter=chapter_num,
                message=f"疑似空章/半成品（有效内容仅 {len(stripped)} 字符 < {MIN_CHAPTER_CHARS}）",
            ))
        return result

    # ------------------------------------------------------------
    # 闸门5：空壳检测（财务章长度够但无数值）
    # ------------------------------------------------------------
    def check_shell(self, chapter_num: int, content: str) -> GateResult:
        result = GateResult(passed=True)
        if chapter_num not in FINANCIAL_CHAPTERS:
            return result
        # 分级阈值：ch5 运营章≥1，ch6 纯财务章≥3
        min_numbers = MIN_FINANCIAL_NUMBERS_BY_CH.get(chapter_num, MIN_FINANCIAL_NUMBERS)
        stripped = re.sub(r"\s", "", content or "")
        if len(stripped) >= MIN_CHAPTER_CHARS:
            decimals = re.findall(r"\d+\.\d+", content)
            if len(decimals) < min_numbers:
                result.passed = False
                result.violations.append(GateViolation(
                    gate="shell", chapter=chapter_num,
                    message=(
                        f"空壳章：长度 {len(stripped)} 达标但仅 {len(decimals)} 个小数数字"
                        f"（第{chapter_num}章须 ≥{min_numbers} 个，如 73.66/-7.76）"
                    ),
                ))
        return result

    # ------------------------------------------------------------
    # 闸门3：财年一致性（B1-1：章节级当期锚断言 + 历史引用上下文豁免 + 章节调参）
    # ------------------------------------------------------------
    def check_fiscal(
        self,
        chapter_num: int,
        content: str,
        wind_data: dict,
    ) -> GateResult:
        result = GateResult(passed=True)
        if chapter_num in FISCAL_LENIENT_CHAPTERS:
            # B1-1：放行章节（ch6 财务分析 / ch4 最近变化）——历史引用宽松豁免
            return result
        if chapter_num not in FISCAL_STRICT_CHAPTERS:
            # 非严格非放行章节：默认检查（同严格语义，当期锚断言）
            pass

        # 最新财年 + 全部历史财年
        labels = ((wind_data or {}).get("_year_labels") or {}).get("财年") or []
        if not labels:
            return result
        latest_fy = labels[-1]
        prior_fys = labels[:-1]
        if not prior_fys:
            return result

        latest_refs = re.findall(rf"{latest_fy}[年财]度?", content)
        if not latest_refs:
            # 全章无最新财年引用：先查是否纯历史引用（全部带豁免）——否则判当期错位
            active_prior = [pf for pf in prior_fys if re.search(rf"{pf}[年财]度?", content)]
            if active_prior:
                exempted = all(
                    self._historical_context_exempt(content, f"{pf}年度", pf) or
                    self._historical_context_exempt(content, f"{pf}财年", pf)
                    for pf in active_prior
                )
                if not exempted:
                    result.passed = False
                    result.violations.append(GateViolation(
                        gate="fiscal", chapter=chapter_num,
                        message=(
                            f"财年错位：本章引用历史财年 {[f'FY{pf}' for pf in active_prior]} 但无 "
                            f"FY{latest_fy} 当期数据，须以 FY{latest_fy} 为当期"
                            f"（历史引用须带 FY 标注或对比/趋势语境）"
                        ),
                    ))
            return result

        # 有最新财年引用：逐处检查历史财年引用是否带豁免（FY 标注 或 对比语境）
        for pf in prior_fys:
            refs = re.findall(rf"{pf}[年财]度?", content)
            if not refs:
                continue
            for ref in refs:
                pos = content.find(ref)
                if pos < 0:
                    continue
                if self._historical_context_exempt(content, ref, pf, pos):
                    continue  # 对比/趋势语境 或 强制 FY 标注 → 豁免
                result.passed = False
                result.violations.append(GateViolation(
                    gate="fiscal", chapter=chapter_num,
                    message=(
                        f"财年错位：'{ref}' 未标注 FY{pf} 且无对比/趋势语境"
                        f"（当期应为 FY{latest_fy}，历史引用须带 FY 标注或对比标注）"
                    ),
                ))
        return result

    def _historical_context_exempt(
        self, content: str, ref: str, prior_fy: int, pos: int | None = None,
    ) -> bool:
        """历史引用豁免判定：引用处附近 80 字符内含豁免语境词，或带强制 FY 标注"""
        if pos is None:
            pos = content.find(ref)
        if pos < 0:
            return False
        window = content[max(0, pos - 80):pos + len(ref) + 80]
        # 强制 FY 标注：引用处附近出现 FY{pf} 或 （{pf}年） 形式
        if re.search(rf"FY\s*{prior_fy}", window):
            return True
        if re.search(rf"[（(]\s*{prior_fy}\s*年\s*[）)]", window):
            return True
        # 对比/趋势语境词
        return any(w in window for w in FISCAL_HISTORICAL_CONTEXT)

    # ------------------------------------------------------------
    # 闸门4：币值/单位语义（估值章每股价值币种对齐）
    # ------------------------------------------------------------
    def check_currency(self, chapter_num: int, content: str, market: str = "hk") -> GateResult:
        result = GateResult(passed=True)
        if chapter_num not in CURRENCY_CHAPTERS:
            return result

        # 港股：每股价值应为港元；"X元/股"或"每股价值X元"无人民币标注 → 违规
        if market == "hk":
            per_share = []
            for m in re.finditer(r"(\d+\.?\d*)\s*元(?:\s*/\s*股)?", content):
                ctx_b = content[max(0, m.start() - 15):m.start()]
                ctx_a = content[m.end():m.end() + 15]
                if re.search(r"每股|/股|股$", ctx_b + ctx_a):
                    per_share.append(m.group(1))
            if per_share:
                has_cny = bool(re.search(r"人民币", content))
                if not has_cny:
                    result.passed = False
                    result.violations.append(GateViolation(
                        gate="currency", chapter=chapter_num,
                        message=(
                            f"港股标的每股价值 {per_share[0]}元 未标注币种/未换算港元"
                            f"（HK 市场应以港元或显式 RMB→HKD 换算）"
                        ),
                    ))
                else:
                    result.warnings.append(
                        f"每股价值 {per_share[0]}元 标注了人民币，但港股市场建议显式换算港元"
                    )
        return result

    # ------------------------------------------------------------
    # 汇总（供 _generate_chapter / 组装闸门调用）
    # ------------------------------------------------------------
    def check_all(
        self,
        chapter_num: int,
        content: str,
        wind_data: dict,
        market: str = "hk",
    ) -> GateResult:
        """全闸门汇总（闸门1-5）"""
        all_violations = []
        all_warnings = []
        checks = [
            self.check_numeric(chapter_num, content, wind_data),
            self.check_empty(chapter_num, content),
            self.check_shell(chapter_num, content),
            self.check_fiscal(chapter_num, content, wind_data),
            self.check_currency(chapter_num, content, market),
        ]
        for r in checks:
            all_violations.extend(r.violations)
            all_warnings.extend(r.warnings)
        return GateResult(
            passed=len(all_violations) == 0,
            violations=all_violations,
            warnings=all_warnings,
        )


# ====================================================================
# 模块级便捷函数
# ====================================================================

def check_chapter_gates(
    chapter_num: int,
    content: str,
    wind_data: dict,
    market: str = "hk",
) -> GateResult:
    """单章前端闸门（供 workflow._generate_chapter 集成）"""
    return NumericGuard().check_all(chapter_num, content, wind_data, market)


def pre_assembly_gate(
    chapters: dict[int, str],
    wind_data: dict,
    market: str = "hk",
) -> dict[int, list[str]]:
    """组装前闸门（闸门6）：11 章全过才组装，失败章标注"""
    guard = NumericGuard()
    failures: dict[int, list[str]] = {}
    for num, content in chapters.items():
        r = guard.check_all(num, content, wind_data, market)
        if not r.passed:
            failures[num] = [v.message for v in r.violations]
    return failures
