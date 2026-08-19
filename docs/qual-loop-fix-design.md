# qual v8 死循环修复——架构设计与代码设计（实施方案）

日期：2026-08-19
依据：`docs/qual-loop-rootcause.md`（根因）+ `docs/qual-loop-rootcause-review.md`（架构评审）+ 代码专家评审
范围：P0 止血（立即实施，~200 行）+ P1 架构重构（第二步）

---

## 第一部分：架构设计

### 0. 设计原则（来自双专家评审）

1. **先分类，后重试**：错误分四类——瞬态（可重试）/ 确定性（不重试，改策略）/ 语义失败（走业务处理）/ 熔断触发（跳过）
2. **嵌套重试只算乘积**：全局墙钟预算 + 总调用次数预算 + 单层上限语义明确
3. **降级必须带语义标记**：shadow 产出显式打"未修复"标
4. **质量闭环清单驱动 + 单调性**：修复目标 = 冻结清单；问题数上升即回滚；判据用"趋势+容差"
5. **检查器与修复器共享契约**：issue 结构化（id/章节/期望值/验证器引用）

---

### 1. 分层架构（修复后）

```
┌─────────────────────────────────────────────────────┐
│  run_xpev_full.py / run_qual_full.py（入口）          │
│   构造 llm_caller（含 fallback 包装）→ 注入 context     │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│  QualWorkflow.execute（workflow.py）                  │
│  • 全局墙钟预算检查（每次 Gate 循环顶部）                │
│  • Gate 级重试：shadow 模式 = 1 次；enforce = 3 次      │
│  • 每 Gate 调用次数硬上限（防内层失控）                  │
│  • 失败后报告打"未修复"标记                              │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│  Gate4AuditRepair（gate4.py）                         │
│  • 实质审查异常 → passed=False（fail-closed，不再吞）   │
│  • 传审查 caller（复用主 caller，带 fallback）          │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│  review_and_repair_loop（review_repair_loop.py）      │
│  • 收敛早停：问题数不降且修复=0 → 终止                  │
│  • 单调性守卫：修复后问题总数上升 → 回滚本轮              │
│  • 同签名问题跨轮 ≥2 次 → 豁免（标记，不再报）           │
│  • 审查 caller = 传入的主 caller（不再独立新建）         │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│  harness_llm.create_harness_caller（LLM 调用层）       │
│  • finish 分类：max-tokens+空=确定性失败（不重试）       │
│  • 瞬态（连接/超时/error finish）= 重试 2 次 + 退避     │
│  • 内置直连 fallback（连续 3 次瞬态失败切直连）          │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│  plugins/llm-bridge.js（宿主桥接）                     │
│  • finishReason 语义补全：stop/max-tokens/error/null   │
│  • 保留 stream 异常 → 500 + error 详情                  │
└─────────────────────────────────────────────────────┘
```

---

### 2. 错误分类模型（核心）

**新增 `tools/finance/llm_errors.py`**——统一错误类型，供 harness_llm / llm_caller / 上层消费：

```python
class LLMFailureKind(Enum):
    TRANSIENT = "transient"      # 瞬态：网络/连接/超时/流中断 → 重试
    DETERMINISTIC = "deterministic"  # 确定性：预算耗尽空输出/格式错误 → 不重试
    SEMANTIC = "semantic"        # 语义失败：ok 但内容不合格 → 业务处理
    CIRCUIT_OPEN = "circuit_open"    # 熔断 → 跳过

class DeterministicLLMFailure(RuntimeError):
    """确定性失败：对同一 prompt+model 必然复现，重试无意义。
    携带 finish_reason 与原始响应，供上层换模型/拆任务/降级。"""
    def __init__(self, message, finish_reason=None, model=None):
        super().__init__(message)
        self.finish_reason = finish_reason
        self.model = model
```

**分类规则（harness_llm.py:105-115 改造）**：

| 桥接响应 | 分类 | 动作 |
|---|---|---|
| `ok=True` | 成功 | 返回 text |
| `ok=False, finish=max-tokens, text非空` | 成功（截断） | 保留 + 打标（现有逻辑） |
| `ok=False, finish=max-tokens, text空` | **DETERMINISTIC** | 抛 `DeterministicLLMFailure`，**不重试** |
| `ok=False, finish=error` | TRANSIENT | 重试 2 次 + 退避 |
| `ok=False, finish=null/流中断` | TRANSIENT | 重试 2 次 + 退避 |
| 网络异常（URLError/ConnectionError/TimeoutError） | TRANSIENT | 重试 2 次 + 退避 |

