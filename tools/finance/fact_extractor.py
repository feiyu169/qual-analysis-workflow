"""
fact_extractor.py — 两阶段财报事实提取器 (方案 C v2.0)

Phase 1: 从财报全文分批提取结构化事实
Phase 2: 事实表格式化为 LLM 上下文

HeavySkill v2.0 修正:
- chunk_size=30K, max_chunks=10, overlap=5%
- 三层 JSON 解析防护
- 合并策略: 任一有效值优先保留
- 持久化到 checkpoint
- 数值合理性校验 + Wind 交叉验证
"""

import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

logger = logging.getLogger(__name__)


# ====================================================================
# 数据结构
# ====================================================================

@dataclass
class OperationalFacts:
    """运营数据"""
    dau: float | None = None
    mau: float | None = None
    dau_mau_ratio: float | None = None
    daily_usage_minutes: float | None = None
    gmv: float | None = None
    gmv_yoy: float | None = None
    monetization_rate: float | None = None
    live_stream_revenue: float | None = None
    ad_revenue: float | None = None
    ecommerce_revenue: float | None = None
    paying_users: float | None = None
    arpu: float | None = None
    arppu: float | None = None
    creators: float | None = None

    # 新增：留存指标
    retention_rate_d1: float | None = None   # 次日留存率
    retention_rate_d7: float | None = None   # 7日留存率
    retention_rate_d30: float | None = None  # 30日留存率

    # 新增：单位经济
    ltv: float | None = None                 # 用户生命周期价值
    cac: float | None = None                 # 获客成本
    ltv_cac_ratio: float | None = None       # LTV/CAC
    payback_period: float | None = None      # 回收期（月）
    user_lifetime: float | None = None       # 用户生命周期（月）

    # 新增：费用数据
    marketing_expense: float | None = None   # 营销费用（亿人民币）
    new_users: float | None = None           # 新增用户（亿）
    gross_margin: float | None = None        # 毛利率

    sources: dict = field(default_factory=dict)


@dataclass
class FinancialFacts:
    """财务数据"""
    revenue: float | None = None
    net_profit: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    net_margin: float | None = None
    operating_cashflow: float | None = None
    capex: float | None = None
    total_assets: float | None = None
    total_liabilities: float | None = None
    equity: float | None = None
    cash_and_equivalents: float | None = None
    interest_bearing_debt: float | None = None


@dataclass
class ManagementFacts:
    """管理层信息"""
    ceo: str | None = None
    chairman: str | None = None
    cfo: str | None = None
    board_changes: list = field(default_factory=list)
    shareholding: dict = field(default_factory=dict)
    buyback_amount: float | None = None
    dividend_per_share: float | None = None


@dataclass
class BusinessFacts:
    """业务信息"""
    segments: list = field(default_factory=list)
    key_products: list = field(default_factory=list)
    strategic_priorities: list = field(default_factory=list)
    risks: list = field(default_factory=list)


@dataclass
class ExtractionMeta:
    """提取元数据"""
    total_sections: int = 0
    sections_processed: int = 0
    chunks_used: int = 0
    llm_calls: int = 0
    extraction_time_seconds: float = 0.0
    coverage_ratio: float = 0.0
    warnings: list = field(default_factory=list)


@dataclass
class ExtractedFacts:
    """完整事实表"""
    company_name: str = ""
    ticker: str = ""
    fiscal_year: int = 0
    report_type: str = "annual"
    operational: OperationalFacts = field(default_factory=OperationalFacts)
    financial: FinancialFacts = field(default_factory=FinancialFacts)
    management: ManagementFacts = field(default_factory=ManagementFacts)
    business: BusinessFacts = field(default_factory=BusinessFacts)
    meta: ExtractionMeta = field(default_factory=ExtractionMeta)
    # B3-1：多财年——每份年报独立提取的结果 {fiscal_year: ExtractedFacts}
    # 主表（本对象）为最新财年；by_year 存全部年份供多财年对照/合并
    by_year: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """序列化为 dict (用于 JSON 持久化)"""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'ExtractedFacts':
        """从 dict 反序列化"""
        obj = cls(
            company_name=d.get('company_name', ''),
            ticker=d.get('ticker', ''),
            fiscal_year=d.get('fiscal_year', 0),
            report_type=d.get('report_type', 'annual'),
            operational=OperationalFacts(**d.get('operational', {})),
            financial=FinancialFacts(**d.get('financial', {})),
            management=ManagementFacts(**d.get('management', {})),
            business=BusinessFacts(**d.get('business', {})),
            meta=ExtractionMeta(**d.get('meta', {})),
        )
        # B3-1：多财年副表反序列化
        by_year = d.get('by_year') or {}
        if by_year:
            obj.by_year = {int(fy): cls.from_dict(v) for fy, v in by_year.items()}
        return obj


# ====================================================================
# G2: 高价值章节选择
# ====================================================================

# 运营数据关键词 (权重 +5)
_OP_KEYWORDS = ['日活', '月活', 'DAU', 'MAU', 'GMV', 'ARPU', 'ARPPU',
                '用户数', '活跃用户', '使用时长', '电商', '货币化',
                '付费用户', '创作者', '日均', '月均', '直播', '电商']

# 财务关键词 (权重 +3)
_FIN_KEYWORDS = ['收入', '利润', '现金流', '毛利率', '净利率', 'ROE',
                 '资产', '负债', '研发费用', '销售费用', 'EBITDA']


def _score_section(content: str) -> float:
    """计算章节的数据密度评分"""
    score = 0.0
    # 包含数字
    numbers = re.findall(r'\d+[\.\d]*', content)
    score += len(numbers) * 1.0
    # 运营关键词
    for kw in _OP_KEYWORDS:
        score += content.count(kw) * 5.0
    # 财务关键词
    for kw in _FIN_KEYWORDS:
        score += content.count(kw) * 3.0
    # 长度奖励
    if len(content) > 500:
        score += 2.0
    return score


