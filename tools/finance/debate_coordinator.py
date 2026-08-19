"""
debate_coordinator.py — Layer 2: 辩论机制模块

功能：
1. Bull→Bear→PM三角色辩论
2. 预期差+催化剂+触发条件
3. 确信度构成(数据/逻辑/预期差)
4. 降级策略(每步独立降级)
"""

import logging
import threading
from dataclasses import dataclass, field
from typing import Optional, Callable

logger = logging.getLogger(__name__)


# ====================================================================
# 超时机制（使用threading.Timer，跨平台安全）
# ====================================================================

class LLMTimeoutError(Exception):
    """LLM调用超时异常"""
    pass


def llm_caller_with_timeout(
    llm_caller: Callable[[str, str], str],
    chapter_name: str,
    prompt: str,
    timeout_seconds: int = 240,
) -> str:
    """
    带超时保护的LLM调用

    Args:
        llm_caller: LLM调用函数
        chapter_name: 章节名称（用于日志）
        prompt: 提示词
        timeout_seconds: 超时秒数（默认 240——推理模型思考+生成；原 60s 过严，见
            docs/qual-debate-timeout-redesign.md；需 < harness_llm 网络超时 300s）
    
    Returns:
        LLM响应内容
    
    Raises:
        LLMTimeoutError: 调用超时
    """
    result = [None]
    exception = [None]
    
    def target():
        try:
            result[0] = llm_caller(chapter_name, prompt)
        except Exception as e:
            exception[0] = e
    
    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout=timeout_seconds)
    
    if thread.is_alive():
        # 超时，线程仍在运行（daemon线程会随主进程退出）
        raise LLMTimeoutError(f"LLM调用超时({timeout_seconds}s): {chapter_name}")
    
    if exception[0]:
        raise exception[0]
    
    return result[0]


# ====================================================================
# 数据结构
# ====================================================================

@dataclass
class DebateResult:
    """辩论结果"""
    bull_argument: str = ""           # 看多论点
    bear_argument: str = ""           # 看空论点
    pm_synthesis: str = ""            # PM综合判断
    investment_thesis: str = ""       # 投资论点摘要
    key_risk: str = ""                # 最大风险
    conviction_score: float = 0.5     # 确信度 0-1
    conviction_breakdown: dict = field(default_factory=lambda: {
        "data": 0.5,
        "logic": 0.5,
        "expectation_gap": 0.5,
    })
    catalysts: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    key_disagreements: list[str] = field(default_factory=list)
    degraded: bool = False            # 是否降级（保留兼容：全失败或关键步骤失败）
    partial: bool = False             # 部分成功（bull/bear/pm 不全 ok 但非全失败）
    stages: dict = field(default_factory=lambda: {"bull": "pending", "bear": "pending", "pm": "pending"})
    warnings: list[str] = field(default_factory=list)


# ====================================================================
# Prompt 模板
# ====================================================================

BULL_SYSTEM = """你是一个严格的买方看多分析师。你的任务是为投资决策构建看多论点。

规则：
1. 每一个论点都必须有数据支撑，标注 [来源: Wind] 或 [来源: 年报]
2. 禁止使用"可能"、"也许"、"大概"等模糊词汇
3. 必须给出具体数字，不得使用"大幅增长"等定性描述
4. 论点结构：主张 → 数据 → 推导 → 结论
5. 必须包含"预期差"——市场当前定价 vs 你认为的合理价值
6. 必须包含"催化剂"——什么事件会触发价值回归

输出格式：
## 核心看多论点
### 论点1: [标题]
- 主张: ...
- 数据支撑: [来源: ...] ...
- 预期差: ...
- 催化剂: ...
### 论点2: ...
## 投资摘要（50字以内）
"""

BEAR_SYSTEM = """你是一个严格的买方看空分析师。你的任务是找出看多论点的每一个漏洞。

规则：
1. 质疑数据的可靠性：数据来源是否权威？是否最新？口径是否一致？
2. 提出替代解释：同样的数据能否支持相反的结论？
3. 指出被忽略的风险：看多报告遗漏了哪些负面因素？
4. 逻辑检验：论点之间的因果链是否成立？
5. 你必须对看多报告中的每一个"核心论点"给出反驳
6. 你必须给出替代估值——如果你的看空论点成立，公司的合理估值范围

输出格式：
## 对看多论点的逐条反驳
### 反驳论点1: [原论点标题]
- 看多观点摘要: ...
- 数据质疑: ...
- 替代解释: ...
- 遗漏风险: ...
### 反驳论点2: ...
## 替代估值（如果看空正确）
## 被忽略的关键风险（至少3个）
"""