---

### 3. 数据流（Gate4 修复循环改造后）

```
审查轮次 1..max_rounds:
  1. 全量审查 → issues[]（带签名 hash）
  2. 收敛判定：
     - issues 数 == 0 → 通过
     - issues 数 >= 上轮 且 上轮修复数 == 0 → 终止（记录 remaining）
     - 签名在豁免清单 → 从本轮 issues 剔除
  3. patch 修复（对可路由的 issue）
  4. 单调性守卫：修复后全量重算 issues，若总数 > 修复前 → 回滚本轮所有 patch
  5. issues 签名加入/更新跨轮记录
```

---

## 第二部分：代码设计（P0 止血，按实施顺序）

### 改动 1：`tools/finance/llm_errors.py`（新增）

```python
# -*- coding: utf-8 -*-
"""LLM 调用错误分类（统一契约，供 harness_llm/llm_caller/上层消费）"""
from enum import Enum


class LLMFailureKind(Enum):
    TRANSIENT = "transient"
    DETERMINISTIC = "deterministic"
    SEMANTIC = "semantic"
    CIRCUIT_OPEN = "circuit_open"


class DeterministicLLMFailure(RuntimeError):
    """确定性失败：同一 prompt+model 必然复现，重试无意义。"""
    def __init__(self, message: str, finish_reason=None, model=None):
        super().__init__(message)
        self.finish_reason = finish_reason
        self.model = model
```

---

### 改动 2：`tools/finance/harness_llm.py`（核心止血）

**2a. 失败分类**（替换 105-115 行逻辑）：

```python
from .llm_errors import DeterministicLLMFailure, LLMFailureKind

# 在 _call_bridge 调用后：
data = _call_bridge(payload, base, timeout)
if not data.get("ok"):
    finish = data.get("finishReason") or data.get("finish") or {}
    text = data.get("text") or ""
    finish_kind = finish.get("kind") if isinstance(finish, dict) else finish

    # 截断但有内容 → 保留（现有）
    if finish_kind in ("max-tokens",) or (isinstance(finish, str) and "max" in finish):
        if text and text.strip():
            return text + "\n\n<!-- ⚠️ LLM 输出被 max-tokens 截断，内容不完整 -->"

    # 确定性失败：max-tokens 且空输出 → 不重试
    if finish_kind in ("max-tokens",) or (isinstance(finish, str) and "max" in finish):
        raise DeterministicLLMFailure(
            f"LLM 输出为空（finish={finish}），确定性失败，不重试",
            finish_reason=finish_kind, model=payload.get("model"),
        )

    # 其余（error/null/网络）→ TRANSIENT，走重试
    raise RuntimeError(data.get("error") or f"finish={json.dumps(finish) if finish else 'null'}")
```

**2b. 重试循环分类**（改造 101-123 行）：

```python
for attempt in range(max_retries + 1):
    try:
        return _one_call(payload, base, timeout, chapter_name, attempt, max_tokens)
    except DeterministicLLMFailure:
        raise  # 确定性失败，不重试
    except Exception as e:
        last_err = e
        _log(f"失败 {chapter_name} 尝试{attempt+1}: {repr(e)[:200]} ({round(time.time()-t0,1)}s)")
        if attempt < max_retries:
            time.sleep(2 * (attempt + 1))
raise last_err
```

---

### 改动 3：`tools/finance/qual_v8/workflow.py`（Gate 级 + 全局预算）

**3a. WorkflowConfig 加字段**（35-40 行附近）：

```python
@dataclass
class WorkflowConfig:
    max_retries: int = 3
    global_timeout_seconds: int = 5400          # 新增：全局墙钟预算（90 分钟）
    max_llm_calls_per_gate: int = 60            # 新增：单 Gate LLM 调用次数硬上限
    shadow_skip_repair: bool = True             # 新增：shadow 模式 Gate4 跳过修复循环
```

