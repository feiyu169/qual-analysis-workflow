"""
Gate 4.4: 断点恢复 (Checkpoint Manager)

管理投资分析工作流的状态持久化，支持:
- 步骤级断点恢复（Step 1-6）
- 章节级断点恢复（逐章写作+审计）
- 分析中断后从断点继续

存储位置: ./workspace/state/{ticker}/
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# --------------------------------------------------
# 默认存储路径
# --------------------------------------------------

_DEFAULT_STATE_DIR = Path.home() / ".hermes" / "workspace" / "state"


# --------------------------------------------------
# CheckpointManager 类
# --------------------------------------------------

class CheckpointManager:
    """断点恢复管理器

    管理工作流状态的持久化和恢复。
    每个 ticker 有独立的状态目录。

    存储结构:
    ./workspace/state/{ticker}/
        steps.json          — 步骤完成状态
        chapters/            — 章节内容
            {chapter_id}.md  — 章节 Markdown
        audit/               — 审计记录
            {chapter_id}.json — 审计结果
        metadata.json        — 分析元数据
    """

    def __init__(
        self,
        ticker: str,
        state_dir: Optional[Path] = None,
    ):
        """初始化

        Args:
            ticker: 股票代码
            state_dir: 状态存储根目录（默认 ./workspace/state/）
        """
        self.ticker = ticker.upper().strip()
        self._state_root = Path(state_dir) if state_dir else _DEFAULT_STATE_DIR
        self._ticker_dir = self._state_root / self.ticker
        self._chapters_dir = self._ticker_dir / "chapters"
        self._audit_dir = self._ticker_dir / "audit"
        self._steps_file = self._ticker_dir / "steps.json"
        self._metadata_file = self._ticker_dir / "metadata.json"

        # 确保目录存在
        self._chapters_dir.mkdir(parents=True, exist_ok=True)
        self._audit_dir.mkdir(parents=True, exist_ok=True)

    @property
    def ticker_dir(self) -> Path:
        """ticker 状态目录"""
        return self._ticker_dir

    # --------------------------------------------------
    # 步骤级管理
    # --------------------------------------------------

    def is_step_completed(self, ticker: str, step: str) -> bool:
        """检查步骤是否已完成

        Args:
            ticker: 股票代码（为兼容接口保留，实际使用 self.ticker）
            step: 步骤名称（如 "infer", "collect", "write", "audit", "memory"）

        Returns:
            True 如果步骤已完成
        """
        steps = self._load_steps()
        step_data = steps.get(step, {})
        return step_data.get("completed", False)

    def save_step_result(self, ticker: str, step: str, result: dict) -> None:
        """保存步骤执行结果

        Args:
            ticker: 股票代码
            step: 步骤名称
            result: 步骤结果数据
        """
        steps = self._load_steps()
        steps[step] = {
            "completed": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "result": self._serialize_result(result),
        }
        self._save_steps(steps)
        logger.info(f"步骤保存: {self.ticker}/{step}")

    def get_step_result(self, ticker: str, step: str) -> Optional[dict]:
        """获取步骤执行结果

        Args:
            ticker: 股票代码
            step: 步骤名称

        Returns:
            步骤结果数据，如果不存在返回 None
        """
        steps = self._load_steps()
        step_data = steps.get(step)
        if step_data and step_data.get("completed"):
            return step_data.get("result")
        return None

    def get_all_steps(self) -> dict[str, dict]:
        """获取所有步骤状态

        Returns:
            {step_name: {completed, timestamp, result}}
        """
        return self._load_steps()

    def reset_step(self, step: str) -> None:
        """重置步骤状态（标记为未完成）

        Args:
            step: 步骤名称
        """
        steps = self._load_steps()
        if step in steps:
            steps[step]["completed"] = False
            steps[step]["reset_at"] = datetime.now(timezone.utc).isoformat()
            self._save_steps(steps)
            logger.info(f"步骤重置: {self.ticker}/{step}")

    # --------------------------------------------------
    # 章节级管理
    # --------------------------------------------------

    def is_chapter_completed(self, ticker: str, chapter_id: str) -> bool:
        """检查章节是否已完成（已写入）

        Args:
            ticker: 股票代码
            chapter_id: 章节标识

        Returns:
            True 如果章节内容文件存在且非空
        """
        chapter_file = self._chapters_dir / f"{chapter_id}.md"
        if not chapter_file.exists():
            return False
        content = chapter_file.read_text(encoding="utf-8")
        return len(content.strip()) > 0

    def save_chapter(self, ticker: str, chapter_id: str, content: str) -> None:
        """保存章节内容

        Args:
            ticker: 股票代码
            chapter_id: 章节标识
            content: 章节 Markdown 内容
        """
        chapter_file = self._chapters_dir / f"{chapter_id}.md"
        chapter_file.write_text(content, encoding="utf-8")
        logger.info(
            f"章节保存: {self.ticker}/{chapter_id} "
            f"({len(content)} 字符)"
        )

    def get_chapter(self, chapter_id: str) -> Optional[str]:
        """获取章节内容

        Args:
            chapter_id: 章节标识

        Returns:
            章节 Markdown 内容，如果不存在返回 None
        """
        chapter_file = self._chapters_dir / f"{chapter_id}.md"
        if chapter_file.exists():
            return chapter_file.read_text(encoding="utf-8")
        return None

    def list_chapters(self) -> list[str]:
        """列出所有已保存的章节

        Returns:
            章节 ID 列表
        """
        return sorted(
            f.stem for f in self._chapters_dir.glob("*.md") if f.is_file()
        )

    # --------------------------------------------------
    # 审计管理
    # --------------------------------------------------

    def mark_chapter_audited(
        self,
        ticker: str,
        chapter_id: str,
        audit_result: Optional[dict] = None,
    ) -> None:
        """标记章节已审计

        Args:
            ticker: 股票代码
            chapter_id: 章节标识
            audit_result: 审计结果数据（可选）
        """
        audit_file = self._audit_dir / f"{chapter_id}.json"
        record = {
            "chapter_id": chapter_id,
            "audited": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if audit_result:
            record["audit_result"] = self._serialize_result(audit_result)
        audit_file.write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"章节审计标记: {self.ticker}/{chapter_id}")

    def save_repair_history(
        self,
        ticker: str,
        chapter_id: str,
        history: list,
    ) -> None:
        """保存修复历史记录

        Args:
            ticker: 股票代码
            chapter_id: 章节标识
            history: repair_chapter() 返回的 history 列表
        """
        repair_dir = self._ticker_dir / "repair"
        repair_dir.mkdir(parents=True, exist_ok=True)
        repair_file = repair_dir / f"{chapter_id}.json"
        record = {
            "chapter_id": chapter_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "rounds": len(history),
            "history": self._serialize_result(history),
        }
        repair_file.write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"修复历史保存: {self.ticker}/{chapter_id} ({len(history)} 轮)")

    def save_facts(self, ticker: str, facts_dict: dict) -> None:
        """保存事实表到 checkpoint

        Args:
            ticker: 股票代码
            facts_dict: ExtractedFacts.to_dict() 的输出
        """
        facts_file = self._ticker_dir / "facts.json"
        facts_file.write_text(
            json.dumps(facts_dict, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"事实表保存: {self.ticker}")

    def load_facts(self, ticker: str) -> Optional[dict]:
        """从 checkpoint 加载事实表

        Args:
            ticker: 股票代码

        Returns:
            事实表 dict，如果不存在返回 None
        """
        facts_file = self._ticker_dir / "facts.json"
        if not facts_file.exists():
            return None
        try:
            data = json.loads(facts_file.read_text(encoding="utf-8"))
            logger.info(f"事实表加载: {self.ticker}")
            return data
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"事实表加载失败: {e}")
            return None

    def is_chapter_audited(self, chapter_id: str) -> bool:
        """检查章节是否已审计

        Args:
            chapter_id: 章节标识

        Returns:
            True 如果章节已审计
        """
        audit_file = self._audit_dir / f"{chapter_id}.json"
        if not audit_file.exists():
            return False
        try:
            record = json.loads(audit_file.read_text(encoding="utf-8"))
            return record.get("audited", False)
        except (json.JSONDecodeError, KeyError):
            return False

    def get_audit_result(self, chapter_id: str) -> Optional[dict]:
        """获取章节审计记录

        Args:
            chapter_id: 章节标识

        Returns:
            审计记录数据，如果不存在返回 None
        """
        audit_file = self._audit_dir / f"{chapter_id}.json"
        if audit_file.exists():
            try:
                return json.loads(audit_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return None
        return None

    # --------------------------------------------------
    # 元数据管理
    # --------------------------------------------------

    def save_metadata(self, metadata: dict) -> None:
        """保存分析元数据

        Args:
            metadata: 元数据字典
        """
        data = {
            "ticker": self.ticker,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            **metadata,
        }
        self._metadata_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_metadata(self) -> Optional[dict]:
        """获取分析元数据

        Returns:
            元数据字典，如果不存在返回 None
        """
        if self._metadata_file.exists():
            try:
                return json.loads(
                    self._metadata_file.read_text(encoding="utf-8")
                )
            except json.JSONDecodeError:
                return None
        return None

    # --------------------------------------------------
    # 清理
    # --------------------------------------------------

    def clear(self) -> None:
        """清除所有状态数据（用于重新开始分析）"""
        import shutil
        if self._ticker_dir.exists():
            shutil.rmtree(self._ticker_dir)
            # 重新创建目录结构
            self._chapters_dir.mkdir(parents=True, exist_ok=True)
            self._audit_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"状态清除: {self.ticker}")

    def get_summary(self) -> dict:
        """获取状态摘要

        Returns:
            包含当前状态的摘要字典
        """
        steps = self._load_steps()
        chapters = self.list_chapters()

        audited_chapters = [
            ch for ch in chapters if self.is_chapter_audited(ch)
        ]

        return {
            "ticker": self.ticker,
            "state_dir": str(self._ticker_dir),
            "steps": {
                name: {
                    "completed": data.get("completed", False),
                    "timestamp": data.get("timestamp"),
                }
                for name, data in steps.items()
            },
            "chapters": {
                "total": len(chapters),
                "list": chapters,
                "audited": len(audited_chapters),
                "audited_list": audited_chapters,
            },
            "metadata": self.get_metadata(),
        }

    # --------------------------------------------------
    # 内部方法
    # --------------------------------------------------

    def _load_steps(self) -> dict[str, dict]:
        """加载步骤状态"""
        if self._steps_file.exists():
            try:
                return json.loads(
                    self._steps_file.read_text(encoding="utf-8")
                )
            except json.JSONDecodeError:
                logger.warning(f"步骤文件损坏，重新初始化: {self._steps_file}")
        return {}

    def _save_steps(self, steps: dict[str, dict]) -> None:
        """保存步骤状态"""
        self._steps_file.write_text(
            json.dumps(steps, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _serialize_result(self, result: dict) -> dict:
        """序列化结果数据（处理不可 JSON 序列化的类型）"""
        try:
            # 测试是否可以直接序列化
            json.dumps(result, ensure_ascii=False)
            return result
        except (TypeError, ValueError):
            # 尝试转换不可序列化的对象
            serialized = {}
            for key, value in result.items():
                try:
                    json.dumps(value, ensure_ascii=False)
                    serialized[key] = value
                except (TypeError, ValueError):
                    if hasattr(value, "__dict__"):
                        # 对象转 dict
                        serialized[key] = {
                            k: v for k, v in value.__dict__.items()
                            if not k.startswith("_")
                        }
                    else:
                        serialized[key] = str(value)
            return serialized
