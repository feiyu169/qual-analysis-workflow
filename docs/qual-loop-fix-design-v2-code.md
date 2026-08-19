# qual v8 死循环修复——修订后代码设计（v2，按 HeavySkill 审查 18 项逐项修正）

日期：2026-08-19
依据：`docs/qual-loop-fix-design.md`（原方案，504 行）+ `docs/heavyskill-fix-review.md`（审查报告，18 项修正清单）
范围：对原方案**代码层面**的逐项修订。所有行号均已对照当前源码逐行核对（核对时间 2026-08-19），引用格式为 `文件:行号`。

## 0. 行号基准（已核对）

| 文件 | 关键锚点（行号 = 当前源码真实行号） |
|---|---|
| `tools/finance/harness_llm.py`（131 行） | 签名 63-72；`llm_caller` 87-124；重试循环 101-123；分类 104-118；通用 except 119-123 |
| `tools/finance/workflow.py`（legacy，3158 行） | `_generate_chapter` 签名 1156-1161；外层格式重试 1183-1241；吞异常 1237-1241；legacy 调用 `review_and_repair_loop` 2942-2949 |
| `tools/finance/qual_v8/gates/gate3.py` | `from ...workflow import _build_chapter_prompt, _generate_chapter` 164；调用 183（v8 写作复用 legacy `_generate_chapter`） |
| `tools/finance/qual_v8/workflow.py`（411 行） | import 17；`WorkflowConfig` 34-40；`execute` 212-400；Gate 循环 241-363；重试 258-311（`max_attempts` 260）；熔断分类 301-305；results 组装 315-321；enforce 阻断 350-359；report 组装 365-374；终态 377-380；熔断阈值 181 |
| `tools/finance/qual_v8/gates/gate4.py`（346 行） | `_substantive_review` 222-280；**fail-open 226-228**；loop 调用 257-265；结果组装 267-277；**异常吞 278-280**；chapters 写回 110-115 |
| `tools/finance/quality/review_repair_loop.py`（410 行） | `ReviewRepairResult` 20-28；签名 31-38；主循环 53-111（循环体 56-101）；审查 63-68；通过 71-80；无 caller 86-95；修复 98；达上限 102-111；`_run_substantive_review` 171-264（caller 构造 182-197；检查器 199-233；**debate 235-262**）；`_repair_chapters` 267-410（LLM 调用 356；**吞异常 407-408**） |
| `tools/finance/quality/depth_reviewer.py`（369 行） | `DepthReviewResult` 31-37；`check` 94-192（LLM 评估 139-142）；`_evaluate_by_llm` 224-261（LLM 调用 248；评分解析 250-252；**吞异常 259-261**）；`_parse_llm_score` 263-283（**默认 50 分 283**） |
| `tools/finance/quality/conclusion_validator.py` | LLM 调用 392；**吞异常 404-405** |
| `tools/finance/qual_v8/core/circuit_breaker.py`（108 行） | `ErrorType` **24-28**；init 34-49；`record_failure` **51-58**（TRANSIENT 0.5 权重 56） |
| `tools/finance/qual_v8/core/error_classifier.py`（114 行） | `ErrorType` **15-19**；`ERROR_CODE_MAPPING` **34-67**；`classify` 76-97；`classify_from_exception` **99-114** |
| `run_xpev_full.py` | import 152-153；状态 155-159；初始化 161-175；**fallback 177-197**；赋值 199 |
| `run_qual_full.py` | 状态 68-72；初始化 74-90；**fallback 92-113**；赋值 115 |
| `plugins/llm-bridge.js`（73 行） | stream 53-63；**finishReason 56-64**（已返回，改动7 = no-op） |

---

## 一、逐项修订表（18 项）

### P0-A：fail-open 堵漏（3 项，最先实施）

---

#### 缺陷 1（P0-A-1）：豁免 → `passed=True` 静默放行 + 豁免学习无证据护栏

**缺陷实证**：原方案 5b 中 R3 轮豁免剔除后 `not round_issues → passed=True`（原方案第 107 行判据），即使问题从未修复也会"静默通过"；且豁免只需"同签名跨轮 ≥2 次"即入清单，无证据护栏。

**修正策略（三件套）**：
1. 收敛判据改为"豁免非空即 fail"：`remaining_issues` 强制计入豁免项（打 `[已豁免N轮]` 标），`passed=False` + 降级标记；
2. 豁免学习加证据护栏：同签名出现 **≥3 轮** 且 **从未被成功修复**（签名差集追踪 `fixed_sigs`）才入豁免；豁免清单随 `ReviewRepairResult` 返回 → gate4 写入 context → 报告打标 + 审计；
3. 签名保留章节号（与缺陷 16 联动，见下）。

**修正后代码**（`tools/finance/quality/review_repair_loop.py`，改造主循环 53-111）：

```python
# --- 模块级常量（新增，置于 logger 定义之后）---
import time as _time
import copy as _copy
from ..llm_errors import (
    DeterministicLLMFailure, LLMCallBudgetExceeded, WallClockDeadlineExceeded,
)

EXEMPT_MIN_ROUNDS = 3          # 证据护栏：同签名至少出现 3 轮
REVIEW_INCOMPLETE_PREFIX = "[审查不完整]"
```

```python
# --- ReviewRepairResult（20-28 行，追加带默认值字段，兼容 legacy workflow.py:2942 消费方）---
@dataclass
class ReviewRepairResult:
    passed: bool
    rounds: int
    chapters: Dict[int, str]
    issues_found: int
    issues_fixed: int
    remaining_issues: List[str]
    # ---- 新增（全部带默认值，旧调用不传也安全）----
    llm_calls: int = 0                 # 本 Gate 真实 LLM 调用次数（预算审计）
    exempted_count: int = 0            # 豁免问题数（报告标 + 审计）
    exempted: List[str] = field(default_factory=list)   # 豁免清单（审计可见）
    review_incomplete: bool = False    # 审查不完整（检查器 LLM 失败）
    wall_clock_exceeded: bool = False
    budget_exceeded: bool = False
```

```python
# --- 主循环收敛判定段（改造 71-80 行附近；伪代码体现判定顺序）---
    for round_num in range(1, max_rounds + 1):
        ...
        round_issues = deep_issues + substantive_issues          # 全量审查（口径 A）

        # 2. 豁免剔除 + 证据护栏（替换原"2 次即豁免"逻辑）
        kept = []
        for iss in round_issues:
            sig = _issue_signature(iss)                          # 保留章节号（缺陷 16）
            entry = exempted.setdefault(sig, {"rounds": 0, "fixed_ever": False,
                                              "exempted": False, "first_seen": round_num})
            entry["rounds"] += 1
            if entry["exempted"]:
                exempted_tracked.add((sig, iss))                 # 豁免项仍计入 remaining
                continue
            kept.append(iss)
        round_issues = kept

        # 3. 收敛判定（P0-A-1：豁免非空即 fail）
        if not round_issues and not exempted_tracked:
            return _ok_result(round_num, chapters, budget_state)          # 真通过
        if not round_issues and exempted_tracked:
            # 问题全部被豁免 → 不允许静默通过：问题未真实修复
            remaining = [f"[已豁免{entry['rounds']}轮] {iss}"
                         for sig, iss in exempted_tracked
                         for entry in [exempted[sig]]][:10]
            return _fail_result(round_num, chapters, budget_state,
                                remaining=remaining,
                                exempted_count=len(exempted_tracked),
                                exempted=sorted({sig for sig, _ in exempted_tracked}))
        ...
        # 5. 豁免学习（证据护栏：≥3 轮 + 无修复迹象，置于修复与单调守卫之后）
        for sig, entry in exempted.items():
            if (entry["rounds"] >= EXEMPT_MIN_ROUNDS
                    and sig not in fixed_sigs                    # 从未被成功修复
                    and not entry["exempted"]):
                entry["exempted"] = True
                entry["exempted_at_round"] = round_num
                logger.warning(f"豁免学习：签名 {sig} 出现 {entry['rounds']} 轮且无修复迹象，加入豁免清单（审计可见）")
                # 审计：清单经 ReviewRepairResult.exempted 返回 → gate4 写 context → workflow 审计日志
```

**接口签名**（无签名变化；`_issue_signature` 修订见缺陷 16）。

**副作用**：豁免门槛从 2 轮提到 3 轮 + 无修复迹象 → 默认 `max_rounds=3` 下几乎不触发豁免，豁免主要服务于 audit 可见性；不会引入新异常（全部为返回分支）。

**验收单测**：`test_exemption_failclosed`（`tools/finance/quality/test_loop_fix.py`）：fake caller 前 3 轮返回同签名 issue、第 4 轮返回空 → `max_rounds=4` 时断言 `passed is False`、`remaining_issues` 含 `[已豁免` 前缀、`exempted_count >= 1`（失败方向：旧代码返回 `passed=True`）。

---

#### 缺陷 2（P0-A-2）：`gate4.py:226-228` `llm_caller=None → passed=True` 第二条 fail-open

**缺陷实证**：审查报告实证 2。`_substantive_review` 无 caller 时返回 `{"passed": True}`，Gate4 静默通过。同时 `278-280` 行 `except Exception` 也返回 `passed=True`（原方案 4a 声称"fail-closed"但**实际代码仍是 fail-open**，属同源缺陷，一并修复）。

**修正后代码**（`tools/finance/qual_v8/gates/gate4.py`）：

```python
# --- 222-228 行改造 ---
    def _substantive_review(self, chapters: Dict[int, str], context: Dict[str, Any]) -> Dict[str, Any]:
        """实质审查（真实：quality.review_and_repair_loop，含锚点注入）"""
        errors = []

        llm_caller = context.get("llm_caller")
        if llm_caller is None:
            # P0-A-2：无 caller 不再静默放行（fail-closed）
            return {"passed": False,
                    "errors": ["无 llm_caller，实质审查无法执行（fail-closed）"],
                    "repaired_chapters": None}
```

