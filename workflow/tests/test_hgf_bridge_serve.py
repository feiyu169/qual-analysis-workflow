"""hgf_bridge --serve 长驻模式测试（V3.2.10）。

验证 stdio JSON-RPC 协议：
- 单条命令返回 ok:true + result；
- 未知命令返回 ok:false 但不退出进程（后续请求仍可处理）；
- 连续多命令复用同一进程；
- 非法 JSON 行返回带 id:null 的错误响应且不退出。
"""

import json
import os
import subprocess
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_BRIDGE = os.path.join(os.path.dirname(_HERE), "hgf_bridge.py")


@pytest.fixture
def bridge():
    """spawn --serve 长驻进程，返回 (send_line, read_line, close) 工具"""
    proc = subprocess.Popen(
        [sys.executable, _BRIDGE, "--serve"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,  # 行缓冲
    )
    out_lines = []

    def _pump_until(predicate, timeout=15.0):
        """读取 stdout 行直到 predicate 满足（按行比对，因为响应是一行 JSON）"""
        import time

        deadline = time.time() + timeout
        while time.time() < deadline:
            line = proc.stdout.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            out_lines.append(line)
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if predicate(obj):
                return obj
        raise AssertionError(f"未在 {timeout}s 内等到预期响应；已收: {out_lines[-5:]}")

    def send(req):
        proc.stdin.write(json.dumps(req) + "\n")
        proc.stdin.flush()

    def read_response(rid):
        return _pump_until(lambda obj: obj.get("id") == rid)

    def close():
        proc.stdin.close()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    yield send, read_response, close
    close()


def test_serve_returns_result(bridge):
    send, read_response, _ = bridge
    send(
        {
            "id": 1,
            "command": "classify_task",
            "args": {"description": "add auth module", "files": ["a.py"]},
        }
    )
    resp = read_response(1)
    assert resp["ok"] is True
    assert resp["id"] == 1
    # V3.4-B：新增轻量等级 L0_LITE/L1_LITE
    assert resp["result"]["level"] in (
        "L0",
        "L0_LITE",
        "L1",
        "L1_LITE",
        "L2",
        "L3",
        "L3_LITE",
    )
    assert resp["result"]["type"] == "CODE"


def test_serve_unknown_command_keeps_process_alive(bridge):
    send, read_response, _ = bridge
    send({"id": 7, "command": "no_such_command", "args": {}})
    resp = read_response(7)
    assert resp["ok"] is False
    assert "未知命令" in resp["error"]
    # 进程仍存活：后续请求正常响应
    send({"id": 8, "command": "assess_risk", "args": {"affected_areas": ["auth"]}})
    resp2 = read_response(8)
    assert resp2["ok"] is True
    assert resp2["result"]["risk"] in ("low", "medium", "high")


def test_serve_multiple_commands_same_process(bridge):
    send, read_response, _ = bridge
    for rid, cmd, args in [
        (10, "classify_task", {"description": "t", "files": ["x.py"]}),
        (11, "assess_risk", {"affected_areas": ["payment"]}),
        (12, "lifecycle", {"action": "status", "working_dir": "."}),
        (13, "history", {"working_dir": "."}),
    ]:
        send({"id": rid, "command": cmd, "args": args})
        resp = read_response(rid)
        assert resp["ok"] is True, (cmd, resp)
        assert resp["id"] == rid


def test_serve_bad_json_line_does_not_crash(bridge):
    """非法 JSON 行返回 id:null 错误且进程不退出（后续请求正常）"""
    p = subprocess.Popen(
        [sys.executable, _BRIDGE, "--serve"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        p.stdin.write("not json at all\n")
        p.stdin.flush()
        line = p.stdout.readline().strip()
        obj = json.loads(line)
        assert obj["ok"] is False
        assert obj["id"] is None
        assert "JSON" in obj["error"]
        # 进程未退出：还能处理后续
        p.stdin.write(
            json.dumps(
                {
                    "id": 30,
                    "command": "classify_task",
                    "args": {"description": "x", "files": ["f.py"]},
                }
            )
            + "\n"
        )
        p.stdin.flush()
        line2 = p.stdout.readline().strip()
        obj2 = json.loads(line2)
        assert obj2["ok"] is True
        assert obj2["id"] == 30
    finally:
        p.stdin.close()
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()


def test_serve_utf8_chinese_payload(bridge):
    """中文 payload 经 UTF-8 往返不损坏（V3.2.10 修复）：中文关键词被正确映射"""
    send, read_response, _ = bridge
    send(
        {
            "id": 40,
            "command": "assess_risk",
            "args": {"affected_areas": ["支付", "认证"]},
        }
    )
    resp = read_response(40)
    assert resp["ok"] is True
    # 中文关键词应被映射为英文因子：支付→payment、认证→authentication
    factors = resp["result"].get("matched_factors", [])
    assert "payment" in factors
    assert "authentication" in factors
