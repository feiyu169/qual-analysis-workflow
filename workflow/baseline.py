"""门禁基线存档（V3.2.0）：标准可复现的机械保证。

每次执行门禁后，把"当前标准"（配置哈希、工具版本、门禁清单）写入
`.hgf/baseline.json`；下次执行检测与上次基线的漂移（配置变更/工具升级），
并告警——让"同一标准复跑"不再只靠自觉。
"""

import hashlib
import json
import os
from datetime import datetime


def snapshot(config_path: str, plugins: dict) -> dict:
    """采集当前标准快照"""
    config_hash = None
    try:
        with open(config_path, "rb") as f:
            config_hash = hashlib.sha256(f.read()).hexdigest()[:12]
    except OSError:
        pass

    tool_versions = {}
    for name, plugin in plugins.items():
        try:
            tool_versions[name] = plugin.get_version()
        except Exception:
            tool_versions[name] = None

    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "config_path": config_path,
        "config_sha256": config_hash,
        "tool_versions": tool_versions,
        "plugins": sorted(plugins.keys()),
    }


def path(working_dir: str) -> str:
    return os.path.join(working_dir, ".hgf", "baseline.json")


def save(working_dir: str, snap: dict) -> None:
    try:
        from . import state_io
    except ImportError:
        import state_io
    doc = {"schema_version": "hgf.v1", "writer": "baseline", **snap}
    state_io.atomic_write_json(path(working_dir), doc)


def load(working_dir: str) -> dict | None:
    p = path(working_dir)
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        # V3.3.2（自审查 S2 修复）：状态文件损坏时不得崩溃（实测旧版本遗留的
        # baseline.json 末尾多一个 }，导致 --canary 抛未捕获 JSONDecodeError）。
        # 返回 None + 告警 → 调用方按"无基线"处理（首次执行/重建基线），
        # 而非让工具链崩溃。
        import logging

        logging.getLogger("baseline").warning(
            "baseline_load_failed_using_default: %s (%s: %s); 将按无基线处理并重建",
            p,
            type(e).__name__,
            e,
        )
        return None


def drift(previous: dict | None, current: dict) -> list[str]:
    """比较两次快照，返回变化列表（空 = 无漂移）"""
    changes = []
    if previous is None:
        return ["首次执行，已建立基线"]

    if (
        previous.get("config_sha256")
        and current.get("config_sha256")
        and previous["config_sha256"] != current["config_sha256"]
    ):
        changes.append(
            f"门禁配置变更: {previous['config_sha256']} → {current['config_sha256']}"
        )

    old_tools = previous.get("tool_versions", {})
    new_tools = current.get("tool_versions", {})
    for tool in sorted(set(old_tools) | set(new_tools)):
        if old_tools.get(tool) != new_tools.get(tool):
            changes.append(
                f"工具版本变更: {tool} {old_tools.get(tool)} → {new_tools.get(tool)}"
            )
    return changes


def update(working_dir: str, snap: dict) -> list[str]:
    """比较、存档、返回漂移列表"""
    prev = load(working_dir)
    changes = drift(prev, snap)
    save(working_dir, snap)
    return changes
