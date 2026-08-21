"""P54 截断治理单测：finish_reason=length 检测、截断轨迹剔除、答案提取加固。

背景：模式2 在 HGF 会话中多次出现"读取审查结果被截断"——
根因是 max_tokens 默认 4096 + 推理模型思维链占预算 + finish_reason 从不检查
+ extract_answer 把思维/断句碎片当答案。

P54 复审（HGF 裁决 FAIL → R1-R7 修复）后新增：
- 冒号标准格式净化（R2："答案是：42" → "42"）
- 审议截断回退共识（R3）
- build_config 三级解析（R4：CLI > config.yaml > 默认）
- 全截断端到端早退 + successful_count 排除截断（R5）
- has_truncation 纳入思维链回退（R5）

运行：
    cd skills/heavyskill && python -m pytest tests/test_truncation.py -v
"""

import argparse
import asyncio
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.openai_compatible import LLMResponse, OpenAICompatibleClient
from configuration import HeavySkillConfig, Language
from scripts.run_heavyskill import build_config
from workflow.memory_cache import MemoryCache
from workflow.parallel_reasoning import ReasoningResult
from workflow.pipeline import HeavySkillPipeline, HeavySkillResult
from workflow.sequential_deliberation import DeliberationResult, SequentialDeliberator
from workflow.utils import extract_answer

# ---------- extract_answer 加固 ----------


def test_extract_answer_rejects_truncated_fragment():
    # 实测 traj[4]-like：标题后即断、无终止符 → 不得被抓成答案
    t = (
        "# HGF 门禁驱动开发工作流生产力评估报告\n\n"
        "> 评估身份：第三方项目开发专家  \n"
        "> 证据基础：仅限 include-file 内联证据包（2026-08"
    )
    assert extract_answer(t) is None


def test_extract_answer_accepts_standard_colon_format():
    # P54-R2：冒号标准格式必须提取（旧守卫误杀回归点）
    assert extract_answer("答案是：42") == "42"
    assert extract_answer("答案是：42。") == "42"
    assert extract_answer("The final answer is: 42") == "42"
    assert extract_answer("**最终答案：HGF 部分具备生产力**") == "HGF 部分具备生产力"


def test_extract_answer_thinking_fragment_handled_by_pipeline_layer():
    # 思维链片段 "the final answer is: X" 在 extract_answer 层净化后返回文本，
    # 垃圾防护由 pipeline 层 content_fallback 承担（见 cache/parallel 测试）
    assert extract_answer("so the final answer is: ning process maybe structured.") == (
        "ning process maybe structured"
    )


def test_extract_answer_accepts_proper_answers():
    assert extract_answer("Therefore, the answer is 42.") == "42"
    # 答案行后跟换行（无句号）也能正确截断
    assert (
        extract_answer("分析如下：\n**最终答案：HGF 部分具备生产力**\n（依据：…）")
        == "HGF 部分具备生产力"
    )
    # 无标记但完整收尾的末行仍可用
    assert extract_answer("…全部完成。\nHGF 部分具备生产力。") == "HGF 部分具备生产力。"


# ---------- memory_cache：截断轨迹剔除 / 思维链不投票 ----------


def test_cache_excludes_truncated_from_valid_and_consensus():
    cache = MemoryCache()
    cache.add_trajectories(
        ["**最终答案：通过。**", "被截断轨迹，断在句中", "**最终答案：通过。**"],
        truncated=[False, True, False],
    )
    assert [t.index for t in cache.get_valid_trajectories()] == [0, 2]
    assert cache.get_consensus_answer() == "通过"


def test_cache_content_fallback_no_vote_but_kept_as_material():
    cache = MemoryCache()
    cache.add_trajectories(
        ["**最终答案：通过。**", "思维链文本（无最终答案，仅作审议素材）"],
        content_fallback=[False, True],
    )
    # 思维链轨迹仍是有效素材（可进审议），但不参与共识投票
    assert len(cache.get_valid_trajectories()) == 2
    assert cache.get_consensus_answer() == "通过"


