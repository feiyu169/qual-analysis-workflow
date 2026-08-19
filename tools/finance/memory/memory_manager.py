"""
Gate 5.4: 记忆管理器

三层并写: GBrain + flomo + nocturne。
单层失败不影响其他层。

使用方式:
    manager = MemoryManager()
    results = manager.save_analysis(ctx, report)
    # results = {"gbrain": True, "flomo": True, "nocturne": False}
"""

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MemoryResult:
    """记忆写入结果"""

    gbrain: bool = False
    flomo: bool = False
    nocturne: bool = False
    errors: list[str] = field(default_factory=list)

    @property
    def success_count(self) -> int:
        """成功写入的层数"""
        return sum([self.gbrain, self.flomo, self.nocturne])

    @property
    def total_count(self) -> int:
        """总层数"""
        return 3

    @property
    def all_success(self) -> bool:
        """是否全部成功"""
        return self.success_count == self.total_count

    @property
    def any_success(self) -> bool:
        """是否有任一层成功"""
        return self.success_count > 0

    def to_dict(self) -> dict[str, Any]:
        """转为字典"""
        return {
            "gbrain": self.gbrain,
            "flomo": self.flomo,
            "nocturne": self.nocturne,
            "success_count": self.success_count,
            "total_count": self.total_count,
            "errors": self.errors,
        }


class MemoryManager:
    """三层记忆管理器

    管理 GBrain、flomo、nocturne 三层记忆写入。
    设计原则:
    - 三层并行写入，互不依赖
    - 单层失败不影响其他层
    - 返回详细的写入结果
    """

    def __init__(
        self,
        enable_gbrain: bool = True,
        enable_flomo: bool = True,
        enable_nocturne: bool = True,
    ):
        """初始化记忆管理器

        Args:
            enable_gbrain: 是否启用 GBrain 写入
            enable_flomo: 是否启用 flomo 写入
            enable_nocturne: 是否启用 nocturne 写入
        """
        self._enable_gbrain = enable_gbrain
        self._enable_flomo = enable_flomo
        self._enable_nocturne = enable_nocturne

    def save_analysis(self, ctx: "DataContext", report: str) -> MemoryResult:
        """将分析结果保存到三层记忆系统

        三层独立写入，单层失败不影响其他层。

        Args:
            ctx: DataContext 实例
            report: 完整分析报告

        Returns:
            MemoryResult 包含各层写入结果
        """
        result = MemoryResult()

        logger.info(
            f"开始三层记忆写入: {ctx.company_name} ({ctx.ticker}) | "
            f"gbrain={self._enable_gbrain}, "
            f"flomo={self._enable_flomo}, "
            f"nocturne={self._enable_nocturne}"
        )

        # ---- GBrain ----
        if self._enable_gbrain:
            try:
                from .gbrain_writer import write_to_gbrain

                result.gbrain = write_to_gbrain(ctx, report)
                if not result.gbrain:
                    result.errors.append("GBrain 写入返回 False")
            except Exception as e:
                error_msg = f"GBrain 写入异常: {e}"
                logger.error(error_msg)
                result.errors.append(error_msg)
        else:
            logger.info("GBrain 已禁用，跳过")

        # ---- flomo ----
        if self._enable_flomo:
            try:
                from .flomo_writer import write_to_flomo

                result.flomo = write_to_flomo(ctx, report)
                if not result.flomo:
                    result.errors.append("flomo 写入返回 False")
            except Exception as e:
                error_msg = f"flomo 写入异常: {e}"
                logger.error(error_msg)
                result.errors.append(error_msg)
        else:
            logger.info("flomo 已禁用，跳过")

        # ---- nocturne ----
        if self._enable_nocturne:
            try:
                from .nocturne_writer import write_to_nocturne

                result.nocturne = write_to_nocturne(ctx, report)
                if not result.nocturne:
                    result.errors.append("nocturne 写入返回 False")
            except Exception as e:
                error_msg = f"nocturne 写入异常: {e}"
                logger.error(error_msg)
                result.errors.append(error_msg)
        else:
            logger.info("nocturne 已禁用，跳过")

        # 汇总日志
        logger.info(
            f"三层记忆写入完成: {ctx.ticker} | "
            f"成功 {result.success_count}/{result.total_count} | "
            f"gbrain={result.gbrain}, flomo={result.flomo}, "
            f"nocturne={result.nocturne}"
        )

        if result.errors:
            logger.warning(f"记忆写入错误 ({len(result.errors)}): {result.errors}")

        return result