**3b. 全局墙钟预算**（execute 顶部 + Gate 循环顶部）：

```python
import time as _time
_wall_start = _time.monotonic()

# Gate 循环顶部（241 行后）：
for gate_num in range(9):
    _elapsed = _time.monotonic() - _wall_start
    if _elapsed > self.config.global_timeout_seconds:
        logger.error(f"全局墙钟预算耗尽（{_elapsed:.0f}s > {self.config.global_timeout_seconds}s），强制终止")
        results[f"gate_{gate_num}"] = {
            "passed": False, "score": 0.0, "execution_time": 0.0,
            "errors": [f"全局墙钟预算耗尽（{_elapsed:.0f}s）"], "check_criteria_passed": False,
        }
        break
    _gate_start = _time.monotonic()
```

**3c. shadow 模式 Gate4 降重试 + 跳过修复**（257-311 行改造）：

```python
# Gate 级重试：shadow 模式最多 1 次重试（共 2 次执行）；enforce 保持 3 次
_max_attempts_this_gate = 1 + self.config.max_retries
if qual_mode == "shadow" and gate_num == 4:
    _max_attempts_this_gate = 1  # shadow + Gate4：只执行 1 次，不再全量重试
elif qual_mode == "shadow":
    _max_attempts_this_gate = 1  # shadow 所有 Gate 不重试（记录即可）
elif qual_mode == "enforce":
    _max_attempts_this_gate = 2  # enforce：至多重试 1 次

while attempts < _max_attempts_this_gate:
    ...
    # 传 shadow_skip_repair 给 Gate4
    if gate_num == 4:
        context["shadow_skip_repair"] = (qual_mode == "shadow" and self.config.shadow_skip_repair)
```

**3d. 失败后报告打"未修复"标记**（365-374 行，组装 report 后）：

```python
# 检查是否有 Gate 失败 → 报告打标
if not all(r["passed"] for r in results.values()):
    failed = [g for g, r in results.items() if not r["passed"]]
    _marker = (
        f"\n\n<!-- ⚠️ 质量状态：本报告由 shadow 模式产出，以下 Gate 未通过：{failed}。"
        f"部分章节可能未完成审查/修复，数字未经最终验证。 -->\n"
    )
    context["report"] = (context.get("report") or "") + _marker
    context["quality_degraded"] = True
```

**3e. 每 Gate LLM 调用次数硬上限**（在 Gate 循环内、execute_gate 前后）：

```python
# 在 Gate 循环顶部初始化
context["_llm_call_count"] = 0
# 注入计数器给 Gate4 内部使用（review_repair_loop 消费）
context["llm_call_budget"] = self.config.max_llm_calls_per_gate
```

---

### 改动 4：`tools/finance/qual_v8/gates/gate4.py`

**4a. 实质审查异常 → fail-closed**（278-280 行）：

```python
except Exception as e:
    logger.error(f"Gate4 实质审查失败: {e}")
    return {"passed": False, "errors": [f"实质审查异常: {e}"], "repaired_chapters": None}
```

**4b. 传审查 caller = 主 caller**（不再让 review_repair_loop 独立新建）：

```python
# _substantive_review 中，把 llm_caller（已含 fallback）直接传入，
# 并设置 review_caller_override=True 让 loop 复用主 caller
result = review_and_repair_loop(
    chapters=chapters, ctx=ctx,
    llm_caller=llm_caller,          # 已含 _llm_with_fallback
    wind_data=wind_data_for_check,
    max_rounds=3,
    industry=industry,
    review_caller_override=True,    # 新增参数：禁止 loop 内部新建 caller
    llm_call_budget=context.get("llm_call_budget"),
)
```

---

### 改动 5：`tools/finance/quality/review_repair_loop.py`（收敛核心）

**5a. 签名函数（新增）**：

```python
def _issue_signature(issue: str) -> str:
    """问题签名：去数字/空格/章节号，用于跨轮去重与豁免"""
    import re
    s = re.sub(r"\d+\.?\d*", "N", issue)
    s = re.sub(r"第\d+章", "第N章", s)
    return s.strip()
```

**5b. 收敛早停 + 豁免 + 单调性守卫**（改造主循环 56-102 行）：

