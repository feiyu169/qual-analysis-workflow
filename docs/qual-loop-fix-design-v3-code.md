# qual v8 死循环修复——代码分册 v3（按 v2 二次审查 7 项修正清单修订）

日期：2026-08-19（v3 修订，承接 `docs/qual-loop-fix-design-v2-code.md`）
依据：v2 代码分册（1230 行）+ `docs/heavyskill-v2-review.md`（二次审查 7 项修正清单）
定位：**v3 = v2（18 项修订，15 项已确认解决）+ 7 项修正（3 项 P0-A 自带测试必红 + 3 项 P0-B + 1 项 P1）**。
v3 不重述 v2 已确认解决项的完整代码，仅在涉及处标注"保持 v2 不变"；v3 修正项的代码均为**可直接实施的完整代码**，行号已对照当前源码逐行复核（核对时间 2026-08-19）。

---

## 0. 行号基准（v3 复核，与 v2 一致并新增 P0-B-1 落点）

| 文件 | 关键锚点（行号 = 当前源码真实行号） |
|---|---|
| `tools/finance/harness_llm.py`（131 行） | 签名 63-72；`llm_caller` 87-124；重试循环 101-123；分类 104-118；通用 except 119-123；**v3 新增 `deadline` keyword-only 参数（签名 63-72 改造）与调用级墙钟检查（101 行 for 循环体顶部）** |
| `tools/finance/workflow.py`（legacy，3158 行） | import 区 27-32；`_generate_chapter` 签名 1156-1162；外层格式重试 1183-1241；吞异常 1237-1241；`_generate_chapter` 调用点 1376；legacy 调用 `review_and_repair_loop` 2942-2949；**v3 新增 `_deadline_guard`（1156 行前）与 `_generate_chapter` 的 `deadline` 透传（签名 1156-1162 改造）** |
| `tools/finance/qual_v8/gates/gate3.py` | `from ...workflow import _build_chapter_prompt, _generate_chapter` 164；调用 183（**v3 加 `deadline=context.get("_wall_deadline")`**） |
| `tools/finance/qual_v8/gates/gate4.py`（346 行） | `_substantive_review` 222-280；**fail-open 226-228**；loop 调用 257-265；**异常吞 278-280**；chapters 写回 110-115；**v3 在 278-280 扩展 `WallClockDeadlineExceeded/LLMCallBudgetExceeded` 显式 fail-closed 分支** |
| `tools/finance/qual_v8/workflow.py`（411 行） | import 17；`WorkflowConfig` 34-40（**v3：`max_llm_calls_per_gate=200`**）；`_FLOW_DEFINITION` 45；熔断阈值 181（保持 2）；`execute` 212-400；Gate 循环 241-363；重试 258-311（`max_attempts` 260，**v3 取 `policy["gate_attempts"]`，enforce=3**）；熔断分类 301-305；results 组装 315-321；enforce 阻断 350-359；report 组装 365-374；终态 377-380；**v3 新增 `RETRY_POLICY`（45 行前）与 execute 顶部主 caller 包装（223-224 后）** |
| `tools/finance/qual_v8/core/circuit_breaker.py`（108 行） | **ErrorType 24-28（v3 删除，改从 error_classifier 单一来源 import）**；init 34-49；`record_failure` **51-58**；`can_execute` 70-90 |
| `tools/finance/qual_v8/core/error_classifier.py`（114 行） | **ErrorType 15-19（v3 追加 UNKNOWN）**；`ERROR_CODE_MAPPING` **34-67（v3 追加 LLM_EMPTY_OUTPUT/REVIEW_UNRESOLVED/UNKNOWN_ERROR）**；`classify` 76-97（**v3 默认分支改 UNKNOWN**）；`classify_from_exception` **99-114** |
| `tools/finance/quality/review_repair_loop.py`（410 行） | `ReviewRepairResult` 20-28；签名 31-38；主循环 53-111（循环体 56-101）；`_run_deep_review` 114-168（纯规则）；`_run_substantive_review` 171-264（caller 构造 182-197；检查器 199-233；debate 235-262）；`_repair_chapters` 267-410（LLM 调用 356；**吞异常 407-408**）；**v3 新增：模块级常量/import（17 行后）、`_issue_signature`（28 行后）、`_ok_result`/`_fail_result`/`_build_review_caller`（171 行前）、`_make_budgeted_caller`** |
| `tools/finance/quality/depth_reviewer.py`（369 行） | `check` 94-192；`_evaluate_by_llm` 224-261（**吞异常 259-261，v2 已改白名单 raise + llm_failed 三元组**）；`_parse_llm_score` 263-283（**默认 50 → None，v2 已改**） |
| `tools/finance/quality/conclusion_validator.py` | `_check_by_llm` 338-407（**吞异常 404-405，v2 已改白名单 raise**） |
| `tools/finance/llm_fallback.py`（v2 新增） | `with_fallback` 装饰器；**v3 在 `except Exception` 前插入 `(LLMCallBudgetExceeded, WallClockDeadlineExceeded)` 白名单** |
| `tools/finance/llm_errors.py`（v2 新增） | `DeterministicLLMFailure` / `LLMCallBudgetExceeded` / **`WallClockDeadlineExceeded`（唯一命名，无 DeadlineExceeded）** |
| `run_qual_full.py`（193 行） / `run_xpev_full.py` | fallback 闭包 68-116 / 151-200（v2 已改 `with_fallback` 接线，v3 不变） |

### v2 → v3 变更摘要（7 项映射）

| # | 审查缺陷（优先级） | v2 问题实证 | v3 修正（本节位置） | 自带测试 |
|---|---|---|---|---|
| 1 | 缺陷 16 签名保留章节号（P0-A） | `re.sub(r"第(\d+)章",r"第@\1章",s)` 后数字归一化把占位符数字也归一化 → 第4/5章签名相等 | findall 捕获 → 归一化 → 计数式 re.sub 还原 | `test_signature_keeps_chapter` 修正版（§1.1） |
| 2 | 缺陷 1 豁免 PASS 绕过（P0-A） | 判据查 `exempted_tracked`（本轮出现集），豁免项停报后空轮 → `passed=True` | PASS 判据改 `not any(e["exempted"] for e in exempted.values())`；DEGRADE 取累积清单 | `test_exemption_failclosed` 修正版（§1.2） |
| 3 | 缺陷 6 单调守卫（P0-A） | `fixed_count=0` 后才 `issues_fixed -= fixed_count` → no-op；before_sigs 取过滤后集不对称 | 先减后置零；before_sigs 取豁免过滤前原始全量集；fixed_sigs 仅未回滚时更新 | `test_monotonic_guard` 修正版（§1.3） |
| 4 | deadline L4 缺失（P0-B） | `create_harness_caller` 无 deadline、`_deadline_guard` 未出现 → Gate3 主链路无调用级检查 | harness 加 keyword-only `deadline`；`_generate_chapter` 透传；`_deadline_guard` 包装主 caller；with_fallback 白名单 | `test_budget_deadline` 修正版（§1.4） |
| 5 | arch/code 三处矛盾（P0-B） | review_caller_override / enable_debate 驱动声称 / DeadlineExceeded 命名漂移 | code 侧确认 + 需同步段落清单（§1.5） | 无新测试（注释/命名确认） |
| 6 | 熔断死激活 + BUSINESS 污染（P0-B） | enforce attempts=2 与阈值 2 同步耗尽 → `can_execute()` 永不 False；UNKNOWN→TRANSIENT 绕过 BUSINESS | enforce 2→3（阈值 2 保持）；ErrorType.UNKNOWN 权重 0 仅记录；文本兜底不再默认 TRANSIENT | `test_circuit_breaker_reachable` 新增（§1.6） |
| 7 | N5 预算错配（P1） | 60 上限 vs 每轮真实 27-50 次 → 第 2 轮 T_BUDGET 早停打降级标 | `max_llm_calls_per_gate` 60→200（§1.7） | 配置断言并入 `test_retry_policy_table`/新增断言 |

---

## 1. 逐项修正表（7 项 × {修正后完整代码 / 接口签名 / 测试用例 / 副作用}）

### 1.1 缺陷 16：签名保留章节号（P0-A-1）——v2 自带测试必红 #1

**缺陷实证**（审查裁决 1，审议者实跑正则链）：v2 `_issue_signature` 先 `re.sub(r"第(\d+)章", r"第@\1章", issue)` 再 `re.sub(r"\d+\.?\d*", "N", s)`——第二条正则把占位符 `第@4章` 的 `4` 也归一化为 `N`，导致 `第4章 营收增长100亿无解释` 与 `第5章 ...` 签名都变成 `第@N章 营收增长N亿无解释`，跨章误豁免。`test_signature_keeps_chapter` 断言不相等 → **必红**。

**修正策略**（审查裁决 1 处方）：① `chapters = re.findall(r"第(\d+)章", issue)` 捕获章节号（保持文本顺序）→ ② `re.sub(r"\d+\.?\d*","N",issue)` 归一化全部数字 → ③ 按捕获顺序把 `第N章` 逐个还原为 `第@<章号>章`。
**注意**：不能对多章节号文本用 `str.replace("第N章", f"第@{ch}章")`——`str.replace` 全量替换，`第4章与第5章` 会变成两个 `第@4章`；必须用带计数的 `re.sub` 回调（一次匹配消费一个章节号）。

**修正后完整代码**（`tools/finance/quality/review_repair_loop.py`，新函数，置于 `ReviewRepairResult`（28 行）之后）：

```python
def _issue_signature(issue: str, keep_chapter: bool = True) -> str:
    """问题签名：归一化数字但保留章节上下文（第N章 → 第@N章，不同章节签名不同）。

    v3 修正（缺陷 16，v2 必红 #1）：v2 实现先换占位符再归一化，把占位符数字
    （第@4章 的 "4"）也归一化成 N → 第4章与第5章签名相等。v3 三段式：
      ① findall 捕获章节号（保持文本顺序）→ ② 归一化全部数字 → ③ 用带计数的
      re.sub 按捕获顺序把 "第N章" 逐个还原为 "第@<章号>章"。
    多章节号文本必须用带计数 re.sub（str.replace 会全量替换，多个章节号变成同一个）。

    keep_chapter=False 仅用于跨章聚合类审计统计，绝不用于豁免判定。
    """
    import re
    if keep_chapter:
        chapters = re.findall(r"第(\d+)章", issue)           # ① 捕获章节号（保持顺序）
        s = re.sub(r"\d+\.?\d*", "N", issue)                 # ② 归一化金额/年份等全部数字
        if chapters:                                         # ③ 按顺序还原（防多处同形）
            it = iter(chapters)
            def _restore(m):
                try:
                    return f"第@{next(it)}章"
                except StopIteration:
                    return m.group(0)                        # 防御：捕获数不足时保留原样，不崩溃
            s = re.sub(r"第N章", _restore, s)
        return s.strip()
    else:
        s = re.sub(r"第\d+章", "第@章", issue)
        s = re.sub(r"\d+\.?\d*", "N", s)
        return s.strip()
```

**接口签名**：`_issue_signature(issue: str, keep_chapter: bool = True) -> str`（模块私有，签名不变；keep_chapter 语义不变——豁免判定强制 True）。

**验收测试**（`tools/finance/quality/test_loop_fix.py`，修正版，断言明确）：

```python
def test_signature_keeps_chapter():
    """缺陷 16 修正版：第4/5章不同签；第12章多数字不破损；同章不同数字同签；多章节号顺序对应。

    v2 必红：第4/5章签名相等（占位符数字被归一化）。v3 修复后：
      - 第4章 vs 第5章 → 不同签名；
      - 第12章 → 章节号 "12" 完整保留（不得被归一化为 N）；
      - 同章不同数字（100亿 vs 99亿）→ 相同签名（数字归一化仍生效）；
      - 多章节号（第4章与第5章）→ 按顺序还原为 第@4章 与 第@5章（防 str.replace 全量替换）。
    """
    s4 = _issue_signature("第4章 营收增长100亿无解释")
    s5 = _issue_signature("第5章 营收增长100亿无解释")
    assert s4 != s5, "不同章节必须不同签名（v2 缺陷：第4/5章签名相等）"
    assert "第@4章" in s4 and "第@5章" in s5

    s12 = _issue_signature("第12章 营收增长100亿无解释")
    assert "第@12章" in s12, "多数字章节号不得被归一化破坏（第12章的 12 必须保留）"
    assert s12 != s4

    assert _issue_signature("第4章 营收增长100亿无解释") == \
           _issue_signature("第4章 营收增长99亿无解释"), "同章不同数字应同签"

    multi = _issue_signature("第4章与第5章数据矛盾")
    assert "第@4章" in multi and "第@5章" in multi, "多章节号必须按顺序对应还原"
```