PM_SYSTEM = """你是投资组合经理。你的职责是权衡看多和看空双方的论点，给出最终投资判断。

规则：
1. 评估正反双方的论点质量（数据支撑度、逻辑严密性）
2. 给出明确的投资判断：看多 / 看空 / 中性
3. 标注确信度等级：高确信(>70%) / 中确信(40-70%) / 低确信(<40%)
4. 确信度构成：
   - 数据支撑度 (0-100%): 有多少硬数据支撑？
   - 逻辑严密性 (0-100%): 因果链是否成立？
   - 预期差大小 (0-100%): 市场是否已定价？
5. 列出触发条件（至少3个上行触发 + 3个下行触发）
6. 触发条件必须是可量化、可监控的指标
7. 输出必须覆盖本章的所有 must_answer 问题

输出格式：
## 投资判断
[看多/看空/中性] - [一句话理由]

## 论点质量评估
- 看多方: 数据支撑度 X%, 逻辑严密性 X%
- 看空方: 数据支撑度 X%, 逻辑严密性 X%

## 确信度
- 综合确信度: X% [高/中/低确信]
- 数据支撑度: X%
- 逻辑严密性: X%
- 预期差大小: X%

## 触发条件
### 上行触发（如果以下事件发生，提升确信度/加仓）
1. [具体可量化条件]
2. ...
3. ...
### 下行触发（如果以下事件发生，降低确信度/减仓）
1. [具体可量化条件]
2. ...
3. ...

## 最终分析
[综合正反双方的详细分析]
"""


# ====================================================================
# 辩论协调器
# ====================================================================