def select_high_value_sections(
    sections: dict[str, str],
    max_chars: int = 300000,
) -> list[tuple[str, str]]:
    """
    选择高价值章节（包含最多数据的章节优先）。

    Args:
        sections: MinerU 解析的章节 {title: content}
        max_chars: 最大总字符数

    Returns:
        排序后的章节列表 [(title, content), ...]
    """
    scored = []
    for title, content in sections.items():
        score = _score_section(content)
        scored.append((score, title, content))

    # 按评分降序排列
    scored.sort(key=lambda x: x[0], reverse=True)

    result = []
    total_chars = 0
    for score, title, content in scored:
        if total_chars + len(content) > max_chars:
            # 截断最后一个章节
            remaining = max_chars - total_chars
            if remaining > 500:
                result.append((title, content[:remaining]))
            break
        result.append((title, content))
        total_chars += len(content)

    logger.info(
        f"高价值章节选择: {len(result)}/{len(sections)} 章节, "
        f"{total_chars}/{sum(len(c) for c in sections.values())} 字符"
    )
    return result


# ====================================================================
# G3: 分批策略 (含 5% 重叠)
# ====================================================================

def chunk_sections(
    selected_sections: list[tuple[str, str]],
    chunk_size: int = 30000,
    overlap_ratio: float = 0.05,
) -> list[str]:
    """
    将选定章节分批，每批 chunk_size 字符，保留 overlap_ratio 重叠。

    Args:
        selected_sections: [(title, content), ...]
        chunk_size: 每批最大字符数
        overlap_ratio: 重叠比例 (0.05 = 5%)

    Returns:
        批次列表 [chunk_text, ...]
    """
    # 拼接为全文（带章节标题）
    full_text = ""
    for title, content in selected_sections:
        full_text += f"\n\n### {title}\n{content}"

    full_text = full_text.strip()
    if not full_text:
        return []

    overlap_chars = int(chunk_size * overlap_ratio)
    step = chunk_size - overlap_chars

    chunks = []
    start = 0
    while start < len(full_text) and len(chunks) < 10:  # max_chunks=10
        end = min(start + chunk_size, len(full_text))
        chunk = full_text[start:end]
        chunks.append(chunk)
        start += step

    logger.info(f"分批完成: {len(chunks)} 批, 每批 ~{chunk_size} 字符, 重叠 {overlap_chars} 字符")
    return chunks


# ====================================================================
# G4: JSON 鲁棒性 (三层防护)
# ====================================================================

def robust_json_parse(llm_output: str) -> tuple[dict | None, list[str]]:
    """
    三层 JSON 解析防护。

    Layer 1: 直接 json.loads
    Layer 2: 截取第一个 '{' 到最后一个 '}'，再 json.loads
    Layer 3: 正则修复常见错误（尾逗号、单引号）

    Returns:
        (parsed_dict or None, warnings)
    """
    warnings = []

    # Layer 1: 直接解析
    try:
        data = json.loads(llm_output)
        if isinstance(data, dict):
            return data, warnings
    except json.JSONDecodeError:
        warnings.append("Layer 1 直接解析失败")

    # Layer 2: 截取 { ... }
    try:
        first_brace = llm_output.find('{')
        last_brace = llm_output.rfind('}')
        if first_brace != -1 and last_brace > first_brace:
            json_str = llm_output[first_brace:last_brace + 1]
            data = json.loads(json_str)
            if isinstance(data, dict):
                warnings.append("Layer 2 截取修复成功")
                return data, warnings
    except json.JSONDecodeError:
        warnings.append("Layer 2 截取解析失败")

    # Layer 3: 正则修复
    try:
        first_brace = llm_output.find('{')
        last_brace = llm_output.rfind('}')
        if first_brace != -1 and last_brace > first_brace:
            json_str = llm_output[first_brace:last_brace + 1]
            # 移除尾逗号
            json_str = re.sub(r',\s*([}\]])', r'\1', json_str)
            # 单引号替换为双引号
            json_str = json_str.replace("'", '"')
            # 移除注释
            json_str = re.sub(r'//.*?\n', '\n', json_str)
            data = json.loads(json_str)
            if isinstance(data, dict):
                warnings.append("Layer 3 正则修复成功")
                return data, warnings
    except json.JSONDecodeError as e:
        warnings.append(f"Layer 3 正则修复失败: {e}")

    warnings.append("所有 JSON 解析层均失败")
    return None, warnings


def extract_operational_from_filings(sections: dict[str, str]) -> dict:
    """v3（用户原则：Wind 没有的由财报提供）：程序化运营提取——不依赖 LLM。

    从财报 sections 用模式匹配提取常见运营指标（交付量/门店数/毛利率等），
    作为 LLM 提取的补充通道（双通道防漏/防编造——数字直接来自原文）。

    Returns:
        {字段名: {"value": float, "source": 章节名, "unit": str}}
    """
    if not sections:
        return {}

    # 模式表：指标 → (regex, 单位换算说明, 目标字段)
    # 单位统一：亿元（财务口径）；运营计数保留原单位
    patterns = [
        # 汽车交付量：全年交付 388,000 辆 / 交付 38.9万辆
        ("deliveries", r"(?:全年|年度|共|累计)?交付[^\d]{0,6}([\d,]+\.?\d*)\s*(万辆|辆)"),
        # 门店数：门店 500 家 / 门店数 520
        ("stores", r"门店[^\d]{0,4}([\d,]+\.?\d*)\s*家"),
        # 毛利率：毛利率 14.5%
        ("gross_margin", r"毛利率[^\d\-]{0,6}(-?\d+\.?\d*)\s*%"),
        # 付费用户：付费用户 1.2 亿
        ("paying_users", r"付费用户[^\d]{0,6}([\d,]+\.?\d*)\s*(亿|万)?人"),
    ]

    result: dict = {}
    for _field, pattern in patterns:
        for title, content in sections.items():
            import re as _re
            m = _re.search(pattern, content)
            if m:
                try:
                    value = float(m.group(1).replace(",", ""))
                    unit = m.group(2) if len(m.groups()) > 1 else ""
                    # 单位换算：万辆→辆（×10000）；亿人→万人（×10000，保亿）
                    if unit == "万辆":
                        value = value * 10000
                        unit = "辆"
                    elif unit == "万" and _field == "paying_users":
                        value = value * 10000
                        unit = "人"
                    elif _field == "gross_margin":
                        value = value / 100.0  # % → 小数
                        unit = ""
                    result[_field] = {"value": value, "source": title[:30], "unit": unit}
                except (TypeError, ValueError):
                    continue
                break  # 每字段取第一个匹配章节
    return result