```python
prev_issue_count = None
round_hist: dict[str, int] = {}   # 签名 → 出现轮次数
exempted: set[str] = set()
monotonic_ok = True

for round_num in range(1, max_rounds + 1):
    # 1. 全量审查
    round_issues = _run_deep_review(chapters, wind_data) + \
                   _run_substantive_review(chapters, llm_caller, wind_data, industry,
                                           review_caller_override=review_caller_override)

    # 2. 豁免剔除（跨轮 ≥2 次的同签名问题）
    kept = []
    for iss in round_issues:
        sig = _issue_signature(iss)
        round_hist[sig] = round_hist.get(sig, 0) + 1
        if sig in exempted:
            continue
        kept.append(iss)
    round_issues = kept

    # 3. 收敛判定（S2 最小版）
    if not round_issues:
        return ReviewRepairResult(passed=True, rounds=round_num, chapters=chapters, ...)
    if prev_issue_count is not None and len(round_issues) >= prev_issue_count:
        if fixed_count == 0:   # 上一轮无有效修复且问题未降 → 终止
            logger.warning(f"收敛早停：第{round_num}轮问题数 {len(round_issues)} 未降（上轮 {prev_issue_count}），修复=0")
            return ReviewRepairResult(passed=False, rounds=round_num, chapters=chapters,
                                      issues_found=..., issues_fixed=...,
                                      remaining_issues=round_issues[:10])

    # 4. 修复（带单调性守卫）
    before = len(round_issues)
    fixed_count = _repair_chapters(chapters, round_issues, llm_caller, wind_data)
    after = len(_run_deep_review(chapters, wind_data)) + \
            len(_run_substantive_review(chapters, llm_caller, wind_data, industry,
                                        review_caller_override=review_caller_override))
    if after > before:
        # 单调性守卫：修复引入回归 → 回滚本轮（用备份恢复 chapters）
        logger.warning(f"单调性守卫：修复后问题数 {before}→{after} 上升，回滚本轮修复")
        chapters.update(_snapshot_before_round)   # 需在轮首备份
        fixed_count = 0

    prev_issue_count = before
    # 5. 豁免学习：同签名跨轮 ≥2 次且从未被修复 → 加入豁免
    for iss in round_issues:
        sig = _issue_signature(iss)
        if round_hist.get(sig, 0) >= 2:
            exempted.add(sig)
```

**5c. 审查 caller 复用主 caller**（改造 182-197 行）：

```python
review_caller = llm_caller
if llm_caller is not None and not review_caller_override:
    try:
        from ..harness_llm import create_harness_caller
        REVIEW_SYSTEM = (...)
        review_caller = create_harness_caller(max_tokens=8000, temperature=0.3, system=REVIEW_SYSTEM)
    except Exception:
        review_caller = llm_caller
# review_caller_override=True 时直接用主 caller（已含 fallback + 确定性失败分类）
```

**5d. 单 Gate 调用次数硬上限**（在 loop 入口消费 budget）：

```python
_llm_calls = 0
def _budgeted_caller(name, prompt):
    nonlocal _llm_calls
    _llm_calls += 1
    if llm_call_budget and _llm_calls > llm_call_budget:
        raise RuntimeError(f"Gate4 LLM 调用次数超预算（>{llm_call_budget}），强制终止")
    return llm_caller(name, prompt)
# 修复调用与审查调用都改用 _budgeted_caller
```

---

### 改动 6：`run_xpev_full.py` — fallback 增强

**K4 修复**：成功不清零，改用滑动窗口（最近 8 次中失败 ≥4 → 切直连）：

```python
_fail_hist: list[bool] = []   # 最近 N 次调用结果

def _llm_with_fallback(chapter_name, prompt):
    nonlocal _direct_caller
    try:
        text = _orig_caller(chapter_name, prompt)
        _fail_hist.append(False)
        if len(_fail_hist) > 8: _fail_hist.pop(0)
        if sum(_fail_hist) >= 4 and llm_route == "harness_bridge" and _direct_caller is None:
            log("[FALLBACK] 滑动窗口失败率高，切换直连")
            _direct_caller = create_deepseek_caller(model="deepseek-chat")
        return text
    except DeterministicLLMFailure:
        _fail_hist.append(True)  # 确定性失败也计数（提示任务-模型错配）
        if len(_fail_hist) > 8: _fail_hist.pop(0)
        raise  # 但确定性失败仍不重试（由 harness_llm 决定）
    except Exception as e:
        _fail_hist.append(True)
        if len(_fail_hist) > 8: _fail_hist.pop(0)
        if _direct_caller is not None:
            return _direct_caller(chapter_name, prompt)
        raise
```