def run_debate(
    chapter_num: int,
    chapter_title: str,
    chapter_content: str,
    base_valuation_summary: str,
    llm_caller: Callable[[str, str], str],
    contract: Optional[dict] = None,
    llm_timeout_seconds: int = 60,  # 新增：超时参数
) -> DebateResult:
    """
    执行三角色辩论

    Args:
        chapter_num: 章节号
        chapter_title: 章节标题
        chapter_content: 章节初稿内容
        base_valuation_summary: 基础估值摘要
        llm_caller: LLM调用函数
        contract: 章节契约(包含must_answer等)
        llm_timeout_seconds: LLM调用超时秒数

    Returns:
        DebateResult 辩论结果
    """
    result = DebateResult()

    # === Step 1: Bull 看多论点 ===
    try:
        logger.info(f"[Debate] Step 1/3 Bull: 第{chapter_num}章 {chapter_title}")
        bull_prompt = _build_bull_prompt(
            chapter_num, chapter_title, chapter_content,
            base_valuation_summary, contract,
        )
        # 使用带超时的LLM调用
        result.bull_argument = llm_caller_with_timeout(
            llm_caller, f"bull_ch{chapter_num}", bull_prompt, llm_timeout_seconds
        )
        if len(result.bull_argument) < 100:
            raise ValueError(f"Bull output too short: {len(result.bull_argument)} chars")
        result.stages["bull"] = "ok"
    except LLMTimeoutError as e:
        logger.error(f"[Debate] Bull超时: {e}")
        result.stages["bull"] = "timeout"
        result.warnings.append(f"Bull超时: {e}")
    except Exception as e:
        logger.error(f"[Debate] Bull失败: {e}")
        result.stages["bull"] = "failed"
        result.warnings.append(f"Bull失败: {e}")

    # 部分成功降级：Bull 失败 → 该章辩论不可用（无论点可辩），标记跳过
    if result.stages["bull"] != "ok":
        result.degraded = True
        result.partial = False
        result.pm_synthesis = chapter_content  # 使用原始内容（兼容旧行为）
        return result

    # === Step 2: Bear 看空质疑 ===
    try:
        logger.info(f"[Debate] Step 2/3 Bear: 第{chapter_num}章 {chapter_title}")
        bear_prompt = _build_bear_prompt(
            chapter_num, chapter_title, result.bull_argument,
            base_valuation_summary, contract,
        )
        # 使用带超时的LLM调用
        result.bear_argument = llm_caller_with_timeout(
            llm_caller, f"bear_ch{chapter_num}", bear_prompt, llm_timeout_seconds
        )
        if len(result.bear_argument) < 100:
            raise ValueError(f"Bear output too short: {len(result.bear_argument)} chars")
        result.stages["bear"] = "ok"
    except LLMTimeoutError as e:
        logger.warning(f"[Debate] Bear超时: {e}")
        result.stages["bear"] = "timeout"
        result.warnings.append(f"Bear超时: {e}")
    except Exception as e:
        logger.warning(f"[Debate] Bear失败: {e}")
        result.stages["bear"] = "failed"
        result.warnings.append(f"Bear失败: {e}")

    # 部分成功降级：Bear 缺失 → 保留 Bull 论点（增强可用），标记 partial
    if result.stages["bear"] != "ok":
        result.partial = True
        result.degraded = True
        logger.warning(f"[Debate] Bear 缺失，使用 Bull 论点（部分辩论）")
        result.pm_synthesis = result.bull_argument  # 兼容：用 Bull 草稿
        return result

    # === Step 3: PM 综合判断 ===
    try:
        logger.info(f"[Debate] Step 3/3 PM: 第{chapter_num}章 {chapter_title}")
        pm_prompt = _build_pm_prompt(
            chapter_num, chapter_title,
            result.bull_argument, result.bear_argument,
            base_valuation_summary, contract,
        )
        # 使用带超时的LLM调用
        result.pm_synthesis = llm_caller_with_timeout(
            llm_caller, f"pm_ch{chapter_num}", pm_prompt, llm_timeout_seconds
        )
        if len(result.pm_synthesis) < 100:
            raise ValueError(f"PM output too short: {len(result.pm_synthesis)} chars")
        result.stages["pm"] = "ok"
    except LLMTimeoutError as e:
        logger.warning(f"[Debate] PM超时: {e}")
        result.stages["pm"] = "timeout"
        result.warnings.append(f"PM超时: {e}")
        # 部分成功降级：PM 缺失 → 用 Bull+Bear 自动裁决（不退回 Bull 草稿）
        result.partial = True
        result.degraded = True
        result.pm_synthesis = _auto_pm_synthesis(result)
    except Exception as e:
        logger.warning(f"[Debate] PM失败: {e}")
        result.stages["pm"] = "failed"
        result.warnings.append(f"PM失败: {e}")
        result.partial = True
        result.degraded = True
        result.pm_synthesis = _auto_pm_synthesis(result)

    # === 解析PM输出 ===
    _parse_pm_output(result)

    logger.info(
        f"[Debate] 完成: 第{chapter_num}章, "
        f"确信度={result.conviction_score:.0%}, "
        f"催化剂={len(result.catalysts)}个, "
        f"触发条件={len(result.triggers)}个, "
        f"stages={result.stages}, partial={result.partial}"
    )

    return result


def _auto_pm_synthesis(result: DebateResult) -> str:
    """PM 缺失时的自动裁决（规则判断，不退回 Bull 草稿）"""
    bear = result.bear_argument or ""
    bull = result.bull_argument or ""
    # Bear 含看空信号 → 看空倾向；否则看多
    bear_signals = ["高估", "风险", "漏洞", "质疑", "被忽略", "替代估值", "下行"]
    bear_hits = sum(1 for s in bear_signals if s in bear)
    if bear_hits >= 2:
        judgment = "看空"
        reason = f"看空质疑命中{bear_hits}个信号（高估/风险/漏洞/替代估值），自动裁决倾向看空"
    else:
        judgment = "看多"
        reason = f"看空质疑较弱（仅{bear_hits}个信号），自动裁决倾向看多"
    return (
        f"## 投资判断\n{judgment} - {reason}（PM 超时自动裁决，非人工权衡）\n\n"
        f"## 看多论点摘要\n{bull[:500]}\n\n"
        f"## 看空质疑摘要\n{bear[:500]}\n"
    )


# ====================================================================
# Prompt 构建
# ====================================================================

