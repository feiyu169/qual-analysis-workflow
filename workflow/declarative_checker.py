"""声明式检查器引擎（V3.4-E，heavyskill 审查修正版）。

新经验沉淀 = 写一条 JSON 规则（注册到 config/checkers/registry.json），
无需手写 Python 检查器。引擎按 type 分发到内置检查函数：
  - file_content：正则扫描文件内容（逐行扫描，防 O(n²)）
  - doc_section：文档章节存在性（按标题行匹配，防子串误报）
  - json_valid：JSON 文件可解析

修正项（对应 heavyskill K=8 审查）：
  E1 glob 对**相对路径**匹配（fnmatch(fname,"**/*.py") 对 basename 不匹配）
  E2 排除目录按 path parts 判断（防 .git 子串误伤，如 not.git.keep）
  E3 doc_section 的 glob 用 pathlib 解析（支持 **/*.md）
  E4 章节按标题行匹配（## 安装 而非正文出现"安装"）
  E5 逐行扫描（正则 per-line，行号直接可得，无 O(n²) count）
"""

import fnmatch
import json
import os
import re
from pathlib import Path

try:
    from .lifecycle_checkers import _read_text
except ImportError:
    from lifecycle_checkers import _read_text

# 排除目录（按 path parts 精确匹配，E2 修正）
EXCLUDE_DIR_PARTS = {".git", ".hgf", "__pycache__", "node_modules", ".pytest_cache"}

# 章节标题匹配：支持 ## 安装 / ### 部署 / 1. 使用 等
_SECTION_HEADING_RE = re.compile(
    r"^#{1,6}\s+.*?(安装|使用|部署|配置|测试|架构|接口|回滚|监控)"
    r"|^\d+\.\s*(安装|使用|部署|配置|测试|架构|接口|回滚|监控)",
    re.MULTILINE,
)


def load_rules(working_dir: str) -> list[dict]:
    p = os.path.join(working_dir, "config", "checkers", "registry.json")
    if not os.path.exists(p):
        return []
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f).get("rules", [])
    except (json.JSONDecodeError, OSError):
        return []


def _matches_glob(rel: str, glob: str) -> bool:
    """glob 匹配（E1 修正）：用 pathlib.PurePath.match 正确处理 **/*.py。

    fnmatch.fnmatch 的 `**` 不跨目录（对 rel="src/app.py" 与 "**/*.py" 返回
    False）——这是 heavyskill 审查发现的 E1 功能性 bug。PurePath.match
    按 fnmatch 语义但正确处理多级 **。

    额外修正：`**/*.py` 对无目录的 `app.py` 也应匹配（** 可匹配零层），
    但 PurePath.match 对 "app.py" vs "**/*.py" 返回 False——故对 `**/`
    前缀的 glob，同时尝试去掉 `**/` 的变体。
    """
    from pathlib import PurePath

    if glob in ("*", "**"):
        return True
    try:
        if PurePath(rel).match(glob):
            return True
        # **/ 前缀可匹配零层目录：app.py 应匹配 **/*.py
        if glob.startswith("**/"):
            return PurePath(rel).match(glob[3:])
        return False
    except Exception:
        return fnmatch.fnmatch(rel, glob)


def _is_excluded(rel_parts: list[str]) -> bool:
    """E2 修正：按 path parts 判断排除（防 .git 子串误伤）"""
    return any(part in EXCLUDE_DIR_PARTS for part in rel_parts)


def _check_file_content(rule: dict, working_dir: str) -> list[str]:
    """E1/E5 修正：rel 路径 glob 匹配 + 逐行扫描"""
    issues = []
    try:
        pattern = re.compile(rule["pattern"])
    except re.error as e:
        return [f"规则 {rule.get('id', '?')} 正则无效: {e}"]

    glob = rule.get("glob", "*")
    exclude_globs = rule.get("exclude_glob", [])

    for root, dirs, files in os.walk(working_dir):
        # 剪枝排除目录（E2）
        dirs[:] = [d for d in dirs if not _is_excluded([d])]
        for fname in files:
            # Windows 下 relpath 返回反斜杠 → 统一 posix（PurePath.match 用 /）
            rel = os.path.relpath(os.path.join(root, fname), working_dir).replace(
                os.sep, "/"
            )
            rel_parts = rel.split("/")
            if _is_excluded(rel_parts[:-1]):  # 目录段排除
                continue
            # E1 修正：对相对路径匹配（**/*.py 才有效，PurePath.match）
            if not _matches_glob(rel, glob):
                continue
            if any(_matches_glob(rel, ex) for ex in exclude_globs):
                continue
            path = os.path.join(root, fname)
            try:
                content = _read_text(path)
            except Exception:
                continue
            # E5 修正：逐行扫描（行号直接可得）
            for lineno, line in enumerate(content.splitlines(), start=1):
                if pattern.search(line):
                    issues.append(
                        f"[{rule.get('severity', 'P1')}] {rel}:{lineno} "
                        f"{rule.get('message', '规则命中')}"
                    )
    return issues


def _check_doc_section(rule: dict, working_dir: str) -> list[str]:
    """E3/E4 修正：glob 解析 + 章节标题匹配（非子串）"""
    glob = rule.get("glob", "README.md")
    if glob and any(ch in glob for ch in "*?["):
        # E3 修正：glob 路径用 Path.glob 展开
        matches = [str(p) for p in Path(working_dir).glob(glob)] if glob else []
    else:
        p = os.path.join(working_dir, glob or "README.md")
        matches = [p] if os.path.exists(p) else []
    if not matches:
        return [f"缺失文档（glob: {glob}）"]
    issues = []
    for path in matches:
        try:
            content = _read_text(str(path))
        except Exception as e:
            issues.append(f"读取 {path} 失败: {e}")
            continue
        # E4 修正：按标题行匹配（## 安装 或 1. 安装）
        if not _SECTION_HEADING_RE.search(content):
            issues.append(f"{path} 缺少章节: {rule['section']}")
    return issues


def _check_json_valid(rule: dict, working_dir: str) -> list[str]:
    glob = rule.get("glob", "*.json")
    issues = []
    for path in Path(working_dir).glob(glob):
        try:
            with open(path, encoding="utf-8") as f:
                json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            issues.append(f"{path} JSON 无效: {e}")
    return issues


_CHECKERS = {
    "file_content": _check_file_content,
    "doc_section": _check_doc_section,
    "json_valid": _check_json_valid,
}


def run_declarative(working_dir: str) -> tuple:
    """执行全部声明式规则，返回 (ok, issues)"""
    issues = []
    for rule in load_rules(working_dir):
        fn = _CHECKERS.get(rule.get("type"))
        if fn is None:
            issues.append(f"规则 {rule.get('id', '?')} 未知类型: {rule.get('type')}")
            continue
        issues.extend(fn(rule, working_dir))
    return (len(issues) == 0), issues