```python
# --- 278-280 行改造（异常同样 fail-closed，堵住原方案 4a 声称但未实现的缺口）---
        except DeterministicLLMFailure as e:
            logger.error(f"Gate4 实质审查确定性失败: {e}")
            return {"passed": False, "errors": [f"实质审查确定性失败: {e}"],
                    "repaired_chapters": None}
        except Exception as e:
            logger.error(f"Gate4 实质审查失败: {e}")
            return {"passed": False, "errors": [f"实质审查异常: {e}"],
                    "repaired_chapters": None}
```

**副作用**：`execute()` 114-115 行 `if not substantive_result["passed"]: errors.extend(...)` 自动承接；shadow 模式不阻断（`qual_v8/workflow.py:350-359` 仅 enforce 阻断），但报告打"未修复"标（缺陷 8 修订后 `_fill_failed_gates`/打标逻辑覆盖）。

**验收单测**：`test_gate4_no_caller_failclosed`（`tools/finance/qual_v8/gates/test_gate4_fix.py`）：`_substantive_review({}, {"llm_caller": None})` 返回 `passed is False`；异常路径：monkeypatch `review_and_repair_loop` 抛 `RuntimeError` → 返回 `passed is False` 且 `errors` 非空。

---

#### 缺陷 3（P0-A-3）：检查器吞 `DeterministicLLMFailure` + 默认 50 分放水

**缺陷实证**：`depth_reviewer.py:259-261` `except Exception` 吞掉 LLM 深度审查的一切失败；`depth_reviewer.py:283` 解析失败默认返回 50 分（"中等"→ 可能恰好跨过 60 分阈值或制造假阳性）；`review_repair_loop.py:214/223/232`（深度/结论/假设检查器）同样 `except Exception` 吞；另核对发现 `conclusion_validator.py:404-405` 也吞（审查报告未点名但属同源，一并修）。

**修正策略**：
- 确定性/预算/超时三类异常（`DeterministicLLMFailure/LLMCallBudgetExceeded/WallClockDeadlineExceeded`）→ **上抛**，由主循环转"审查不完整"失败项并终止（修复会重复同一失败，故不进入修复）；
- 其它异常 → 转"审查不完整"失败项（`[审查不完整] 检查器名: ...`），**不再静默**；
- `_parse_llm_score` 解析失败 → 返回 `None`（"失败不评分"），`_evaluate_by_llm` 置 `llm_failed=True`，`DepthReviewResult` 新增 `llm_failed` 字段，由 `_run_substantive_review` 消费。

**修正后代码**（`tools/finance/quality/depth_reviewer.py`）：

```python
# --- 31-37 行 DepthReviewResult 追加字段 ---
@dataclass
class DepthReviewResult:
    passed: bool
    issues: List[DepthIssue] = field(default_factory=list)
    score: float = 100.0
    chapter_scores: Dict[int, int] = field(default_factory=dict)
    llm_failed: bool = False        # 新增：LLM 深度评估失败（未评分）
```

```python
# --- _evaluate_by_llm（224-261 行）改造：返回三元组 (score, issues, llm_failed) ---
    def _evaluate_by_llm(self, content, ch_num, llm_caller, wind_anchor="") -> tuple:
        issues = []
        segments = _split_for_review(content, max_chars=20000)
        scores = []
        try:
            for seg in segments:
                ...
                response = llm_caller(f"depth_review_ch{ch_num}", prompt)
                score = self._parse_llm_score(response)          # 283 行改为可能返回 None
                if score is not None:
                    scores.append(score)
                issues.extend(self._parse_llm_issues(response, ch_num))
        except (DeterministicLLMFailure, LLMCallBudgetExceeded, WallClockDeadlineExceeded):
            raise                                              # P0-A-3：确定性/预算/超时上抛
        except Exception as e:
            logger.warning(f"LLM深度审查失败: {e}")
            return None, [], True                               # 审查不完整（不再静默）
        if not scores:
            return None, issues, True                           # 无有效评分 → 审查不完整
        return min(scores), issues, False
```

```python
# --- _parse_llm_score（263-283 行）改造：解析失败返回 None，删除"默认 50" ---
    def _parse_llm_score(self, response: str):
        total_pattern = r"总分[：:]\s*(\d+)"
        match = re.search(total_pattern, response)
        if match:
            return int(match.group(1))
        scores = []
        for dimension in self.depth_dimensions.keys():
            match = re.search(f"{dimension}[：:]\\s*(\\d+)", response)
            if match:
                scores.append(int(match.group(1)))
        if scores:
            return int(sum(scores) / len(scores))
        return None          # 原 283 行 return 50 → 失败不评分（P0-A-3）
```

```python
# --- check()（134-165 行附近）消费三元组 ---
        for ch_num, content in chapters.items():
            keyword_score = self._evaluate_by_keywords(content)
            llm_score, llm_issues, llm_failed = (None, [], False)
            if llm_caller:
                llm_score, llm_issues, llm_failed = self._evaluate_by_llm(content, ch_num, llm_caller, wind_anchor)
            if llm_failed:
                llm_any_failed = True                            # 结果打标
            ...
        return DepthReviewResult(passed=passed, issues=issues, score=score,
                                 chapter_scores=chapter_scores,
                                 llm_failed=llm_any_failed)      # 187-192 行
```

```python
# --- conclusion_validator.py:404-405 改造（同源吞异常）---
        except (DeterministicLLMFailure, LLMCallBudgetExceeded, WallClockDeadlineExceeded):
            raise
        except Exception as e:
            logger.warning(f"LLM结论审查失败: {e}")
```
（顶部补 `from ..llm_errors import DeterministicLLMFailure, LLMCallBudgetExceeded, WallClockDeadlineExceeded`。）

```python
# --- review_repair_loop.py 检查器调用段（199-233 行）改造为统一守卫 ---
    # 2. 分析深度审查（LLM 检查器：确定性失败必须上抛）
    try:
        from .depth_reviewer import check_depth
        result = check_depth(chapters, review_caller, wind_data)
        if getattr(result, "llm_failed", False):
            issues.append(f"{REVIEW_INCOMPLETE_PREFIX} 分析深度 LLM 评估失败（未评分）")
        elif not result.passed:
            issues.extend([f"[分析深度] {issue.description}" for issue in result.issues])
    except (DeterministicLLMFailure, LLMCallBudgetExceeded, WallClockDeadlineExceeded):
        raise
    except Exception as e:
        issues.append(f"{REVIEW_INCOMPLETE_PREFIX} 分析深度审查失败: {e}")
    # 3. 结论合理性审查（同型守卫；原 218-224 行）
    # 4. 假设合理性审查（纯规则检查器：无确定性失败风险，仅"不完整"化；原 226-233 行）
    # 1. 事实核查（纯规则检查器，同 4）
```

```python
# --- 主循环消费"审查不完整"（56-101 行，审查调用之后立即短路，避免进入无谓修复）---
        try:
            substantive_issues = _run_substantive_review(
                chapters, repair_caller, wind_data, industry,
                enable_debate=enable_debate,
                budget_state=budget_state, deadline=deadline, llm_call_budget=llm_call_budget,
            )
        except (DeterministicLLMFailure, LLMCallBudgetExceeded, WallClockDeadlineExceeded) as e:
            return _fail_result(round_num, chapters, budget_state,
                                remaining=[f"{REVIEW_INCOMPLETE_PREFIX} {e}"],
                                review_incomplete=True,
                                budget_exceeded=isinstance(e, LLMCallBudgetExceeded),
                                wall_clock_exceeded=isinstance(e, WallClockDeadlineExceeded))
        if any(i.startswith(REVIEW_INCOMPLETE_PREFIX) for i in substantive_issues):
            return _fail_result(round_num, chapters, budget_state,
                                remaining=substantive_issues[:10], review_incomplete=True)
```

**副作用**：`REVIEW_INCOMPLETE_PREFIX` 在 `_run_substantive_review` 与主循环共享（模块常量）；"审查不完整"是终止性失败项，不进入修复（修复会重复失败）；`_run_deep_review`（114-168 行）5 个检查器为**纯规则**（无 LLM），无确定性失败风险，保持"异常降级 warning"不变（改动范围控制，文档注明）。

**验收单测**：`test_review_incomplete`：fake `llm_caller` 抛 `RuntimeError` → `check_depth` 返回 `llm_failed=True` 且 **无默认 50 分**（`_parse_llm_score("无分数文本") is None`）；loop 返回 `review_incomplete=True`、`remaining` 含 `[审查不完整]`。

---

### P0-B：止血修正（8 项）

---

#### 缺陷 4（P0-B-4）：`_generate_chapter`（`tools/finance/workflow.py:1183-1241`）外层 except 吞确定性失败并重试 3 次

**缺陷实证**：审查报告实证 3。`1237-1241` `except Exception` 把 `DeterministicLLMFailure` 当普通失败重试 3 次（每次 300s 超时），且 v8 引擎 Gate3 写作（`qual_v8/gates/gate3.py:164,183`）**复用同一函数**，故 6 小时死循环的主要吞点在此。

**修正后代码**（`tools/finance/workflow.py`）：

```python
# --- 模块顶部 import 区补（tools/finance/workflow.py，约 20-40 行之间）---
from .llm_errors import DeterministicLLMFailure
```

```python
# --- 1237-1241 行改造：确定性失败短路 + 降级区分（先于通用 except）---
            except DeterministicLLMFailure as e:
                # P0-B-4：确定性失败（空输出/预算耗尽）不重试，立即降级
                # 区分语义：格式/闸门失败可重试（119-128 行原逻辑），确定性失败不可重试
                logger.error(f"{chapter_name} 确定性失败，不重试: {e}")
                return _build_insufficient_data_response(chapter_num, ctx, f"确定性失败: {e}")
            except Exception as e:
                logger.error(f"LLM 调用失败 {chapter_name}: {e}")
                if attempt == max_format_retries:
                    return _build_insufficient_data_response(chapter_num, ctx, str(e))
```