def validate_numerical_ranges(data: dict) -> list[str]:
    """数值合理性校验"""
    warnings = []
    op = data.get('operational', {})

    # DAU < 100亿
    dau = op.get('dau')
    if isinstance(dau, (int, float)) and dau > 100:
        warnings.append(f"DAU={dau}亿 超出合理范围 (>100亿)")

    # GMV > 0
    gmv = op.get('gmv')
    if isinstance(gmv, (int, float)) and gmv < 0:
        warnings.append(f"GMV={gmv}亿 为负数")

    # 毛利率 0-100%
    fin = data.get('financial', {})
    gm = fin.get('gross_margin')
    if isinstance(gm, (int, float)) and (gm < 0 or gm > 100):
        warnings.append(f"毛利率={gm}% 超出 0-100% 范围")

    return warnings


def normalize_units(data: dict, warnings: list | None = None) -> dict:
    """
    Layer 2: 自动检测和修复单位错误。

    LLM 常见错误:
    - DAU=410.2 → 应为 4.102 (亿, LLM 把"4.102亿"读成 410.2)
    - GMV=1598070.7 → 应为 15980.707 (亿, LLM 把"1.6万亿"读成 1598070.7)
    - 毛利率=0.549 → 应为 54.9 (%, LLM 用小数而非百分比)
    """
    if warnings is None:
        warnings = []
    op = data.get('operational', {})
    fin = data.get('financial', {})

    # DAU 合理范围: 0.01-20亿
    dau = op.get('dau')
    if isinstance(dau, (int, float)) and dau > 0:
        if dau > 100 and dau <= 10000:
            op['dau'] = round(dau / 100, 2)
            warnings.append(f"DAU单位修正: {dau}→{op['dau']} (÷100, 可能是万)")
        elif dau > 10000:
            op['dau'] = round(dau / 10000, 2)
            warnings.append(f"DAU单位修正: {dau}→{op['dau']} (÷10000, 可能是万)")

    # MAU 合理范围: 0.05-30亿
    mau = op.get('mau')
    if isinstance(mau, (int, float)) and mau > 0:
        if mau > 200 and mau <= 20000:
            op['mau'] = round(mau / 100, 2)
            warnings.append(f"MAU单位修正: {mau}→{op['mau']} (÷100)")
        elif mau > 20000:
            op['mau'] = round(mau / 10000, 2)
            warnings.append(f"MAU单位修正: {mau}→{op['mau']} (÷10000)")

    # GMV 合理范围: 100-100000亿
    gmv = op.get('gmv')
    if isinstance(gmv, (int, float)) and gmv > 0:
        if gmv > 100000 and gmv <= 10000000:
            op['gmv'] = round(gmv / 100, 2)
            warnings.append(f"GMV单位修正: {gmv}→{op['gmv']} (÷100, 可能是万元)")
        elif gmv > 10000000:
            op['gmv'] = round(gmv / 10000, 2)
            warnings.append(f"GMV单位修正: {gmv}→{op['gmv']} (÷10000)")

    # 毛利率 合理范围: 0-100%
    gm = fin.get('gross_margin')
    if isinstance(gm, (int, float)) and 0 < gm < 1:
        fin['gross_margin'] = round(gm * 100, 1)
        warnings.append(f"毛利率单位修正: {gm}→{fin['gross_margin']}% (×100)")

    # 净利率 合理范围: -50~50%
    nm = fin.get('net_margin')
    if isinstance(nm, (int, float)) and 0 < abs(nm) < 1:
        fin['net_margin'] = round(nm * 100, 1)
        warnings.append(f"净利率单位修正: {nm}→{fin['net_margin']}% (×100)")

    # ARPU 合理范围: 1-10000元
    arpu = op.get('arpu')
    if isinstance(arpu, (int, float)) and arpu > 10000:
        op['arpu'] = round(arpu / 100, 2)
        warnings.append(f"ARPU单位修正: {arpu}→{op['arpu']} (÷100)")

    return data


def _is_facts_empty(facts: 'ExtractedFacts') -> bool:
    """检查事实表是否几乎为空（所有关键字段都为 None）"""
    op = facts.operational
    fin = facts.financial
    key_fields = [
        op.dau, op.mau, op.gmv, op.arpu,
        fin.revenue, fin.net_profit, fin.gross_margin,
    ]
    non_null = sum(1 for f in key_fields if f is not None)
    return non_null < 2  # 少于2个有效字段视为空


def cross_validate_with_wind(data: dict, wind_data: dict | None) -> list[str]:
    """与 Wind 数据交叉验证（canonical 别名兜底，修复键契约断裂）"""
    warnings = []
    if not wind_data:
        return warnings

    try:
        from .canonical import get_series
    except ImportError:
        get_series = None

    fin = data.get('financial', {})
    income = wind_data.get('income', {})

    def _latest_series(canonical: str):
        """取 Wind 某 canonical 指标的 3 年序列（先精确后别名）"""
        if get_series is not None:
            return get_series(wind_data, canonical)
        return income.get(canonical) or []

    # 净利润偏差检查
    extracted_np = fin.get('net_profit')
    wind_np_list = _latest_series('归母净利润')
    if not wind_np_list:
        wind_np_list = _latest_series('净利润')
    if extracted_np and wind_np_list and isinstance(wind_np_list, list) and len(wind_np_list) > 0:
        wind_np = wind_np_list[-1]  # 最新年份
        if wind_np and abs(extracted_np - wind_np) / max(abs(wind_np), 1) > 0.05:
            warnings.append(
                f"净利润偏差>5%: 提取={extracted_np}亿, Wind={wind_np}亿"
            )

    # 营收偏差检查
    extracted_rev = fin.get('revenue')
    wind_rev_list = _latest_series('营业收入')
    if extracted_rev and wind_rev_list and isinstance(wind_rev_list, list) and len(wind_rev_list) > 0:
        wind_rev = wind_rev_list[-1]
        if wind_rev and abs(extracted_rev - wind_rev) / max(abs(wind_rev), 1) > 0.05:
            warnings.append(
                f"营收偏差>5%: 提取={extracted_rev}亿, Wind={wind_rev}亿"
            )

    return warnings


