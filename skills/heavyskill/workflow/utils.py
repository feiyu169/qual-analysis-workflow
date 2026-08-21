"""
HeavySkill Workflow Utilities

Helper functions for token estimation, trajectory quality filtering,
and answer extraction.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Regex patterns for answer extraction across languages and formats
# 注意：停止符含 \n——答案行后跟换行（无句号）也能正确截断，避免整段吞进 group
ANSWER_PATTERNS = [
    # English patterns
    re.compile(r"\*\*(?:Final\s+)?Answer[:\s]*\*\*\s*(.+?)(?:\n|$)", re.IGNORECASE),
    re.compile(r"(?:final|the)\s+answer\s+(?:is|:)\s*(.+?)(?:\n|\.|$)", re.IGNORECASE),
    re.compile(r"(?:therefore|thus|so|hence),?\s*(?:the\s+answer\s+is\s+)?(.+?)(?:\n|\.|$)", re.IGNORECASE),
    re.compile(r"answer\s*[:=]\s*(.+?)(?:\n|\.|$)", re.IGNORECASE),
    # Chinese patterns
    re.compile(r"\*\*(?:最终)?答案[：:]\s*\*\*\s*(.+?)(?:\n|$)"),
    re.compile(r"(?:最终)?答案[为是：:]\s*(.+?)(?:\n|。|$)"),
    re.compile(r"(?:因此|所以|综上),?\s*(.+?)(?:\n|。|$)"),
    # Box notation (common in math)
    re.compile(r"\\boxed\{(.+?)\}"),
    re.compile(r"\$\$(.+?)\$\$"),
]


def estimate_tokens(text: str) -> int:
    """Estimate token count for text.

    Uses a simple heuristic: ~4 characters per token for English,
    ~2 characters per token for CJK, mixed for combined text.

    Args:
        text: Input text to estimate.

    Returns:
        Estimated token count.
    """
    if not text:
        return 0

    # Count CJK characters
    cjk_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    non_cjk_chars = len(text) - cjk_chars

    # CJK: ~1.5 tokens per character, non-CJK: ~0.25 tokens per character
    estimate = int(cjk_chars * 1.5 + non_cjk_chars * 0.25)
    return max(1, estimate)


# P54：句子终止符——文本被 max_tokens 硬截断时通常没有终止符，
# 靠它识别"残稿"，避免把断句/思维碎片当成答案
SENTENCE_TERMINATORS = (
    "。", "！", "？", "；", "…",
    ".", "!", "?", ";",
    "”", '"', "』", "」", "）", ")", "]", "}", ">", "```",
)


def is_terminated(text: str) -> bool:
    """判断文本是否以句子终止符收尾（未被截断的完整文本通常满足）。"""
    t = text.strip()
    return bool(t) and t.endswith(SENTENCE_TERMINATORS)


# P54：明显的思考/元话语起始短语——答案开头出现它们说明抓到的是推理过程而非结论。
# 保守清单：只收录"几乎不可能作为正式答案开头"的元话语，避免误杀"可以合并"这类短裁决。
_THINKING_STARTS = (
    "我们", "让我们", "Let", "We need", "I need", "The user", "Need",
    "需要注意", "用户要求", "要求我们",
)


def _is_fragment(answer: str) -> bool:
    """判断提取出的答案是否像碎片。

    仅在"最后一行回退"路径使用（该路径抓的是任意末行，风险最高）；
    正则路径已按答案标记锚定，只额外检查是否仍含答案标记本身。
    """
    a = answer.strip()
    if not a:
        return True
    a_lower = a.lower()
    if "最终答案" in a or "final answer" in a_lower:
        return True
    if a.startswith(_THINKING_STARTS):
        return True
    return False


def extract_answer(text: str) -> Optional[str]:
    """Extract the final answer from a reasoning trajectory.

    Tries multiple regex patterns to find the answer in various formats.

    P54 加固：截断残稿（无终止符）不走"最后一行"回退；明显是思维链碎片
    （以思考短语开头 / 仍含答案标记）的候选被拒绝，避免共识被垃圾污染。

    Args:
        text: Full reasoning trajectory text.

    Returns:
        Extracted answer string, or None if no answer found.
    """
    if not text:
        return None

    for pattern in ANSWER_PATTERNS:
        match = pattern.search(text)
        if match:
            answer = match.group(1).strip()
            # Clean up common artifacts (含 markdown 加粗闭合符)
            answer = answer.rstrip("。，、；：！？.,;:!?*")
            if not answer or answer.startswith((":", "：")):
                continue
            if len(answer) < 500:  # Sanity check
                # P54：匹配内容仍含答案标记（大小写不敏感）= 抓到标记附近的残段，跳过继续找
                a_lower = answer.lower()
                if "最终答案" in answer or "final answer" in a_lower:
                    continue
                return answer

    # Fallback: try to get the last non-empty line
    # P54：只在文本"完整收尾"（有终止符）时才信任末行——截断残稿的末行是断句
    lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
    if lines and is_terminated(text):
        last_line = lines[-1]
        # Only use if it looks like an answer (short, no question marks, not a fragment)
        if (
            len(last_line) < 200
            and "?" not in last_line
            and not _is_fragment(last_line)
        ):
            return last_line

    return None


def extract_all_answers(texts: List[str]) -> List[Optional[str]]:
    """Extract answers from multiple trajectories.

    Args:
        texts: List of trajectory texts.

    Returns:
        List of extracted answers (None for failed extractions).
    """
    return [extract_answer(text) for text in texts]


def get_answer_frequencies(answers: List[Optional[str]]) -> Counter:
    """Count frequency of each unique answer.

    Args:
        answers: List of extracted answers.

    Returns:
        Counter mapping answer -> frequency count.
    """
    valid_answers = [a for a in answers if a is not None]
    return Counter(valid_answers)


def is_repetitive(text: str, min_unique_ratio: float = 0.3, ngram_size: int = 10) -> bool:
    """Detect if a trajectory is excessively repetitive.

    Checks for repeated n-grams that indicate the model is stuck in a loop.

    Args:
        text: Trajectory text to check.
        min_unique_ratio: Minimum ratio of unique n-grams to total n-grams.
        ngram_size: Size of n-grams to check.

    Returns:
        True if the trajectory appears to be repetitive.
    """
    if not text or len(text) < ngram_size * 2:
        return False

    words = text.split()
    if len(words) < ngram_size * 2:
        return False

    # Generate n-grams
    ngrams = []
    for i in range(len(words) - ngram_size + 1):
        ngram = " ".join(words[i : i + ngram_size])
        ngrams.append(ngram)

    if not ngrams:
        return False

    unique_ratio = len(set(ngrams)) / len(ngrams)
    return unique_ratio < min_unique_ratio


def filter_trajectories(
    trajectories: List[str],
    answers: List[Optional[str]],
    min_length: int = 50,
    max_repetition_ratio: float = 0.3,
) -> Tuple[List[str], List[int]]:
    """Filter trajectories by quality metrics.

    Removes trajectories that are too short, have no extractable answer,
    or are excessively repetitive.

    Args:
        trajectories: List of trajectory texts.
        answers: List of extracted answers (parallel to trajectories).
        min_length: Minimum character length for a valid trajectory.
        max_repetition_ratio: Max allowed repetition ratio (lower = stricter).

    Returns:
        Tuple of (filtered_trajectories, original_indices).
    """
    filtered = []
    indices = []

    for i, (traj, answer) in enumerate(zip(trajectories, answers)):
        # Check length
        if len(traj) < min_length:
            logger.debug(f"Trajectory {i}: too short ({len(traj)} chars)")
            continue

        # Check for errors
        if traj.startswith("[ERROR:"):
            logger.debug(f"Trajectory {i}: contains error")
            continue

        # Check for repetition
        if is_repetitive(traj, min_unique_ratio=max_repetition_ratio):
            logger.debug(f"Trajectory {i}: too repetitive")
            continue

        filtered.append(traj)
        indices.append(i)

    logger.info(
        f"Filtered trajectories: {len(filtered)}/{len(trajectories)} passed quality check"
    )
    return filtered, indices


def select_top_k_trajectories(
    trajectories: List[str],
    answers: List[Optional[str]],
    k: int = 4,
) -> List[int]:
    """Select top-k trajectory indices by answer frequency.

    Selects trajectories whose answers appear most frequently,
    as this indicates higher likelihood of correctness.

    Args:
        trajectories: List of trajectory texts.
        answers: List of extracted answers.
        k: Number of trajectories to select.

    Returns:
        List of selected trajectory indices.
    """
    answer_freq = get_answer_frequencies(answers)

    if not answer_freq:
        # No valid answers found, return first k
        return list(range(min(k, len(trajectories))))

    # Sort answers by frequency (descending)
    sorted_answers = sorted(answer_freq.items(), key=lambda x: x[1], reverse=True)

    # Select trajectories with the most frequent answers first
    selected_indices: List[int] = []
    for answer, _ in sorted_answers:
        for i, traj_answer in enumerate(answers):
            if traj_answer == answer and i not in selected_indices:
                selected_indices.append(i)
                if len(selected_indices) >= k:
                    return selected_indices

    # If we don't have enough, fill with remaining
    for i in range(len(trajectories)):
        if i not in selected_indices:
            selected_indices.append(i)
            if len(selected_indices) >= k:
                break

    return selected_indices


def estimate_total_tokens(
    trajectories: List[str], deliberation_text: str = ""
) -> int:
    """Estimate total tokens used across all trajectories.

    Args:
        trajectories: List of trajectory texts.
        deliberation_text: Deliberation prompt and response.

    Returns:
        Estimated total token count.
    """
    total = sum(estimate_tokens(t) for t in trajectories)
    total += estimate_tokens(deliberation_text)
    return total


def format_trajectory_for_display(index: int, trajectory: str, max_chars: int = 200) -> str:
    """Format a trajectory for display in logs.

    Args:
        index: Trajectory index (1-based).
        trajectory: Full trajectory text.
        max_chars: Maximum characters to show.

    Returns:
        Formatted string for display.
    """
    preview = trajectory[:max_chars].replace("\n", " ")
    if len(trajectory) > max_chars:
        preview += "..."
    return f"[Trajectory {index}] ({len(trajectory)} chars): {preview}"
