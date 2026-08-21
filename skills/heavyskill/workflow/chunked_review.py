"""P54-增强-路径4：分批审查 + 元审议（ChunkedReviewer）。

大审查包（>max_chars）不再截断：split_pack 分块 → 每块独立跑 HeavySkillPipeline
→ 分块结论聚合 → 元审议（复用 SequentialDeliberator，分块结论作为"轨迹"）→ 最终结论。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from configuration import HeavySkillConfig
from .memory_cache import MemoryCache
from .pipeline import HeavySkillPipeline, HeavySkillResult
from .sequential_deliberation import SequentialDeliberator
from .splitter import split_pack

logger = logging.getLogger(__name__)


@dataclass
class ChunkedReviewResult:
    """分批审查 + 元审议的完整结果。"""

    final_answer: Optional[str]
    chunk_results: List[HeavySkillResult] = field(default_factory=list)
    meta_deliberation: str = ""
    chunks_truncated: int = 0
    total_tokens: int = 0
    total_latency: float = 0.0
    meta_deliberation_truncated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "final_answer": self.final_answer,
            "chunk_count": len(self.chunk_results),
            "chunks_truncated": self.chunks_truncated,
            "meta_deliberation": self.meta_deliberation,
            "meta_deliberation_truncated": self.meta_deliberation_truncated,
            "total_tokens": self.total_tokens,
            "total_latency_seconds": round(self.total_latency, 2),
            "chunks": [
                {
                    "index": i,
                    "final_answer": r.final_answer,
                    "truncation": r.to_dict().get("truncation"),
                    "latency": r.total_latency,
                }
                for i, r in enumerate(self.chunk_results)
            ],
        }


class ChunkedReviewer:
    """分批审查编排器：split → 逐块 pipeline → 元审议。"""

    def __init__(self, config: HeavySkillConfig):
        self.config = config

    async def run(
        self,
        query: str,
        content: str,
        max_chars: int = 18000,
        overlap: int = 500,
        max_chunks: int = 5,
    ) -> ChunkedReviewResult:
        """执行分批审查。

        Args:
            query: 审查请求（不含被审内容，内容走 content 参数）。
            content: 被审内容全文（超 max_chars 自动分块）。
            max_chars / overlap / max_chunks: 切分参数（透传 split_pack）。

        Returns:
            ChunkedReviewResult 聚合结果。
        """
        start = time.monotonic()
        chunks = split_pack(content, max_chars, overlap, max_chunks)
        logger.info(f"分块审查：{len(chunks)} 块，块长 {[len(c) for c in chunks]}")

        total_tokens = 0
        chunk_results: List[HeavySkillResult] = []
        chunk_conclusions: List[str] = []
        truncated_chunks = 0

        for i, chunk in enumerate(chunks):
            logger.info(f"--- 块 {i + 1}/{len(chunks)} 审查开始 ---")
            chunk_query = f"{query}\n\n以下是待审查内容（第 {i + 1}/{len(chunks)} 部分）：\n{chunk}"
            pipe = HeavySkillPipeline(self.config)
            res = await pipe.run(query=chunk_query)
            chunk_results.append(res)
            total_tokens += res.total_tokens
            if res.has_truncation():
                truncated_chunks += 1
            # 分块结论：优先审议最终答案，否则共识
            conclusion = (
                res.final_answer or res.consensus_answer or "（该块无有效结论）"
            )
            chunk_conclusions.append(f"--- 块 {i + 1} 结论 ---\n{conclusion}")

        # 元审议：分块结论作为"轨迹"再综合一次
        meta_answer: Optional[str] = None
        meta_text = ""
        meta_truncated = False
        if chunk_conclusions:
            meta_cache = MemoryCache()
            meta_cache.add_trajectories(chunk_conclusions)
            async with SequentialDeliberator(self.config) as deliberator:
                meta_res = await deliberator.deliberate(
                    query=query, cache=meta_cache, iteration=0
                )
            meta_answer = meta_res.final_answer or meta_cache.get_consensus_answer()
            meta_text = meta_res.deliberation_response
            meta_truncated = meta_res.truncated
            total_tokens += meta_res.tokens

        return ChunkedReviewResult(
            final_answer=meta_answer,
            chunk_results=chunk_results,
            meta_deliberation=meta_text,
            chunks_truncated=truncated_chunks,
            total_tokens=total_tokens,
            total_latency=time.monotonic() - start,
            meta_deliberation_truncated=meta_truncated,
        )