**副作用**：legacy 与 v8 Gate3 双路径同时受益；降级响应文本带原因（`_build_insufficient_data_response` 已接收 `reason` 参数，1241 行既有用法），shadow 模式报告打"未修复"标兜底。

**验收单测**：`test_generate_chapter_deterministic_no_retry`（`tools/finance/test_workflow_fix.py`）：fake `llm_caller` 抛 `DeterministicLLMFailure` 且计数 → 返回降级响应、**调用次数 == 1**（旧代码为 4 次）。

---

#### 缺陷 5（P0-B-5）：确定性失败无消费策略（直连/换模型单次 → 降级+打标；补 import）

**缺陷实证**：审查报告实证 4。原方案改动 6 引用 `DeterministicLLMFailure` 但两个 run 脚本均无 import（NameError）；且 fallback 切换只检查成功分支后的失败历史（`run_xpev_full.py:182` 成功才清零），确定性失败时 `_fail_count` 不涨也不切。

**修正策略**：新增 `tools/finance/llm_fallback.py` 提供可复用装饰器 `with_fallback`（同时服务缺陷 11 的审查 caller），语义：
- 确定性失败 → **直连/换模型单次重试**（同模型绝不重试——由 harness_llm 层保证）；直连也失败 → **抛原异常**（上层降级+打标）；
- 滑动窗口（最近 8 次中失败 ≥4 → 切直连），成功不清零（K4）；
- 降级输出可打标（`degrade_marker` 追加 HTML 注释标记）。

```python
# ============ 新增文件 tools/finance/llm_fallback.py ============
# -*- coding: utf-8 -*-
"""LLM fallback 装饰器：桥接优先、确定性失败换模型单次、滑动窗口降级（run 脚本与审查 caller 共用）"""
from typing import Callable, Optional
from .llm_errors import DeterministicLLMFailure


def with_fallback(
    primary: Callable[[str, str], str],
    fallback_factory: Callable[[], Callable[[str, str], str]],
    *,
    switch_on_deterministic: bool = True,   # 确定性失败也切直连单次重试（换模型）
    window: int = 8,                        # 滑动窗口长度（K4：成功不清零）
    fail_threshold: int = 4,                # 窗口内失败 ≥4 → 切直连
    degrade_marker: Optional[str] = None,   # 降级输出追加的标记（如 "<!-- ⚠️ 已降级直连 -->"）
) -> Callable[[str, str], str]:
    """返回带降级的 llm_caller(chapter_name, prompt) -> str。"""
    hist: list = []
    direct: Optional[Callable[[str, str], str]] = None

    def _trim():
        if len(hist) > window:
            del hist[:-window]

    def _switch():
        nonlocal direct
        if direct is None:
            direct = fallback_factory()          # 换模型（deepseek-chat ≠ 桥接 deepseek-v4-flash）

    def caller(chapter_name: str, prompt: str) -> str:
        nonlocal direct
        try:
            text = primary(chapter_name, prompt)
            hist.append(False); _trim()          # 成功不清零（K4）
            return text
        except DeterministicLLMFailure as e:
            # 确定性失败：换模型单次重试；仍败 → 抛原异常（上层降级+打标）
            hist.append(True); _trim()
            try:
                _switch()
                if direct is not None:
                    out = direct(chapter_name, prompt)
                    return out + (degrade_marker or "")
            except Exception:
                pass
            raise
        except Exception:
            # 瞬态失败：窗口降级 + 已切换时走直连
            hist.append(True); _trim()
            if sum(hist) >= fail_threshold or direct is not None:
                _switch()
                if direct is not None:
                    return direct(chapter_name, prompt)
            raise
    return caller
```

**接口签名**：`with_fallback(primary, fallback_factory, *, switch_on_deterministic=True, window=8, fail_threshold=4, degrade_marker=None) -> Callable[[str,str], str]`（新函数）。

**run 脚本接线**（`run_xpev_full.py:151-199` / `run_qual_full.py:67-115`，两文件同步）：

```python
# run_xpev_full.py 151-153 行改造（补 import）
    from finance.harness_llm import create_harness_caller
    from finance.llm_caller import create_deepseek_caller
    from finance.llm_fallback import with_fallback          # 新增（缺陷 11 补 import）

# 177-197 行 _llm_with_fallback 整体替换为装饰器调用：
    llm_caller = with_fallback(
        _orig_caller,
        lambda: create_deepseek_caller(model="deepseek-chat"),
        degrade_marker="\n\n<!-- ⚠️ 已降级直连（桥接失败/确定性失败） -->",
    )
    log(f"LLM 路由: harness_bridge（确定性/瞬态失败自动切直连，滑动窗口 {with_fallback.__defaults__}）")
```

**副作用**：`_llm_with_fallback` 闭包删除（无其它引用，grep 确认仅两 run 脚本定义）；直连也失败时抛回**原确定性异常**（不是直连异常），保证上层按确定性语义降级；`degrade_marker` 默认 None（审查 caller 用 None，避免污染审查输出解析，见缺陷 11）。

**验收单测**：`test_fallback_deterministic_switch`（`tools/finance/test_llm_fallback.py`）：primary 抛 `DeterministicLLMFailure` → 结果含直连文本且带 marker；primary 恢复成功 → 不再切（历史保留）。

---

#### 缺陷 6（P0-B-6）：单调守卫（deepcopy 快照 + 签名差集 + 前后同口径）

**缺陷实证**：原方案 5b 用 `chapters.update(_snapshot_before_round)`（浅恢复、无快照定义）；判据仅 `after > before`（漏"问题数相同但换新问题"）；"修复前"与"修复后"口径不一致风险（前者用"本轮审查出的问题"，后者用"重审问题"——两者必须同为全量审查结果）。

**修正后代码**（`tools/finance/quality/review_repair_loop.py` 主循环 56-101 行，修复段）：

```python
        # 4. 修复（单调性守卫：deepcopy 快照 + 签名差集 + 前后同口径）
        snapshot = _copy.deepcopy(chapters)                    # 轮首 deepcopy 快照
        before_sigs = {_issue_signature(i) for i in round_issues}
        before_count = len(round_issues)
        try:
            fixed_count = _repair_chapters(chapters, round_issues, repair_caller, wind_data)
        except (DeterministicLLMFailure, LLMCallBudgetExceeded, WallClockDeadlineExceeded) as e:
            return _fail_result(round_num, chapters, budget_state,
                                remaining=[f"{REVIEW_INCOMPLETE_PREFIX} 修复失败: {e}"],
                                review_incomplete=True, ...)
        issues_fixed += fixed_count

        # 修复后重审：与轮首完全同口径（deep + substantive，同一 budget_state/deadline）
        after_issues = (_run_deep_review(chapters, wind_data)
                        + _run_substantive_review(chapters, repair_caller, wind_data, industry,
                                                  enable_debate=enable_debate,
                                                  budget_state=budget_state,
                                                  deadline=deadline,
                                                  llm_call_budget=llm_call_budget))
        after_sigs = {_issue_signature(i) for i in after_issues}
        new_sigs = after_sigs - before_sigs
        if len(after_issues) > before_count or new_sigs:
            # 问题总数上升 或 出现修复前不存在的新签名 → 回滚本轮全部 patch
            logger.warning(
                f"单调性守卫：问题数 {before_count}→{len(after_issues)}，"
                f"新签名 {sorted(new_sigs)[:3]}，回滚本轮修复")
            chapters.clear()
            chapters.update(snapshot)                          # deepcopy 快照恢复
            fixed_count = 0
            issues_fixed -= fixed_count                        # 回滚后计数同步还原
        fixed_last_round = fixed_count
        prev_issue_count = before_count
        # 追踪"从未被修复"签名（供豁免证据护栏）：
        for sig in before_sigs - after_sigs:
            fixed_sigs.add(sig)
```

**副作用**：单调守卫的 after 重审每次调用 LLM → 调用计数真实递增（缺陷 7 的 budget_state 覆盖）；`fixed_sigs` 供缺陷 1 豁免护栏使用；回滚后 `chapters` 恢复为轮首 deepcopy，后续轮从干净状态继续。

**验收单测**：`test_monotonic_guard`：fake caller 第 1 轮修复后使 chapter 出现**新签名问题**（`after` 含 `before` 没有的签名）→ 断言 `chapters` 等于轮首快照、`issues_fixed` 不增。

---

#### 缺陷 7（P0-B-7）：`_budgeted_caller` 死代码 → 修复/审查调用全走预算包装，计数真实递增

**缺陷实证**：原方案 5d 定义了 `_budgeted_caller` 但主循环从未使用（审查报告"悬空接线"典型）；且原计数方案每次调用都重置，无法统计真实调用数。

**修正策略**：loop 内建统一计数状态 `budget_state = {"calls": 0}`，`_make_budgeted_caller` 包装**所有** LLM 调用（修复 + 审查 depth/conclusion/debate），超预算抛 `LLMCallBudgetExceeded`（新异常，禁止被吞——见缺陷 3 的 except 白名单）；loop 结束时 `result.llm_calls = budget_state["calls"]` → gate4 写回 `context["_llm_call_count"]` → workflow 审计。

**修正后代码**（`tools/finance/quality/review_repair_loop.py` 新增模块级工厂）：

