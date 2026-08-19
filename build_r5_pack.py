#!/usr/bin/env python3
"""从 R5 报告提取各章结论要点 + 关键财务表述，供复审。"""
import re
import os

root = os.path.dirname(os.path.abspath(__file__))
rep_path = os.path.join(root, "output", "yuewen-00772", "00772.HK_analysis.md")
out_path = os.path.join(root, ".pip-tmp", "r5-review-pack.txt")

rep = open(rep_path, encoding="utf-8").read()
parts = re.split(r"(?=^# )", rep, flags=re.M)
out = []
for p in parts:
    m = re.match(r"^# (.+)\n", p)
    title = m.group(1).strip() if m else "头部"
    cm = re.search(r"## 结论要点\n(.*?)(?=\n## |\n# )", p, flags=re.S)
    body = (cm.group(1) if cm else p[:500])
    out.append("【" + title + "】\n" + body.strip()[:1500])

# 关键财务表述
key_lines = []
for kw in ["归母净利润", "净利润", "经营现金流", "总收入", "营业收入", "资产负债率"]:
    for mm in re.finditer(r"[^。\n]{0,30}" + kw + r"[^。\n]{0,60}", rep):
        key_lines.append(mm.group(0).strip()[:110])
        if len(key_lines) > 12:
            break
    if len(key_lines) > 12:
        break

text = "\n\n".join(out) + "\n\n## 报告中的关键财务表述抽样\n" + "\n".join(key_lines[:15])
with open(out_path, "w", encoding="utf-8") as f:
    f.write(text)
print("blocks:", len(out), "chars:", len(text))
