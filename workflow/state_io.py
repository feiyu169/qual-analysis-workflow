"""HGF 状态文件原子写入（V3.3-R1，架构评审修复 C）。

背景：此前 .hgf/ 下所有 JSON/JSONL 文件都是裸 open() 覆写/追加——
`failure_log.update_failure` 甚至"先删文件再逐条重写"，进程在删除后、
重写完成前崩溃会**丢失全部失败记录**（而失败记录恰恰是崩溃时最需要
保留的数据）。架构专家评审（8 轨迹共识）定为中等-高风险缺陷。

本模块提供：
- atomic_write_text(path, text)：写临时文件 → os.replace 原子替换
- atomic_write_json(path, data)：JSON 序列化 + 原子替换
- atomic_append_jsonl(path, record)：JSONL 追加（单次 write + flush，
  内容含换行保证行完整；跨进程追加在单次 write 下原子）
"""

import json
import os
import tempfile


def atomic_write_text(path: str, text: str) -> None:
    """原子写文本：写临时文件 → os.replace（POSIX/Windows 均原子）。"""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_json(path: str, data: dict) -> None:
    """原子写 JSON 文档（indent=2，ensure_ascii=False）。"""
    text = json.dumps(data, ensure_ascii=False, indent=2)
    atomic_write_text(path, text)


def atomic_append_jsonl(path: str, record: dict) -> None:
    """JSONL 追加一条（信封或裸记录由调用方决定）。

    V3.3.1（复审共识 D：并发声明诚实化）：
    - **单进程内安全**：同一进程内多次追加不会交错（open("a") 每次新打开
      文件描述符 + 单次 write，对普通文件由内核保证 seek+write 原子）；
    - **跨进程并发不保证**：POSIX PIPE_BUF 原子性仅对 pipe/FIFO 有效，
      不适用于普通文件；Windows 无类似保证。HGF 当前设计为单进程使用
      （CLI/bridge/mcp 各自独占 .hgf/），多进程并发追加需外部文件锁；
    - 写入后 flush + fsync（与 atomic_write_text 持久化语义一致，防断电丢最后一条）。
    """
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