---

### 改动 7：`plugins/llm-bridge.js` — finishReason 语义补全

```js
// 桥接响应补全语义：区分 stop / max-tokens / error / aborted
for await (const chunk of llm.stream({...})) {
  if (chunk.type === 'text-delta') text += chunk.text
  if (chunk.type === 'finish') {
    finishReason = chunk.reason && chunk.reason.kind   // 'stop' | 'max-tokens' | 'error' | 'aborted' | null
  }
}
return send(200, { ok: finishReason === 'stop', text, provider, model, finishReason })
```

---

### 改动 8（P1，第二步）：`tools/finance/qual_v8/core/circuit_breaker.py` + `error_classifier.py` 熔断修复

**8a. 统一枚举**：`circuit_breaker.py` 改为导入 `error_classifier.ErrorType`（删除重复定义）：

```python
# circuit_breaker.py 顶部
from .error_classifier import ErrorType   # 单一来源
```

**8b. 分类修正**（error_classifier.py:113-114）：`RuntimeError` 不再一律 UNKNOWN/TRANSIENT，按消息内容细分：

```python
elif isinstance(exception, RuntimeError):
    msg = str(exception)
    if "确定性" in msg or "finish=max-tokens" in msg or "空输出" in msg:
        return self.classify("LLM_EMPTY_OUTPUT", msg)   # 新码：deterministic，retry=False
    if "审查未修复" in msg or "逻辑矛盾" in msg:
        return self.classify("VALIDATION_FAILED", msg)   # business
    return self.classify("UNKNOWN_ERROR", msg)
```

**8c. record_failure 分类加权修正**（circuit_breaker.py:51-58）：

```python
def record_failure(self, error_type: ErrorType):
    if error_type == ErrorType.PERMANENT:
        self.failure_count += 1
    elif error_type == ErrorType.TRANSIENT:
        self.failure_count += 1          # 权重从 0.5 → 1（阈值 3 次即可熔断）
    elif error_type == ErrorType.BUSINESS:
        self.failure_count += 0.5        # 业务失败低权重（可重试类）
    ...
```

---

## 第三部分：实施顺序与回归

### 步骤 1（止血，先跑通小鹏）：
1. 新增 `llm_errors.py`
2. 改造 `harness_llm.py`（确定性失败不重试）
3. 改造 `workflow.py`（全局预算 + shadow 降重试 + 打标）
4. 改造 `gate4.py`（fail-closed + 传主 caller）
5. 改造 `review_repair_loop.py`（收敛早停 + 豁免 + 单调性 + caller 复用）
6. `run_xpev_full.py` fallback 滑动窗口
7. `llm-bridge.js` finishReason 补全（需重建动态插件）
8. 回归：`pytest test_numeric_guard test_core`；dry-run 单章生成验证

### 步骤 2（架构重构，单独回归）：
9. 熔断器枚举统一 + 分类修正
10. 结构化 issue 契约 + 问题清单驱动（M2/B）
11. 检查点/恢复（每 Gate 落盘 chapters JSON）

### 步骤 3（可选）：
12. 假阳性自学习豁免（M3）
13. 模型-任务匹配（短结构输出换非推理模型）

---

## 第四部分：验收标准

| 指标 | 现状 | 目标 |
|---|---|---|
| 最坏运行时长 | 31.5h（理论）/ 6h+（实测卡死） | **≤ 30-40 分钟**（正常路径） |
| LLM 空输出重试 | 106 次失败 × 3 尝试 | **0 次重试**（确定性失败一次返回） |
| Gate4 收敛 | 3 轮 × 4 次执行全跑 | 问题数不降即早停（1-2 轮） |
| 审查-修复闭环 | 每轮全量重审、无收敛 | 清单驱动 + 单调性 + 豁免 |
| shadow 语义 | 全量重试 + 静默产出 | 单次执行 + 报告打"未修复"标 |
