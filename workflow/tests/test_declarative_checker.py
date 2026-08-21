"""声明式检查器测试（V3.4-E，heavyskill 审查修正版）。

重点验证审查发现的 E1 glob bug 已修复（**/*.py 对 rel 匹配生效）。
"""

import json
import os

import declarative_checker
from declarative_checker import run_declarative


def _mk_wd(tmp_path, files: dict) -> str:
    wd = str(tmp_path)
    for rel, content in files.items():
        path = os.path.join(wd, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    return wd


def test_file_content_matches_nested_py(tmp_path):
    """E1 修正：**/*.py 必须匹配嵌套目录（此前 fnmatch(fname) 对 basename 失效）"""
    wd = _mk_wd(
        tmp_path,
        {
            "src/app.py": "api_key = 'abcdefghijklmnopqrst'\n",
            "src/util.py": "x = 1\n",
        },
    )
    rule = {
        "id": "t1",
        "type": "file_content",
        "pattern": r"api_key\s*=\s*['\"][A-Za-z0-9]{16,}",
        "glob": "**/*.py",
        "severity": "P0",
        "message": "hardcoded",
    }
    issues = declarative_checker._check_file_content(rule, wd)
    assert len(issues) == 1
    assert "src/app.py" in issues[0]


def test_exclude_glob_skips_tests(tmp_path):
    wd = _mk_wd(
        tmp_path,
        {
            "app.py": "password = 'abcdefghijklmnopqrst'\n",
            "tests/test_app.py": "password = 'abcdefghijklmnopqrst'\n",
        },
    )
    rule = {
        "id": "t2",
        "type": "file_content",
        "pattern": r"password\s*=\s*['\"][A-Za-z0-9]{16,}",
        "glob": "**/*.py",
        "exclude_glob": ["tests/**"],
        "severity": "P0",
        "message": "hardcoded",
    }
    issues = declarative_checker._check_file_content(rule, wd)
    assert len(issues) == 1
    assert "app.py" in issues[0]


def test_exclude_dir_by_parts_not_substring(tmp_path):
    """E2 修正：not.git.keep 目录不应被排除（子串匹配 bug 修复）"""
    wd = _mk_wd(
        tmp_path,
        {
            "not.git.keep/file.py": "secret = 'abcdefghijklmnopqrst'\n",
            ".git/config.py": "secret = 'abcdefghijklmnopqrst'\n",  # 应被排除
        },
    )
    rule = {
        "id": "t3",
        "type": "file_content",
        "pattern": r"secret\s*=\s*['\"][A-Za-z0-9]{16,}",
        "glob": "**/*.py",
        "severity": "P0",
        "message": "hardcoded",
    }
    issues = declarative_checker._check_file_content(rule, wd)
    assert len(issues) == 1
    assert "not.git.keep/file.py" in issues[0]


def test_doc_section_heading_match(tmp_path):
    """E4 修正：章节按标题行匹配（正文出现"安装"不算通过）"""
    wd = _mk_wd(
        tmp_path,
        {
            "README.md": "这个项目讨论安装流程的细节，但正文没有标题。\n",
        },
    )
    rule = {
        "id": "t4",
        "type": "doc_section",
        "section": "安装",
        "glob": "README.md",
        "severity": "P1",
        "message": "缺安装章节",
    }
    issues = declarative_checker._check_doc_section(rule, wd)
    assert len(issues) == 1  # 无标题 → FAIL
    # 有标题 → PASS
    wd2 = _mk_wd(tmp_path, {"README.md": "# 项目\n\n## 安装\n\npip install x\n"})
    issues2 = declarative_checker._check_doc_section(rule, wd2)
    assert issues2 == []


def test_doc_section_glob_supports_recursive(tmp_path):
    """E3 修正：doc_section 的 glob 支持 **/*.md"""
    wd = _mk_wd(
        tmp_path,
        {
            "docs/guide.md": "# Guide\n\n## 使用\n\nusage\n",
        },
    )
    rule = {
        "id": "t5",
        "type": "doc_section",
        "section": "使用",
        "glob": "**/*.md",
        "severity": "P1",
        "message": "缺使用章节",
    }
    issues = declarative_checker._check_doc_section(rule, wd)
    assert issues == []


def test_json_valid_checker(tmp_path):
    wd = _mk_wd(tmp_path, {"config/checkers/registry.json": '{"a": 1}\n'})
    rule = {
        "id": "t6",
        "type": "json_valid",
        "glob": "config/checkers/registry.json",
        "severity": "P1",
        "message": "json invalid",
    }
    assert declarative_checker._check_json_valid(rule, wd) == []
    # 损坏
    wd2 = _mk_wd(tmp_path, {"config/checkers/registry.json": '{"a": 1\n'})
    assert len(declarative_checker._check_json_valid(rule, wd2)) == 1


def test_run_declarative_with_registry(tmp_path):
    """真实 registry 规则加载执行"""
    wd = _mk_wd(
        tmp_path,
        {
            "config/checkers/registry.json": json.dumps(
                {
                    "rules": [
                        {
                            "id": "no-secret",
                            "type": "file_content",
                            "pattern": r"password\s*=\s*['\"][A-Za-z0-9]{16,}",
                            "glob": "**/*.py",
                            "severity": "P0",
                            "message": "hardcoded",
                        },
                    ]
                }
            ),
            "app.py": "password = 'abcdefghijklmnopqrst'\n",
        },
    )
    ok, issues = run_declarative(wd)
    assert ok is False
    assert any("hardcoded" in i for i in issues)