# ====================================================================
# G5: 事实提取主逻辑
# ====================================================================

EXTRACTION_PROMPT = """你是一个财务数据提取专家。请从以下财报原文中提取结构化数据。

## 提取规则
1. 只提取财报中明确写出的数据，不要推断或计算
2. 每个数据点必须标注来源章节
3. 数值统一使用亿元为单位（人民币），保留2位小数
4. 百分比保留1位小数
5. 如果某项数据在本段中未出现，不要填充（用 null）——**宁可缺失不可杜撰**
6. **不要提取财务数字（营收/净利润/毛利率/现金流/总资产等）**——财务数据 100% 以 Wind 为准（B2b-1），
   本表只提取运营指标（用户/时长/GMV/ARPU 等）与管理信息（高管/回购/分红）
7. **禁止用本批次之外的数据补当前批次**（不得引用前一批/其他章节/自行回忆的数值）——
   本批未出现即 null，由后续合并处理

## 单位规范（必须严格遵守，违反将导致数据错误）
- DAU/MAU: 亿（如"日活跃用户4.1亿"→填4.1，不是410或4100）
- GMV/收入/利润: 亿元（如"GMV1.6万亿元"→填16000.0，不是1600000）
- ARPU/ARPPU: 元（如"每用户平均收入198.6元"→填198.6）
- 百分比: %（如"毛利率54.9%"→填54.9，不是0.549）
- 用户时长: 分钟（如"日均使用时长125分钟"→填125）
- 核心原则: 数值必须与财报原文的单位完全一致，不得自行换算

## 财报原文
{chunk_text}

## 输出格式 (严格 JSON，不要其他文字)
{{
  "operational": {{
    "dau": {{"value": 4.01, "source": "业务概览"}},
    "mau": {{"value": 7.14, "source": "业务概览"}},
    "daily_usage_minutes": {{"value": 125, "source": "业务概览"}},
    "gmv": {{"value": 13900, "source": "电商业务"}},
    "gmv_yoy": {{"value": 15.0, "source": "电商业务"}},
    "monetization_rate": {{"value": 1.5, "source": "电商业务"}},
    "ad_revenue": {{"value": 800, "source": "收入分析"}},
    "live_stream_revenue": {{"value": 350, "source": "收入分析"}},
    "ecommerce_revenue": {{"value": 280, "source": "收入分析"}},
    "paying_users": {{"value": 1.2, "source": "业务概览"}},
    "arpu": {{"value": 198.6, "source": "业务概览"}}
  }},
  "management": {{
    "ceo": {{"value": "程一笑", "source": "董事会报告"}},
    "chairman": {{"value": "程一笑", "source": "董事会报告"}},
    "buyback_amount": {{"value": 60, "source": "股东回报"}},
    "dividend_per_share": {{"value": 0.25, "source": "股东回报"}}
  }},
  "business": {{
    "segments": [
      {{"name": "线上营销", "revenue": 800, "yoy": 15.0}},
      {{"name": "直播", "revenue": 350, "yoy": 5.0}},
      {{"name": "其他服务(电商)", "revenue": 280, "yoy": 20.0}}
    ],
    "strategic_priorities": ["AI大模型", "电商货币化", "海外拓展"]
  }}
}}"""


def _parse_chunk_response(llm_output: str, chunk_idx: int,
                          sections: dict[str, str] | None = None) -> tuple[dict | None, list[str]]:
    """解析单批次的 LLM 输出

    v3（用户原则：Wind 没有的由财报提供）：sections=财报原文章节，
    对运营字段做**原文核对**——LLM 提取值必须能在其标注的 source 章节原文中找到
    （verify_value_against_source，B5-2 接线），否则标 confidence=low + warning
    （防 LLM 提取时编造运营数字——源必须是财报）。
    """
    data, warnings = robust_json_parse(llm_output)

    if data is None:
        warnings.append(f"批次 {chunk_idx} JSON 解析完全失败")
        return None, warnings

    # 规范化：将 {"value": X, "source": Y} 格式扁平化
    normalized = {}
    for section in ['operational', 'financial', 'management']:
        if section in data:
            normalized[section] = {}

            for key, val in data[section].items():
                if isinstance(val, dict) and 'value' in val:
                    normalized[section][key] = val['value']
                    # 记录来源
                    source_key = f"{section}.{key}"
                    if 'sources' not in normalized:
                        normalized['sources'] = {}
                    normalized['sources'][source_key] = val.get('source', '')

                    # v3：运营字段原文核对（Wind 没有的 → 财报提供——LLM 提取值必须能在原文找到）
                    if section == 'operational':
                        _src_name = val.get('source', '')
                        _src_text = ""
                        if _src_name and sections:
                            # 在 sections 里找标注的章节
                            for _t, _c in sections.items():
                                if _src_name in _t or _src_name in _c[:50]:
                                    _src_text = _c
                                    break
                        if _src_text:
                            try:
                                from .normalize_values import verify_value_against_source
                                _conf = verify_value_against_source(_src_text, float(val['value']))
                                if _conf == "low":
                                    warnings.append(
                                        f"批次 {chunk_idx} 运营字段 {key}={val['value']} 未在财报原文"
                                        f"章节'{_src_name}'中找到（B5-2 原文核对失败，防编造）——"
                                        f"标 confidence=low，报告需人工核对该数字"
                                    )
                                    if 'confidences' not in normalized:
                                        normalized['confidences'] = {}
                                    normalized['confidences'][source_key] = "low"
                            except Exception as _e:
                                warnings.append(f"批次 {chunk_idx} {key} 原文核对异常: {_e}")
                else:
                    normalized[section][key] = val
    if 'business' in data:
        normalized['business'] = data['business']

    # 数值合理性校验
    range_warnings = validate_numerical_ranges(normalized)
    warnings.extend(range_warnings)

    # 单位归一化 (Layer 2)
    normalize_units(normalized, warnings)

    return normalized, warnings