```python
def _make_budgeted_caller(
    base_caller: Optional[Callable[[str, str], str]],
    budget_state: Dict[str, int],
    deadline: Optional[float],
    llm_call_budget: Optional[int],
) -> Optional[Callable[[str, str], str]]:
    """预算/墙钟包装：每次调用前查 deadline、计数递增、超预算抛 LLMCallBudgetExceeded。"""
    if base_caller is None:
        return None
    def budgeted(name: str, prompt: str) -> str:
        if deadline is not None and _time.monotonic() > deadline:
            raise WallClockDeadlineExceeded(f"墙钟预算耗尽（deadline={deadline:.0f}）")
        budget_state["calls"] += 1                          # 计数真实递增
        if llm_call_budget is not None and budget_state["calls"] > llm_call_budget:
            raise LLMCallBudgetExceeded(
                f"Gate4 LLM 调用次数超预算（>{llm_call_budget}，第 {budget_state['calls']} 次）")
        return base_caller(name, prompt)
    return budgeted
```

```python
# --- 主循环入口（56 行前）：统一包装 + 全链透传 ---
    budget_state: Dict[str, int] = {"calls": 0}
    repair_caller = _make_budgeted_caller(llm_caller, budget_state, deadline, llm_call_budget)
    # 修复调用（98 行）：_repair_chapters(chapters, round_issues, repair_caller, wind_data)
    # 审查调用（67 行）：_run_substantive_review(..., repair_caller, ..., budget_state=budget_state, ...)
    #   → 审查专用 caller 内部同样经 _make_budgeted_caller 包同一 budget_state（见缺陷 11）
    # 退出路径统一：result.llm_calls = budget_state["calls"]
```

**接口签名**：`_make_budgeted_caller(base_caller, budget_state, deadline, llm_call_budget) -> Callable`（模块私有）。

**副作用**：`LLMCallBudgetExceeded` 必须出现在所有 `except Exception` 之前的白名单（已列入缺陷 3/4/6/11 的 raise 分支）；超预算即终止（不再吞着空转）。

**验收单测**：`test_budget_deadline`：`llm_call_budget=2` → 第 3 次调用后 loop 终止，断言 `result.llm_calls == 3`、`budget_exceeded is True`、fake caller 未被第 4 次调用。

---

#### 缺陷 8（P0-B-8）：墙钟预算只查 Gate 边界 → deadline 注入调用层 + 轮顶检查；修 break 后 results/打标

**缺陷实证**：原方案 3b 只在 Gate 循环顶部查墙钟；且 `break` 直接跳出 for 后 `results` 缺后续 Gate 条目 → `qual_v8/workflow.py:377` `all(r["passed"] for r in results.values())` 对**残缺 dict 空转**（漏判 fail），打标逻辑（3d）也依赖完整 results。

**修正策略**：
1. `execute()` 顶部计算**全局 deadline**（`time.monotonic()` 绝对值）注入 `context["_wall_deadline"]` → gate4 → loop（轮顶 + 单调用前，缺陷 7 的 budgeted caller 内已含调用前检查）；
2. 新增 `_fill_failed_gates` 在 break 前补全当前及后续 Gate 的失败条目（堵 `all()` 空转 fail-open）；
3. 打标移到 report 组装后统一执行（覆盖所有失败路径）。

**修正后代码**（`tools/finance/qual_v8/workflow.py`）：

```python
# --- execute() 顶部（223-224 行后）---
        _wall_start = _time.monotonic()
        _wall_deadline = _wall_start + self.config.global_timeout_seconds
        context["_wall_deadline"] = _wall_deadline            # 注入 gate4（缺陷 8）
        context["_llm_call_count"] = 0                        # 审计（缺陷 7 写回点）
        context["llm_call_budget"] = self.config.max_llm_calls_per_gate
        policy = RETRY_POLICY.get(qual_mode, RETRY_POLICY["shadow"])   # 缺陷 13
        context["shadow_skip_repair"] = policy["skip_repair"] and self.config.shadow_skip_repair
        context["gate4_max_rounds"] = policy["repair_rounds"]
```

```python
# --- 241 行 Gate 循环顶部：墙钟检查 + break 前补全 results（修复原 3b 缺口）---
        for gate_num in range(9):
            if _time.monotonic() > _wall_deadline:
                logger.error(f"全局墙钟预算耗尽（{_time.monotonic()-_wall_start:.0f}s），强制终止")
                _fill_failed_gates(results, gate_num, reason="全局墙钟预算耗尽")   # 补全本 Gate 及后续
                break
            _gate_start = _time.monotonic()

# --- 模块级辅助（新增）---
def _fill_failed_gates(results: Dict[str, Any], from_gate: int, reason: str) -> None:
    """补全 from_gate..8 的失败条目：堵 results 残缺导致 all() 空转 fail-open。"""
    for g in range(from_gate, 9):
        results.setdefault(f"gate_{g}", {
            "passed": False, "score": 0.0, "execution_time": 0.0,
            "errors": [reason], "check_criteria_passed": False,
        })
```

```python
# --- 365-374 行 report 组装之后：统一打标（含豁免数，缺陷 1 的"报告标"）---
        failed_gates = [g for g, r in results.items() if not r["passed"]]
        if failed_gates:
            _marker = (
                f"\n\n<!-- ⚠️ 质量状态：以下 Gate 未通过：{failed_gates}。"
                f"部分章节可能未完成审查/修复，数字未经最终验证。"
                f"（Gate4 豁免问题数：{context.get('_exempted_count', 0)}） -->\n"
            )
            context["report"] = (context.get("report") or "") + _marker
            context["quality_degraded"] = True
```

**副作用**：`_fill_failed_gates` 保证 `results` 恒有 9 条 → `377` 行 `all()` 语义正确；`_wall_deadline` 为单调时钟绝对值，loop 与 budgeted caller 直接比较。

**验收单测**：`test_wall_clock_break_fills_results`：monkeypatch `_time.monotonic` 使 Gate 1 后超时 → 断言 `results` 含 9 条、`results["gate_8"]["passed"] is False`、report 含 `质量状态` 标记。

---

#### 缺陷 9（P0-B-9）：D9 辩论无条件运行 → `enable_debate=False` 门控 `review_repair_loop.py:235-262`

**缺陷实证**：审查裁决 (b)：`235-262` 对抗性辩论无条件执行，3 关键章 × 3 角色 × 240s 超时 ≈ 72 分钟/轮，直接击穿 30-40 分钟验收；`quality_enhancer.py:55` 与 `qual_v8/gates/gate5.py:202` 已有 `enable_debate` 门控先例（且 `tools/finance/workflow.py:2758` 注释明示"辩论机制已禁用（会导致进程卡死）"）。

**修正后代码**（`tools/finance/quality/review_repair_loop.py`）：

```python
# --- _run_substantive_review 签名与 235-236 行门控 ---
def _run_substantive_review(
    chapters: Dict[int, str],
    llm_caller: Optional[Callable],
    wind_data: Optional[Dict],
    industry: str,
    *,
    enable_debate: bool = False,            # 新增：辩论默认关（与 quality_enhancer 对齐）
    budget_state: Optional[Dict] = None,
    deadline: Optional[float] = None,
    llm_call_budget: Optional[int] = None,
) -> List[str]:
    ...
    # 5. 对抗性辩论审查（P0-B-9：enable_debate=False 时整块跳过）
    if enable_debate and review_caller is not None:
        try:
            from .debate_service import DebateService, REVIEW_DEBATE_CHAPTERS
            svc = DebateService(llm_caller=review_caller, wind_data=wind_data, timeout=240)
            for ch_num in REVIEW_DEBATE_CHAPTERS:
                ...
                try:
                    debate_issues = svc.run(...)
                    if debate_issues:
                        issues.extend(debate_issues)
                except (DeterministicLLMFailure, LLMCallBudgetExceeded, WallClockDeadlineExceeded):
                    raise
                except Exception as e:
                    issues.append(f"{REVIEW_INCOMPLETE_PREFIX} 对抗辩论审查 第{ch_num}章失败: {e}")
        except (DeterministicLLMFailure, LLMCallBudgetExceeded, WallClockDeadlineExceeded):
            raise
        except Exception as e:
            issues.append(f"{REVIEW_INCOMPLETE_PREFIX} 对抗辩论审查初始化失败: {e}")
```

```python
# --- review_and_repair_loop 签名同步（31-38 行）---
def review_and_repair_loop(
    chapters: Dict[int, str],
    ctx: Any,
    llm_caller: Optional[Callable[[str, str], str]] = None,
    wind_data: Optional[Dict] = None,
    max_rounds: int = 3,
    industry: str = "新能源汽车",
    *,
    enable_debate: bool = False,            # 新增：辩论默认关
    skip_repair: bool = False,              # 新增：shadow 只审不修（缺陷 10）
    llm_call_budget: Optional[int] = None,  # 新增：单 Gate 调用硬上限（缺陷 7）
    deadline: Optional[float] = None,       # 新增：墙钟 deadline（缺陷 8）
) -> ReviewRepairResult:
```

**副作用**：`enable_debate` 为 keyword-only 默认 False → legacy `workflow.py:2942`（旧参数调用）与 gate4（缺陷 10 接线）均兼容；辩论路径保留但默认关闭，后续如需开启有明确开关与超时/预算护栏。

**验收单测**：`test_debate_gated`：monkeypatch `debate_service.DebateService.run` 计数 → `enable_debate=False` 时调用 0 次；`True` 时按 `REVIEW_DEBATE_CHAPTERS` 调用。

---

#### 缺陷 10（P0-B-10）：`shadow_skip_repair` 无消费方 → gate4 读标志跳过修复循环

**缺陷实证**：原方案 3c 注入 `context["shadow_skip_repair"]` 但 gate4 从未读取（审查"悬空接线"典型）。取"gate4 读标志跳过修复循环"方案（保留字段，接上消费方；shadow 语义 = 只审不修 + 打标）。

**修正后代码**（`tools/finance/qual_v8/gates/gate4.py:257-265`）：