**副作用**：无新异常；`keep_chapter=False` 分支行为不变；跨章同形 issue 不再被合并（豁免学习按章独立计数，误豁免概率下降）；无签名变化（原 v2 签名即 `_issue_signature(issue, keep_chapter=True)`）。

---

### 1.2 缺陷 1：豁免 PASS 绕过（P0-A-2）——v2 自带测试必红 #2

**缺陷实证**（审查裁决 2）：v2 收敛判据查 `exempted_tracked`（仅本轮豁免**再次出现**时非空），而豁免学习只置 `entry["exempted"]=True`、不写入该集 → 已豁免签名后续轮不再报出时，`not round_issues and not exempted_tracked → passed=True` 静默放行。`test_exemption_failclosed`（第 4 轮返回空）→ **必红**。

**修正策略**（审查裁决 2 处方）：
1. **PASS 判据**改为 `not round_issues and not any(e["exempted"] for e in exempted.values())`（查**累积豁免清单**，不是本轮出现集）；
2. **DEGRADE 分支**的 `remaining`/`exempted_count` 取自累积清单（含本轮未再报出的豁免项）——为此豁免条目新增 `"example"` 字段记录最近一次问题文本（v2 的 `exempted_tracked` 集合整体删除）；
3. 豁免证据护栏（≥3 轮 + 从未修复成功）与 `fixed_sigs` 追踪保持 v2 语义（详见 1.3 对 fixed_sigs 的落点修正）。

**修正后完整代码**（`tools/finance/quality/review_repair_loop.py`，主循环内步骤 2-3，替换 v2 文档 §缺陷 1 的对应段；与 1.3/§2.2 合并版联看）：

```python
        # 2. 豁免剔除（缺陷 1 修正版：条目记录 example 文本；豁免项不进入修复，但累积计入收敛判定）
        kept = []
        for iss in round_issues:
            sig = _issue_signature(iss)
            entry = exempted.setdefault(sig, {
                "rounds": 0, "exempted": False, "first_seen": round_num, "example": iss,
            })
            entry["rounds"] += 1
            entry["example"] = iss                            # 最近一次问题文本（随修复演变）
            if entry["exempted"]:
                continue                                      # 豁免项不进入修复（仍计入 remaining）
            kept.append(iss)
        round_issues = kept

        # 3. 收敛判定（缺陷 1 修正版：PASS 判据 = 无未豁免问题 且 累积豁免为空）
        exempted_active = any(e["exempted"] for e in exempted.values())
        if not round_issues and not exempted_active:
            logger.info(f"审查修复循环 第{round_num}轮 通过，无问题")
            return _ok_result(round_num, chapters, budget_state, len(all_issues), issues_fixed)
        if not round_issues and exempted_active:
            # 全部问题被豁免 → 不允许静默通过（v3：含本轮未再报出的豁免项——
            # v2 查 exempted_tracked（本轮出现集）→ 豁免项停报后空轮 passed=True 绕过）
            exempted_sigs = sorted(sig for sig, e in exempted.items() if e["exempted"])
            remaining = [f"[已豁免{e['rounds']}轮] {e['example']}"
                         for sig, e in exempted.items() if e["exempted"]][:10]
            logger.warning(
                f"审查修复循环 第{round_num}轮：{len(exempted_sigs)} 个问题已豁免，判定不通过")
            return _fail_result(round_num, chapters, budget_state,
                                remaining=remaining,
                                issues_found=len(all_issues), issues_fixed=issues_fixed,
                                exempted_count=len(exempted_sigs), exempted=exempted_sigs)
```

（主循环入口的豁免状态初始化：`exempted: Dict[str, Dict[str, Any]] = {}`；`fixed_sigs: set = set()`。`exempted_tracked` 从 v2 代码中删除，避免与累积清单双轨。）

**接口签名**：无签名变化（`exempted`/`fixed_sigs` 为函数内状态；`ReviewRepairResult.exempted/exempted_count` 字段 v2 已定义）。

**验收测试**（`tools/finance/quality/test_loop_fix.py`，修正版，断言明确）：

```python
def test_exemption_failclosed(monkeypatch):
    """缺陷 1 修正版：PASS 判据查累积豁免，非本轮出现集（v2 必红 #2）。

    场景：fake 审查 caller 前 6 次审查调用（第 1-3 轮，含修复后重审）持续报出同签名问题、
    且从未修复成功 → 豁免学习激活（≥3 轮 + 无修复迹象）；第 7 次起审查返回干净
    （问题消失但未真实修复——v2 在此空轮 passed=True 静默放行）。
    v3：空轮 + 累积豁免非空 → passed=False、remaining 含 "[已豁免" 前缀、exempted_count >= 1。
    注：豁免轮次按"出现次数"累计（重审重复报出加速豁免），触发轮次可能早于第 4 轮，
    断言不依赖具体轮次，只依赖"空轮 + 累积豁免 → 不通过"。
    """
    from finance.quality import review_repair_loop as rrl

    state = {"depth_calls": 0}
    def fake(ch_name, prompt):
        if ch_name.startswith("repair_patch"):
            return "无法修复"                       # 非 JSON → parse 空 → fixed 0（问题未修复）
        if ch_name == "conclusion_validation":
            return "总分：90"                       # 结论无问题
        state["depth_calls"] += 1
        if state["depth_calls"] <= 6:
            return "总分：50\n问题：第4章 营收增长100亿无解释"   # 同签名问题（跨轮重复）
        return "总分：90"                           # 第 7 次起审查干净

    monkeypatch.setattr("finance.harness_llm.create_harness_caller", lambda **kw: fake)
    monkeypatch.setattr("finance.llm_caller.create_deepseek_caller", lambda **kw: fake)
    monkeypatch.setattr(rrl, "_run_deep_review", lambda ch, wd: [])

    chapters = {4: "第4章 营收增长100亿无解释"}
    result = rrl.review_and_repair_loop(
        chapters, ctx=None, llm_caller=fake,
        wind_data=None, max_rounds=4, industry="新能源汽车",
    )
    assert result.passed is False                       # 旧代码：空轮 + exempted_tracked 空 → passed=True（必红）
    assert any("[已豁免" in r for r in result.remaining_issues)
    assert result.exempted_count >= 1
    assert result.rounds <= 4
```

**副作用**：`exempted_tracked` 删除后，`ReviewRepairResult.exempted` 语义从"本轮出现过的豁免签名"变为"累积豁免签名全量"（审计更完整）；`remaining` 条目标签 `[已豁免N轮]` 中 N 为出现次数（跨轮+重审累计）；无新异常。

---

### 1.3 缺陷 6：单调守卫（P0-A-3）——v2 自带测试必红 #3

**缺陷实证**（审查裁决 3）：v2 代码 `fixed_count = 0` 后才执行 `issues_fixed -= fixed_count` → 恒减 0，no-op，计数虚高（`test_monotonic_guard` 必红）；且 `before_sigs` 取"豁免剔除后"的 `round_issues`，与 `after_sigs`（修复后全量重审，未做豁免剔除）口径不对称。

**修正策略**（审查裁决 3 处方）：
1. **先减后置零**：`issues_fixed -= fixed_count` 必须在 `fixed_count = 0` **之前**；
2. **before 同口径**：`before_sigs`/`before_count` 移到豁免过滤**之前**，直接取 `deep_issues + substantive_issues` 原始全量集（与 after_sigs 严格同口径）；
3. **fixed_sigs 落点修正**（v3 语义完善）：仅在**未回滚**时把 `before_sigs - after_sigs` 记入 `fixed_sigs`——若本轮回滚，章节恢复为轮首快照，"已修复"标记不得写入（否则豁免证据护栏被污染）。

**修正后完整代码**（`tools/finance/quality/review_repair_loop.py`，主循环步骤 1b 与 6，替换 v2 文档 §缺陷 6）：

```python
        # 1. 执行审查（全量审查，口径 A）
        deep_issues = _run_deep_review(chapters, wind_data)
        substantive_issues = _run_substantive_review(
            chapters, repair_caller, wind_data, industry,
            enable_debate=enable_debate,
            budget_state=budget_state,
            deadline=deadline,
            llm_call_budget=llm_call_budget,
        )
        round_issues = deep_issues + substantive_issues

        # 1b. before 口径（缺陷 6 修正版）：豁免过滤前的原始全量问题集，
        #     与 after_sigs（修复后全量重审）严格同口径
        before_sigs = {_issue_signature(i) for i in round_issues}
        before_count = len(round_issues)

        # ...（步骤 2 豁免剔除 + 步骤 3 收敛判定 + 步骤 4/5 shadow/无 caller，见 1.2 与 §2.2）...

        # 6. 修复（单调性守卫：deepcopy 快照 + 签名差集 + 前后同口径；缺陷 6 修正版）
        snapshot = _copy.deepcopy(chapters)
        try:
            fixed_count = _repair_chapters(chapters, round_issues, repair_caller, wind_data)
        except (DeterministicLLMFailure, LLMCallBudgetExceeded, WallClockDeadlineExceeded) as e:
            return _fail_result(round_num, chapters, budget_state,
                                remaining=[f"{REVIEW_INCOMPLETE_PREFIX} 修复失败: {e}"],
                                issues_found=len(all_issues), issues_fixed=issues_fixed,
                                review_incomplete=True,
                                budget_exceeded=isinstance(e, LLMCallBudgetExceeded),
                                wall_clock_exceeded=isinstance(e, WallClockDeadlineExceeded))
        issues_fixed += fixed_count

        # 修复后重审（与轮首同口径：deep + substantive，同一 budget_state/deadline）
        try:
            after_issues = (_run_deep_review(chapters, wind_data)
                            + _run_substantive_review(
                                chapters, repair_caller, wind_data, industry,
                                enable_debate=enable_debate,
                                budget_state=budget_state,
                                deadline=deadline,
                                llm_call_budget=llm_call_budget))
        except (DeterministicLLMFailure, LLMCallBudgetExceeded, WallClockDeadlineExceeded) as e:
            return _fail_result(round_num, chapters, budget_state,
                                remaining=[f"{REVIEW_INCOMPLETE_PREFIX} 重审失败: {e}"],
                                issues_found=len(all_issues), issues_fixed=issues_fixed,
                                review_incomplete=True,
                                budget_exceeded=isinstance(e, LLMCallBudgetExceeded),
                                wall_clock_exceeded=isinstance(e, WallClockDeadlineExceeded))
        after_sigs = {_issue_signature(i) for i in after_issues}
        new_sigs = after_sigs - before_sigs
        if len(after_issues) > before_count or new_sigs:
            logger.warning(
                f"单调性守卫：问题数 {before_count}→{len(after_issues)}，"
                f"新签名 {sorted(new_sigs)[:3]}，回滚本轮修复")
            chapters.clear()
            chapters.update(snapshot)                        # deepcopy 快照恢复
            issues_fixed -= fixed_count                      # 缺陷 6 修正：先还原计数（fixed_count 尚未置零）
            fixed_count = 0                                  # 再置零（v2 顺序相反 → no-op 必红）
        else:
            for sig in before_sigs - after_sigs:
                fixed_sigs.add(sig)                          # 仅未回滚时记录"已修复"（供豁免证据护栏）
        logger.info(f"审查修复循环 第{round_num}轮 修复{fixed_count}个问题")
```

**接口签名**：无签名变化（全部为主循环内部语句序修正）。

**验收测试**（`tools/finance/quality/test_loop_fix.py`，修正版，断言明确）：

