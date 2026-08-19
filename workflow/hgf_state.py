"""HGF 状态目录规范（V3.2.5）：.hgf/ 下所有 JSONL 记录的统一信封。

此前 .hgf/ 下 failures/runs/baseline/lifecycle/reviews 各自为政（无 schema、
无写入者、无校验），会漂移。本模块提供：
- record(kind, ...)：以 `hgf.v1` 信封追加记录（schema/kind/writer/timestamp/payload）
- records(kind, ...)：读取（兼容旧版裸记录，自动解信封）
- ensure_state_dir(...)：创建 .hgf/ 并写入 STATE.md 注册表

单文档状态（baseline.json / lifecycle.json）在各自模块的 save 中附加
schema_version 与 writer 字段。
"""

import json
import os
from datetime import datetime

try:
    from . import state_io
except ImportError:
    import state_io

SCHEMA_VERSION = "hgf.v1"

_STATE_MD = """# HGF 状态目录注册表（schema: hgf.v1）

| 文件 | kind | 写入者 | 内容 |
|------|------|--------|------|
| `failures.jsonl` | failures | failure_log | 门禁失败记录（failure-log 门禁数据层） |
| `runs.jsonl` | runs | run_history | 每次门禁执行历史（趋势/回归） |
| `baseline.json` | baseline | baseline | 标准基线（配置哈希+工具版本） |
| `lifecycle.json` | lifecycle | lifecycle | 生命周期 DAG 状态 |
| `reviews.jsonl` | reviews | 人工/agent | 评审记录（双签名：reviewer≠verifier） |

规则：
- JSONL 每条记录 = `{{"schema": "hgf.v1", "kind": <kind>, "writer": <写入者>,
  "timestamp": <ISO>, "payload": <业务数据>}}`
- 读取必须兼容旧版裸记录（无 schema 信封），读取器自动解信封返回 payload。
"""


def record(kind: str, working_dir: str, payload: dict, writer: str = "hgf") -> dict:
    """以 hgf.v1 信封追加一条记录，返回信封。"""
    envelope = {
        "schema": SCHEMA_VERSION,
        "kind": kind,
        "writer": writer,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "payload": payload,
    }
    p = os.path.join(working_dir, ".hgf", f"{kind}.jsonl")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    state_io.atomic_append_jsonl(p, envelope)
    return envelope


def records(kind: str, working_dir: str) -> list[dict]:
    """读取 kind 的全部记录（返回 payload；旧版裸记录原样返回）。"""
    p = os.path.join(working_dir, ".hgf", f"{kind}.jsonl")
    if not os.path.exists(p):
        return []
    out = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and "schema" in obj and "payload" in obj:
                out.append(obj["payload"])
            else:
                out.append(obj)  # 旧版裸记录
    return out


def ensure_state_dir(working_dir: str) -> str:
    """创建 .hgf/ 并写入 STATE.md 注册表（幂等），返回 .hgf 路径。"""
    hgf_dir = os.path.join(working_dir, ".hgf")
    os.makedirs(hgf_dir, exist_ok=True)
    md_path = os.path.join(hgf_dir, "STATE.md")
    if not os.path.exists(md_path):
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(_STATE_MD)
    return hgf_dir