```python
            from ...quality.review_repair_loop import review_and_repair_loop
            skip_repair = bool(context.get("shadow_skip_repair", False))   # workflow 注入（缺陷 8）
            result = review_and_repair_loop(
                chapters=chapters,
                ctx=ctx,
                llm_caller=llm_caller,                       # 主 caller（含 fallback，缺陷 11）
                wind_data=wind_data_for_check,
                max_rounds=1 if skip_repair else int(context.get("gate4_max_rounds", 3)),
                industry=industry,
                enable_debate=False,                          # 缺陷 9：Gate4 辩论关闭
                skip_repair=skip_repair,
                llm_call_budget=context.get("llm_call_budget"),     # 缺陷 7
                deadline=context.get("_wall_deadline"),             # 缺陷 8
            )
            # 审计写回（缺陷 1/7）：豁免清单 + 真实调用数
            context["_exempted_count"] = getattr(result, "exempted_count", 0)
            context["_llm_call_count"] = getattr(result, "llm_calls", 0)
```

```python
# --- loop 内 skip_repair 消费（主循环 86-98 行之间插入）---
        if skip_repair:
            # shadow：只审不修，单轮即返回（gate4 已把 max_rounds 降为 1）
            logger.warning(f"shadow 模式跳过修复：第{round_num}轮发现 {len(round_issues)} 个问题（只审不修）")
            return _fail_result(round_num, chapters, budget_state,
                                remaining=round_issues[:10])
        if not llm_caller:
            logger.warning("无LLM调用器，跳过修复")
            return _fail_result(round_num, chapters, budget_state, remaining=round_issues[:10])
```

**副作用**：`skip_repair=True` 时 loop 每轮**跳过 `_repair_chapters` 且不进入单调守卫重审**（无修复即无回滚）；`max_rounds=1` 保证单轮返回；shadow 报告经缺陷 8 打标。

**验收单测**：`test_shadow_skip_repair`：`loop(skip_repair=True, max_rounds=1)` → fake caller 的 `repair_*` 分支调用次数 == 0、返回 `passed=False`、`remaining` 非空。

---

#### 缺陷 11（P0-B-11）：5c 丢 REVIEW_SYSTEM → fallback 做成可复用装饰器，审查 caller 保留 REVIEW_SYSTEM 且带 fallback

**缺陷实证**：审查报告实证 7（`review_repair_loop.py:180-181` 注释明示审查专用 system 的动机）。原方案 5c 让 gate4 传 `review_caller_override=True` 裸复用主 caller → 审查 prompt 被报告撰写格式约束污染，判断失真。

**修正策略**：`_run_substantive_review` **内部构造**审查专用 caller：`create_harness_caller(max_tokens=8000, temperature=0.3, system=REVIEW_SYSTEM)`（保留 REVIEW_SYSTEM）→ `with_fallback` 包装（缺陷 5 装饰器，`degrade_marker=None` 避免污染审查输出解析）→ `_make_budgeted_caller` 包同一 `budget_state`（缺陷 7）。删除原方案未发布的 `review_caller_override` 参数（无兼容负担）。

**修正后代码**（`tools/finance/quality/review_repair_loop.py`，替换 182-197 行）：

```python
def _build_review_caller(primary, budget_state, deadline, llm_call_budget):
    """审查专用 caller：REVIEW_SYSTEM + fallback + budgeted（P0-B-11/5、P1-14 修正）"""
    if primary is None:
        return None
    try:
        from ..harness_llm import create_harness_caller
        from ..llm_caller import create_deepseek_caller
        from ..llm_fallback import with_fallback
        REVIEW_SYSTEM = (
            "你是资深买方投资分析师（Research QC）。你的任务是评估报告的分析深度、结论合理性与"
            "数据支撑质量，给出批判性判断。你不写报告，不受报告格式约束。"
        )
        inner = create_harness_caller(max_tokens=8000, temperature=0.3, system=REVIEW_SYSTEM)
        fb = with_fallback(inner, lambda: create_deepseek_caller(model="deepseek-chat"))
        return _make_budgeted_caller(fb, budget_state, deadline, llm_call_budget)
    except Exception as e:
        logger.warning(f"审查 caller 构造失败，使用主 caller: {e}")
        return _make_budgeted_caller(primary, budget_state, deadline, llm_call_budget)
```

```python
# --- _run_substantive_review 内调用（原 182 行 review_caller = llm_caller 替换）---
    review_caller = _build_review_caller(llm_caller, budget_state, deadline, llm_call_budget)
```

**副作用**：审查调用与修复调用**共享同一 budget_state 计数**（缺陷 7 的单 Gate 总预算口径）；gate4 传入的 `llm_caller` 仍作为修复 caller（其自身已含 fallback，双层 fallback 无害——内层审查专用 caller 的 fallback 在直连失败时抛回，外层主 caller 的 fallback 不再触发因为异常已由审查路径处理）。

**验收单测**：`test_review_caller_keeps_review_system`：monkeypatch `create_harness_caller` 记录 `system` 参数 → 断言审查路径调用时 `system` 含 `"Research QC"`；且审查调用失败（primary 抛 `DeterministicLLMFailure`）时直连工厂被调用一次。

---

### P1：架构修正（5 项）

---

#### 缺陷 12（P1-12）：`run_qual_full.py:92-113` 未同步 + import 缺失

**缺陷实证**：审查报告实证 4（"run_qual_full.py:92-113 同款 fallback 未同步确认"）。两 run 脚本的 fallback 各写一份，原方案只改 xpev。

**修正后代码**：`run_qual_full.py` 与 `run_xpev_full.py` 同步应用缺陷 5 的替换（`with_fallback` + import `DeterministicLLMFailure`/`with_fallback`）。为杜绝再漂移，**两文件 fallback 构造收敛为同一表达式**：

```python
# run_qual_full.py 92-113 行整体替换（与 run_xpev_full.py 177-197 行逐字一致）：
    llm_caller = with_fallback(
        _orig_caller,
        lambda: create_deepseek_caller(model="deepseek-chat"),
        degrade_marker="\n\n<!-- ⚠️ 已降级直连（桥接失败/确定性失败） -->",
    )
```

**副作用**：删除两文件各自的 `_llm_with_fallback` 闭包与 `_fail_count/_switch_threshold` 状态（统一由 `with_fallback` 内部滑动窗口接管）。

**验收单测**：`test_run_scripts_consistent`：AST 解析两文件，断言 `_llm_with_fallback` 均不存在、`with_fallback` 调用参数一致。

---

#### 缺陷 13（P1-13）：enforce 重试数 3/3/2 矛盾 + soft 无分支 → 统一语义、显式分支

**缺陷实证**：`WorkflowConfig.max_retries=3`（→ `qual_v8/workflow.py:260` `max_attempts=4`）与 GateSpec.max_retries=3、原方案 3c 的 enforce=2 三处矛盾；soft 模式无显式分支（落入 1+3=4）。

**修正后代码**（`tools/finance/qual_v8/workflow.py`）：

```python
# --- 模块级常量（新增，置于 _FLOW_DEFINITION 之前）---
RETRY_POLICY = {
    # gate_attempts: 单 Gate 执行次数（含首次）；repair_rounds: Gate4 修复轮数；skip_repair: 只审不修
    "shadow":  {"gate_attempts": 1, "repair_rounds": 1, "skip_repair": True},
    "soft":    {"gate_attempts": 1, "repair_rounds": 3, "skip_repair": False},
    "enforce": {"gate_attempts": 2, "repair_rounds": 3, "skip_repair": False},
}
```

```python
# --- 260 行：max_attempts 统一取策略表（删除 1 + config.max_retries）---
            max_attempts = policy["gate_attempts"]
```

```python
# --- 34-40 行 WorkflowConfig：新增字段（原有 max_retries 保留作默认值兜底）---
@dataclass
class WorkflowConfig:
    max_retries: int = 3                 # 兼容保留（策略表 shadow/soft 下不再直接消费）
    timeout_per_gate: int = 600
    human_sla_working_hours: int = 30
    human_sla_non_working_hours: int = 240
    global_timeout_seconds: int = 5400   # 新增：全局墙钟预算（90 分钟）
    max_llm_calls_per_gate: int = 60     # 新增：单 Gate LLM 调用次数硬上限
    shadow_skip_repair: bool = True      # 新增：shadow 模式 Gate4 跳过修复
```

**副作用**：`policy` 在 execute() 顶部按 `qual_mode` 解析一次（缺陷 8 处已注入 context）；shadow/soft 均为 1 次执行（soft 记录不阻断，与 `350-359` 行仅 enforce 阻断的既有语义一致）；enforce 2 次失败即耗尽 → 结合缺陷 15 熔断阈值 2，第二次失败即触发熔断。

**验收单测**：`test_retry_policy_table`：断言 `RETRY_POLICY["shadow"]["gate_attempts"] == 1`、`enforce == 2`；`execute()` 内 shadow 模式 Gate4 失败后 `attempts` 不再 +1（fake gate 恒失败，断言仅执行 1 次）。

---

#### 缺陷 14（P1-14）：`LLM_EMPTY_OUTPUT` 缺映射（`error_classifier.py:34-67`）

**缺陷实证**：`ERROR_CODE_MAPPING` 无 `LLM_EMPTY_OUTPUT`；`classify_from_exception` 对 `DeterministicLLMFailure` 落入 else → `UNKNOWN_ERROR` → 默认 `TRANSIENT retry=True`（确定性失败被当瞬态重试，fail-open）。

**修正后代码**（`tools/finance/qual_v8/core/error_classifier.py`）：

```python
# --- 34-67 行 ERROR_CODE_MAPPING 追加（放"系统错误"段之后）---
    # 确定性失败：不重试、计入熔断（P1-14；deterministic 键供策略消费方显式区分）
    "LLM_EMPTY_OUTPUT": {"type": "permanent", "retry": False, "escalate": False,
                         "deterministic": True},
    "REVIEW_UNRESOLVED": {"type": "permanent", "retry": False, "escalate": False,
                          "deterministic": True},
```