```python
def test_monotonic_guard(monkeypatch):
    """缺陷 6 修正版：先减后置零 + before 取原始全量集（v2 必红 #3）。

    场景：第 1 轮轮首审查报出签名 A 的问题 → 修复（monkeypatch 的 _repair_chapters
    直接把章节改成新内容并返回 fixed_count=1）→ 修复后重审报出全新签名 B
    （after_sigs ⊄ before_sigs）→ 单调守卫回滚：
      - chapters == 轮首 deepcopy 快照（内容恢复）；
      - result.issues_fixed == 0（v2 顺序 fixed_count=0 后才减 → issues_fixed 恒 1 → 必红）。
    """
    import copy
    from finance.quality import review_repair_loop as rrl

    chapters = {4: "第4章 营收增长100亿无解释"}
    snapshot = copy.deepcopy(chapters)

    state = {"depth_calls": 0}
    def fake_review(ch_name, prompt):
        if ch_name.startswith("repair_patch"):
            return "无法修复"
        if ch_name == "conclusion_validation":
            return "总分：90"
        state["depth_calls"] += 1
        if state["depth_calls"] == 1:
            return "总分：50\n问题：第4章 营收增长100亿无解释"   # 轮首审查（签名 A）
        return "总分：50\n问题：第4章 风险提示缺失"             # 修复后重审（签名 B：全新）
    def fake_repair(chapters_, issues, caller, wind_data):
        chapters_[4] = "第4章 营收增长5000亿无解释"             # 修复引入新内容（fixed=1）
        return 1

    monkeypatch.setattr("finance.harness_llm.create_harness_caller", lambda **kw: fake_review)
    monkeypatch.setattr("finance.llm_caller.create_deepseek_caller", lambda **kw: fake_review)
    monkeypatch.setattr(rrl, "_run_deep_review", lambda ch, wd: [])
    monkeypatch.setattr(rrl, "_repair_chapters", fake_repair)

    result = rrl.review_and_repair_loop(
        chapters, ctx=None, llm_caller=fake_review,
        wind_data=None, max_rounds=1, industry="新能源汽车",
    )
    assert chapters == snapshot                 # 回滚到轮首 deepcopy 快照
    assert result.issues_fixed == 0             # 计数同步还原（v2 no-op → 1，必红）
    assert result.passed is False
```

**副作用**：回滚后 `chapters` 恢复为轮首快照，下一轮从干净状态继续；`fixed_sigs` 只在未回滚时更新（v3 语义完善，防止回滚轮误标"已修复"污染豁免证据护栏）；单调守卫的 after 重审照常计入 `budget_state["calls"]`（缺陷 7 口径一致）。

---

### 1.4 deadline L4 缺失（P0-B-1）——code 侧补调用级墙钟检查

**缺陷实证**（审查裁决 3 + 修正清单 P0-B-1）：v2 code 分册 `create_harness_caller` 签名无 `deadline` 参数、`_deadline_guard` 全文未出现 → "deadline+300s 可证明上界"验收不成立（**Gate3 写作主链路无调用级检查**：`execute()` 只在 Gate 循环顶部查墙钟，单次 300s 调用期间与 `_generate_chapter` 重试链内均无检查）。

**修正策略**（审查修正清单 P0-B-1 处方，三件套）：
1. `create_harness_caller` 加 **keyword-only** `deadline: Optional[float] = None`，`llm_caller` 每次尝试前查 `time.monotonic() > deadline` → 抛 `WallClockDeadlineExceeded`（检查点在重试循环内、`try` 之外 → 天然不被 `except Exception` 吞）；
2. 新增 `_deadline_guard(caller, deadline)`（`tools/finance/workflow.py`）包装主 caller；`qual_v8/workflow.py execute()` 顶部对 `context["llm_caller"]` 单点包装（Gate1/3/4/5/6/8 全部经 context 取 caller，单点即全覆盖主链路）；`_generate_chapter` 增加 keyword-only `deadline` 透传（gate3 调用点传入 `context["_wall_deadline"]`），并在 except 链中把 `WallClockDeadlineExceeded` 与 `DeterministicLLMFailure` 并列短路降级（**不重试**）；
3. `with_fallback` 的 `except Exception` 之前插入 `(LLMCallBudgetExceeded, WallClockDeadlineExceeded)` 白名单（**预算/墙钟耗尽不换模型重试**——重试重复消耗预算/时间）；gate4 的兜底 except 扩展这两个异常的显式 fail-closed 分支。

**修正后完整代码**：

(a) `tools/finance/harness_llm.py`——签名 63-72 与 `llm_caller` 87-124 改造（顶部 import 区补 `from typing import Optional` 与 `from .llm_errors import DeterministicLLMFailure, WallClockDeadlineExceeded`）：

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
    *,
    deadline: Optional[float] = None,   # v3 新增（P0-B-1）：墙钟 deadline（time.monotonic 绝对值）；
                                        # keyword-only + 默认 None → 旧调用零修改兼容
):
    """创建 llm_caller(chapter_name, prompt) -> str。

    ...（原 docstring 保持）...
    deadline: 墙钟截止（time.monotonic 绝对值，秒）。每次调用尝试前检查，
              超时抛 WallClockDeadlineExceeded（不重试）。None 表示不启用。
    """
    base = base_url or _default_base_url()
    sys_prompt = system if system is not None else SYSTEM_PROMPT

    def llm_caller(chapter_name: str, prompt: str) -> str:
        payload = {
            "system": sys_prompt,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "maxTokens": max_tokens,
        }
        if model:
            payload["model"] = model
        if provider:
            payload["provider"] = provider

        _log(f"开始 {chapter_name} (prompt={len(prompt)}字符, maxTokens={max_tokens})")
        last_err = None
        for attempt in range(max_retries + 1):
            # v3（P0-B-1）：调用级墙钟检查——在重试循环内、每次尝试前，命中即抛且不重试。
            # 检查点位于 try 之外 → WallClockDeadlineExceeded 不会被下方 except Exception 吞掉。
            if deadline is not None and time.monotonic() > deadline:
                raise WallClockDeadlineExceeded(
                    f"墙钟预算耗尽（deadline={deadline:.0f}，当前={time.monotonic():.0f}）")
            t0 = time.time()
            try:
                data = _call_bridge(payload, base, timeout)
                if not data.get("ok"):
                    finish = data.get("finishReason") or data.get("finish") or {}
                    text = data.get("text") or ""
                    if (isinstance(finish, dict) and finish.get("kind") == "max-tokens") or \
                       (isinstance(finish, str) and "max" in finish):
                        if text and len(text.strip()) > 0:
                            _log(f"⚠️ 完成 {chapter_name} 尝试{attempt+1}: max-tokens 截断，保留 {len(text)} 字符")
                            return text + "\n\n<!-- ⚠️ LLM 输出被 max-tokens 截断，内容不完整 -->"
                        # P0-B-4（v2）：max-tokens 且无内容 → 确定性失败（不重试，上抛）
                        raise DeterministicLLMFailure(
                            data.get("error") or ("finish=" + json.dumps(finish) if finish else "max-tokens 空输出"))
                    raise RuntimeError(
                        data.get("error") or ("finish=" + json.dumps(finish) if finish else "llm bridge 调用失败"))
                text = data["text"]
                _log(f"完成 {chapter_name} 尝试{attempt+1} ({round(time.time()-t0,1)}s, {len(text)}字符)")
                return text
            except DeterministicLLMFailure:
                raise                                        # P0-B-4（v2）：确定性失败不重试
            except Exception as e:  # noqa: BLE001
                last_err = e
                _log(f"失败 {chapter_name} 尝试{attempt+1}: {repr(e)[:200]} ({round(time.time()-t0,1)}s)")
                if attempt < max_retries:
                    time.sleep(2 * (attempt + 1))
        raise last_err

    return llm_caller
```

（**v3 清理**：v2 §2.3 曾列出 `on_deterministic` 参数，v3 **移除**——v2 全部代码块与测试均未消费它，保留只会成为死参数；确定性失败统一由 raise + 全链 except 白名单表达。）

(b) `tools/finance/workflow.py`——新增 `_deadline_guard`（置于 `_generate_chapter` 1156 行之前；模块顶部 import 区补 `import time` 与 `from .llm_errors import DeterministicLLMFailure, WallClockDeadlineExceeded`）：

```python
def _deadline_guard(
    caller: Optional[Callable[[str, str], str]],
    deadline: Optional[float],
) -> Optional[Callable[[str, str], str]]:
    """包装 llm_caller：每次调用前检查墙钟 deadline，超时抛 WallClockDeadlineExceeded。

    P0-B-1（v3）：Gate3 写作主链路的调用级墙钟检查——补上 v2 只查 Gate 边界的缺口，
    使"deadline + 300s 单调用超时"的可证明上界成立。deadline=None 时原样返回（零开销、兼容旧调用）。
    """
    if caller is None or deadline is None:
        return caller
    def guarded(chapter_name: str, prompt: str) -> str:
        if time.monotonic() > deadline:
            raise WallClockDeadlineExceeded(
                f"墙钟预算耗尽（deadline={deadline:.0f}，当前={time.monotonic():.0f}）")
        return caller(chapter_name, prompt)
    return guarded
```

(c) `tools/finance/workflow.py`——`_generate_chapter` 1156-1162 签名 + 1183-1241 循环改造：

```python
def _generate_chapter(
    chapter_num: int,
    prompt: str,
    ctx: DataContext,
    llm_caller: Optional[Callable[[str, str], str]] = None,
    max_format_retries: int = 3,
    *,
    deadline: Optional[float] = None,    # v3 新增（P0-B-1）：keyword-only，旧调用零修改兼容
) -> str:
    """...（原 docstring 保持，补 deadline 说明）..."""
    from .quality.structural_check import structural_check

    chapter_def = CHAPTERS[chapter_num]
    chapter_name = f"第{chapter_num}章: {chapter_def['title']}"

    if llm_caller is not None:
        caller = _deadline_guard(llm_caller, deadline)      # v3：调用级墙钟检查（写作主链路）
        for attempt in range(max_format_retries + 1):
            try:
                if attempt == 0:
                    logger.info(f"调用 LLM 生成 {chapter_name}")
                else:
                    logger.info(f"格式验证失败，重试 {attempt}/{max_format_retries}: {chapter_name}")

                content = caller(chapter_name, prompt)       # v3：经 guard 的 caller（原 1190 行 llm_caller 替换）

                # T4: 清洗AI生成痕迹
                content, violations = clean_ai_artifacts(content)
                if violations:
                    logger.warning(f"{chapter_name} 发现AI痕迹: {violations}")

                # 格式验证
                check_result = structural_check(f"ch{chapter_num}", content)

                # 前端闸门1-5（HGF 驱动：数值量级/空章/空壳/财年/币值）
                gate_issues = []
                try:
                    from .quality.numeric_guard import check_chapter_gates
                    gate_result = check_chapter_gates(
                        chapter_num, content,
                        _wind_to_dict(ctx.wind) if ctx.wind else {},
                        market=ctx.market,
                    )
                    if not gate_result.passed:
                        gate_issues = [v.message for v in gate_result.violations[:4]]
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"前端闸门执行失败（非阻断）: {e}")

                all_issues = list(check_result.issues) + gate_issues

                if check_result.passed and not gate_issues:
                    logger.info(f"{chapter_name} 生成完成: {len(content)} 字符, 格式+闸门验证通过")
                    return content
                elif attempt < max_format_retries:
                    logger.warning(
                        f"{chapter_name} 验证失败 (score={check_result.score:.0f}, "
                        f"gate_issues={len(gate_issues)}, issues={len(all_issues)}), 准备重试"
                    )
                    format_fix = _build_gate_fix_prompt(chapter_num, chapter_title=chapter_def['title'],
                                                        issues=all_issues[:6])
                    prompt = prompt + format_fix
                else:
                    logger.warning(
                        f"{chapter_name} 验证失败 (score={check_result.score:.0f}, "
                        f"gate={gate_issues[:3]}), 已达最大重试次数，返回当前内容"
                    )
                    return content

            except WallClockDeadlineExceeded as e:           # v3：deadline 不可重试，立即降级
                logger.error(f"{chapter_name} 墙钟预算耗尽，不重试: {e}")
                return _build_insufficient_data_response(chapter_num, ctx, f"墙钟预算耗尽: {e}")
            except DeterministicLLMFailure as e:             # P0-B-4（v2）：确定性失败不重试
                logger.error(f"{chapter_name} 确定性失败，不重试: {e}")
                return _build_insufficient_data_response(chapter_num, ctx, f"确定性失败: {e}")
            except Exception as e:
                logger.error(f"LLM 调用失败 {chapter_name}: {e}")
                if attempt == max_format_retries:
                    return _build_insufficient_data_response(chapter_num, ctx, str(e))

        # 不应该到达这里，但作为安全措施
        return _build_insufficient_data_response(chapter_num, ctx, "生成失败")
    else:
        return _build_insufficient_data_response(chapter_num, ctx, "LLM 调用器未提供")
