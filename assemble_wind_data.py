#!/usr/bin/env python3
"""组装 wind_data：解析已保存的 Wind CLI 响应 → workflow 期望的 canonical 结构。

输入: .pip-tmp/wind-fin.json (财务三表) + wind-fin2.json (负债/权益/资本开支) + wind-quote.json (行情)
输出: .pip-tmp/wind_data.json
"""
import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
TMP = os.path.join(ROOT, ".pip-tmp")


def extract_inner(path):
    with open(path, encoding="utf-8") as f:
        outer = json.load(f)
    return json.loads(outer["content"][0]["text"])


def collect(fin_files):
    """收集所有记录，返回 (records, shares)"""
    records = []
    shares = None
    for path in fin_files:
        fin = extract_inner(path)["data"]
        for ds in fin["data"]:
            cols = [c["name"] for c in ds["columns"]]
            for row in ds["rows"]:
                records.append(dict(zip(cols, row)))
    return records


def main():
    records = collect([os.path.join(TMP, "wind-fin.json"), os.path.join(TMP, "wind-fin2.json")])
    quote = extract_inner(os.path.join(TMP, "wind-quote.json"))["data"]

    income, balance, cashflow = {}, {}, {}
    shares = None

    # Wind 列名 → canonical 键
    FIELD_MAP = {
        "近3年每年营业总收入": ("income", "营业收入"),
        "近3年每年营业利润": ("income", "营业利润"),
        "近3年每年归母净利润": ("income", "归母净利润"),
        "近3年每年净利润": ("income", "净利润"),
        "近3年每年总资产": ("balance", "总资产"),
        "近3年每年归母净资产": ("balance", "归母净资产"),
        "最近3年所有者权益合计": ("balance", "年所有者权益合计"),
        "最近3年负债合计": ("balance", "年负债合计"),
        "近3年每年经营活动产生的现金流量净额": ("cashflow", "经营活动现金流量净额"),
        "最近3年购建固定资产无形资产和其他长期资产支付的现金": ("cashflow", "购建固定资产、无形资产和其他长期资产支付的现金"),
    }
    for rec in records:
        for col, v in rec.items():
            if v is None or col in ("Wind代码", "证券简称", "日期", "记账本位币", "记账本位币_2"):
                continue
            if col in FIELD_MAP:
                section, key = FIELD_MAP[col]
                target = {"income": income, "balance": balance, "cashflow": cashflow}[section]
                target.setdefault(key, []).append(v)
            if col == "近3年每年总股本":
                shares = v
            if col == "总股本" and not isinstance(v, list):
                shares = v

    # 净利润缺失时用归母净利润近似（写日志说明）
    if "净利润" not in income and "归母净利润" in income:
        income["净利润"] = income["归母净利润"]

    # 最新快照（估值）
    valuation = {}
    for rec in records:
        if rec.get("最新市盈率TTM") is not None:
            valuation["pe_ttm"] = rec["最新市盈率TTM"]
            valuation["pb"] = rec.get("最新市净率")
            if rec.get("总股本"):
                shares = rec["总股本"]
            if rec.get("营业总收入") is not None:
                income["营业收入_latest"] = rec["营业总收入"]
            if rec.get("归属母公司股东的净利润") is not None:
                income["归母净利润_latest"] = rec["归属母公司股东的净利润"]

    # 行情
    qcols = [c["name"] for c in quote["columns"]]
    q = dict(zip(qcols, quote["rows"][0]))
    quote_dict = {
        "中文简称": q.get("中文简称"),
        "最新价": float(q.get("最新成交价", 0) or 0),
        "涨跌幅": float(q.get("涨跌幅", 0) or 0),
        "总市值": float(q.get("总市值1", 0) or 0),
    }
    if valuation.get("pe_ttm") is None:
        valuation["pe_ttm"] = float(q.get("市盈率(TTM)", 0) or 0)
        valuation["pb"] = float(q.get("市净率(LF)", 0) or 0)
    if q.get("总市值1"):
        valuation["总市值"] = round(float(q["总市值1"]) / 1e8, 2)  # 元 → 亿元
    if q.get("最新成交价"):
        valuation["最新价"] = float(q["最新成交价"])

    wind_data = {
        "quote": quote_dict,
        "valuation": valuation,
        "income": income,
        "balance": balance,
        "cashflow": cashflow,
        "_year_labels": {"财年": [2023, 2024, 2025]},
    }

    out = {
        "wind_data": wind_data,
        "shares": (float(shares) / 1e8) if shares else None,
        "company_name": q.get("中文简称"),
    }
    with open(os.path.join(TMP, "wind_data.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(json.dumps({
        "shares_亿股": out["shares"],
        "income": {k: str(v)[:80] for k, v in income.items()},
        "balance": {k: str(v)[:80] for k, v in balance.items()},
        "cashflow": {k: str(v)[:80] for k, v in cashflow.items()},
        "valuation": valuation,
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
