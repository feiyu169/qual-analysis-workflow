"""
canonical.py — 数据契约单源真源（方案 A：解决 S1/S2 字段映射 4 套并存 / 检查器键不匹配）

三刻度之一：本模块是**字段映射的唯一真源**。所有层（assemble_wind_data 产出、data_context 契约、
fact_checker/cross_validate/data_repair/DataAnchor 校验）必须通过本模块的 canonicalize() 归一，
禁止各自维护字段名副本。

用法:
    from .canonical import canonical_key, canonicalize, REQUIRED_CANONICAL_FIELDS

    data = {"年营业总收入": [...]}          # 任意历史键名
    norm = canonicalize({"income": data})   # -> {"income": {"营业收入": [...]}}
"""

# canonical 财务键（唯一真源；assemble_wind_data 已产出此形态）
CANONICAL_FIELDS = frozenset({
    # 利润表
    "营业收入", "营业利润", "归母净利润", "净利润",
    # 资产负债表
    "总资产", "归母净资产", "年负债合计", "年所有者权益合计",
    # 现金流量表
    "经营活动现金流量净额", "购建固定资产、无形资产和其他长期资产支付的现金",
})

# 三张表位置
SECTIONS = ("income", "balance", "cashflow")

# 所有历史键名 → canonical（单向；含 Wind 原始列名、data_context 映射、v3 检查器期望键）
ALIASES = {
    # ---- 营业收入 ----
    "营业收入": "营业收入", "年营业收入": "营业收入", "营业总收入": "营业收入",
    "年营业总收入": "营业收入", "近3年每年营业总收入": "营业收入",
    # ---- 营业利润 ----
    "营业利润": "营业利润", "年营业利润": "营业利润", "近3年每年营业利润": "营业利润",
    # ---- 归母净利润 ----
    "归母净利润": "归母净利润", "年归母净利润": "归母净利润", "净利润": "净利润",
    "年净利润": "归母净利润", "近3年每年归母净利润": "归母净利润",
    "年归属母公司股东的净利润": "归母净利润", "近3年每年净利润": "净利润",
    "归属母公司股东的净利润": "归母净利润",
    # ---- 总资产 ----
    "总资产": "总资产", "年资产总计": "总资产", "资产总计": "总资产",
    "近3年每年总资产": "总资产", "最近3年每年资产总计": "总资产",
    # ---- 归母净资产 ----
    "归母净资产": "归母净资产", "年归母净资产": "归母净资产",
    "近3年每年归母净资产": "归母净资产", "年归属母公司股东权益": "归母净资产",
    "归属于母公司股东权益": "归母净资产",
    # ---- 负债合计 ----
    "年负债合计": "年负债合计", "负债合计": "年负债合计",
    "近3年每年负债合计": "年负债合计", "最近3年每年负债合计": "年负债合计",
    "总负债": "年负债合计",
    # ---- 所有者权益合计 ----
    "年所有者权益合计": "年所有者权益合计", "所有者权益合计": "年所有者权益合计",
    "最近3年所有者权益合计": "年所有者权益合计", "股东权益": "年所有者权益合计",
    # ---- 经营活动现金流量净额 ----
    "经营活动现金流量净额": "经营活动现金流量净额",
    "经营活动产生的现金流量净额": "经营活动现金流量净额",
    "年经营活动现金流量净额": "经营活动现金流量净额",
    "近3年每年经营活动现金流量净额": "经营活动现金流量净额",
    "近3年每年经营活动产生的现金流量净额": "经营活动现金流量净额",
    "过去三年每年经营活动产生的现金流量净额": "经营活动现金流量净额",
    "经营活动现金净流量_TTM": "经营活动现金流量净额",
    # ---- 资本开支 ----
    "购建固定资产、无形资产和其他长期资产支付的现金": "购建固定资产、无形资产和其他长期资产支付的现金",
    "年购建固定资产无形资产和其他长期资产支付的现金": "购建固定资产、无形资产和其他长期资产支付的现金",
    "最近3年购建固定资产无形资产和其他长期资产支付的现金": "购建固定资产、无形资产和其他长期资产支付的现金",
    "购建固定资产、无形资产和其他长期资产支付的现金_TTM": "购建固定资产、无形资产和其他长期资产支付的现金",
}

# 反向索引：canonical → 该 canonical 下所有已知别名（用于检查器"给任意键找 canonical 值"）
_CANONICAL_ALIAS_GROUPS = None


def _build_alias_groups() -> dict:
    groups: dict = {}
    for alias, canonical in ALIASES.items():
        groups.setdefault(canonical, set()).add(alias)
    return groups


def alias_groups() -> dict:
    """canonical → 该 canonical 下所有已知键名（含 canonical 自身）"""
    global _CANONICAL_ALIAS_GROUPS
    if _CANONICAL_ALIAS_GROUPS is None:
        _CANONICAL_ALIAS_GROUPS = _build_alias_groups()
    return _CANONICAL_ALIAS_GROUPS


def canonical_key(key: str) -> str:
    """任意键 → canonical 键（找不到则原样返回）"""
    return ALIASES.get(key, key)


def canonicalize_table(table: dict) -> dict:
    """把一张表（income/balance/cashflow）的键全部归一到 canonical 形态

    若 canonical 键已存在则保留；否则从任意别名取值。
    多个别名指向同一 canonical 时，按 ALIASES 顺序取第一个非空。
    """
    if not table:
        return {}
    out: dict = {}
    # 1) 已存在的 canonical 键直接保留
    for k, v in table.items():
        if k in CANONICAL_FIELDS:
            out[k] = v
    # 2) 从别名补 canonical 键
    for canonical in CANONICAL_FIELDS:
        if canonical in out:
            continue
        for alias in alias_groups().get(canonical, ()):
            if alias in table and table[alias] is not None:
                out[canonical] = table[alias]
                break
    # 3) 非财务键原样保留（如 _latest 后缀、其他扩展字段）
    for k, v in table.items():
        if k not in ALIASES and k not in CANONICAL_FIELDS:
            out[k] = v
    return out


def canonicalize(wind_data: dict) -> dict:
    """整个 wind_data（含 income/balance/cashflow/_year_labels）归一为 canonical 形态"""
    if not wind_data:
        return wind_data
    out = dict(wind_data)
    for section in SECTIONS:
        if section in out and isinstance(out[section], dict):
            out[section] = canonicalize_table(out[section])
    return out


def get_series(wind_data: dict, canonical: str) -> list:
    """从 wind_data 取某 canonical 指标的 3 年序列（自动别名兜底）"""
    if not wind_data:
        return []
    for section in SECTIONS:
        table = wind_data.get(section) or {}
        if canonical in table and isinstance(table[canonical], list):
            return table[canonical]
        for alias in alias_groups().get(canonical, ()):
            if alias in table and isinstance(table[alias], list):
                return table[alias]
    return []


def latest_value(wind_data: dict, canonical: str, default=0) -> float:
    """取某 canonical 指标的最新财年值（3 年序列最后一个非空）"""
    series = get_series(wind_data, canonical)
    if not series:
        return default
    for v in reversed(series):
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return default