```

(d) 调用链（v8 主链路单点包装 + gate3 透传 + gate4 保持 + gate8 推荐）：

`tools/finance/qual_v8/workflow.py` execute() 顶部（223-224 行后，v2 缺陷 8 注入块内追加）：

```python
        _wall_start = _time.monotonic()
        _wall_deadline = _wall_start + self.config.global_timeout_seconds
        context["_wall_deadline"] = _wall_deadline            # 注入 gate4/loop（缺陷 8）
        context["_llm_call_count"] = 0                        # 审计（缺陷 7 写回点）
        context["llm_call_budget"] = self.config.max_llm_calls_per_gate
        policy = RETRY_POLICY.get(qual_mode, RETRY_POLICY["shadow"])   # 缺陷 13
        context["shadow_skip_repair"] = policy["skip_repair"] and self.config.shadow_skip_repair
        context["gate4_max_rounds"] = policy["repair_rounds"]
        # P0-B-1（v3）：单点包装主 caller——Gate1/3/4/5/6/8 全部经 context["llm_caller"] 调用，
        # 包装后 Gate3 写作主链路获得调用级墙钟检查（与 gate3 透传 deadline 双保险）
        if context.get("llm_caller") is not None:
            from ..workflow import _deadline_guard           # 惰性 import（gate3 同款，防循环依赖）
            context["llm_caller"] = _deadline_guard(context["llm_caller"], _wall_deadline)
```

`tools/finance/qual_v8/gates/gate3.py:183`：

```python
                content = _generate_chapter(chapter_num, prompt, ctx, llm_caller,
                                            deadline=context.get("_wall_deadline"))   # P0-B-1（v3）
```

`tools/finance/qual_v8/gates/gate4.py:257-265`（v2 缺陷 10 接线，deadline 已传 `context.get("_wall_deadline")`，v3 保持）；`gate8.py:325-327` 推荐同步：

```python
            review_caller = create_harness_caller(
                # ...（原有参数）...
                deadline=context.get("_wall_deadline"),    # P0-B-1（v3）推荐：红队审查同样受墙钟约束
            )
```

(e) `tools/finance/llm_fallback.py`——`with_fallback` 的 caller 内 except 链改造（**新异常不被吞**）：

```python
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
        except (LLMCallBudgetExceeded, WallClockDeadlineExceeded):
            # v3（P0-B-1）：预算/墙钟耗尽不换模型重试（重试重复消耗预算/时间），原样上抛
            hist.append(True); _trim()
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

（`with_fallback` 顶部补 `from .llm_errors import DeterministicLLMFailure, LLMCallBudgetExceeded, WallClockDeadlineExceeded`。）

(f) `tools/finance/qual_v8/gates/gate4.py:278-280`——兜底 except 扩展（新异常显式 fail-closed；gate4 顶部补 `from ...llm_errors import DeterministicLLMFailure, LLMCallBudgetExceeded, WallClockDeadlineExceeded`）：

```python
        except DeterministicLLMFailure as e:
            logger.error(f"Gate4 实质审查确定性失败: {e}")
            return {"passed": False, "errors": [f"实质审查确定性失败: {e}"],
                    "repaired_chapters": None}
        except WallClockDeadlineExceeded as e:
            logger.error(f"Gate4 实质审查墙钟预算耗尽: {e}")
            return {"passed": False, "errors": [f"实质审查墙钟预算耗尽: {e}"],
                    "repaired_chapters": None}
        except LLMCallBudgetExceeded as e:
            logger.error(f"Gate4 实质审查调用超预算: {e}")
            return {"passed": False, "errors": [f"实质审查调用超预算: {e}"],
                    "repaired_chapters": None}
        except Exception as e:
            logger.error(f"Gate4 实质审查失败: {e}")
            return {"passed": False, "errors": [f"实质审查异常: {e}"],
                    "repaired_chapters": None}
```

**接口签名**：
- `create_harness_caller(..., *, deadline: Optional[float] = None)`（keyword-only 追加；v3 移除无消费方的 `on_deterministic`，见上）；
- `_deadline_guard(caller: Optional[Callable[[str, str], str]], deadline: Optional[float]) -> Optional[Callable[[str, str], str]]`（新函数，`tools/finance/workflow.py`）；
- `_generate_chapter(..., *, deadline: Optional[float] = None)`（keyword-only 追加）。

**验收测试**（`tools/finance/quality/test_loop_fix.py` + `tools/finance/test_harness_llm_fix.py`，修正版，断言明确）：

```python
def test_budget_deadline(monkeypatch):
    """缺陷 7/8 + P0-B-1 修正版：预算与墙钟双重护栏在调用级生效（v2 仅断言预算）。

    (a) 预算：llm_call_budget=2 → 第 3 次包装调用抛 LLMCallBudgetExceeded → loop 终止：
        result.budget_exceeded is True、result.llm_calls == 3（计数递增后抛）、
        result.passed is False、fake 未被第 3 次调用（n <= 2）；
    (b) 墙钟：deadline=monotonic()-1（已过期）→ 首次包装调用即抛 WallClockDeadlineExceeded →
        result.wall_clock_exceeded is True、result.passed is False；
    (c) harness 自身 deadline：create_harness_caller(max_retries=0, deadline=已过期)
        首次调用即抛 WallClockDeadlineExceeded（Gate3 主链路 L4，无需网络）。
    """
    import time
    import pytest
    from finance.quality import review_repair_loop as rrl
    from finance.harness_llm import create_harness_caller
    from finance.llm_errors import WallClockDeadlineExceeded

    # (a) 预算
    calls = {"n": 0}
    def fake(ch_name, prompt):
        calls["n"] += 1
        return "总分：50\n问题：第4章 营收增长100亿无解释"
    monkeypatch.setattr("finance.harness_llm.create_harness_caller", lambda **kw: fake)
    monkeypatch.setattr("finance.llm_caller.create_deepseek_caller", lambda **kw: fake)
    monkeypatch.setattr(rrl, "_run_deep_review", lambda ch, wd: [])
    result = rrl.review_and_repair_loop(
        {4: "第4章 营收增长100亿无解释"}, ctx=None, llm_caller=fake,
        wind_data=None, max_rounds=4, industry="新能源汽车",
        llm_call_budget=2, deadline=None,
    )
    assert result.budget_exceeded is True
    assert result.llm_calls == 3                 # 第 3 次包装调用（计数递增后）抛预算异常
    assert result.passed is False
    assert calls["n"] <= 2                       # fake 未被第 3 次调用（第 3 次在 base 调用前被拒）

    # (b) 墙钟（loop 内 budgeted caller 调用前检查）
    result2 = rrl.review_and_repair_loop(
        {4: "第4章 营收增长100亿无解释"}, ctx=None, llm_caller=fake,
        wind_data=None, max_rounds=4, industry="新能源汽车",
        llm_call_budget=None, deadline=time.monotonic() - 1,
    )
    assert result2.wall_clock_exceeded is True
    assert result2.passed is False

    # (c) harness 自身 deadline（Gate3 主链路调用级检查，L4）
    caller = create_harness_caller(max_retries=0, deadline=time.monotonic() - 1)
    with pytest.raises(WallClockDeadlineExceeded):
        caller("t", "p")
```

**副作用**：`_generate_chapter`/`create_harness_caller` 新参数全部 keyword-only + 默认 None → 旧调用（`workflow.py:1376`、run 脚本、gate8）零修改兼容；`_deadline_guard` 惰性 import（`qual_v8/workflow.py` 内 `from ..workflow import ...`）防循环依赖；WallClockDeadlineExceeded 已列入全链白名单（深度/结论/修复/debate/gate4/`_generate_chapter`/with_fallback），不被任何 `except Exception` 吞掉（自检表见 §5）；deadline 粒度=单次调用前检查（在途 300s 调用不受中断，下一尝试前生效——文档注明）。

---

### 1.5 arch/code 三处矛盾（P0-B-2）——code 侧确认 + 需同步段落清单

**缺陷实证**（审查裁决 3）：v2-arch 与 v2-code 三处互斥：① review_caller 构造互斥（arch 注入 vs code 内部自建）；② enable_debate 链（arch config 驱动 vs code gate4 硬编码 False）；③ 异常命名漂移（DeadlineExceeded vs WallClockDeadlineExceeded）。

**code 侧最终裁决（v3 确认）**：

| # | 矛盾点 | code 侧裁决 | 需同步的具体位置（v2 code 分册行号 + 源码落点） |
|---|---|---|---|
| ① | review_caller_override | **code 侧已删除**：审查 caller 由 loop 内部 `_build_review_caller` 构造（REVIEW_SYSTEM + fallback + budgeted + deadline），gate4 只传主 caller；**全仓无 review_caller_override 参数**（grep 实测 `tools/finance` 0 匹配） | v2 文档 §2.2 说明段（v2 文档 1016 行"删除原方案虚构的 review_caller_override 参数"）保持；v3 在 §2.2 签名确认无该参数；源码：`review_repair_loop.py` 182-197 改造为 `_build_review_caller` 调用（§2.2 附完整代码） |
| ② | enable_debate 驱动 | **gate4 硬编码 False，非 config 驱动**：gate4 调用点写死 `enable_debate=False`，不接受任何 context 覆盖（debate 由 loop 层 `enable_debate` 参数统一控制，gate4 固定关闭避免 72min/轮击穿 30-40 分钟验收） | v2 文档 §缺陷 10 gate4 接线（v2 文档 659 行注释 `# 缺陷 9：Gate4 辩论关闭`）→ v3 改为 `# 硬编码 False（非 config 驱动；P0-B-2 v3）`；源码：`gate4.py:257-265` 的 `enable_debate=False` 注释同步 |
| ③ | 异常命名 | **统一 WallClockDeadlineExceeded，删除 DeadlineExceeded 命名**：`llm_errors.py` 只定义 `WallClockDeadlineExceeded`；v2 全部代码块/import 已是该名（v2 文档 49/202/244/261/434/491/610/614 行）；grep 裸 `DeadlineExceeded`（非 WallClock 前缀）实测 0 匹配 | v2 文档 §三 链路图与 §缺陷 14/15 段落（v2 文档 1054-1106 行）确认无裸名；v3 新增 §1.4(f) gate4 显式分支与 §1.4(e) with_fallback 白名单继续只引用 WallClockDeadlineExceeded |

**接口签名**：无新签名（纯确认 + 注释/命名同步）。

**验收测试**：无新测试；回归由既有 `test_legacy_call_compat`（`workflow.py:2942` 旧关键字调用新签名无 TypeError）与新增 `test_circuit_breaker_reachable`（§1.6）覆盖兼容性侧面。

**副作用**：无行为变化（v2 已实现）；仅文档与注释层面消除互斥表述。

---

### 1.6 熔断死激活 + BUSINESS 污染（P0-B-3）——can_execute 可真正返回 False

**缺陷实证**（审查裁决 3 + 修正清单 P0-B-3）：① **死激活**：RETRY_POLICY enforce `gate_attempts=2` 与熔断阈值 2 同步耗尽——第 1 次失败 count=1、第 2 次失败 count=2 打开熔断，但此时 `while attempts < max_attempts` 已到上限退出，`can_execute()` 从未被查询（或查询时恒 True）→ 熔断器是"记录器"不是"执行器"；② **BUSINESS 污染**：`classify()` 默认分支把未知文本兜底为 `TRANSIENT retry=True`，`record_failure` 按权重计入 → "BUSINESS 不计入熔断"被文本兜底绕过。