def test_cache_truncated_and_fallback_combined():
    cache = MemoryCache()
    cache.add_trajectories(["思维链残稿"], truncated=[True], content_fallback=[True])
    assert cache.trajectories[0].is_valid is False
    assert cache.trajectories[0].answer is None


# ---------- configuration ----------


def test_config_has_summary_max_tokens():
    c = HeavySkillConfig()
    assert c.max_tokens == 32768
    assert c.summary_max_tokens == 16384


# ---------- openai_compatible：截断/回退标记 ----------


class _FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class _FakeHttpClient:
    is_closed = False

    def __init__(self, data):
        self._data = data

    async def post(self, *args, **kwargs):
        return _FakeResponse(self._data)

    async def aclose(self):
        self.is_closed = True


def _run(client):
    return asyncio.run(
        client.chat_completion(
            messages=[{"role": "user", "content": "q"}],
            model="m",
            temperature=0.7,
            max_tokens=100,
        )
    )


def test_client_marks_truncated_when_finish_reason_length():
    client = OpenAICompatibleClient(api_base="http://x", api_key="k")
    client._client = _FakeHttpClient(
        {
            "choices": [
                {
                    "message": {"content": "partial output"},
                    "finish_reason": "length",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        }
    )
    resp = _run(client)
    assert resp.truncated is True
    assert resp.finish_reason == "length"
    assert resp.content_fallback is False


def test_client_marks_content_fallback_for_reasoning_model():
    client = OpenAICompatibleClient(api_base="http://x", api_key="k")
    client._client = _FakeHttpClient(
        {
            "choices": [
                {
                    "message": {
                        "content": "",
                        "reasoning_content": "thinking...",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {},
        }
    )
    resp = _run(client)
    assert resp.content_fallback is True
    assert resp.content == "thinking..."
    assert resp.truncated is False


# ---------- pipeline：截断摘要 ----------


def test_result_truncation_summary_and_flag():
    responses = [
        LLMResponse(content="a", model="m", finish_reason="length", truncated=True)
    ]
    rr = ReasoningResult(
        trajectories=["a"],
        answers=["x"],
        responses=responses,
        total_tokens=10,
        total_latency=1.0,
        successful_count=0,
        failed_count=0,
        truncated_count=1,
        content_fallback_count=1,
    )
    res = HeavySkillResult(
        query="q",
        final_answer="f",
        consensus_answer="c",
        reasoning_result=rr,
        deliberation_results=[
            DeliberationResult(
                final_answer="f2",
                deliberation_response="d",
                selected_indices=[0],
                iteration=0,
                truncated=True,
            )
        ],
    )
    d = res.to_dict()
    assert d["truncation"] == {
        "reasoning_truncated_count": 1,
        "content_fallback_count": 1,
        "deliberation_truncated": True,
    }
    assert res.has_truncation() is True
    assert "WARNING" in res.summary()
    assert rr.to_dict()["truncated_flags"] == [True]
    assert rr.to_dict()["finish_reasons"] == ["length"]


def test_has_truncation_includes_content_fallback_only():
    # P54-R5：8/8 思维链回退（无截断）也必须触发退化告警
    responses = [
        LLMResponse(content="thinking", model="m", content_fallback=True),
        LLMResponse(content="thinking2", model="m", content_fallback=True),
    ]
    rr = ReasoningResult(
        trajectories=["t1", "t2"],
        answers=[None, None],
        responses=responses,
        total_tokens=20,
        total_latency=1.0,
        successful_count=2,
        failed_count=0,
        truncated_count=0,
        content_fallback_count=2,
    )
    res = HeavySkillResult(
        query="q", final_answer=None, consensus_answer=None, reasoning_result=rr
    )
    assert res.has_truncation() is True


# ---------- P54-R3：审议截断回退共识 ----------


class _FakeDelibClient:
    """返回截断审议响应的 fake client。"""

    async def deliberation_call(self, messages, temperature, max_tokens):
        return LLMResponse(
            content="## 主要分歧\n- Attempt 2 认为成本高\n\n**最终答案：HGF 部分具备生产力，但",
            model="m",
            finish_reason="length",
            truncated=True,
            total_tokens=500,
        )


def test_deliberation_truncated_falls_back_to_consensus():
    async def run():
        config = HeavySkillConfig(
            api_key="k", reason_k=2, summary_k=2, language=Language.CN
        )
        delib = SequentialDeliberator(config)
        delib.client = _FakeDelibClient()
        cache = MemoryCache()
        cache.add_trajectories(["**最终答案：通过。**", "**最终答案：通过。**"])
        return await delib.deliberate(query="q", cache=cache, iteration=0)

    res = asyncio.run(run())
    assert res.truncated is True
    # 截断残稿 "HGF 部分具备生产力，但" 不得被采信 → 回退共识 "通过"
    assert res.final_answer == "通过"


# ---------- P54-R4：build_config 三级解析 ----------


def _ns(**kwargs):
    defaults = {
        "model": None,
        "summary_model": None,
        "api_base": None,
        "api_key": None,
        "reason_k": None,
        "summary_k": None,
        "iterations": None,
        "temperature": None,
        "summary_temperature": None,
        "max_tokens": None,
        "summary_max_tokens": None,
        "token_budget": None,
        "prompt_type": None,
        "language": None,
        "strategy": None,
        "verbose": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def test_build_config_config_values_win_over_defaults():
    # config 命中：CLI 未传 → 用 config.yaml 值
    cfg = build_config(
        _ns(), {"max_tokens": 20000, "language": "cn", "temperature": 0.5}
    )
    assert cfg.max_tokens == 20000
    assert cfg.language == Language.CN
    assert cfg.temperature == 0.5


def test_build_config_builtin_fallback_when_config_missing():
    cfg = build_config(_ns(), {})
    assert cfg.max_tokens == 32768
    assert cfg.summary_max_tokens == 16384
    assert cfg.reason_k == 8


def test_build_config_cli_overrides_config():
    cfg = build_config(
        _ns(max_tokens=9999, temperature=0.2),
        {"max_tokens": 20000, "temperature": 0.5},
    )
    assert cfg.max_tokens == 9999
    assert cfg.temperature == 0.2


def test_build_config_invalid_config_value_raises():
    import pytest

    # 非法类型（str 而非 int）在 HeavySkillConfig.__post_init__ 校验时抛 TypeError
    with pytest.raises(TypeError):
        build_config(_ns(), {"max_tokens": "not-an-int"})


# ---------- P54-R5：全截断端到端早退 ----------


class _FakeAllTruncatedReasoner:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def reason(self, query):
        return ReasoningResult(
            trajectories=["残稿一", "残稿二"],
            answers=["a", "b"],
            responses=[
                LLMResponse(
                    content="残稿一",
                    model="m",
                    finish_reason="length",
                    truncated=True,
                ),
                LLMResponse(
                    content="残稿二",
                    model="m",
                    finish_reason="length",
                    truncated=True,
                ),
            ],
            total_tokens=10,
            total_latency=1.0,
            successful_count=0,  # R5：截断不计 successful
            failed_count=0,
            truncated_count=2,
            content_fallback_count=0,
        )


def test_pipeline_all_truncated_returns_early_no_deliberation():
    async def run():
        config = HeavySkillConfig(api_key="k", reason_k=2, summary_k=2)
        pipeline = HeavySkillPipeline(config)
        with mock.patch(
            "workflow.pipeline.ParallelReasoner",
            lambda cfg: _FakeAllTruncatedReasoner(),
        ):
            return await pipeline.run(query="q")

    res = asyncio.run(run())
    assert res.final_answer is None
    assert res.iterations_completed == 0
    assert res.has_truncation() is True
    d = res.to_dict()
    assert d["truncation"]["reasoning_truncated_count"] == 2
    assert d["reasoning"]["successful_count"] == 0