```python
# --- classify_from_exception（99-114 行）改造 ---
    def classify_from_exception(self, exception: Exception) -> ErrorClassification:
        from ...llm_errors import (
            DeterministicLLMFailure, LLMCallBudgetExceeded, WallClockDeadlineExceeded,
        )
        error_type = type(exception).__name__
        error_message = str(exception)
        if isinstance(exception, (DeterministicLLMFailure, LLMCallBudgetExceeded, WallClockDeadlineExceeded)):
            return self.classify("LLM_EMPTY_OUTPUT", error_message)   # 确定性：不重试
        elif isinstance(exception, (ConnectionError, TimeoutError)):
            return self.classify("NETWORK_TIMEOUT", error_message)
        elif isinstance(exception, PermissionError):
            return self.classify("HTTP_403", error_message)
        elif isinstance(exception, FileNotFoundError):
            return self.classify("DATA_NOT_FOUND", error_message)
        elif isinstance(exception, ValueError):
            return self.classify("VALIDATION_FAILED", error_message)
        else:
            # 文本兜底（Gate 边界收到的是字符串 errors 构造的 RuntimeError，见 qual_v8/workflow.py:302-304）
            if "审查未修复" in error_message:
                return self.classify("REVIEW_UNRESOLVED", error_message)   # 缺陷 15："审查未修复"不归 BUSINESS
            if "确定性" in error_message or "空输出" in error_message or "finish" in error_message:
                return self.classify("LLM_EMPTY_OUTPUT", error_message)
            return self.classify("UNKNOWN_ERROR", error_message)
```

**副作用**：`LLM_EMPTY_OUTPUT`/`REVIEW_UNRESOLVED` 映射为 `permanent`（= 确定性语义）→ `qual_v8/workflow.py:305` 熔断计数 +1（配合缺陷 15 阈值 2 → 可熔断）；`deterministic` 键为附加信息，`ErrorClassification` dataclass（22-30 行）不加字段，不破坏既有消费者。

**验收单测**：`test_llm_empty_output_classification`：`classify_from_exception(DeterministicLLMFailure("空输出"))` → `error_type == ErrorType.PERMANENT`、`retry is False`；`classify_from_exception(RuntimeError("审查未修复: ..."))` → `REVIEW_UNRESOLVED` 且 `retry is False`。

---

#### 缺陷 15（P1-15）：熔断仍不触发（8a 枚举统一 + 阈值降 2 + "审查未修复"不归 BUSINESS）

**缺陷实证**：审查报告实证 6 双重死因：① `circuit_breaker.py:24-28` 与 `error_classifier.py:15-19` 各定义一份 `ErrorType`，`record_failure(classification.error_type)` 跨类比较**恒 False**（TRANSIENT/BUSINESS 权重分支永不命中）；② 即使统一，enforce 2 次 × TRANSIENT 0.5 = 1.0 < 阈值 3。

**修正后代码**：

```python
# --- circuit_breaker.py 顶部（7-14 行 import 区）---
from .error_classifier import ErrorType          # 单一来源（8a：删除 24-28 行重复枚举）
```

```python
# --- circuit_breaker.py record_failure（51-62 行）改造 ---
    def record_failure(self, error_type: ErrorType):
        if error_type in (ErrorType.TRANSIENT, ErrorType.PERMANENT):
            self.failure_count += 1              # 权重统一 1（原 56 行 TRANSIENT 0.5 → 1）
        # BUSINESS 不计入熔断（业务失败可重试，不视为服务故障；缺陷 15）
        self.last_failure_time = datetime.now()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(f"熔断器 {self.name} 打开：连续{self.failure_count}次失败")
```

```python
# --- qual_v8/workflow.py 17 行 import 与 181 行阈值 ---
from .core.circuit_breaker import CircuitBreaker            # 不再需要 ErrorType（与分类器统一）
...
        self.circuit_breakers: Dict[int, CircuitBreaker] = {
            n: CircuitBreaker(name=f"gate_{n}", failure_threshold=2, reset_timeout=60)  # 阈值 3 → 2
            for n in range(9)
        }
```

**副作用**：enforce 模式 Gate4 连续 2 次失败（每次含多次 LLM 失败）→ `failure_count=2 ≥ 2` → 熔断打开，`workflow.py:262` `can_execute()` 短路跳过执行（不再 3 轮×N 次空转）；BUSINESS 不再污染熔断计数（业务失败走重试语义，不误伤服务健康度）；`ErrorType` 单一定义后 `error_classifier` 15-19 行保持为权威来源。

**验收单测**：`test_circuit_breaker_unified`：`record_failure(ErrorType.TRANSIENT)` ×2 → `state == OPEN`（阈值 2）；`record_failure(ErrorType.BUSINESS)` ×5 → 计数不变、仍 CLOSED；`circuit_breaker.ErrorType is error_classifier.ErrorType`。

---

#### 缺陷 16（P1-16）：签名归一化误豁免 → 保留章节上下文（第N章用占位符非删除）

**缺陷实证**：审查报告实证 8。原方案 `_issue_signature` 去数字并把"第N章"替换为"第N章"后继续去数字 → 跨章同形 issue 合并为同一签名 → 误豁免（第 4 章与第 5 章同样的描述性 issue 被豁免一次，后续全放行）。

**修正后代码**（`tools/finance/quality/review_repair_loop.py`）：

```python
def _issue_signature(issue: str, keep_chapter: bool = True) -> str:
    """问题签名：归一化数字但保留章节上下文（第N章 → 第@N章，不同章节签名不同）。

    keep_chapter=False 仅用于跨章聚合类审计统计，绝不用于豁免判定。
    """
    import re
    if keep_chapter:
        s = re.sub(r"第(\d+)章", r"第@\1章", issue)    # 保留章节号（缺陷 16：防误豁免）
    else:
        s = re.sub(r"第\d+章", "第@章", issue)
    s = re.sub(r"\d+\.?\d*", "N", s)                   # 归一化金额/年份等数字
    return s.strip()
```

**副作用**：`第4章 营收增长100亿无解释` 与 `第5章 营收增长100亿无解释` 签名不同 → 各自独立计数/豁免；豁免门槛（缺陷 1）叠加后误豁免概率显著下降；keep_chapter=False 模式仅供审计报表聚合，豁免路径强制 True。

**验收单测**：`test_signature_keeps_chapter`：断言 `_issue_signature("第4章 营收增长100亿无解释") != _issue_signature("第5章 营收增长100亿无解释")`；`_issue_signature("第4章 营收增长100亿无解释") == _issue_signature("第4章 营收增长99亿无解释")`（数字归一化仍生效）。

---

### 清理（2 项）

---

#### 缺陷 17（清理-17）：改动 7 no-op → 从 P0 移除，补桥接契约回归测试

**缺陷实证**：审查报告实证 5。`plugins/llm-bridge.js:56-64` **已实现** `finishReason = chunk.reason && chunk.reason.kind; ok = finishReason === 'stop'` 并在 64 行返回，原方案改动 7（"补全 finishReason 语义"）为 no-op。

**修正策略**：**不改 `llm-bridge.js` 一行代码**（从实施清单移除）；将验收转化为桥接契约回归测试——锁定 `harness_llm` 对 `finishReason` 各取值的分类行为（stop/max-tokens 有文/无文/error/null），防止桥接侧或调用侧未来回归。

**修正后代码**：无源码变更。新增契约测试（`tools/finance/test_harness_llm_fix.py`）：

```python
def test_bridge_finishreason_contract(monkeypatch):
    """锁定 harness_llm 对桥接 finishReason 的分类契约（缺陷 17 回归护栏）。"""
    cases = [
        ({"ok": True, "text": "内容", "finishReason": "stop"},           "内容",           False),
        ({"ok": False, "text": "部分", "finishReason": "max-tokens"},    "截断",           False),
        ({"ok": False, "text": "",     "finishReason": "max-tokens"},    None,             True),  # DeterministicLLMFailure
        ({"ok": False, "text": "",     "finishReason": "error"},         None,             False), # RuntimeError→瞬态重试
        ({"ok": False, "text": "",     "finishReason": None},            None,             False),
    ]
    for payload, expect_text, expect_deterministic in cases:
        monkeypatch.setattr("finance.harness_llm._call_bridge", lambda *a, **k: payload)
        caller = create_harness_caller(max_retries=0)      # 关重试隔离分类层
        try:
            out = caller("t", "p")
            assert expect_text in out
        except DeterministicLLMFailure:
            assert expect_deterministic
        except RuntimeError:
            assert not expect_deterministic
```

**副作用**：无（桥接保持现状）；`ok=False + finish=max-tokens + text 空` 的确定性分支由缺陷 2（harness 分类）配套落地后契约测试才全绿——**契约测试与 harness 分类同提交**。

**验收单测**：上表 5 例全断言通过。

---

#### 缺陷 18（清理-18）：无新增单测 → 每项修正配测试

**缺陷实证**：审查"新逻辑单测"缺口。原方案仅一句"回归 pytest"，未按改动建测试。

**修正策略**：新建 4 个测试文件（每项缺陷映射到至少一个用例），随缺陷所在提交一并合入：