**修正策略**（修正清单 P0-B-3 处方）：
- **(a) 二选一裁决：enforce `gate_attempts` 2→3（阈值 2 保持）**。理由：阈值 2 保留"连续 2 次失败才熔断"的既有语义，单次瞬态失败（网络抖动）不致误熔断；`gate_attempts=3` 使熔断在第 3 次尝试前生效——第 1 次失败 count=1、第 2 次失败 count=2 → OPEN，第 3 次尝试 `can_execute()=False` 短路（省一次真实执行 + LLM 调用）。若反向选"阈值降 1"：TRANSIENT 单次即熔断，抖动误伤，且 PERMANENT 的"不重试"语义已由 `retry=False` 表达、无需熔断提前——故不选。
- **(b) 文本兜底改 UNKNOWN 权重 0**：`ErrorType` 追加 `UNKNOWN`；`ERROR_CODE_MAPPING` 显式定义 `UNKNOWN_ERROR → type="unknown"`；`classify()` 默认分支返回 `ErrorType.UNKNOWN`（不再默认 TRANSIENT）；`record_failure` 对 `BUSINESS/UNKNOWN` 只记录时间戳、**不计入 failure_count**。业务类文本（如"风险提示覆盖不足""发现N个致命逻辑矛盾"）自然落入 UNKNOWN → 权重 0，满足"业务类文本单独分类"的等价方案（"UNKNOWN 权重 0 仅记录"）。
- **(c)** 新增 `test_circuit_breaker_reachable`：阈值 2、两次 TRANSIENT 失败后 OPEN，`reset_timeout` 未过 → `can_execute() is False`（配合 RETRY_POLICY enforce=3 > 2 的断言）。

**修正后完整代码**：

(a) `tools/finance/qual_v8/core/error_classifier.py`：

```python
class ErrorType(Enum):
    """错误类型"""
    TRANSIENT = "transient"   # 临时性错误
    PERMANENT = "permanent"   # 永久性错误
    BUSINESS = "business"     # 业务错误
    UNKNOWN = "unknown"       # 无法识别的文本兜底（v3 新增：不计入熔断，仅记录）
```

`ERROR_CODE_MAPPING`（34-67 行）追加：

```python
    # 确定性失败：不重试、计入熔断（P1-14；deterministic 键供策略消费方显式区分）
    "LLM_EMPTY_OUTPUT": {"type": "permanent", "retry": False, "escalate": False,
                         "deterministic": True},
    "REVIEW_UNRESOLVED": {"type": "permanent", "retry": False, "escalate": False,
                          "deterministic": True},

    # v3（P0-B-3）：文本兜底显式分类为 UNKNOWN（权重 0，仅记录不计入熔断），
    # 取代 v1/v2 的"默认 TRANSIENT retry=True"——那是"BUSINESS 不计入"护栏被绕过的根因
    "UNKNOWN_ERROR": {"type": "unknown", "retry": True, "max_retries": 1, "backoff": False},
```

`classify()`（76-97 行）默认分支：

```python
        # 默认分类（v3）：UNKNOWN（不计入熔断，仅记录）—— 不再默认 TRANSIENT
        return ErrorClassification(
            error_type=ErrorType.UNKNOWN,
            retry=True,
            max_retries=1,
            escalate=False,
            backoff=False,
            description=f"未知错误: {error_code} - {error_message}",
        )
```

`classify_from_exception`（99-114 行）else 分支末尾（v2 已加 LLM_EMPTY_OUTPUT/REVIEW_UNRESOLVED 文本识别）：

```python
        else:
            # 文本兜底（Gate 边界收到的是字符串 errors 构造的 RuntimeError，见 qual_v8/workflow.py:302-304）
            if "审查未修复" in error_message:
                return self.classify("REVIEW_UNRESOLVED", error_message)   # 缺陷 15："审查未修复"不归 BUSINESS
            if "确定性" in error_message or "空输出" in error_message or "finish" in error_message:
                return self.classify("LLM_EMPTY_OUTPUT", error_message)
            # v3（P0-B-3）：其余文本一律 UNKNOWN（权重 0，不计入熔断）——不再回落 TRANSIENT
            return self.classify("UNKNOWN_ERROR", error_message)
```

(b) `tools/finance/qual_v8/core/circuit_breaker.py`：

```python
# --- 顶部 import（7-14 行区域）---
from .error_classifier import ErrorType          # 单一来源（8a：删除 24-28 行重复枚举）
```

（删除 24-28 行本地 `ErrorType` 枚举；`qual_v8/__init__.py:18`、`qual_v8/core/__init__.py:8`、`workflow_context.py:235` 的 `from .core.circuit_breaker import ErrorType` 均继续有效——circuit_breaker 模块属性即 error_classifier.ErrorType。）

```python
    def record_failure(self, error_type: ErrorType):
        """记录失败：TRANSIENT/PERMANENT 权重 1 计数；BUSINESS/UNKNOWN 不计入（仅记录时间戳）。

        v3（P0-B-3）：
        - 权重统一 1（原 56 行 TRANSIENT 0.5 → 1）；
        - BUSINESS 不计入熔断（业务失败可重试，不视为服务故障）；
        - UNKNOWN 不计入熔断（文本兜底仅记录，堵住"UNKNOWN→TRANSIENT 绕过 BUSINESS 护栏"）。
        """
        if error_type in (ErrorType.TRANSIENT, ErrorType.PERMANENT):
            self.failure_count += 1
        self.last_failure_time = datetime.now()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(f"熔断器 {self.name} 打开：连续{self.failure_count}次失败")
```

(c) `tools/finance/qual_v8/workflow.py`——RETRY_POLICY（模块级，置于 `_FLOW_DEFINITION` 45 行之前；v2 缺陷 13 的 enforce=2 改为 v3 值，**随引入即落地，不留死激活中间态**）：

```python
RETRY_POLICY = {
    # gate_attempts: 单 Gate 执行次数（含首次）；repair_rounds: Gate4 修复轮数；skip_repair: 只审不修
    "shadow":  {"gate_attempts": 1, "repair_rounds": 1, "skip_repair": True},
    "soft":    {"gate_attempts": 1, "repair_rounds": 3, "skip_repair": False},
    "enforce": {"gate_attempts": 3, "repair_rounds": 3, "skip_repair": False},
    # v3（P0-B-3）：enforce 2→3。阈值 2 保持：第 2 次失败后熔断 OPEN，
    # 第 3 次尝试 can_execute()=False 短路——熔断器从"记录器"变为"执行器"。
}
```

（260 行 `max_attempts = policy["gate_attempts"]`；181 行 `failure_threshold=2` 保持；17 行 import 改 `from .core.circuit_breaker import CircuitBreaker`，不再需要 ErrorType 直接引用。）

熔断触发时序（enforce）：attempt 0 失败 → count=1 → `can_retry` → attempt 1 失败 → count=2 → OPEN → attempt 2：`can_execute()` 返回 False → 以"熔断器打开"失败结果 break（不再执行第 3 次真实调用）。

**接口签名**：`record_failure(error_type: ErrorType)` 签名不变；`ErrorType` 追加 `UNKNOWN` 成员（既有消费者只用 TRANSIENT/PERMANENT/BUSINESS，向后兼容）；`RETRY_POLICY` 结构不变（值 2→3）。

**验收测试**（`tools/finance/qual_v8/core/test_circuit_breaker_fix.py`，新增，断言明确）：

```python
def test_circuit_breaker_reachable():
    """P0-B-3（v3 新增）：can_execute() 必须能真正返回 False（v2 死激活回归）。

    阈值 2、reset_timeout=60：两次 TRANSIENT 失败 → OPEN，冷却期未过 → can_execute() is False。
    （配合 RETRY_POLICY["enforce"]["gate_attempts"] == 3 > 阈值 2，第 3 次尝试必被短路。）
    """
    from finance.qual_v8.core.circuit_breaker import CircuitBreaker, CircuitState
    from finance.qual_v8.core.error_classifier import ErrorType
    from finance.qual_v8.workflow import RETRY_POLICY

    cb = CircuitBreaker(name="gate_4", failure_threshold=2, reset_timeout=60)
    assert cb.can_execute() is True                       # 初始 CLOSED
    cb.record_failure(ErrorType.TRANSIENT)
    assert cb.can_execute() is True                       # 1 次未达阈值
    cb.record_failure(ErrorType.TRANSIENT)
    assert cb.get_state() == CircuitState.OPEN
    assert cb.can_execute() is False                      # ← v2 死激活：此处旧实现永不为 False

    # 死激活根因断言：enforce 尝试上限必须大于熔断阈值
    assert RETRY_POLICY["enforce"]["gate_attempts"] == 3
    assert RETRY_POLICY["enforce"]["gate_attempts"] > 2   # > failure_threshold

def test_unknown_and_business_not_counted():
    """P0-B-3（v3 新增）：文本兜底 UNKNOWN 与 BUSINESS 不计入熔断（权重 0，仅记录）。"""
    from finance.qual_v8.core.circuit_breaker import CircuitBreaker, CircuitState
    from finance.qual_v8.core.error_classifier import ErrorType

    cb = CircuitBreaker(name="gate_4", failure_threshold=2, reset_timeout=60)
    for _ in range(5):
        cb.record_failure(ErrorType.UNKNOWN)              # 5 次未知文本错误
    assert cb.get_state() == CircuitState.CLOSED          # 不熔断（v2：默认 TRANSIENT 计入 → 打开）
    assert cb.can_execute() is True
    for _ in range(5):
        cb.record_failure(ErrorType.BUSINESS)             # 业务失败同样不计入
    assert cb.get_state() == CircuitState.CLOSED
    cb.record_failure(ErrorType.PERMANENT)
    cb.record_failure(ErrorType.PERMANENT)
    assert cb.get_state() == CircuitState.OPEN            # 确定性失败仍正常计数熔断
```

`test_llm_empty_output_classification`（v2 保持）追加断言：`classify_from_exception(RuntimeError("某通用错误文本"))` → `error_type == ErrorType.UNKNOWN`（不再 TRANSIENT）。

**副作用**：`ErrorType.UNKNOWN` 追加不破坏既有消费者（`qual_v8/tests/test_core.py` 的 TRANSIENT/PERMANENT 用例不受影响）；shadow/soft（gate_attempts=1）行为不变；`record_failure` 对 UNKNOWN 也刷新 `last_failure_time`（与既有对所有类型刷新的行为一致）；熔断"熔断器打开"失败结果经 `classify_from_exception` 文本兜底 → UNKNOWN → 权重 0，不会二次污染计数。

---

### 1.7 N5 预算错配（P1-1）——`max_llm_calls_per_gate` 60→200

**缺陷实证**（审查裁决 3）：实读 depth_reviewer/conclusion_validator/repair → **每轮真实 27-50 次调用 vs 上限 60** → "需第 2 轮"的报告大概率 T_BUDGET 早停打降级标（arch §8.2"3-5 次/轮"与代码矛盾）。

**修正策略**（修正清单 P1-1 处方，二选一裁决：**上限提至 200**）：
- 不选"S5 单调重审不计预算"：预算审计口径必须"每调用必计数"，否则 `result.llm_calls` 不再是真实调用数（缺陷 7 的核心承诺被破坏），且引入豁免路径复杂度 > 提额一行。
- 选"60→200"：200 > 墙钟 5400s 内理论最大调用数（5400s / 最短 30s ≈ 180 次）→ **T_BUDGET 恒晚于 T_DEADLINE 触发**，预算不再早停；终止性仍由 deadline（5400s）保证（四重有界第 4 重不变）。

**修正后完整代码**（`tools/finance/qual_v8/workflow.py`，WorkflowConfig 34-40 行）：

```python
@dataclass
class WorkflowConfig:
    """工作流配置"""
    max_retries: int = 3                 # 兼容保留（策略表 shadow/soft 下不再直接消费）
    timeout_per_gate: int = 600          # 10分钟
    human_sla_working_hours: int = 30    # 分钟
    human_sla_non_working_hours: int = 240  # 分钟
    global_timeout_seconds: int = 5400   # 新增：全局墙钟预算（90 分钟）
    max_llm_calls_per_gate: int = 200    # v3：60→200（N5 预算错配修正；> 5400s 内理论最大调用 ~180）
    shadow_skip_repair: bool = True      # 新增：shadow 模式 Gate4 跳过修复
```

**接口签名**：`WorkflowConfig` 字段不变（仅默认值 60→200）；`context["llm_call_budget"] = self.config.max_llm_calls_per_gate` 自动取新值，无其它接线改动。

**时长推导**（N5 修正依据）：

