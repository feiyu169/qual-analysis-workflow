"""P54 截断治理单测：finish_reason=length 检测、截断轨迹剔除、答案提取加固。

背景：模式2 在 HGF 会话中多次出现"读取审查结果被截断"——
根因是 max_tokens 默认 4096 + 推理模型思维链占预算 + finish_reason 从不检查
+ extract_answer 把思维/断句碎片当答案。

运行：
    cd skills/heavyskill && python -m pytest tests/test_truncation.py -v
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from configuration import HeavySkillConfig
from agent.openai_compatible import LLMResponse, OpenAICompatibleClient
from workflow.memory_cache import MemoryCache
from workflow.pipeline import HeavySkillResult
from workflow.parallel_reasoning import ReasoningResult
from workflow.sequential_deliberation import DeliberationResult
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


def test_extract_answer_rejects_thinking_fragment():
    # 实测 traj[0]-like：思维链里的 "the final answer is ..." 片段 → 不得当答案
    t = "so the final answer is: ning process maybe structured."
    assert extract_answer(t) is None


def test_extract_answer_accepts_proper_answers():
    assert extract_answer("**最终答案：HGF 部分具备生产力**") == "HGF 部分具备生产力"
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
        LLMResponse(
            content="a", model="m", finish_reason="length", truncated=True
        )
    ]
    rr = ReasoningResult(
        trajectories=["a"],
        answers=["x"],
        responses=responses,
        total_tokens=10,
        total_latency=1.0,
        successful_count=1,
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