| 测试文件 | 用例 | 覆盖缺陷 |
|---|---|---|
| `tools/finance/quality/test_loop_fix.py` | `test_convergence_earlystop`（问题数不降且修复=0 → 第 2 轮终止 passed=False） | 18（原 5b 收敛） |
| | `test_exemption_failclosed`（豁免非空即 fail + 证据护栏 ≥3 轮） | 1 |
| | `test_monotonic_guard`（deepcopy 回滚 + 新签名回滚） | 6 |
| | `test_budget_deadline`（调用数硬上限 + deadline 轮顶终止） | 7、8 |
| | `test_review_incomplete`（检查器吞异常 → 审查不完整失败项；`_parse_llm_score` 无默认 50） | 3 |
| | `test_signature_keeps_chapter` | 16 |
| | `test_shadow_skip_repair` | 10 |
| | `test_debate_gated` | 9 |
| | `test_legacy_call_compat`（按 workflow.py:2942 关键字调用新签名 → 无 TypeError） | 18（兼容） |
| `tools/finance/test_harness_llm_fix.py` | `test_deterministic_no_retry`（max-tokens 空输出 → 1 次调用即抛） | 4/5 基础 |
| | `test_bridge_finishreason_contract` | 17 |
| `tools/finance/test_llm_fallback.py` | `test_fallback_deterministic_switch`（换模型单次 + 原异常回抛） | 5、11 |
| `tools/finance/test_workflow_fix.py` | `test_generate_chapter_deterministic_no_retry` | 4 |
| `tools/finance/qual_v8/core/test_error_classifier_fix.py` | `test_llm_empty_output_classification` | 14、15 |
| `tools/finance/qual_v8/core/test_circuit_breaker_fix.py` | `test_circuit_breaker_unified` | 15 |
| `tools/finance/qual_v8/gates/test_gate4_fix.py` | `test_gate4_no_caller_failclosed` | 2 |
| `tools/finance/test_run_scripts_consistent.py` | `test_run_scripts_consistent` | 12 |

测试约定：LLM 一律用**可注入 fake caller**（记录调用序列、可配置抛 `DeterministicLLMFailure`/`RuntimeError`、返回固定文本），禁真实网络；`_run_deep_review` 用 monkeypatch 替换为返回 `[]`（隔离确定性检查器干扰）。

**副作用**：新增测试文件与 `tools/finance/quality/` 既有 `test_*.py` 同目录、pytest 自动收集；`test_legacy_call_compat` 同时充当 legacy `workflow.py:2942` 的契约回归。

---

## 二、完整新签名（含默认值，兼容 legacy workflow.py:2942 调用）

### 2.1 `review_and_repair_loop`（`tools/finance/quality/review_repair_loop.py:31-38` 改造）

```python
def review_and_repair_loop(
    chapters: Dict[int, str],
    ctx: Any,
    llm_caller: Optional[Callable[[str, str], str]] = None,
    wind_data: Optional[Dict] = None,
    max_rounds: int = 3,
    industry: str = "新能源汽车",
    *,
    enable_debate: bool = False,            # 新增：辩论默认关（缺陷 9）
    skip_repair: bool = False,              # 新增：shadow 只审不修（缺陷 10）
    llm_call_budget: Optional[int] = None,  # 新增：单 Gate 调用硬上限（缺陷 7）
    deadline: Optional[float] = None,       # 新增：墙钟 deadline，time.monotonic 绝对值（缺陷 8）
) -> ReviewRepairResult:
```

兼容性：新增参数全部 **keyword-only**（`*` 之后）且带默认值 → `tools/finance/workflow.py:2942-2949` 的旧关键字调用（`chapters/ctx/llm_caller/wind_data/max_rounds/industry`）**零修改兼容**；`ReviewRepairResult` 新字段（2.1 下）全部带默认值，旧消费方（`workflow.py:2951-2962` 读 `passed/rounds/issues_found/issues_fixed/remaining_issues`）兼容。`quality/v3/review_repair_loop.py:2` 的 re-export 无需改动。

### 2.2 `_run_substantive_review`（`review_repair_loop.py:171-176` 改造）

```python
def _run_substantive_review(
    chapters: Dict[int, str],
    llm_caller: Optional[Callable],
    wind_data: Optional[Dict],
    industry: str,
    *,
    enable_debate: bool = False,            # 新增（缺陷 9）
    budget_state: Optional[Dict] = None,    # 新增：统一计数 {calls: int}（缺陷 7）
    deadline: Optional[float] = None,       # 新增（缺陷 8）
    llm_call_budget: Optional[int] = None,  # 新增（缺陷 7）
) -> List[str]:
```

说明：返回 `List[str]`（issue 文本），其中 `[审查不完整]` 前缀项为主循环终止信号（缺陷 3）；**删除**原方案虚构的 `review_caller_override` 参数（从未发布，无兼容负担；语义反转见缺陷 11）。

### 2.3 `create_harness_caller`（`tools/finance/harness_llm.py:63-72` 改造）

```python
def create_harness_caller(
    base_url: str = None,
    model: str = None,
    provider: str = None,
    timeout: int = 300,
    max_retries: int = 2,
    temperature: float = 0.2,
    max_tokens: int = 12000,
    system: str = None,
    on_deterministic: Optional[Callable[[DeterministicLLMFailure], str]] = None,  # 新增
) -> Callable[[str, str], str]:
```

新增参数语义：确定性失败（max-tokens 空输出）时，若提供 `on_deterministic` 则调用它消费（返回降级文本），否则**抛出** `DeterministicLLMFailure`（硬语义"不重试"，默认值 None 保持既有 raise 行为，零破坏）。既有调用方（run 脚本、gate3/gate8、审查 caller）均不传 → 默认 raise。

### 2.4 `_llm_with_fallback` → 可复用装饰器 `with_fallback`（新增 `tools/finance/llm_fallback.py`）

```python
def with_fallback(
    primary: Callable[[str, str], str],
    fallback_factory: Callable[[], Callable[[str, str], str]],
    *,
    switch_on_deterministic: bool = True,   # 确定性失败也切直连单次重试
    window: int = 8,                        # 滑动窗口（K4：成功不清零）
    fail_threshold: int = 4,                # 窗口内失败 ≥4 切直连
    degrade_marker: Optional[str] = None,   # 降级输出追加标记
) -> Callable[[str, str], str]:
```

`run_xpev_full.py:177-197` / `run_qual_full.py:92-113` 的 `_llm_with_fallback` 闭包**整体删除**，改为一行装饰器调用（缺陷 5/12）。旧闭包仅在两个 run 脚本内定义与使用（grep 确认无第三方引用），删除无兼容风险。

---

## 三、确定性失败链路（harness_llm 抛出 → 各消费方完整处理）

```
                    ┌──────────────────────────────────────────────┐
                    │ harness_llm.create_harness_caller 内层        │
                    │ 104-118 行：ok=False + finish=max-tokens      │
                    │            + text 空 → raise                  │
                    │            DeterministicLLMFailure            │
                    │ 重试循环 101-123：except DeterministicLLMFailure│
                    │            → raise（不重试）                   │
                    └───────────────┬──────────────────────────────┘
                                    │ DeterministicLLMFailure
        ┌───────────────┬───────────┼──────────────┬─────────────────┐
        ▼               ▼           ▼              ▼                 ▼
  (A) run 脚本 fallback   (B) 审查检查器     (C) 修复 _repair    (D) Gate 边界分类
      with_fallback         depth/conclusion    _repair_chapters      qual_v8/workflow.py
      except Det. →         _run_substantive    356 行调用点          301-305 行
      直连/换模型单次       _review 内 guard    except Det. → raise   classify_from_exception
      重试（换模型）        except Det. → raise （主循环捕获终止）       → LLM_EMPTY_OUTPUT
      │ 直连成功: 返回      │                     │                   （permanent, retry=False）
      │  (可带 marker)      ▼                     ▼                    → circuit_breaker
      │ 直连失败: raise ┌──主循环 67 行──────────┐                      record_failure(+1)
      ▼                 │ catch → 审查不完整      │                    （缺陷 14/15）
  (E) _generate_chapter  │  终止：passed=False    │
      1237-1241 行       │  review_incomplete=T   │
      except Det. →      │  remaining=[审查不完整] │
      立即降级响应        └───────────┬────────────┘
      （不重试）                      ▼
                               (F) gate4._substantive_review 278-280
                                   except DeterministicLLMFailure →
                                   passed=False + errors（fail-closed）
```

**各消费方伪代码**（均已在前述缺陷项给出具体代码，此处给调用序）：

1. **抛出点**（`harness_llm.py:104-118` + `119-123`）：
   ```
   for attempt in range(max_retries+1):
       try: data = _call_bridge(...)
            if not ok and finish==max-tokens and text空: raise DeterministicLLMFailure
            if not ok and finish==max-tokens and text非空: return 截断文本（打标）
            if not ok: raise RuntimeError(瞬态)
            return data["text"]
       except DeterministicLLMFailure: on_deterministic(e) if 提供 else raise   # 不重试
       except Exception: last_err=e; 退避; 继续
   raise last_err
   ```
2. **消费方 A（run 脚本，缺陷 5/11）**：`with_fallback` 内 `except DeterministicLLMFailure` → 直连单次 → 失败则 `raise`（原异常，保留确定性语义）→ 上游（_generate_chapter/gate4/loop）按确定性降级。
3. **消费方 B（审查检查器，缺陷 3）**：`depth_reviewer._evaluate_by_llm` / `conclusion_validator` 的 except 白名单 → raise → `_run_substantive_review` 不捕获（继续上抛）→ 主循环 67 行捕获 → **终止**（不进修复）。
4. **消费方 C（修复，缺陷 6）**：`_repair_chapters:407-408` 白名单 → raise → 主循环 98 行捕获 → 终止（`review_incomplete=True`）。
5. **消费方 D（Gate 边界熔断，缺陷 14/15）**：Gate 结果 errors 拼接 → `classify_from_exception`（类型识别或文本识别"确定性/空输出/finish"）→ `LLM_EMPTY_OUTPUT`（permanent, retry=False）→ `record_failure` 计数 +1 → 阈值 2 熔断。
6. **消费方 E（legacy/v8 写作，缺陷 4）**：`_generate_chapter` except 白名单 → 立即 `_build_insufficient_data_response(..., "确定性失败")`，**重试次数保持 0**（旧代码 3 次）。
7. **消费方 F（gate4 兜底，缺陷 2）**：任何逃逸到 `_substantive_review` 的确定性失败 → `passed=False` fail-closed。