| 项 | 数值 | 依据 |
|---|---|---|
| 每轮真实调用数（enable_debate=False） | 20-37 次/轮 | 深度审查 6-10（3 关键章×分段）+ 结论审查 3-6 + 修复 patch 2-5 + 单调重审 9-16 |
| v2 审查报告实读口径 | 27-50 次/轮 | depth_reviewer/conclusion_validator/repair 实读 |
| 3 轮完整循环合计 | 60-111 次（实读口径 81-150 次） | 3 × 每轮 |
| 单次调用实际耗时 | 60-180s | bridge 推理模型长任务（300s 为硬超时上界） |
| 墙钟 5400s 内最大调用数 | ≈180 次（最短 30s/次）；实际 60-90 次 | 5400 / 30；5400 / 60-90 |
| 预算 60 的行为（v2 缺陷） | 第 2 轮中段（~60 次）触发 T_BUDGET → 报告打降级标 | N5 错配实证 |
| 预算 200 的行为（v3） | 3 轮（≤150 次）内不触发；>200 才触发，而 deadline 内不可能达到 | 200 > 180 |
| 结论 | 报告质量判定不再被预算误伤；终止性仍由 deadline 保证 | 四重有界第 4 重不变 |

**验收测试**：断言并入 `test_retry_policy_table`（`tools/finance/qual_v8/core/test_circuit_breaker_fix.py` 或 `qual_v8/tests` 对应文件）：

```python
def test_workflow_config_budget():
    """P1-1（v3）：预算上限 200 > 墙钟 5400s 内理论最大调用数（~180），T_BUDGET 不早停。"""
    from finance.qual_v8.workflow import WorkflowConfig
    cfg = WorkflowConfig()
    assert cfg.max_llm_calls_per_gate == 200
    assert cfg.global_timeout_seconds == 5400
    # 预算不早于墙钟的数学保证：200 > 5400 / 30
    assert cfg.max_llm_calls_per_gate > cfg.global_timeout_seconds / 30
```

**副作用**：单 Gate 预算上限放宽不影响终止性（deadline 仍为硬上界）；`context["_llm_call_count"]` 审计值可到 200，报告打标逻辑（缺陷 8）不依赖具体预算值；shadow 模式（gate_attempts=1 + skip_repair）调用量远小于 200，无感知。

---

## 2. 完整新签名（v3）

### 2.1 `_issue_signature`（`tools/finance/quality/review_repair_loop.py`，新函数）

```python
def _issue_signature(issue: str, keep_chapter: bool = True) -> str:
    """问题签名：归一化数字但保留章节上下文（第N章 → 第@N章，不同章节签名不同）。

    v3 修正（缺陷 16）：findall 捕获章节号 → 归一化全部数字 → 带计数 re.sub 按顺序还原。
    keep_chapter=False 仅用于跨章聚合类审计统计，绝不用于豁免判定。
    """
    import re
    if keep_chapter:
        chapters = re.findall(r"第(\d+)章", issue)
        s = re.sub(r"\d+\.?\d*", "N", issue)
        if chapters:
            it = iter(chapters)
            def _restore(m):
                try:
                    return f"第@{next(it)}章"
                except StopIteration:
                    return m.group(0)
            s = re.sub(r"第N章", _restore, s)
        return s.strip()
    else:
        s = re.sub(r"第\d+章", "第@章", issue)
        s = re.sub(r"\d+\.?\d*", "N", s)
        return s.strip()
```

### 2.2 `review_and_repair_loop`（`tools/finance/quality/review_repair_loop.py:31-38` 改造，含主循环 v3 合并版完整代码）

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
    deadline: Optional[float] = None,       # 新增：墙钟 deadline，time.monotonic 绝对值（缺陷 8 + P0-B-1）
) -> ReviewRepairResult:
    """审查修复循环

    v3 完整实现（缺陷 1/6/7/8/10 + P0-B-1 修正）：
    - 豁免收敛判据查累积豁免（缺陷 1 修正版）；
    - 单调守卫 before_sigs 取豁免过滤前原始全量集、先减后置零（缺陷 6 修正版）；
    - 预算/墙钟统一计数源 budget_state + _make_budgeted_caller（缺陷 7/8 + P0-B-1）。
    """
    all_issues = []
    issues_fixed = 0

    # ---- 预算/墙钟统一计数源 + 修复 caller（缺陷 7/8）----
    budget_state: Dict[str, int] = {"calls": 0}
    repair_caller = _make_budgeted_caller(llm_caller, budget_state, deadline, llm_call_budget)

    # ---- 豁免学习状态（缺陷 1）----
    exempted: Dict[str, Dict[str, Any]] = {}   # sig -> {rounds, exempted, first_seen, example}
    fixed_sigs: set = set()                    # 从未被成功修复的签名（证据护栏）

    for round_num in range(1, max_rounds + 1):
        logger.info(f"审查修复循环 第{round_num}轮")

        # 1. 执行审查（全量审查，口径 A；deep 纯规则 + substantive LLM 检查器）
        deep_issues = _run_deep_review(chapters, wind_data)
        try:
            substantive_issues = _run_substantive_review(
                chapters, repair_caller, wind_data, industry,
                enable_debate=enable_debate,
                budget_state=budget_state,
                deadline=deadline,
                llm_call_budget=llm_call_budget,
            )
        except (DeterministicLLMFailure, LLMCallBudgetExceeded, WallClockDeadlineExceeded) as e:
            # 轮首审查即被确定性/预算/墙钟中断 → 终止（不进修复，修复会重复同一失败）
            return _fail_result(round_num, chapters, budget_state,
                                remaining=[f"{REVIEW_INCOMPLETE_PREFIX} {e}"],
                                issues_found=len(all_issues), issues_fixed=issues_fixed,
                                review_incomplete=True,
                                budget_exceeded=isinstance(e, LLMCallBudgetExceeded),
                                wall_clock_exceeded=isinstance(e, WallClockDeadlineExceeded))
        if any(i.startswith(REVIEW_INCOMPLETE_PREFIX) for i in substantive_issues):
            # 检查器 LLM 失败 → "审查不完整"终止性失败项，不进入修复（缺陷 3）
            return _fail_result(round_num, chapters, budget_state,
                                remaining=substantive_issues[:10],
                                issues_found=len(all_issues), issues_fixed=issues_fixed,
                                review_incomplete=True)
        round_issues = deep_issues + substantive_issues

        # 1b. before 口径（缺陷 6 修正版）：豁免过滤前的原始全量问题集，与 after_sigs 严格同口径
        before_sigs = {_issue_signature(i) for i in round_issues}
        before_count = len(round_issues)

        # 2. 豁免剔除（缺陷 1 修正版）
        kept = []
        for iss in round_issues:
            sig = _issue_signature(iss)
            entry = exempted.setdefault(sig, {
                "rounds": 0, "exempted": False, "first_seen": round_num, "example": iss,
            })
            entry["rounds"] += 1
            entry["example"] = iss
            if entry["exempted"]:
                continue
            kept.append(iss)
        round_issues = kept

        # 3. 收敛判定（缺陷 1 修正版：查累积豁免清单）
        exempted_active = any(e["exempted"] for e in exempted.values())
        if not round_issues and not exempted_active:
            logger.info(f"审查修复循环 第{round_num}轮 通过，无问题")
            return _ok_result(round_num, chapters, budget_state, len(all_issues), issues_fixed)
        if not round_issues and exempted_active:
            exempted_sigs = sorted(sig for sig, e in exempted.items() if e["exempted"])
            remaining = [f"[已豁免{e['rounds']}轮] {e['example']}"
                         for sig, e in exempted.items() if e["exempted"]][:10]
            logger.warning(
                f"审查修复循环 第{round_num}轮：{len(exempted_sigs)} 个问题已豁免，判定不通过")
            return _fail_result(round_num, chapters, budget_state,
                                remaining=remaining,
                                issues_found=len(all_issues), issues_fixed=issues_fixed,
                                exempted_count=len(exempted_sigs), exempted=exempted_sigs)

        logger.info(f"审查修复循环 第{round_num}轮 发现{len(round_issues)}个问题")
        all_issues.extend(round_issues)

        # 4. shadow：只审不修（缺陷 10）
        if skip_repair:
            logger.warning(f"shadow 模式跳过修复：第{round_num}轮发现 {len(round_issues)} 个问题（只审不修）")
            return _fail_result(round_num, chapters, budget_state,
                                remaining=round_issues[:10],
                                issues_found=len(all_issues), issues_fixed=issues_fixed)

        # 5. 无 LLM 调用器，无法修复
        if not llm_caller:
            logger.warning("无LLM调用器，跳过修复")
            return _fail_result(round_num, chapters, budget_state,
                                remaining=round_issues[:10],
                                issues_found=len(all_issues), issues_fixed=issues_fixed)

        # 6. 修复（单调性守卫：deepcopy 快照 + 签名差集 + 前后同口径；缺陷 6 修正版）
        snapshot = _copy.deepcopy(chapters)
        try:
            fixed_count = _repair_chapters(chapters, round_issues, repair_caller, wind_data)
        except (DeterministicLLMFailure, LLMCallBudgetExceeded, WallClockDeadlineExceeded) as e:
            return _fail_result(round_num, chapters, budget_state,
                                remaining=[f"{REVIEW_INCOMPLETE_PREFIX} 修复失败: {e}"],
                                issues_found=len(all_issues), issues_fixed=issues_fixed,
                                review_incomplete=True,
                                budget_exceeded=isinstance(e, LLMCallBudgetExceeded),
                                wall_clock_exceeded=isinstance(e, WallClockDeadlineExceeded))
        issues_fixed += fixed_count

        # 修复后重审（与轮首同口径：deep + substantive，同一 budget_state/deadline）
        try:
            after_issues = (_run_deep_review(chapters, wind_data)
                            + _run_substantive_review(
                                chapters, repair_caller, wind_data, industry,
                                enable_debate=enable_debate,
                                budget_state=budget_state,
                                deadline=deadline,
                                llm_call_budget=llm_call_budget))
        except (DeterministicLLMFailure, LLMCallBudgetExceeded, WallClockDeadlineExceeded) as e:
            return _fail_result(round_num, chapters, budget_state,
                                remaining=[f"{REVIEW_INCOMPLETE_PREFIX} 重审失败: {e}"],
                                issues_found=len(all_issues), issues_fixed=issues_fixed,
                                review_incomplete=True,
                                budget_exceeded=isinstance(e, LLMCallBudgetExceeded),
                                wall_clock_exceeded=isinstance(e, WallClockDeadlineExceeded))
        after_sigs = {_issue_signature(i) for i in after_issues}
        new_sigs = after_sigs - before_sigs
        if len(after_issues) > before_count or new_sigs:
            logger.warning(
                f"单调性守卫：问题数 {before_count}→{len(after_issues)}，"
                f"新签名 {sorted(new_sigs)[:3]}，回滚本轮修复")
            chapters.clear()
            chapters.update(snapshot)
            issues_fixed -= fixed_count          # 缺陷 6 修正：先还原计数（fixed_count 尚未置零）
            fixed_count = 0                      # 再置零（v2 顺序相反 → no-op 必红）
        else:
            for sig in before_sigs - after_sigs:
                fixed_sigs.add(sig)              # 仅未回滚时记录"已修复"（供豁免证据护栏）
        logger.info(f"审查修复循环 第{round_num}轮 修复{fixed_count}个问题")

        # 7. 豁免学习（证据护栏：≥3 轮 + 从未被成功修复；缺陷 1）
        for sig, entry in exempted.items():
            if (entry["rounds"] >= EXEMPT_MIN_ROUNDS
                    and sig not in fixed_sigs
                    and not entry["exempted"]):
                entry["exempted"] = True
                entry["exempted_at_round"] = round_num
                logger.warning(
                    f"豁免学习：签名 {sig} 出现 {entry['rounds']} 轮且无修复迹象，加入豁免清单（审计可见）")

    # 达到最大轮数
    logger.warning(f"审查修复循环 达到最大轮数{max_rounds}，仍有问题未修复")
    return _fail_result(max_rounds, chapters, budget_state,
                        remaining=round_issues[:10],
                        issues_found=len(all_issues), issues_fixed=issues_fixed)
```

配套模块级代码（`review_repair_loop.py`，logger 17 行后 + 28 行后 + 171 行前）：

```python
# --- 模块级常量与 import（logger 定义 17 行后）---
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
    """审查修复结果"""
    passed: bool
    rounds: int
    chapters: Dict[int, str]
    issues_found: int
    issues_fixed: int
    remaining_issues: List[str]
    # ---- 新增（全部带默认值，旧调用不传也安全）----
    llm_calls: int = 0                 # 本 Gate 真实 LLM 调用次数（预算审计）
    exempted_count: int = 0            # 豁免问题数（报告标 + 审计）
    exempted: List[str] = field(default_factory=list)   # 豁免清单（审计可见；v3 = 累积豁免签名全量）
    review_incomplete: bool = False    # 审查不完整（检查器 LLM 失败）
    wall_clock_exceeded: bool = False
    budget_exceeded: bool = False
