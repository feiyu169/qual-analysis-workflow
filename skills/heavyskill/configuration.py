"""
HeavySkill Configuration

Dataclass-based configuration for the HeavySkill pipeline.
Supports bilingual prompts and domain-specific settings.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PromptType(str, Enum):
    """Domain-specific prompt types."""
    GENERAL = "general"
    STEM = "stem"


class Language(str, Enum):
    """Supported languages for deliberation prompts."""
    EN = "en"
    CN = "cn"


class SelectionStrategy(str, Enum):
    """Strategies for selecting trajectories in deliberation."""
    RANDOM = "random"
    MAX_ANSWER_FREQUENCY = "max_answer_frequency"
    MAX_DIVERSITY = "max_diversity"


@dataclass
class HeavySkillConfig:
    """Configuration for the HeavySkill pipeline.

    Attributes:
        api_base: Base URL for the OpenAI-compatible API endpoint.
        api_key: API authentication key.
        model: Model name for reasoning stage.
        summary_model: Model name for deliberation/summary stage.
        reason_k: Number of parallel reasoning trajectories to generate.
        summary_k: Number of top trajectories to use in deliberation.
        max_iterations: Maximum number of deliberation iterations.
        temperature: Temperature for reasoning (higher = more diverse).
        summary_temperature: Temperature for deliberation/summary stage.
        max_tokens: Maximum tokens per LLM response.
        token_budget: Total token budget across all trajectories.
        prompt_type: Domain type (general or stem).
        language: Language for deliberation prompts (en or cn).
        selection_strategy: Strategy for selecting trajectories.
        timeout: HTTP request timeout in seconds.
        max_retries: Maximum retry attempts for failed requests.
        retry_base_delay: Base delay for exponential backoff in seconds.
        system_prompt: Optional custom system prompt for reasoning.
        deliberation_system_prompt: Optional custom system prompt for deliberation.
        verbose: Enable verbose logging.
    """

    # API Configuration
    api_base: str = "https://api.deepseek.com"
    api_key: str = "<YOUR_DEEPSEEK_API_KEY>"
    model: str = "deepseek-v4-pro"
    summary_model: str = "deepseek-v4-pro"

    # Pipeline Configuration
    reason_k: int = 8
    summary_k: int = 4
    max_iterations: int = 1

    # Generation Parameters
    temperature: float = 1.0
    summary_temperature: float = 0.7
    max_tokens: int = 4096
    token_budget: int = 80000

    # Prompt Configuration
    prompt_type: PromptType = PromptType.GENERAL
    language: Language = Language.EN
    selection_strategy: SelectionStrategy = SelectionStrategy.MAX_ANSWER_FREQUENCY

    # HTTP Configuration
    timeout: float = 120.0
    max_retries: int = 3
    retry_base_delay: float = 1.0

    # Custom Prompts
    system_prompt: Optional[str] = None
    deliberation_system_prompt: Optional[str] = None

    # Logging
    verbose: bool = False

    def __post_init__(self) -> None:
        """Validate and normalize configuration."""
        # Normalize enum types from strings
        if isinstance(self.prompt_type, str):
            self.prompt_type = PromptType(self.prompt_type)
        if isinstance(self.language, str):
            self.language = Language(self.language)
        if isinstance(self.selection_strategy, str):
            self.selection_strategy = SelectionStrategy(self.selection_strategy)

        # Validate ranges
        if self.reason_k < 1:
            raise ValueError(f"reason_k must be >= 1, got {self.reason_k}")
        if self.summary_k < 1:
            raise ValueError(f"summary_k must be >= 1, got {self.summary_k}")
        if self.summary_k > self.reason_k:
            logger.warning(
                f"summary_k ({self.summary_k}) > reason_k ({self.reason_k}), "
                f"capping summary_k to {self.reason_k}"
            )
            self.summary_k = self.reason_k
        if self.max_iterations < 1:
            raise ValueError(f"max_iterations must be >= 1, got {self.max_iterations}")
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError(f"temperature must be in [0, 2], got {self.temperature}")
        if not 0.0 <= self.summary_temperature <= 2.0:
            raise ValueError(
                f"summary_temperature must be in [0, 2], got {self.summary_temperature}"
            )
        if self.max_tokens < 1:
            raise ValueError(f"max_tokens must be >= 1, got {self.max_tokens}")
        if self.token_budget < 1:
            raise ValueError(f"token_budget must be >= 1, got {self.token_budget}")

        # Ensure API key is set
        if not self.api_key:
            logger.warning("No API key configured - API calls will fail")

    @property
    def reasoning_api_url(self) -> str:
        """Full URL for the chat completions endpoint."""
        base = self.api_base.rstrip("/")
        if not base.endswith("/chat/completions"):
            base = f"{base}/chat/completions"
        return base

    def to_dict(self) -> Dict[str, Any]:
        """Serialize config to dictionary."""
        result = {}
        for k, v in self.__dict__.items():
            if isinstance(v, Enum):
                result[k] = v.value
            else:
                result[k] = v
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> HeavySkillConfig:
        """Create config from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# Bilingual deliberation prompts