def _verify_company_identity(sections: dict[str, str], company_name: str, ticker: str) -> list[str]:
    """
    验证财报是否属于目标公司。

    全文搜索所有章节（不做 50 章/500 字截断），同时匹配简体/繁体公司名与股票代码。
    如果不匹配，说明下载了错误公司的财报。

    Returns:
        空列表 = 验证通过
        非空列表 = 验证失败的警告信息
    """
    warnings = []

    # 从 ticker 提取纯数字代码
    ticker_code = ticker.split('.')[0] if '.' in ticker else ticker

    # 全文搜索（不再截断前50章/每章500字；港股繁体年报需匹配繁体公司名）
    search_text = ""
    for title, content in sections.items():
        search_text += title + "\n" + content + "\n"

    # 公司名变体：简体/繁体/英文/带"-W"后缀（2026-08-22：小鹏港股年报用
    # "小鹏汽车-W"/"小鹏汽车－W"（繁体全角横线）而非"小鹏汽车"，导致误告警）
    name_variants = [company_name]
    _tc_map = {
        "阅": "閱", "文": "文", "集": "集", "团": "團",
    }
    if "阅文集团" in company_name:
        name_variants += ["閱文集團", "阅文集團", "閱文集团", "China Literature"]
    if "集团" in company_name:
        name_variants.append(company_name.replace("集团", "集團"))
    # 通用变体：去"-W"/"－W"后缀 + 全角横线替换（港股同股不同权标记，非公司名一部分）
    _base = company_name.replace("-W", "").replace("－W", "").replace("－", "-")
    if _base != company_name:
        name_variants.append(_base)
    # 英文名兜底：取中文名中非中文部分（如"XPeng"），或常见英文简写
    import re as _re
    _en = _re.sub(r"[\u4e00-\u9fff\-—－·]", "", company_name).strip()
    if _en and len(_en) >= 3:
        name_variants.append(_en)
    name_found = any(v in search_text for v in name_variants if v)
    # 股票代码（含 0772 / 00772 / 0772.HK）
    code_found = any(c in search_text for c in (ticker_code, "0" + ticker_code, ticker, "0772", "00772"))

    if not name_found and not code_found:
        warnings.append(
            f"公司归属验证失败: 全文未找到'{company_name}'/'閱文集團'或代码'{ticker_code}'。"
            f"可能下载了错误公司的财报。"
        )
    elif not name_found:
        logger.warning(f"全文未找到公司名'{company_name}'，但找到股票代码'{ticker_code}'")
    elif not code_found:
        logger.warning(f"全文未找到股票代码'{ticker_code}'，但找到公司名'{company_name}'")

    return warnings



def _calculate_unit_economics(facts: 'ExtractedFacts') -> list[str]:
    """自动计算单位经济指标，返回假设列表"""
    assumptions = []
    op = facts.operational

    # 毛利率：优先财报（Wind 派生）数据；**无源时不填充默认值**（B4-2：删 50% 启发式）
    # LTV/回收期等派生指标在毛利率缺失时跳过，标注"数据不足"而非用假值
    if op.gross_margin is None:
        if facts.financial.gross_margin:
            op.gross_margin = facts.financial.gross_margin
        else:
            assumptions.append("毛利率未披露（Wind 无源），单位经济指标跳过计算（宁缺毋滥）")

    # LTV = 月ARPU x 毛利率 x 用户生命周期（毛利率缺失时跳过——B4-2 不用默认值）
    if op.arpu and op.user_lifetime and op.gross_margin is not None:
        monthly_arpu = op.arpu / 12
        op.ltv = monthly_arpu * op.gross_margin * op.user_lifetime
        assumptions.append(
            f"LTV = {monthly_arpu:.1f}元/月 x {op.gross_margin:.0%} x "
            f"{op.user_lifetime:.0f}月 = {op.ltv:.0f}元"
        )

    # CAC = 营销费用 / 新增用户
    if op.marketing_expense and op.new_users and op.new_users > 0:
        op.cac = (op.marketing_expense * 1e8) / (op.new_users * 1e8)
        assumptions.append(
            f"CAC = {op.marketing_expense:.1f}亿 / {op.new_users:.1f}亿 = {op.cac:.0f}元"
        )

    # LTV/CAC
    if op.ltv and op.cac and op.cac > 0:
        op.ltv_cac_ratio = op.ltv / op.cac

    # 回收期 = CAC / (月ARPU x 毛利率)（毛利率缺失时跳过）
    if op.cac and op.arpu and op.gross_margin is not None:
        monthly_contribution = (op.arpu / 12) * op.gross_margin
        if monthly_contribution > 0:
            op.payback_period = op.cac / monthly_contribution

    return assumptions