```

```python
# --- 结果构造辅助（28 行后）---
def _ok_result(round_num: int, chapters: Dict[int, str], budget_state: Dict[str, int],
               issues_found: int, issues_fixed: int) -> ReviewRepairResult:
    return ReviewRepairResult(
        passed=True, rounds=round_num, chapters=chapters,
        issues_found=issues_found, issues_fixed=issues_fixed,
        remaining_issues=[], llm_calls=budget_state["calls"],
    )


def _fail_result(round_num: int, chapters: Dict[int, str], budget_state: Dict[str, int],
                 remaining: List[str], issues_found: int = 0, issues_fixed: int = 0,
                 exempted_count: int = 0, exempted: Optional[List[str]] = None,
                 review_incomplete: bool = False,
                 budget_exceeded: bool = False, wall_clock_exceeded: bool = False,
                 ) -> ReviewRepairResult:
    return ReviewRepairResult(
        passed=False, rounds=round_num, chapters=chapters,
        issues_found=issues_found, issues_fixed=issues_fixed,
        remaining_issues=remaining,
        llm_calls=budget_state["calls"],
        exempted_count=exempted_count,
        exempted=exempted or [],
        review_incomplete=review_incomplete,
        budget_exceeded=budget_exceeded,
        wall_clock_exceeded=wall_clock_exceeded,
    )
```

```python
# --- 审查专用 caller（171 行 _run_substantive_review 前）---
def _build_review_caller(primary, budget_state, deadline, llm_call_budget):
    """审查专用 caller：REVIEW_SYSTEM + fallback + budgeted + deadline（缺陷 11/5、P1-14、P0-B-1 v3）。

    v3：create_harness_caller 传入 deadline（P0-B-1）——审查调用同样受墙钟约束；
    P0-B-2（v3）确认：loop 内部自建审查 caller，不存在 review_caller_override 参数。
    测试可注入：本函数每次调用时 `from ..harness_llm import create_harness_caller`，
    monkeypatch "finance.harness_llm.create_harness_caller" 即可接管审查路径。
    """
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
        inner = create_harness_caller(
            max_tokens=8000, temperature=0.3, system=REVIEW_SYSTEM,
            deadline=deadline,                        # P0-B-1（v3）：审查 caller 自带调用级墙钟检查
        )
        fb = with_fallback(inner, lambda: create_deepseek_caller(model="deepseek-chat"))
        return _make_budgeted_caller(fb, budget_state, deadline, llm_call_budget)
    except Exception as e:
        logger.warning(f"审查 caller 构造失败，使用主 caller: {e}")
        return _make_budgeted_caller(primary, budget_state, deadline, llm_call_budget)
```

`_run_substantive_review` v3（171-264 行改造，保持 v2 缺陷 3/9 语义 + P0-B-1）：

```python
def _run_substantive_review(
    chapters: Dict[int, str],
    llm_caller: Optional[Callable],
    wind_data: Optional[Dict],
    industry: str,
    *,
    enable_debate: bool = False,            # 新增（缺陷 9）
    budget_state: Optional[Dict] = None,    # 新增：统一计数 {calls: int}（缺陷 7）
    deadline: Optional[float] = None,       # 新增（缺陷 8 + P0-B-1）
    llm_call_budget: Optional[int] = None,  # 新增（缺陷 7）
) -> List[str]:
    """执行实质性审查（v3：P0-B-2 确认无 review_caller_override 参数，审查 caller 内部构造）"""
    issues = []

    review_caller = _build_review_caller(llm_caller, budget_state, deadline, llm_call_budget)

    # 1. 事实核查（纯规则检查器）
    try:
        from .fact_checker import check_facts
        result = check_facts(chapters, wind_data or {})
        if not result.passed:
            issues.extend([f"[事实核查] {issue.description}" for issue in result.issues])
    except Exception as e:
        logger.warning(f"事实核查失败: {e}")

    # 2. 分析深度审查（LLM 检查器：确定性/预算/超时上抛，其它转"审查不完整"）
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

    # 3. 结论合理性审查（同型守卫）
    try:
        from .conclusion_validator import check_conclusion
        result = check_conclusion(chapters, review_caller, wind_data)
        if not result.passed:
            issues.extend([f"[结论合理性] {issue.description}" for issue in result.issues])
    except (DeterministicLLMFailure, LLMCallBudgetExceeded, WallClockDeadlineExceeded):
        raise
    except Exception as e:
        issues.append(f"{REVIEW_INCOMPLETE_PREFIX} 结论合理性审查失败: {e}")

    # 4. 假设合理性审查（纯规则检查器）
    try:
        from .assumption_checker import check_assumptions
        result = check_assumptions(chapters, industry, wind_data)
        if not result.passed:
            issues.extend([f"[假设合理性] {issue.description}" for issue in result.issues])
    except Exception as e:
        logger.warning(f"假设合理性审查失败: {e}")

    # 5. 对抗性辩论审查（缺陷 9：enable_debate=False 时整块跳过）
    if enable_debate and review_caller is not None:
        try:
            from .debate_service import DebateService, REVIEW_DEBATE_CHAPTERS
            svc = DebateService(llm_caller=review_caller, wind_data=wind_data, timeout=240)
            for ch_num in REVIEW_DEBATE_CHAPTERS:
                if ch_num not in chapters or not chapters[ch_num]:
                    continue
                try:
                    title = f"第{ch_num}章"
                    debate_issues = svc.run(
                        chapter_num=ch_num, chapter_title=title,
                        chapter_content=chapters[ch_num], contract=None, mode="review",
                    )
                    if debate_issues:
                        issues.extend(debate_issues)
                        logger.info(f"对抗辩论审查 第{ch_num}章: 发现 {len(debate_issues)} 个问题")
                except (DeterministicLLMFailure, LLMCallBudgetExceeded, WallClockDeadlineExceeded):
                    raise
                except Exception as e:
                    issues.append(f"{REVIEW_INCOMPLETE_PREFIX} 对抗辩论审查 第{ch_num}章失败: {e}")
        except (DeterministicLLMFailure, LLMCallBudgetExceeded, WallClockDeadlineExceeded):
            raise
        except Exception as e:
            issues.append(f"{REVIEW_INCOMPLETE_PREFIX} 对抗辩论审查初始化失败: {e}")

    return issues
```

兼容性：新增参数全部 keyword-only + 默认值 → `tools/finance/workflow.py:2942-2949` 旧关键字调用（chapters/ctx/llm_caller/wind_data/max_rounds/industry）**零修改兼容**；`ReviewRepairResult` 新字段全部带默认值 → `workflow.py:2951-2962` 消费方兼容；`quality/v3/review_repair_loop.py` re-export 无需改动。

### 2.3 `create_harness_caller`（`tools/finance/harness_llm.py:63-72` 改造，含 deadline）

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
    *,
    deadline: Optional[float] = None,   # v3 新增（P0-B-1）：墙钟 deadline（time.monotonic 绝对值）；
                                        # keyword-only + 默认 None → 旧调用零修改兼容
) -> Callable[[str, str], str]:
```

（内部 `llm_caller` 每次尝试前查 `time.monotonic() > deadline` → 抛 `WallClockDeadlineExceeded`，完整代码见 §1.4(a)。v3 移除 v2 §2.3 无消费方的 `on_deterministic`。）

### 2.4 `_deadline_guard`（`tools/finance/workflow.py`，新函数）

```python
def _deadline_guard(
    caller: Optional[Callable[[str, str], str]],
    deadline: Optional[float],
) -> Optional[Callable[[str, str], str]]:
    """包装 llm_caller：每次调用前检查墙钟 deadline，超时抛 WallClockDeadlineExceeded。

    P0-B-1（v3）：Gate3 写作主链路的调用级墙钟检查。deadline=None 时原样返回（零开销、兼容旧调用）。
    """
    if caller is None or deadline is None:
        return caller
    def guarded(chapter_name: str, prompt: str) -> str:
        if time.monotonic() > deadline:
            raise WallClockDeadlineExceeded(
                f"墙钟预算耗尽（deadline={deadline:.0f}，当前={time.monotonic():.0f}）")
        return caller(chapter_name, prompt)
    return guarded
```

### 2.5 `_make_budgeted_caller`（`tools/finance/quality/review_repair_loop.py`，新模块级工厂，v3 保持 v2 语义）

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

---

## 3. 修订后测试清单（每个测试断言明确）

测试约定（v2 保持 + v3 补充）：LLM 一律用可注入 fake caller（记录调用序列、可配置抛 `DeterministicLLMFailure`/`RuntimeError`、返回固定文本），禁真实网络；**v3 补充：`_build_review_caller` 每次调用时 `from ..harness_llm import create_harness_caller`，测试用 `monkeypatch.setattr("finance.harness_llm.create_harness_caller", lambda **kw: fake)` 接管审查路径（同时 patch `finance.llm_caller.create_deepseek_caller` 防 fallback 触发）；`_run_deep_review` 用 monkeypatch 替换为返回 `[]`（隔离纯规则检查器干扰）**。标记：✓ = v2 保持；★ = v2 修正版；▲ = v3 新增。

| 文件 | 用例 | 标记 | 覆盖 | 核心断言 |
|---|---|---|---|---|
| `tools/finance/quality/test_loop_fix.py` | `test_signature_keeps_chapter` | ★（缺陷 16） | `s4 != s5`；`"第@12章" in s12`（多数字不破损）；同章不同数字同签；`multi` 含 `第@4章` 与 `第@5章` |
| | `test_exemption_failclosed` | ★（缺陷 1） | 前 6 次审查调用报同签名问题、第 7 次起干净 → `passed is False`；`remaining` 含 `"[已豁免"`；`exempted_count >= 1`；`rounds <= 4` |
| | `test_monotonic_guard` | ★（缺陷 6） | 修复引入新签名 → 回滚：`chapters == snapshot`；`issues_fixed == 0`；`passed is False` |
| | `test_budget_deadline` | ★（缺陷 7/8 + P0-B-1） | (a) `budget_exceeded is True`、`llm_calls == 3`、`n <= 2`；(b) `wall_clock_exceeded is True`；(c) harness caller deadline 已过期首次调用抛 `WallClockDeadlineExceeded` |
| | `test_review_incomplete` | ✓（缺陷 3） | fake 抛 `RuntimeError` → `check_depth` 返回 `llm_failed=True`、`_parse_llm_score("无分数文本") is None`；loop 返回 `review_incomplete=True`、`remaining` 含 `[审查不完整]` |
| | `test_convergence_earlystop` | ✓（缺陷 18） | 问题数不降且修复=0 → 第 2 轮终止 `passed is False` |
| | `test_shadow_skip_repair` | ✓（缺陷 10） | `skip_repair=True, max_rounds=1` → `repair_*` 分支调用 0 次、`passed is False`、`remaining` 非空 |
| | `test_debate_gated` | ✓（缺陷 9） | monkeypatch `DebateService.run` 计数 → `enable_debate=False` 调用 0 次 |
| | `test_legacy_call_compat` | ✓（缺陷 18） | 按 `workflow.py:2942` 关键字调用新签名 → 无 TypeError |
| `tools/finance/test_harness_llm_fix.py` | `test_deterministic_no_retry` | ✓（缺陷 4/5 基础） | max-tokens 空输出 → 1 次调用即抛 `DeterministicLLMFailure` |
| | `test_bridge_finishreason_contract` | ✓（缺陷 17） | 5 例 finishReason 分类契约（stop/max-tokens 有文/无文/error/null）全断言 |
| `tools/finance/test_llm_fallback.py` | `test_fallback_deterministic_switch` | ✓（缺陷 5/11） | primary 抛 `DeterministicLLMFailure` → 直连文本带 marker；恢复后不再切 |
| `tools/finance/test_workflow_fix.py` | `test_generate_chapter_deterministic_no_retry` | ✓（缺陷 4） | 抛 `DeterministicLLMFailure` → 降级响应、调用次数 == 1 |
| `tools/finance/qual_v8/core/test_error_classifier_fix.py` | `test_llm_empty_output_classification` | ✓（缺陷 14/15 + P0-B-3 扩展） | `DeterministicLLMFailure` → `PERMANENT`/`retry False`；`RuntimeError("审查未修复: …")` → `REVIEW_UNRESOLVED`；**追加：`RuntimeError("通用文本")` → `error_type == ErrorType.UNKNOWN`（不再 TRANSIENT）** |
| `tools/finance/qual_v8/core/test_circuit_breaker_fix.py` | `test_circuit_breaker_unified` | ✓（缺陷 15） | TRANSIENT×2 → OPEN（阈值 2）；BUSINESS×5 → CLOSED；`circuit_breaker.ErrorType is error_classifier.ErrorType` |
| | `test_circuit_breaker_reachable` | ▲（P0-B-3 新增） | 阈值 2、TRANSIENT×2 → OPEN、`can_execute() is False`；`RETRY_POLICY["enforce"]["gate_attempts"] == 3 > 2` |
| | `test_unknown_and_business_not_counted` | ▲（P0-B-3 新增） | UNKNOWN×5 + BUSINESS×5 → CLOSED、`can_execute() is True`；PERMANENT×2 → OPEN |
| | `test_workflow_config_budget` | ▲（P1-1 新增） | `max_llm_calls_per_gate == 200`；`200 > 5400/30`（预算不早于墙钟） |
| `tools/finance/qual_v8/gates/test_gate4_fix.py` | `test_gate4_no_caller_failclosed` | ✓（缺陷 2） | `_substantive_review({}, {"llm_caller": None})` → `passed is False`；异常路径 monkeypatch 抛 `RuntimeError` → `passed is False` 且 `errors` 非空 |
| `tools/finance/test_run_scripts_consistent.py` | `test_run_scripts_consistent` | ✓（缺陷 12） | AST 断言两 run 脚本 `_llm_with_fallback` 均不存在、`with_fallback` 参数一致 |