DELIBERATION_PROMPTS = {
    "en": {
        "general": """You are given {k} independent reasoning attempts for the following problem.

Problem: {query}

{trajectories}

Your task is to carefully analyze all {k} reasoning attempts above. Please:

1. **Identify Errors**: Find any logical errors, calculation mistakes, or flawed assumptions in each attempt.
2. **Cross-Validate**: Compare the final answers and reasoning paths across all attempts. Look for convergence or divergence.
3. **Synthesize**: Based on your analysis, produce a single, well-reasoned final answer.

Think step-by-step. If most attempts agree on an answer, verify the reasoning is sound. If they disagree, carefully determine which reasoning is correct.

Provide your final answer in the format:
**Final Answer:** [your answer here]""",

        "stem": """You are given {k} independent reasoning attempts for the following STEM problem.

Problem: {query}

{trajectories}

Your task as an expert in the relevant scientific/mathematical domain is to carefully analyze all {k} reasoning attempts above. Please:

1. **Verify Mathematical/Scientific Rigor**: Check each attempt for correct application of formulas, theorems, and scientific principles.
2. **Identify Errors**: Find any calculation mistakes, unit errors, sign errors, or conceptual misunderstandings.
3. **Cross-Validate**: Compare approaches and final answers. Different valid methods should yield the same result.
4. **Synthesize**: Produce a single, rigorously verified final answer with complete reasoning.

Pay special attention to:
- Correct formula application
- Unit consistency
- Boundary conditions and edge cases
- Proper mathematical notation

Provide your final answer in the format:
**Final Answer:** [your answer here]""",
    },
    "cn": {
        "general": """以下是针对同一问题的 {k} 个独立推理尝试。

问题：{query}

{trajectories}

请仔细分析以上所有 {k} 个推理尝试，并完成以下任务：

1. **找出错误**：识别每个尝试中的逻辑错误、计算错误或错误假设。
2. **交叉验证**：比较所有尝试的最终答案和推理路径，观察它们是否收敛或发散。
3. **综合分析**：基于你的分析，给出一个经过深思熟虑的最终答案。

请逐步思考。如果大多数尝试得出相同的答案，请验证推理是否正确。如果它们有分歧，请仔细判断哪个推理是正确的。

请按以下格式给出最终答案：
**最终答案：** [你的答案]""",

        "stem": """以下是针对同一 STEM 问题的 {k} 个独立推理尝试。

问题：{query}

{trajectories}

作为相关科学/数学领域的专家，请仔细分析以上所有 {k} 个推理尝试，并完成以下任务：

1. **验证数学/科学严谨性**：检查每个尝试是否正确应用了公式、定理和科学原理。
2. **找出错误**：识别计算错误、单位错误、符号错误或概念性误解。
3. **交叉验证**：比较不同方法和最终答案。不同的有效方法应得出相同结果。
4. **综合分析**：给出一个经过严格验证的最终答案，并附上完整推理过程。

请特别注意：
- 公式应用的正确性
- 单位一致性
- 边界条件和特殊情况
- 数学符号的规范使用

请按以下格式给出最终答案：
**最终答案：** [你的 answer here]""",
    },
}

REASONING_SYSTEM_PROMPTS = {
    "en": {
        "general": "You are a helpful assistant. Think step-by-step to solve the problem. Show your reasoning clearly.",
        "stem": "You are a STEM expert. Solve this problem rigorously, showing all steps, formulas, and calculations. Verify your answer.",
    },
    "cn": {
        "general": "你是一个有用的助手。请逐步思考来解决这个问题。清晰地展示你的推理过程。",
        "stem": "你是一个 STEM 专家。请严谨地解决这个问题，展示所有步骤、公式和计算过程。验证你的答案。",
    },
}


@dataclass
class DeliberationRecord:
    """Record of a single deliberation round."""

    iteration: int
    selected_indices: List[int]
    prompt: str
    response: str
    extracted_answer: Optional[str] = None
    tokens: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "iteration": self.iteration,
            "selected_indices": self.selected_indices,
            "prompt": self.prompt,
            "response": self.response,
            "extracted_answer": self.extracted_answer,
            "tokens": self.tokens,
        }


def get_reasoning_system_prompt(
    language: Language = Language.EN, prompt_type: PromptType = PromptType.GENERAL
) -> str:
    """Get the system prompt for the reasoning stage."""
    return REASONING_SYSTEM_PROMPTS[language.value][prompt_type.value]


def get_deliberation_prompt(
    language: Language = Language.EN, prompt_type: PromptType = PromptType.GENERAL
) -> str:
    """Get the deliberation prompt template."""
    return DELIBERATION_PROMPTS[language.value][prompt_type.value]
