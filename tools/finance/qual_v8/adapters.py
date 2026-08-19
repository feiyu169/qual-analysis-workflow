"""
Qual v8 适配层（2026-08-18 新增）

把 v2-v7 已验证的真实组件适配为 Gate 可调用形式：
- build_data_context: 构造 DataContext（复用 finance.workflow._collect_data）
- canonical 键工具（复用 data_anchor.CANONICAL_ALIASES）
- 惰性导入避免循环依赖
"""

from typing import Dict, Any, Optional, List, Tuple
import logging

logger = logging.getLogger(__name__)

# 关键财务指标（Gate0 覆盖率检查用）— canonical 键
REQUIRED_WIND_FIELDS = [
    "营业收入", "归母净利润", "营业利润", "总资产",
    "归母净资产", "年负债合计", "年所有者权益合计", "经营活动现金流量净额",
]

# 三张表位置
WIND_SECTIONS = ["income", "balance", "cashflow"]


def canonical_aliases() -> Dict[str, str]:
    """canonical 键别名表（与 data_anchor 共用，避免重复定义）"""
    from .data_anchor import CANONICAL_ALIASES
    return dict(CANONICAL_ALIASES)


def build_data_context(
    ticker: str,
    company_name: str,
    market: str,
    wind_data: Optional[Dict[str, Any]] = None,
    filing_data: Optional[Dict[str, Any]] = None,
    search_results: Optional[List[dict]] = None,
) -> Any:
    """构造 DataContext（复用 finance.workflow._collect_data）"""
    from ..workflow import _collect_data, infer_facets
    facets = infer_facets(ticker, market, company_name)
    return _collect_data(
        ticker=ticker,
        company_name=company_name,
        market=market,
        facets=facets,
        wind_data=wind_data,
        filing_data=filing_data,
        search_results=search_results,
    )


def wind_coverage(wind_data: Optional[Dict[str, Any]]) -> Tuple[float, List[str]]:
    """Wind 数据 canonical 键覆盖率（0-1）+ 缺失字段列表"""
    if not wind_data:
        return 0.0, REQUIRED_WIND_FIELDS
    missing = []
    present = 0
    for field in REQUIRED_WIND_FIELDS:
        found = False
        for section in WIND_SECTIONS:
            table = wind_data.get(section) or {}
            if field in table and isinstance(table[field], list) and table[field]:
                found = True
                break
            # 别名兜底
            for raw, canonical in canonical_aliases().items():
                if canonical == field and raw in table and isinstance(table[raw], list) and table[raw]:
                    found = True
                    break
            if found:
                break
        if found:
            present += 1
        else:
            missing.append(field)
    return present / len(REQUIRED_WIND_FIELDS), missing


def has_3y_range(wind_data: Optional[Dict[str, Any]]) -> bool:
    """检查 Wind 数据是否覆盖 3 年（_year_labels 或任一系列长度≥3）"""
    if not wind_data:
        return False
    labels = (wind_data.get("_year_labels") or {}).get("财年")
    if labels and len(labels) >= 3:
        return True
    for section in WIND_SECTIONS:
        table = wind_data.get(section) or {}
        for field, values in table.items():
            if isinstance(values, list) and len(values) >= 3:
                return True
    return False


def get_latest_wind_value(wind_data: Optional[Dict[str, Any]], canonical: str) -> Optional[float]:
    """获取某 canonical 指标的最新财年值"""
    if not wind_data:
        return None
    for section in WIND_SECTIONS:
        table = wind_data.get(section) or {}
        if canonical in table and isinstance(table[canonical], list) and table[canonical]:
            try:
                return float(table[canonical][-1])
            except (TypeError, ValueError):
                return None
        for raw, c in canonical_aliases().items():
            if c == canonical and raw in table and isinstance(table[raw], list) and table[raw]:
                try:
                    return float(table[raw][-1])
                except (TypeError, ValueError):
                    return None
    return None


def industry_for(company_name: str) -> str:
    """从公司名推导行业（替代硬编码'新能源汽车'默认）"""
    name = company_name or ""
    if any(k in name for k in ("小鹏", "蔚来", "理想", "比亚迪")):
        return "新能源汽车"
    if any(k in name for k in ("腾讯", "阿里", "百度", "字节")):
        return "科技"
    if any(k in name for k in ("美团", "京东", "拼多多", "淘宝")):
        return "消费"
    if any(k in name for k in ("阅文", "中文在线", "掌阅", "晋江")):
        return "数字内容"
    if any(k in name for k in ("招行", "工行", "建行", "平安")):
        return "金融"
    return "综合"


def extract_rating_from_chapters(chapters: Dict[int, str]) -> str:
    """从章节中提取投资评级（买入/增持/中性/减持/卖出/推荐/回避）"""
    import re
    for ch_num, content in chapters.items():
        for pattern in [
            r"评级[：:]\s*(买入|增持|中性|减持|卖出|推荐|回避)",
            r"(买入|增持|中性|减持|卖出|推荐|回避)\s*评级",
            r"投资评级[：:]\s*(买入|增持|中性|减持|卖出|推荐|回避)",
        ]:
            m = re.search(pattern, content)
            if m:
                r = m.group(1)
                if r == "推荐":
                    return "买入"
                if r == "回避":
                    return "减持"
                return r
    return ""
