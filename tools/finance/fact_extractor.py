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
import re
import time
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional, Callable, Any

logger = logging.getLogger(__name__)


# ====================================================================
# 数据结构
# ====================================================================

@dataclass
class OperationalFacts:
    """运营数据"""
    dau: Optional[float] = None
    mau: Optional[float] = None
    dau_mau_ratio: Optional[float] = None
    daily_usage_minutes: Optional[float] = None
    gmv: Optional[float] = None
    gmv_yoy: Optional[float] = None
    monetization_rate: Optional[float] = None
    live_stream_revenue: Optional[float] = None
    ad_revenue: Optional[float] = None
    ecommerce_revenue: Optional[float] = None
    paying_users: Optional[float] = None
    arpu: Optional[float] = None
    arppu: Optional[float] = None
    creators: Optional[float] = None
    
    # 新增：留存指标
    retention_rate_d1: Optional[float] = None   # 次日留存率
    retention_rate_d7: Optional[float] = None   # 7日留存率
    retention_rate_d30: Optional[float] = None  # 30日留存率
    
    # 新增：单位经济
    ltv: Optional[float] = None                 # 用户生命周期价值
    cac: Optional[float] = None                 # 获客成本
    ltv_cac_ratio: Optional[float] = None       # LTV/CAC
    payback_period: Optional[float] = None      # 回收期（月）
    user_lifetime: Optional[float] = None       # 用户生命周期（月）
    
    # 新增：费用数据
    marketing_expense: Optional[float] = None   # 营销费用（亿人民币）
    new_users: Optional[float] = None           # 新增用户（亿）
    gross_margin: Optional[float] = None        # 毛利率
    
    sources: dict = field(default_factory=dict)


@dataclass
class FinancialFacts:
    """财务数据"""
    revenue: Optional[float] = None
    net_profit: Optional[float] = None
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    net_margin: Optional[float] = None
    operating_cashflow: Optional[float] = None
    capex: Optional[float] = None
    total_assets: Optional[float] = None
    total_liabilities: Optional[float] = None
    equity: Optional[float] = None
    cash_and_equivalents: Optional[float] = None
    interest_bearing_debt: Optional[float] = None