**新异常不被吞的自检清单**（提交前逐处 grep `except Exception` 与白名单配对）：

| 文件:行号 | 原 except | 修订后 |
|---|---|---|
| `depth_reviewer.py:259-261` | `except Exception` 吞 | 白名单 raise（缺陷 3） |
| `conclusion_validator.py:404-405` | `except Exception` 吞 | 白名单 raise（缺陷 3） |
| `review_repair_loop.py:214/223/232` | `except Exception` 吞 | 白名单 raise（缺陷 3） |
| `review_repair_loop.py:259-261`（debate 内） | `except Exception` 吞 | 白名单 raise（缺陷 9） |
| `review_repair_loop.py:407-408`（repair） | `except Exception` 吞 | 白名单 raise（缺陷 6） |
| `tools/finance/workflow.py:1237-1241` | `except Exception` 吞+重试 | 白名单短路（缺陷 4） |
| `gate4.py:278-280` | `except Exception` → passed=True | fail-closed（缺陷 2） |
| `qual_v8/gates/gate3.py:142/187/201` | 无 LLM 重试循环（调 _generate_chapter） | 无需改（短路在 _generate_chapter 内） |

---

## 四、预算接线（`_budgeted_caller` 透传 `_run_substantive_review` 全链）

**数据流图**：

```
QualWorkflow.execute (qual_v8/workflow.py)
  ├─ context["llm_call_budget"]  = config.max_llm_calls_per_gate (60)
  ├─ context["_wall_deadline"]   = monotonic() + global_timeout_seconds
  └─ context["_llm_call_count"]  ← gate4 写回（审计）
        ▼
gate4._substantive_review (gate4.py:257-265)
  ├─ llm_call_budget=context.get("llm_call_budget")
  ├─ deadline=context.get("_wall_deadline")
  └─ result → context["_llm_call_count"]=result.llm_calls / context["_exempted_count"]
        ▼
review_and_repair_loop (review_repair_loop.py:31-38)
  ├─ budget_state = {"calls": 0}                         ← 唯一计数源
  ├─ repair_caller = _make_budgeted_caller(llm_caller, budget_state, deadline, budget)
  │     └─ 修复调用：_repair_chapters(..., repair_caller, ...)      [98 行]
  └─ 审查调用：_run_substantive_review(..., repair_caller, ...,
                 budget_state=budget_state, deadline=deadline, llm_call_budget=budget)
        │
        └─ _build_review_caller (缺陷 11)
              ├─ inner  = create_harness_caller(REVIEW_SYSTEM, max_tokens=8000, t=0.3)
              ├─ fb     = with_fallback(inner, lambda: create_deepseek_caller("deepseek-chat"))
              └─ review = _make_budgeted_caller(fb, budget_state, deadline, budget)   ← 同一 budget_state
                    ├─ depth_reviewer.check_depth(chapters, review, wind_data)        [depth]
                    ├─ conclusion_validator.check_conclusion(chapters, review, wind_data) [conclusion]
                    └─ DebateService(llm_caller=review, ...)  (仅 enable_debate=True)  [debate]
```

**关键代码**（`review_repair_loop.py`）：

```python
# 主循环入口（56 行前）：
    budget_state: Dict[str, int] = {"calls": 0}
    repair_caller = _make_budgeted_caller(llm_caller, budget_state, deadline, llm_call_budget)

# 每轮审查（67 行）：
    substantive_issues = _run_substantive_review(
        chapters, repair_caller, wind_data, industry,
        enable_debate=enable_debate,
        budget_state=budget_state, deadline=deadline, llm_call_budget=llm_call_budget,
    )

# 单调守卫重审（缺陷 6）与轮首审查用同一 budget_state → 计数真实、口径一致。

# 所有返回路径统一：
    # _ok_result/_fail_result 内部构造 ReviewRepairResult(..., llm_calls=budget_state["calls"],
    #                              exempted_count=len(exempted_tracked), exempted=sorted(exempted_sigs))
```

**计数语义**：每次 LLM 调用（修复 + 审查 depth/conclusion/debate + 审查 fallback 直连重试内层）只经 budgeted 包装一次 → 每调用 `calls += 1` 恰好一次；超预算抛 `LLMCallBudgetExceeded`（缺陷 7）；deadline 在 budgeted 调用前与轮顶（缺陷 8）双检查，抛 `WallClockDeadlineExceeded`。两类异常均列入全链 except 白名单（第三节自检表）。

---

## 五、实施顺序（依赖 + 合并提交）

```
提交 #1（P0-A 堵漏，最先合入；含 P1-16 签名修订）
  ├─ 新增 tools/finance/llm_errors.py（全部新异常的唯一来源；后续提交依赖）
  ├─ P1-16 _issue_signature 保留章节号          ← 先于豁免学习，防误豁免
  ├─ P0-A-1 收敛判据"豁免非空即 fail" + 豁免证据护栏（≥3 轮 + 无修复迹象）
  ├─ P0-A-2 gate4.py:226-228 + 278-280 fail-closed
  ├─ P0-A-3 depth_reviewer（llm_failed 字段 / 无默认 50 / 白名单 raise）
  │        + conclusion_validator.py:404-405 + review_repair_loop 检查器守卫
  ├─ test_loop_fix.py（exemption_failclosed / review_incomplete / signature_keeps_chapter）
  └─ test_gate4_fix.py（no_caller_failclosed）
  依赖说明：gate4 fail-closed 后 shadow 不阻断但需打标 → 打标依赖提交 #2 的 _fill_failed_gates，
  故 #1 合入时 Gate4 失败会在报告打标前短暂"静默失败"——可接受（shadow 本就记录不阻断），
  但若要求零窗口，将 #2 的 workflow 打标段一并纳入 #1（推荐：#1+#2 的 workflow 部分合并提交）。

提交 #2（P0-B 止血；workflow + loop + gate4 接线必须同提交，原子化）
  ├─ P0-B-4 harness_llm 分类（104-118/119-123）+ _generate_chapter 短路（workflow.py:1237-1241）
  ├─ P0-B-5/11 新增 llm_fallback.py（with_fallback）+ run 脚本接线（xpev + qual 同步，P1-12）
  ├─ P0-B-6 单调守卫（deepcopy 快照 + 签名差集 + 同口径）
  ├─ P0-B-7 _make_budgeted_caller + budget_state 全链透传
  ├─ P0-B-8 全局 deadline + _fill_failed_gates + 统一打标
  ├─ P0-B-9 enable_debate=False 门控（loop + _run_substantive_review 签名）
  ├─ P0-B-10 shadow_skip_repair 消费（gate4 接线）
  ├─ P1-13 RETRY_POLICY 三模式显式分支（workflow.py:260 + WorkflowConfig 新字段）
  ├─ 测试：deterministic_no_retry / budget_deadline / monotonic_guard / convergence_earlystop /
  │        fallback_deterministic_switch / shadow_skip_repair / debate_gated /
  │        generate_chapter_deterministic_no_retry / legacy_call_compat / run_scripts_consistent
  └─ 依赖：loop 新签名（enable_debate/skip_repair/budget/deadline）是 gate4 接线前提；
           先改 loop 签名再改 gate4 调用（审查 P1-16 同款调序要求），二者同提交；
           harness_llm 分类是 fallback 确定性分支的前提 → 同提交。

提交 #3（P1 架构；熔断链路独立回归）
  ├─ P1-14 error_classifier：LLM_EMPTY_OUTPUT / REVIEW_UNRESOLVED + 类型/文本识别
  ├─ P1-15 circuit_breaker：枚举统一（删 24-28）+ 权重 1 + 阈值 2 + workflow.py:17/181
  ├─ 测试：llm_empty_output_classification / circuit_breaker_unified
  └─ 依赖：#2 的 RETRY_POLICY（enforce=2 次）是"阈值 2 即可熔断"的触发前提 → 不得提前。

提交 #4（清理）
  ├─ 清理-17：改动 7 从实施清单移除（llm-bridge.js 零改动）+ bridge 契约测试
  ├─ 清理-18：全部测试文件收口（含 #1-#3 已建用例的 CI 接线）
  └─ 回归：pytest tools/finance/quality/test_loop_fix.py tools/finance/test_harness_llm_fix.py \
             tools/finance/test_llm_fallback.py tools/finance/test_workflow_fix.py \
             tools/finance/qual_v8/core tools/finance/qual_v8/gates/test_gate4_fix.py
```

**必须合并提交的步骤**（防中间态不可运行）：
- #1 内：`llm_errors.py`（异常定义）必须与第一批 raise/except 白名单同提交；
- #2 内：`review_and_repair_loop` 新签名 与 `gate4.py` 调用接线、`_run_substantive_review` 新签名与 `_build_review_caller` 同提交；`harness_llm` 分类 与 `_generate_chapter` 短路 同提交（否则确定性失败仍被吞）；`with_fallback` 与两个 run 脚本接线同提交；
- #3 内：`circuit_breaker` 枚举统一 与 `error_classifier` 权威枚举同提交（否则跨类比较回归）。

**验收口径（承接审查裁决）**：终止性 = for 上界（RETRY_POLICY gate_attempts ≤ 2）+ 每调用硬超时（timeout 300s）+ 预算硬上限（60 次/Gate）+ 墙钟 deadline（5400s）四重有界；"确定性不重试"由 harness 层 raise 与全链 except 白名单保证；"豁免非空即 fail"消除 P0-A-1 静默放行；30-40 分钟验收依赖 enable_debate=False（消除 72min/轮辩论）——该项在 #2 落地后重新实测。