def extract_facts(
    sections: dict[str, str],
    company_name: str,
    ticker: str,
    market: str,
    llm_caller: Callable[[str, str], str],
    max_chars: int = 300000,
    chunk_size: int = 30000,
    wind_data: dict | None = None,
    fiscal_year: int | None = None,
    report_type: str = "年报",
) -> ExtractedFacts:
    """
    从财报全文中提取结构化事实。

    Args:
        sections: MinerU 解析的章节
        company_name: 公司名称
        ticker: 股票代码
        market: 市场
        llm_caller: LLM 调用函数
        max_chars: 最大处理字符数
        chunk_size: 每批字符数
        wind_data: Wind 数据 (用于交叉验证)
        fiscal_year: 年报所属财年（P0-B1 财年锚定；由调用方从年报报告期/Wind labels[-1] 推断传入。
            不传时回退：从 wind_data._year_labels[-1] 推断）
        report_type: 报告类型（默认"年报"）

    Returns:
        ExtractedFacts 事实表
    """
    start_time = time.time()
    all_warnings = []

    # P0-B1: 财年锚定（优先入参；其次 Wind 最新财年；都没有则 0=未知）
    if fiscal_year is None and wind_data:
        try:
            labels = (wind_data.get("_year_labels") or {}).get("财年") or []
            if labels:
                fiscal_year = int(labels[-1])
        except (TypeError, ValueError):
            fiscal_year = None
    if fiscal_year is None:
        all_warnings.append("⚠️ 未提供财年信息（fiscal_year 未知），提取结果需人工核对财年")

    # 0. 验证财报归属 (防止下载错公司)
    verify_warnings = _verify_company_identity(sections, company_name, ticker)
    if verify_warnings:
        all_warnings.extend(verify_warnings)
        logger.error(f"公司归属验证失败: {verify_warnings}")
        # 返回空事实表，不继续提取
        facts = ExtractedFacts(company_name=company_name, ticker=ticker)
        facts.meta = ExtractionMeta(
            total_sections=len(sections),
            warnings=verify_warnings,
        )
        return facts

    # 1. 选择高价值章节
    selected = select_high_value_sections(sections, max_chars=max_chars)
    total_chars = sum(len(c) for _, c in selected)

    # 2. 分批
    chunks = chunk_sections(selected, chunk_size=chunk_size)

    # 3. 逐批提取（注入财年上下文）
    all_chunk_data = []
    llm_calls = 0
    max_retries = 2
    for i, chunk in enumerate(chunks):
        # P0-B1: 注入财年指令（区分当期/对比期，要求标注所属财年）
        chunk_with_fy = _inject_fiscal_year_instruction(chunk, fiscal_year, report_type)
        prompt = EXTRACTION_PROMPT.format(chunk_text=chunk_with_fy)
        chunk_data = None
        for attempt in range(max_retries + 1):
            try:
                output = llm_caller(f"事实提取_批次{i+1}", prompt)
                llm_calls += 1
                data, warnings = _parse_chunk_response(output, i, sections)
                all_warnings.extend(warnings)
                if data:
                    chunk_data = data
                    logger.info(f"批次 {i+1}/{len(chunks)} 提取成功 (attempt {attempt+1})")
                    break
                else:
                    if attempt < max_retries:
                        logger.warning(f"批次 {i+1}/{len(chunks)} 提取为空，重试 {attempt+1}/{max_retries}")
                    else:
                        logger.warning(f"批次 {i+1}/{len(chunks)} 提取失败 (已重试{max_retries}次): {warnings}")
            except Exception as e:
                all_warnings.append(f"批次 {i+1} LLM 调用异常 (attempt {attempt+1}): {e}")
                logger.error(f"批次 {i+1} LLM 调用异常: {e}")
                if attempt >= max_retries:
                    break
        if chunk_data:
            all_chunk_data.append(chunk_data)

    # 4. 合并（P0-B1: 设置 fiscal_year / report_type）
    facts = _merge_chunk_data(all_chunk_data, company_name, ticker)
    facts.fiscal_year = fiscal_year or 0
    facts.report_type = report_type
    facts.meta = ExtractionMeta(
        total_sections=len(sections),
        sections_processed=len(selected),
        chunks_used=len(chunks),
        llm_calls=llm_calls,
        extraction_time_seconds=time.time() - start_time,
        coverage_ratio=total_chars / max(sum(len(c) for c in sections.values()), 1),
        warnings=all_warnings,
    )

    # 5. B2b-1：财务 100% Wind——从 Wind 处置表填充 financial（有源/派生/未披露）
    if wind_data:
        from .wind_field_disposition import resolve_financial_from_wind
        # 双专家 P1：按 facts.fiscal_year 取对应财年值（防财年标签与数值脱钩——
        # facts.fiscal_year 可能来自 filing 元数据，非 Wind 最新财年）
        fy = facts.fiscal_year if facts.fiscal_year else None
        fin_values, fin_annotations = resolve_financial_from_wind(wind_data, fiscal_year=fy)
        for field, val in fin_values.items():
            if hasattr(facts.financial, field):
                setattr(facts.financial, field, val)
        facts.meta.warnings.extend(fin_annotations)
        logger.info(f"财务字段 Wind 填充: {len(fin_values)} 个（含派生/未披露标注 {len(fin_annotations)} 条）")

    # 6. Wind 交叉验证（financial 已 100% Wind，此处主要验证运营/派生字段偏差）
    if wind_data:
        wind_warnings = cross_validate_with_wind(facts.to_dict(), wind_data)
        facts.meta.warnings.extend(wind_warnings)

    # 7. B4-1 运营数据验证链（结构性铁律阻断：MAU ≥ DAU ≥ 付费用户；派生钩稽 warning 级）
    chain_violations = validate_operational_chain(facts)
    facts.meta.warnings.extend(chain_violations)
    if chain_violations:
        facts.meta.warnings.append("⚠️ 运营数据存在结构性铁律冲突（B4-1），相关数字需人工复核")

    # v3（用户原则：Wind 没有的由财报提供）：程序化运营提取补充——
    # 从财报 sections 用模式匹配提取交付量/门店数/毛利率等（不依赖 LLM，双通道防漏）
    try:
        _prog_ops = extract_operational_from_filings(sections)
        if _prog_ops:
            _filled = 0
            for _k, _v in _prog_ops.items():
                if hasattr(facts.operational, _k) and getattr(facts.operational, _k, None) is None:
                    setattr(facts.operational, _k, _v["value"])
                    _filled += 1
            if _filled:
                _ops_names = list(_prog_ops.keys())[:_filled][:4]
                facts.meta.warnings.append(
                    f"运营数据补充：程序化财报提取 {_filled} 项"
                    f"（{_ops_names}，源=财报原文）"
                )
                logger.info(f"程序化运营提取补充 {_filled} 项")
    except Exception as _e:
        logger.warning(f"程序化运营提取失败（非阻断）: {_e}")

    # v3（用户原则）：运营数据源=财报（LLM 提取经原文核对 + 程序化提取补充）——
    # 标注更新：不再"未经锚点校验"，而是"经财报原文核对（非 Wind）"
    if getattr(facts, "operational", None) is not None and any(
        getattr(facts.operational, f, None) is not None
        for f in ("dau", "mau", "arpu", "gmv", "ltv", "cac", "paying_users",
                  "deliveries", "stores")
        if hasattr(facts.operational, f)
    ):
        facts.meta.warnings.append(
            "运营数据来源=财报原文（LLM 提取经原文核对/程序化提取），"
            "非 Wind 锚点——仅供方向参考，投资结论勿单独依赖"
        )

    logger.info(
        f"事实提取完成: {llm_calls} 次调用, "
        f"FY{facts.fiscal_year} {facts.report_type}, "
        f"{facts.meta.extraction_time_seconds:.1f}秒, "
        f"覆盖率 {facts.meta.coverage_ratio:.1%}, "
        f"warnings={len(facts.meta.warnings)}"
    )
    return facts