@dataclass
class ManagementFacts:
    """管理层信息"""
    ceo: Optional[str] = None
    chairman: Optional[str] = None
    cfo: Optional[str] = None
    board_changes: list = field(default_factory=list)
    shareholding: dict = field(default_factory=dict)
    buyback_amount: Optional[float] = None
    dividend_per_share: Optional[float] = None


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

    def to_dict(self) -> dict:
        """序列化为 dict (用于 JSON 持久化)"""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'ExtractedFacts':
        """从 dict 反序列化"""
        return cls(
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

def robust_json_parse(llm_output: str) -> tuple[Optional[dict], list[str]]:
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


def normalize_units(data: dict, warnings: list[str] = None) -> dict:
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
    if isinstance(gm, (int, float)):
        if 0 < gm < 1:
            fin['gross_margin'] = round(gm * 100, 1)
            warnings.append(f"毛利率单位修正: {gm}→{fin['gross_margin']}% (×100)")

    # 净利率 合理范围: -50~50%
    nm = fin.get('net_margin')
    if isinstance(nm, (int, float)):
        if 0 < abs(nm) < 1:
            fin['net_margin'] = round(nm * 100, 1)
            warnings.append(f"净利率单位修正: {nm}→{fin['net_margin']}% (×100)")

    # ARPU 合理范围: 1-10000元
    arpu = op.get('arpu')
    if isinstance(arpu, (int, float)) and arpu > 0:
        if arpu > 10000:
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


def cross_validate_with_wind(data: dict, wind_data: Optional[dict]) -> list[str]:
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
5. 如果某项数据在本段中未出现，不要填充（用 null）

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
  "financial": {{
    "revenue": {{"value": 1427.76, "source": "利润表"}},
    "net_profit": {{"value": 186.17, "source": "利润表"}},
    "gross_margin": {{"value": 54.9, "source": "利润表"}},
    "operating_cashflow": {{"value": 267.16, "source": "现金流量表"}},
    "total_assets": {{"value": 1645.04, "source": "资产负债表"}},
    "cash_and_equivalents": {{"value": 111.80, "source": "资产负债表"}}
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


def _parse_chunk_response(llm_output: str, chunk_idx: int) -> tuple[Optional[dict], list[str]]:
    """解析单批次的 LLM 输出"""
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

    # 公司名变体：简体/繁体/英文
    name_variants = [company_name]
    _tc_map = {
        "阅": "閱", "文": "文", "集": "集", "团": "團",
        "集": "集團", "團": "團",
    }
    if "阅文集团" in company_name:
        name_variants += ["閱文集團", "阅文集團", "閱文集团", "China Literature"]
    if "集团" in company_name:
        name_variants.append(company_name.replace("集团", "集團"))
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
    
    # 毛利率：优先使用财报数据，否则使用行业默认值
    if op.gross_margin is None:
        if facts.financial.gross_margin:
            op.gross_margin = facts.financial.gross_margin
        else:
            op.gross_margin = 0.5  # 默认 50%
            assumptions.append("毛利率未披露，使用默认值 50%")
    
    # LTV = 月ARPU x 毛利率 x 用户生命周期
    if op.arpu and op.user_lifetime:
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
    
    # 回收期 = CAC / (月ARPU x 毛利率)
    if op.cac and op.arpu:
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
    wind_data: Optional[dict] = None,
    fiscal_year: Optional[int] = None,
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
                data, warnings = _parse_chunk_response(output, i)
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

    # 5. Wind 交叉验证
    if wind_data:
        wind_warnings = cross_validate_with_wind(facts.to_dict(), wind_data)
        facts.meta.warnings.extend(wind_warnings)

    logger.info(
        f"事实提取完成: {llm_calls} 次调用, "
        f"FY{facts.fiscal_year} {facts.report_type}, "
        f"{facts.meta.extraction_time_seconds:.1f}秒, "
        f"覆盖率 {facts.meta.coverage_ratio:.1%}, "
        f"warnings={len(facts.meta.warnings)}"
    )
    return facts


def _inject_fiscal_year_instruction(chunk: str, fiscal_year: Optional[int],
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
        # 合并 operational
        op = chunk_data.get('operational', {})
        for key, val in op.items():
            if val is not None and hasattr(facts.operational, key):
                current = getattr(facts.operational, key)
                if current is None:
                    setattr(facts.operational, key, val)
                else:
                    # 后批次覆盖
                    setattr(facts.operational, key, val)

        # 合并 financial
        fin = chunk_data.get('financial', {})
        for key, val in fin.items():
            if val is not None and hasattr(facts.financial, key):
                current = getattr(facts.financial, key)
                if current is None:
                    setattr(facts.financial, key, val)
                else:
                    setattr(facts.financial, key, val)

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
        if 'segments' in biz and biz['segments']:
            existing_names = {s.get('name') for s in facts.business.segments}
            for seg in biz['segments']:
                if isinstance(seg, dict) and seg.get('name') not in existing_names:
                    facts.business.segments.append(seg)
                    existing_names.add(seg.get('name'))
        if 'strategic_priorities' in biz and biz['strategic_priorities']:
            for p in biz['strategic_priorities']:
                if p not in facts.business.strategic_priorities:
                    facts.business.strategic_priorities.append(p)
        if 'risks' in biz and biz['risks']:
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

    # 财务数据表
    lines.append("### 财务数据（单财年 FY{}）".format(fy))
    lines.append("| 指标 | 口径 | FY{} | 单位 | 来源 |".format(fy))
    lines.append("|------|------|------|------|------|")
    fin_fields = [
        ("营业收入", "IFRS", fin.revenue, "亿元"),
        ("净利润", "IFRS归母", fin.net_profit, "亿元"),
        ("毛利率", "-", fin.gross_margin, "%"),
        ("经营现金流", "IFRS", fin.operating_cashflow, "亿元"),
        ("总资产", "IFRS", fin.total_assets, "亿元"),
        ("现金及等价物", "IFRS", fin.cash_and_equivalents, "亿元"),
        ("有息负债", "IFRS", fin.interest_bearing_debt, "亿元"),
    ]
    for name, basis, val, unit in fin_fields:
        if val is not None:
            lines.append(f"| {name} | {basis} | {val} | {unit} | 财报原文 |")

    lines.append("")

    # 运营数据表
    lines.append("### 运营数据（FY{}）".format(fy))
    lines.append("| 指标 | FY{} | 单位 | 来源 |".format(fy))
    lines.append("|------|------|------|------|")
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
            lines.append(f"| {name} | {val} | {unit}{source_str} | |")

    lines.append("")

    # 业务分部表
    if biz.segments:
        lines.append("### 业务分部（FY{}）".format(fy))
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
