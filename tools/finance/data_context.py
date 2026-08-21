"""
DataContext - 层间传递的数据契约

定义了整个投资分析工作流中各层之间的数据接口。
字段映射单源真源：canonical.py（本模块不再维护独立映射副本，WIND_FIELD_MAPPING 保留为
"内部名 → Wind MCP 原始名"的历史对照，仅作文档/调试；运行时归一一律走 canonical.canonicalize）。
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

logger = logging.getLogger(__name__)


# ====================================================================
# Wind MCP 原始字段名对照（历史参考，非运行时真源）
# 运行时字段归一请用 canonical.canonicalize()（唯一真源，见 docs/qual-data-contradiction-source.md 方案A）
# 基于 2026-06-30 实测 600519.SH 确认
# 内部名 → Wind 实际返回字段名
# ====================================================================

WIND_FIELD_MAPPING = {
    # 利润表
    "营业收入": "年营业总收入",
    "营业成本": "年营业总成本",
    "营业利润": "年营业利润",
    "净利润": "年净利润",
    "归母净利润": "年归属母公司股东的净利润",
    "研发费用": "年研发费用",
    "EBIT": "年EBIT",
    "EBITDA": "年EBITDA",

    # 资产负债表
    "流动资产": "最近3年每年流动资产合计",
    "总资产": "最近3年每年资产总计",
    "流动负债": "最近3年每年流动负债合计",
    "总负债": "最近3年每年负债合计",
    "股东权益": "最近3年每年所有者权益合计",

    # 现金流量表
    "经营活动现金流量净额": "过去三年每年经营活动产生的现金流量净额",
    "投资活动现金流量净额": "过去三年每年投资活动产生的现金流量净额",
    "筹资活动现金流量净额": "过去三年每年筹资活动产生的现金流量净额",
}


def safe_get(data: dict, key: str, default=0) -> float:
    """安全获取字段值（canonical 优先，Wind 原始名兜底）

    查找顺序: data[key] → data[WIND_FIELD_MAPPING[key]] → canonicalize 后取值
    """
    value = data.get(key)
    if value is not None:
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    mapped = WIND_FIELD_MAPPING.get(key)
    if mapped:
        value = data.get(mapped)
        if value is not None:
            try:
                return float(value)
            except (ValueError, TypeError):
                return default

    # canonical 兜底（key 可能是历史别名）
    try:
        from .canonical import canonical_key
        ck = canonical_key(key)
        if ck != key:
            value = data.get(ck)
            if value is not None:
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return default
    except ImportError:
        pass

    return default


def has_field(data: dict, key: str) -> bool:
    """检查字段是否存在（canonical 优先）"""
    if key in data and data[key] is not None:
        return True
    mapped = WIND_FIELD_MAPPING.get(key)
    if mapped and mapped in data and data[mapped] is not None:
        return True
    try:
        from .canonical import canonical_key
        ck = canonical_key(key)
        if ck != key and ck in data and data[ck] is not None:
            return True
    except ImportError:
        pass
    return False


def latest_value(data: dict, key: str, default=0) -> float:
    """Wind 返回3年数组，取最新一年（最后一个非空元素）

    Wind 数据约定: rows 按时间升序排列，最后一个元素为最新年份。
    若数据未按此约定排序，结果可能不准确。
    canonical 优先，Wind 原始名兜底。
    """
    value = data.get(key)
    if value is None:
        # 尝试映射
        mapped = WIND_FIELD_MAPPING.get(key)
        if mapped:
            value = data.get(mapped)
        if value is None:
            try:
                from .canonical import canonical_key
                ck = canonical_key(key)
                if ck != key:
                    value = data.get(ck)
            except ImportError:
                pass
        if value is None:
            return default
    if isinstance(value, list):
        if not value:
            return default
        for v in reversed(value):
            if v is not None:
                try:
                    return float(v)
                except (ValueError, TypeError):
                    continue
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


# ====================================================================
# 数据源权威契约（SOURCE_AUTHORITY）
# 评审结论（docs/qual-data-source-authority.md）：数据权威分两个维度——
#   - 内容真实性：财报（一手披露）> Wind（二手整理）> 搜索（三手观点）
#   - 数值锚定：Wind canonical 为唯一真源（结构化+财年明确+可机器校验），财报提取做交叉印证
# 分工矩阵：
#   财务数值（收入/利润/现金流/资产）→ 内容源=财报，数值锚=Wind（唯一真源），
#     冲突仲裁：同财年偏差≤1% 保留财报值；>1% 以 Wind 覆盖；异财年降级为参考（见 workflow._reconcile_facts_with_wind）
#   运营/定性（MAU/付费/IP/治理/风险）→ 财报事实表（唯一源）
#   行业/市场/新闻 → 搜索（anysearch/tavily），仅参考，不参与财务数值
# ====================================================================
SOURCE_AUTHORITY = {
    "filing": "content_primary",     # 财报：内容/运营事实的一手权威
    "wind": "numeric_primary",       # Wind：财务数值的唯一锚定权威
    "search": "supplementary",       # 搜索：行业/外部补充，不参与数值
}

# 数据源真实性层级（内容维度：谁披露谁权威）
SOURCE_TRUTH_ORDER = ("filing", "wind", "search")  # 一手 > 二手 > 三手


@dataclass
class WindData:
    """Wind MCP 结构化数据"""

    quote: dict | None = None          # 实时行情
    valuation: dict | None = None      # 估值指标
    income: dict | None = None         # 利润表
    balance: dict | None = None        # 资产负债表
    cashflow: dict | None = None       # 现金流量表
    news: list | None = None           # 财经新闻
    industry: dict | None = None       # 行业数据
    _year_labels: dict | None = None   # 年份标签映射 {field: [FY2023, FY2024, FY2025]}


@dataclass
class FilingData:
    """财报原文数据"""

    sections: dict[str, str] = field(default_factory=dict)   # section_name → content
    tables: list[dict] = field(default_factory=list)          # 表格列表
    metadata: dict = field(default_factory=dict)              # 元数据
    source: Literal["filing", "search"] = "filing"            # 数据来源


@dataclass
class SearchResult:
    """搜索结果"""

    query: str
    results: list[dict] = field(default_factory=list)
    source: Literal["anysearch", "exa", "tavily"] = "anysearch"


@dataclass
class FacetResult:
    """类型推断结果"""

    business_model: list[str] = field(default_factory=list)   # 业务模型 ID 列表
    constraints: list[str] = field(default_factory=list)       # 约束条件 ID 列表
    market: Literal["us", "cn", "hk"] = "us"                  # 市场


@dataclass
class DataContext:
    """数据上下文 - 层间传递的数据契约

    包含完整的投资分析所需数据:
    - 基本信息 (ticker, company_name, market)
    - 财报原文层 (filing)
    - 结构化数字层 (wind)
    - 搜索补充 (search_results)
    - 类型推断 (facets)
    - 数据质量标记
    """

    # 基本信息
    ticker: str
    company_name: str
    market: Literal["us", "cn", "hk"]

    # 财报原文层
    filing: FilingData | None = None

    # 结构化数字层
    wind: WindData | None = None

    # 搜索补充
    search_results: list[SearchResult] = field(default_factory=list)

    # 类型推断
    facets: FacetResult | None = None

    # 结构化事实表 (fact_extractor 提取)
    facts: Any | None = None  # ExtractedFacts, 用 Any 避免循环导入

    # 数据质量标记
    filing_source: Literal["filing", "search", "unavailable"] = "unavailable"
    wind_source: Literal["wind", "fallback", "unavailable"] = "unavailable"

    @property
    def data_quality(self) -> Literal["high", "medium", "low"]:
        """评估数据质量

        Returns:
            high: 财报原文 + Wind 结构化数据均可用
            medium: 其中之一可用
            low: 均不可用
        """
        if self.filing_source == "filing" and self.wind_source == "wind":
            return "high"
        elif self.filing_source == "filing" or self.wind_source == "wind":
            return "medium"
        else:
            return "low"