合计：17 个用例 = v2 保持 12 + v2 修正 4（signature/exemption/monotonic/budget_deadline）+ v3 新增 3（circuit_breaker_reachable / unknown_and_business_not_counted / workflow_config_budget）。

---

## 4. 实施顺序（4 个合并提交，标注修正项归属）

```
提交 #1（P0-A 三必红堵漏，最先合入）
  ├─ 新增 tools/finance/llm_errors.py（DeterministicLLMFailure / LLMCallBudgetExceeded /
  │   WallClockDeadlineExceeded——唯一来源，后续提交依赖；无 DeadlineExceeded 命名）
  ├─ 缺陷 16（修正）：_issue_signature findall→归一化→计数还原          ← 先于豁免学习，防误豁免
  ├─ 缺陷 1（修正）：PASS 判据查累积豁免 + 豁免条目 example 字段 + 删 exempted_tracked
  ├─ 缺陷 6（修正）：单调守卫先减后置零 + before 取原始全量集 + fixed_sigs 仅未回滚更新
  ├─ P0-A-2 gate4.py:226-228 + 278-280 fail-closed（v2 保持）
  ├─ P0-A-3 depth_reviewer（llm_failed / 无默认 50 / 白名单 raise）+ conclusion_validator + 检查器守卫（v2 保持）
  ├─ 测试：signature_keeps_chapter（修正）/ exemption_failclosed（修正）/ monotonic_guard（修正）/
  │        review_incomplete / gate4_no_caller_failclosed
  └─ 依赖：llm_errors.py 与第一批 raise/except 白名单同提交；gate4 fail-closed 后 shadow 打标
     依赖 #2 的 _fill_failed_gates（v2 结论：可接受短暂静默窗口，或 #1+#2 的 workflow 部分合并）

提交 #2（P0-B 止血；workflow + loop + gate4 接线必须同提交，原子化）
  ├─ P0-B-1 deadline L4（修正）：create_harness_caller 加 deadline（keyword-only）+
  │   _deadline_guard（workflow.py）+ _generate_chapter 透传（gate3.py:183 传入 _wall_deadline）+
  │   execute() 顶部包装主 caller + with_fallback 白名单 + gate4 except 扩展三异常分支
  ├─ P0-B-2 arch/code 矛盾（修正）：gate4 enable_debate=False 注释改"硬编码，非 config 驱动"；
  │   确认无 review_caller_override；命名统一 WallClockDeadlineExceeded（§1.5 清单）
  ├─ P0-B-4 harness_llm 分类（max-tokens 空 → DeterministicLLMFailure）+ _generate_chapter 短路（v2 保持）
  ├─ P0-B-5/11 llm_fallback.py（with_fallback）+ run 脚本接线（xpev + qual 同步，P1-12）（v2 保持）
  ├─ P0-B-6 单调守卫主体（#1 已含修正，本提交不再重复；若 #1 拆细，则与 #1 合并实施）
  ├─ P0-B-7 _make_budgeted_caller + budget_state 全链透传（v2 保持）
  ├─ P0-B-8 全局 deadline + _fill_failed_gates + 统一打标（v2 保持）
  ├─ P0-B-9 enable_debate=False 门控（loop + _run_substantive_review 签名）（v2 保持）
  ├─ P0-B-10 shadow_skip_repair 消费（gate4 接线）（v2 保持）
  ├─ P1-13 RETRY_POLICY 三模式显式分支：enforce gate_attempts **直接写 3**（v3 值，
  │   不留 2 的死激活中间态；v2 原为 2）+ WorkflowConfig 新字段
  ├─ P1-1 N5 预算（修正）：WorkflowConfig.max_llm_calls_per_gate **直接写 200**（不留 60 中间态）
  ├─ 测试：budget_deadline（修正）/ deterministic_no_retry / fallback_deterministic_switch /
  │        shadow_skip_repair / debate_gated / generate_chapter_deterministic_no_retry /
  │        legacy_call_compat / run_scripts_consistent / workflow_config_budget
  └─ 依赖：loop 新签名是 gate4 接线前提（同提交）；harness 分类是 fallback 确定性分支前提（同提交）；
           RETRY_POLICY/预算以 v3 终值落地（避免 60/2 的中间态）

提交 #3（P1 架构 + 熔断修正；熔断链路独立回归）
  ├─ P0-B-3 熔断修正：ErrorType.UNKNOWN 追加（error_classifier）+ UNKNOWN_ERROR 映射 +
  │   classify() 默认分支改 UNKNOWN + record_failure 权重 1 / BUSINESS/UNKNOWN 不计入
  │   + circuit_breaker 删本地枚举（从 error_classifier 单一来源）
  ├─ P1-14 error_classifier：LLM_EMPTY_OUTPUT / REVIEW_UNRESOLVED + 类型/文本识别（v2 保持）
  ├─ P1-15 circuit_breaker：枚举统一 + 权重 1 + 阈值 2（workflow.py:181 保持 2）（v2 保持，
  │   与 P0-B-3 同文件合并实施）
  ├─ 测试：circuit_breaker_reachable（新增）/ unknown_and_business_not_counted（新增）/
  │        llm_empty_output_classification（+UNKNOWN 断言扩展）/ circuit_breaker_unified
  └─ 依赖：#2 的 RETRY_POLICY（enforce=3）是"第 3 次尝试被 can_execute 短路"的触发前提；
           circuit_breaker 枚举统一与 error_classifier 权威枚举同提交（防跨类比较回归）

提交 #4（清理）
  ├─ 清理-17：llm-bridge.js 零改动 + bridge 契约测试（v2 保持）
  ├─ 清理-18：全部测试文件收口（含 #1-#3 已建用例的 CI 接线）
  └─ 回归：pytest tools/finance/quality/test_loop_fix.py tools/finance/test_harness_llm_fix.py \
             tools/finance/test_llm_fallback.py tools/finance/test_workflow_fix.py \
             tools/finance/qual_v8/core tools/finance/qual_v8/gates/test_gate4_fix.py \
             tools/finance/test_run_scripts_consistent.py
```

**必须合并提交的步骤**（防中间态不可运行，v3 增补）：
- #1 内：`llm_errors.py` 与第一批 raise/except 白名单同提交；`_issue_signature` 修正先于豁免学习（同提交）；
- #2 内：`create_harness_caller` deadline 参数 与 `_deadline_guard`/`_generate_chapter` 透传 同提交（否则 Gate3 主链路仍无调用级检查）；`with_fallback` 白名单与 harness 分类同提交（否则预算/墙钟异常在 fallback 层被 `except Exception` 吞掉）；loop 新签名与 gate4 接线同提交；RETRY_POLICY/预算以 v3 终值落地（**不留 60/2 中间态**）；
- #3 内：`circuit_breaker` 枚举统一与 `error_classifier` 权威枚举同提交；RETRY_POLICY enforce=3（#2 已落地）是熔断可达前提。

---

## 5. 验收口径（承接审查裁决 + 3 项必红消除确认）

**终止性**（v2 已达成，v3 不破坏）：for 上界（RETRY_POLICY gate_attempts ≤ 3）+ 每调用硬超时（timeout 300s）+ 预算硬上限（200 次/Gate，恒晚于墙钟触发）+ 墙钟 deadline（5400s，且 v3 补上 Gate3 主链路调用级检查）四重有界；"确定性不重试"由 harness 层 raise 与全链 except 白名单保证。

**3 项自带测试必红消除确认**：
| 必红项 | v2 失败原因 | v3 修正 | v3 测试断言 |
|---|---|---|---|
| test_signature_keeps_chapter | 占位符数字被二次归一化 → 第4/5章签名相等 | findall→归一化→计数还原 | `s4 != s5`、`"第@12章" in s12`、同章同签、多章节号顺序还原 |
| test_exemption_failclosed | 判据查本轮出现集 → 豁免项停报后空轮 passed=True | 判据查累积豁免 | 空轮 + 累积豁免 → `passed is False`、remaining 含 `[已豁免` |
| test_monotonic_guard | `fixed_count=0` 后才减 → no-op 计数虚高 | 先减后置零 + before 原始口径 | 回滚后 `chapters == snapshot`、`issues_fixed == 0` |

**新问题零引入自检**：
- 新参数默认值兼容：`create_harness_caller`/`_generate_chapter`/`review_and_repair_loop`/`_run_substantive_review` 全部 keyword-only + 默认值；`ReviewRepairResult` 新字段带默认值；`ErrorType.UNKNOWN` 为追加成员；`WorkflowConfig` 新字段带默认值——旧调用全部零修改兼容；
- 新异常不被吞（v3 增补自检表，提交前逐处 grep `except Exception` 配对）：

| 文件:行号 | 原 except | v3 修订后 |
|---|---|---|
| `harness_llm.py` 101-123 | deadline 检查在 try 外 → 天然上抛 | 新增 WallClockDeadlineExceeded（不重试） |
| `llm_fallback.py`（v3 增补） | `except Exception` 吞 → 换模型重试 | 白名单 `(LLMCallBudgetExceeded, WallClockDeadlineExceeded)` 前移 raise |
| `depth_reviewer.py:259-261` | `except Exception` 吞 | 白名单 raise（v2 缺陷 3） |
| `conclusion_validator.py:404-405` | `except Exception` 吞 | 白名单 raise（v2 缺陷 3） |
| `review_repair_loop.py:214/223/232`（检查器） | `except Exception` 吞 | 白名单 raise（v2 缺陷 3） |
| `review_repair_loop.py:259-261`（debate） | `except Exception` 吞 | 白名单 raise（v2 缺陷 9） |
| `review_repair_loop.py:407-408`（repair） | `except Exception` 吞 | 白名单 raise（v2 缺陷 6） |
| `workflow.py:1237-1241`（_generate_chapter） | `except Exception` 吞+重试 | WallClockDeadlineExceeded/DeterministicLLMFailure 短路（v3 + v2 缺陷 4） |
| `gate4.py:278-280` | `except Exception` → passed=True | 三异常显式 fail-closed + 通用异常 fail-closed（v3 + v2 缺陷 2） |

- 熔断行为：`can_execute()` 在 enforce 第 3 次尝试前真实返回 False（`test_circuit_breaker_reachable`）；UNKNOWN/BUSINESS 权重 0（`test_unknown_and_business_not_counted`）；既有 `qual_v8/tests/test_core.py` 熔断用例不受影响。

**运行验收**：30-40 分钟验收依赖 `enable_debate=False`（gate4 硬编码 False 已确认，非 config 驱动）；"需第 2 轮"的报告不再被 T_BUDGET 误伤（预算 200 恒晚于 deadline 触发）；deadline+300s 上界在 Gate3 主链路成立（调用级检查落地）。