def _build_bull_prompt(
    chapter_num: int,
    chapter_title: str,
    chapter_content: str,
    valuation_summary: str,
    contract: Optional[dict],
) -> str:
    """构建看多分析师prompt"""
    must_answer = ""
    if contract and 'must_answer' in contract:
        must_answer = "\n## 必须回答的问题\n"
        for q in contract['must_answer']:
            must_answer += f"- {q}\n"

    return f"""{BULL_SYSTEM}

## 章节信息
- 章节: 第{chapter_num}章 {chapter_title}

## 当前估值水平
{valuation_summary}

## 现有分析内容
{chapter_content[:20000]}
{must_answer}
请基于以上信息，构建看多论点。"""


def _build_bear_prompt(
    chapter_num: int,
    chapter_title: str,
    bull_argument: str,
    valuation_summary: str,
    contract: Optional[dict],
) -> str:
    """构建看空分析师prompt"""
    return f"""{BEAR_SYSTEM}

## 章节信息
- 章节: 第{chapter_num}章 {chapter_title}

## 当前估值水平
{valuation_summary}

## 看多分析师的论点
{bull_argument[:3000]}

请逐条质疑看多论点，并给出替代估值。"""


def _build_pm_prompt(
    chapter_num: int,
    chapter_title: str,
    bull_argument: str,
    bear_argument: str,
    valuation_summary: str,
    contract: Optional[dict],
) -> str:
    """构建PM综合判断prompt"""
    must_answer = ""
    if contract and 'must_answer' in contract:
        must_answer = "\n## 必须覆盖的问题\n"
        for q in contract['must_answer']:
            must_answer += f"- {q}\n"

    return f"""{PM_SYSTEM}

## 章节信息
- 章节: 第{chapter_num}章 {chapter_title}

## 当前估值水平
{valuation_summary}

## 看多论点
{bull_argument[:2000]}

## 看空质疑
{bear_argument[:2000]}
{must_answer}
请权衡正反双方，给出最终投资判断。"""


# ====================================================================
# 输出解析
# ====================================================================

def _parse_pm_output(result: DebateResult) -> None:
    """解析PM输出，提取确信度、催化剂、触发条件"""
    import re

    pm = result.pm_synthesis

    # 提取确信度
    conviction_match = re.search(r'综合确信度[：:]\s*(\d+)\s*%', pm)
    if conviction_match:
        result.conviction_score = int(conviction_match.group(1)) / 100

    # 提取确信度构成
    data_match = re.search(r'数据支撑度[：:]\s*(\d+)\s*%', pm)
    if data_match:
        result.conviction_breakdown['data'] = int(data_match.group(1)) / 100

    logic_match = re.search(r'逻辑严密性[：:]\s*(\d+)\s*%', pm)
    if logic_match:
        result.conviction_breakdown['logic'] = int(logic_match.group(1)) / 100

    gap_match = re.search(r'预期差大小[：:]\s*(\d+)\s*%', pm)
    if gap_match:
        result.conviction_breakdown['expectation_gap'] = int(gap_match.group(1)) / 100

    # 提取催化剂（从Bull输出中）
    catalyst_section = re.search(r'催化剂[：:]\s*\n((?:- .+\n)+)', result.bull_argument)
    if catalyst_section:
        result.catalysts = [
            line.strip('- ').strip()
            for line in catalyst_section.group(1).strip().split('\n')
            if line.strip()
        ]

    # 提取触发条件
    trigger_section = re.search(r'### (?:上行|下行)触发.*?\n((?:\d+\. .+\n)+)', pm)
    if trigger_section:
        result.triggers = [
            re.sub(r'^\d+\.\s*', '', line).strip()
            for line in trigger_section.group(1).strip().split('\n')
            if line.strip()
        ]

    # 提取投资论点摘要
    thesis_match = re.search(r'投资判断\s*\n(.+?)(?:\n\n|\n##)', pm, re.DOTALL)
    if thesis_match:
        result.investment_thesis = thesis_match.group(1).strip()

    # 提取最大风险
    risk_match = re.search(r'被忽略的关键风险.*?\n(?:- .+\n)*- (.+)', result.bear_argument)
    if risk_match:
        result.key_risk = risk_match.group(1).strip()