def validate_operational_chain(facts: 'ExtractedFacts') -> list[str]:
    """B4-1 运营数据验证链（结构性铁律 + 派生钩稽）。

    铁律（阻断级）：MAU ≥ DAU ≥ 付费用户（结构性不可能违反）
    派生钩稽（warning 级）：DAU/MAU 比率范围、付费渗透率范围等
    """
    violations: list[str] = []
    op = facts.operational

    # 铁律 1：DAU ≤ MAU（日活不可能大于月活）
    if op.dau is not None and op.mau is not None and op.dau > op.mau * 1.001:
        violations.append(f"结构性铁律: DAU {op.dau} > MAU {op.mau}（不可能，B4-1）")

    # 铁律 2：付费用户 ≤ DAU（付费渗透率 ≤ 100%）
    if op.paying_users is not None and op.dau is not None and op.paying_users > op.dau * 1.001:
        violations.append(
            f"结构性铁律: 付费用户 {op.paying_users} > DAU {op.dau}（付费渗透率>100%，不可能，B4-1）"
        )

    # 派生钩稽（warning 级）：DAU/MAU 比率合理范围（10%-90%，极端值提示复核）
    if op.dau is not None and op.mau and op.mau > 0:
        ratio = op.dau / op.mau
        if ratio > 0.9 or ratio < 0.1:
            violations.append(f"派生钩稽: DAU/MAU={ratio:.0%} 超常见范围 10%-90%（提示复核，B4-1）")

    # 派生钩稽：GMV 与 ARPU×付费用户 数量级对照（若均有值，偏差>50% 提示）
    if op.gmv is not None and op.arpu is not None and op.paying_users is not None:
        implied_gmv = op.arpu * op.paying_users * 1e4 / 1e8  # ARPU(元)×付费用户(亿)→亿元
        if implied_gmv > 0 and abs(op.gmv - implied_gmv) / implied_gmv > 0.5:
            violations.append(
                f"派生钩稽: GMV {op.gmv}亿 vs ARPU×付费用户 ≈{implied_gmv:.0f}亿，偏差>50%（提示复核，B4-1）"
            )

    return violations


def _inject_fiscal_year_instruction(chunk: str, fiscal_year: int | None,
                                    report_type: str = "年报") -> str:
    """P0-B1: 向批次文本注入财年指令（区分当期/对比期）"""
    if fiscal_year is None:
        return chunk
    prior = fiscal_year - 1
    return (
        f"\n\n【财年上下文·必须遵守】\n"
        f"本批文本来自 {fiscal_year} 财年{report_type}原文。\n"
        f"- '本年度/报告期/本报告期/本集团' 指 FY{fiscal_year}\n"
        f"- '上年/上年度/对比期/同期' 指 FY{prior}\n"
        f"- 提取的财务数字（收入/利润/现金流等）必须标注其所属财年：FY{fiscal_year} 或 FY{prior}\n"
        f"- 若数字无法确认财年，标注 FY?（待核实），不得默认为当期\n"
        f"- 当期（FY{fiscal_year}）数据放当期字段；对比期数据只作参考，不要放入当期字段\n"
        f"\n以下为待提取文本：\n\n{chunk}"
    )


# ====================================================================
# G6: 合并策略 (v2.0: 任一有效值优先保留)
# ====================================================================

def _merge_chunk_data(all_data: list[dict], company_name: str, ticker: str) -> ExtractedFacts:
    """
    合并多批次提取结果。

    v2.0 策略: 任一有效值优先保留，后批次覆盖同字段。
    """
    facts = ExtractedFacts(company_name=company_name, ticker=ticker)

    for chunk_data in all_data:
        # 合并 operational —— B3-3：冲突保留首个 + warning（无静默覆盖）
        op = chunk_data.get('operational', {})
        for key, val in op.items():
            if val is not None and hasattr(facts.operational, key):
                current = getattr(facts.operational, key)
                if current is None:
                    setattr(facts.operational, key, val)
                elif (isinstance(val, (int, float)) and isinstance(current, (int, float))
                      and abs(current - val) > 1e-9) or (
                          not isinstance(val, (int, float)) and current != val):
                    # B3-3：跨批冲突——保留首个（先提取更可靠），记录冲突
                    logger.warning(f"批次仲裁: {key} 冲突 {current} vs {val}，保留首个 {current}")
                    facts.meta.warnings.append(f"批次仲裁: {key} 冲突 {current} vs {val}，保留首个")

        # 合并 financial —— B2b-1：财务 100% Wind，忽略 LLM 提取的财务字段（防污染）
        # （LLM 财务值不再合并；financial 由 extract_facts 从 Wind 处置表填充）
        fin = chunk_data.get('financial', {})
        if fin:
            logger.info(f"忽略 LLM 财务字段 {len(fin)} 个（B2b-1：财务以 Wind 为准）")

        # 合并 management
        mgmt = chunk_data.get('management', {})
        for key, val in mgmt.items():
            if val is not None and hasattr(facts.management, key):
                current = getattr(facts.management, key)
                if current is None:
                    setattr(facts.management, key, val)
                else:
                    setattr(facts.management, key, val)

        # 合并 business (列表字段: 合并去重)
        biz = chunk_data.get('business', {})
        if biz.get('segments'):
            existing_names = {s.get('name') for s in facts.business.segments}
            for seg in biz['segments']:
                if isinstance(seg, dict) and seg.get('name') not in existing_names:
                    facts.business.segments.append(seg)
                    existing_names.add(seg.get('name'))
        if biz.get('strategic_priorities'):
            for p in biz['strategic_priorities']:
                if p not in facts.business.strategic_priorities:
                    facts.business.strategic_priorities.append(p)
        if biz.get('risks'):
            for r in biz['risks']:
                if r not in facts.business.risks:
                    facts.business.risks.append(r)

        # 合并来源
        sources = chunk_data.get('sources', {})
        for key, source in sources.items():
            if source:
                facts.operational.sources[key] = source

    return facts


