#!/usr/bin/env python3
"""重建复审包：从最新报告提取各章结论要点。"""
import re
import os
import sys

root = os.path.dirname(os.path.abspath(__file__))
rep_path = os.path.join(root, "output", "yuewen-00772", "00772.HK_analysis.md")
out_path = os.path.join(root, ".pip-tmp", "review-pack3.txt")

rep = open(rep_path, encoding="utf-8").read()
parts = re.split(r"(?=^# )", rep, flags=re.M)
out = []
for p in parts:
    title_m = re.match(r"^# (.+)\n", p)
    title = title_m.group(1).strip() if title_m else "头部"
    cm = re.search(r"## 结论要点\n(.*?)(?=\n## |\n# )", p, flags=re.S)
    body = (cm.group(1) if cm else p[:600])
    out.append("【" + title + "】\n" + body.strip()[:1600])
pack = "\n\n".join(out)
with open(out_path, "w", encoding="utf-8") as f:
    f.write(pack)
print("blocks:", len(out), "chars:", len(pack))
