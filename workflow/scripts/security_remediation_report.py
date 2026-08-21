"""从 safety 扫描结果生成完整修复清单（V3.2 安全治理）。

用法: python scripts/security_remediation_report.py <safety-json> <输出.md>
"""

import json
import sys
from collections import defaultdict


def extract_json(text: str) -> dict:
    """safety 输出可能混入 warning 行：取首个 { 到最后一个 }"""
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("未找到 JSON")
    return json.loads(text[start : end + 1])


def severity_level(vuln: dict) -> str:
    sev = vuln.get("severity") or {}
    cvss = sev.get("cvssv3") or {}
    return cvss.get("base_severity") or sev.get("source") or "UNKNOWN"


def main() -> None:
    if len(sys.argv) < 3:
        print("用法: python security_remediation_report.py <safety-json> <输出.md>")
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        data = extract_json(f.read())

    vulns = data.get("vulnerabilities", [])
    remediations = data.get("remediations", {})

    # 按包聚合漏洞
    by_pkg: dict[str, list[dict]] = defaultdict(list)
    for v in vulns:
        by_pkg[v["package_name"]].append(v)

    # 每个包推荐的修复版本（取 requirements 中最常见的 recommended_version）
    pkg_recommend: dict[str, set] = defaultdict(set)
    for pkg, spec in remediations.items():
        for req in (spec.get("requirements") or {}).values():
            if req.get("recommended_version"):
                pkg_recommend[pkg].add(req["recommended_version"])
            closest = (req.get("closest_secure_version") or {}).get("upper")
            if closest:
                pkg_recommend[pkg].add(closest)

    lines = []
    lines.append("# Python 3.14 依赖安全修复清单")
    lines.append("")
    lines.append("> 来源：`safety check --json`（SAFETY_API_KEY 在线扫描）")
    lines.append(
        f"> 扫描时间：{data.get('metadata', {}).get('scan_timestamp', 'N/A') if isinstance(data.get('metadata'), dict) else 'N/A'}"
    )
    lines.append(f"> 漏洞总数：**{len(vulns)}**，受影响包：**{len(by_pkg)}**")
    lines.append("")
    lines.append("## 逐包修复建议")
    lines.append("")
    lines.append("| 包 | 当前版本 | 漏洞数 | 高危 | 中危 | 建议修复版本 | 说明 |")
    lines.append("|----|----------|--------|------|------|--------------|------|")

    for pkg in sorted(by_pkg, key=lambda p: -len(by_pkg[p])):
        pvulns = by_pkg[pkg]
        versions = sorted(
            {v.get("analyzed_version") for v in pvulns if v.get("analyzed_version")}
        )
        high = sum(1 for v in pvulns if severity_level(v) == "HIGH")
        medium = sum(1 for v in pvulns if severity_level(v) == "MEDIUM")
        recs = sorted(pkg_recommend.get(pkg, set()))
        rec_str = ", ".join(recs) if recs else "无官方修复版本"
        cves = "; ".join(sorted({v["CVE"] for v in pvulns if v.get("CVE")})[:3])
        lines.append(
            f"| {pkg} | {', '.join(versions)} | {len(pvulns)} | {high} | {medium} "
            f"| {rec_str} | {cves} |"
        )

    lines.append("")
    lines.append("## 高危漏洞明细（HIGH）")
    lines.append("")
    lines.append("| 漏洞ID | 包 | CVE | 当前版本 | 修复版本 | 说明 |")
    lines.append("|--------|----|-----|----------|----------|------|")
    for v in vulns:
        if severity_level(v) == "HIGH":
            fixed = ", ".join(v.get("fixed_versions") or []) or "无"
            adv = (v.get("advisory") or "").replace("|", "/")[:100]
            lines.append(
                f"| {v.get('vulnerability_id')} | {v['package_name']} "
                f"| {v.get('CVE') or '-'} | {v.get('analyzed_version')} "
                f"| {fixed} | {adv} |"
            )

    report = "\n".join(lines) + "\n"
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        f.write(report)
    print(report[:3000])


if __name__ == "__main__":
    main()