# ====================================================================
# G7: 事实表格式化
# ====================================================================

def format_facts_as_context(facts: ExtractedFacts) -> str:
    """将事实表格式化为 LLM 可读的结构化表格（单财年、统一口径，~5K 字符）"""
    op = facts.operational
    fin = facts.financial
    mgmt = facts.management
    biz = facts.business
    fy = facts.fiscal_year

    lines = [f"## 财报结构化事实表（{facts.company_name}，FY{fy} {facts.report_type}，来源：财报原文）"]
    lines.append("")

    # 财务数据表（B2b-1：来源 Wind；B3-2：无 LLM 编造页码）
    lines.append(f"### 财务数据（单财年 FY{fy}）")
    lines.append(f"| 指标 | 口径 | FY{fy} | 单位 | 来源 |")
    lines.append("|------|------|------|------|------|")
    fin_fields = [
        ("营业收入", "IFRS", fin.revenue, "亿元"),
        ("净利润", "IFRS归母", fin.net_profit, "亿元"),
        # 双专家 P0（2026-08-22）：毛利率 Wind 无 canonical 列 → 未披露（禁用营业利润率顶替）
        ("毛利率", "Wind无列", fin.gross_margin, "%"),
        ("经营现金流", "IFRS", fin.operating_cashflow, "亿元"),
        ("总资产", "IFRS", fin.total_assets, "亿元"),
        ("现金及等价物", "IFRS", fin.cash_and_equivalents, "亿元"),
        ("有息负债", "IFRS", fin.interest_bearing_debt, "亿元"),
    ]
    for name, basis, val, unit in fin_fields:
        if val is not None:
            lines.append(f"| {name} | {basis} | {val} | {unit} | Wind |")
        else:
            lines.append(f"| {name} | {basis} | 未披露 | {unit} | Wind |")

    lines.append("")

    # 运营数据表（B3-2：页码列——MinerU 无 page 元数据 → 未提供/unverified，禁止 LLM 编造）
    lines.append(f"### 运营数据（FY{fy}）")
    lines.append(f"| 指标 | FY{fy} | 单位 | 来源 | 页码 |")
    lines.append("|------|------|------|------|------|")
    op_fields = [
        ("DAU", op.dau, "亿"), ("MAU", op.mau, "亿"),
        ("DAU/MAU", op.dau_mau_ratio, ""), ("日均使用时长", op.daily_usage_minutes, "分钟"),
        ("电商GMV", op.gmv, "亿元"), ("GMV同比增速", op.gmv_yoy, "%"),
        ("货币化率", op.monetization_rate, "%"), ("广告收入", op.ad_revenue, "亿元"),
        ("直播收入", op.live_stream_revenue, "亿元"), ("电商收入", op.ecommerce_revenue, "亿元"),
        ("付费用户", op.paying_users, "亿"), ("ARPU", op.arpu, "元"),
    ]
    for name, val, unit in op_fields:
        if val is not None:
            source = op.sources.get(f"operational.{name.lower().replace('/', '_')}", "")
            source_str = f" [{source}]" if source else ""
            lines.append(f"| {name} | {val} | {unit}{source_str} | 未提供(unverified) |")

    lines.append("")

    # 业务分部表
    if biz.segments:
        lines.append(f"### 业务分部（FY{fy}）")
        lines.append("| 分部 | 收入(亿元) | YoY(%) |")
        lines.append("|------|-----------|--------|")
        for seg in biz.segments:
            name = seg.get('name', '')
            rev = seg.get('revenue', '')
            yoy = seg.get('yoy', '')
            lines.append(f"| {name} | {rev} | {yoy} |")

    # 管理层与战略
    if mgmt.ceo or mgmt.chairman or mgmt.buyback_amount or mgmt.dividend_per_share:
        lines.append("")
        lines.append("### 管理层")
        if mgmt.ceo:
            lines.append(f"- CEO: {mgmt.ceo}")
        if mgmt.chairman:
            lines.append(f"- 董事长: {mgmt.chairman}")
        if mgmt.buyback_amount:
            lines.append(f"- 回购金额: {mgmt.buyback_amount}亿港元")
        if mgmt.dividend_per_share:
            lines.append(f"- 每股股息: {mgmt.dividend_per_share}港元")

    if biz.strategic_priorities:
        lines.append("")
        lines.append("### 战略重点")
        for p in biz.strategic_priorities:
            lines.append(f"- {p}")

    # 财年统一铁律（通用，不硬编码具体年份）
    lines.append("")
    lines.append("⚠️ **财年统一铁律（必须遵守）**：")
    lines.append(f"1. 本事实表仅含 **FY{fy}** 单一年度数据（来自财报原文，口径为财报原口径）。")
    lines.append("2. 报告中引用任何财务数字**必须标注财年**；全报告同一指标只允许一个数值。")
    lines.append("3. **禁止**把本表数据与其他财年（如 Wind 锚点的其他年度）的数字混用或自行推算。")
    lines.append("4. 涉及跨财年对比时，只允许引用 Wind 锚点表中同一年份的数据，并在文中标注两个财年。")

    return "\n".join(lines)
