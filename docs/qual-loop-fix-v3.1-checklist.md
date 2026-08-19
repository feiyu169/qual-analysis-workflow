# v3.1 最终修正清单（综合审议裁决，2026-08-19）

依据：v3 第三轮 HeavySkill 验证（4 轨迹）+ 综合审议（亲自读真实源码验证）
判定：**需修改后通过**——修正清单作为 v3.1 直接交付实施，不单开第四轮全量验证；每项附接线级验收（防"文档绿生产死"复发）

---

## 一、综合审议的独立验证（读真实源码证实）

| # | 发现 | 证实 |
|---|---|---|
| 1 | **熔断阈值锚点错误**：v3-code:816/18/1458 声称"workflow.py:181 保持 threshold=2"，实测 **181 行实际是 failure_threshold=3**；且现状 max_retries=3→attempts=4 时第 4 次可短路，按 v3 字面实施（attempts=3+threshold=3）反而**死激活** | ✅ 读源码证实 |
| 2 | **幽灵模块**：`tools/finance/llm_fallback.py` 不存在，真实 fallback 是 run_qual_full.py:92 / run_xpev_full.py:177 内联 `_llm_with_fallback`；v3-code:574/1438/1499 引用幽灵模块且 4 提交计划未创建它；test_run_scripts_consistent 断言内联函数不存在 | ✅ 读源码证实 |
| 3 | **非自包含**：gate4.py:226-228 与 278-280 真实仍是 fail-open（llm_caller None→passed=True、except→passed=True）；v3-code 仅给 278-280 修复代码，226-228 标"v2 保持"但 v2 从未落地 | ✅ 读源码证实 |
| 4 | with_fallback 设计代码（v3-code:583）`except DeterministicLLMFailure` 排在白名单（594）之前 → 子类 WallClock 被父类遮蔽（墙钟异常被吞+触发逃生）；逃生分支 direct() 无 deadline 预检；arch=300+S5不计 vs code=200+S5计；harness deadline 参数 arch 说不加(439/515)/code 说加(344/633)/导读 34 行加 50 行不加；导读:42 "200<180" 反向；测试实为 20 行声称 17 | ✅ 复核 |

---

## 二、最终必须修正清单（v3.1，7 项 P0 + 2 项 P1）

### P0（必须修正后才能实施，每项附接线级验收）

| # | 缺陷 | 修正方案 | 涉及文件 | 接线级验收标准 |
|---|---|---|---|---|
| P0-1 | 熔断阈值锚点错误（threshold 实为 3，文档称 2） | 显式将 workflow.py:181 的 failure_threshold 改为 2（或阈值<attempts）；补接线级测试 | qual_v8/workflow.py:181、circuit_breaker.py | 断言生产 workflow.py:181==2；enforce 模式第 3 次尝试被 can_execute()=False 短路（真实调用=2） |
| P0-2 | 幽灵模块 llm_fallback.py | 提交计划补建该模块（把 run 脚本内联 _llm_with_fallback 抽取为公共 with_fallback 装饰器）或把修复落在内联闭包 | 新建 tools/finance/llm_fallback.py + run_qual_full.py:92 + run_xpev_full.py:177 | 模块存在且两脚本 import 它；test_run_scripts_consistent 改为断言两脚本用同一模块 |
| P0-3 | 非自包含（gate4 226-228 fail-open 未修） | 补 gate4.py:226-228 修复代码（llm_caller None→passed=False+errors），与 278-280 同改 | gate4.py:226-228 | 单测：无 llm_caller 时 Gate4 passed=False |
| P0-4 | with_fallback except 顺序（子类遮蔽） | 白名单 `except (LLMCallBudgetExceeded, WallClockDeadlineExceeded)` 移到 `except DeterministicLLMFailure` 之前 | v3-code §1.4(e) with_fallback | 单测：墙钟耗尽 → 抛 WallClock 而非触发逃生；逃生调用数为 0 |
| P0-5 | 逃生直连无 deadline 预检 | with_fallback 的 direct() 调用前加 `monotonic()>deadline → raise WallClockDeadlineExceeded` | v3-code §1.4(e) | 单测：deadline 后逃生调用被拒；上界改为"deadline+600s 或实现预检后 +300s"（文档同步） |
| P0-6 | harness deadline 参数三册矛盾 | 裁决：采纳 code 侧（harness 加 keyword-only deadline）；arch §439/515 与导读第 50 行同步改口 | v3-arch §4.4 + 导读 | 三册对"harness 是否加 deadline"描述一致；test_budget_deadline(c) 按 code 实施绿 |
| P0-7 | arch/code 预算双矛盾（300+S5不计 vs 200+S5计） | 裁决：采纳 code 侧（200 + S5 每调用必计数）；arch 全文改 200 + 删除"S5 不计"表述；导读:42 不等式改 200>180 | v3-arch §3.1/§4.1/§8.1 + 导读:42 | 三册数值与 S5 规则一致；test_workflow_config_budget 断言==200 |

### P1（实施中一并处理）

| # | 缺陷 | 修正方案 | 验收 |
|---|---|---|---|
| P1-1 | 测试计数 17 vs 实际 20 | 重数并同步导读（13✓+4★+3▲=20） | 导读测试计数与实际清单一致 |
| P1-2 | v3 非自包含范围扩大 | 实施清单补列 v2 全部代码依赖（gate4 fail-open、depth_reviewer 吞异常+默认50分、harness 分类等） | 按 v3.1 实施清单可从干净仓库跑通 |

---

## 三、执行建议

1. **v3.1 作为最终交付**：修正 7 项 P0 + 2 项 P1 后即为可靠实施基础
2. **不再单开第四轮全量验证**：每项 P0 附接线级验收标准（防"文档绿生产死"复发）；若实施后接线验收仍失败，再回审议
3. **实施顺序**：P0-2（建模块）→ P0-3（gate4 fail-open）→ P0-1（熔断阈值）→ P0-4/5（with_fallback）→ P0-6/7（三册同步）→ P1

---

## 四、三轮迭代总结

| 轮次 | 审查对象 | 结论 | 核心问题 |
|---|---|---|---|
| 第一轮 | v1 方案 | 需修改后通过 | 18 项缺陷（豁免 fail-open、debate 未关、3 处悬空接线、预算死代码等） |
| 第二轮 | v2 方案 | 需修改后通过 | 3 项自带测试必红（签名/豁免/单调）+ deadline 上界失实 + arch/code 矛盾 |
| 第三轮 | v3 方案 | **需修改后通过（收敛）** | P0-A 三项已实修绿；剩余 7 P0+2 P1（熔断阈值锚点、幽灵模块、except 顺序、逃生预检、三册矛盾、非自包含）——均为接线/文档层，修正量小 |

**核心验证成果**：v3 的 P0-A 三项（签名保留章节号、豁免累积判据、单调守卫计数）经 Python 实跑与 4 轨迹独立模拟**全部真绿**，3 个"必红测试"修正版确认可通过；终止性四重有界 + 确定性失败不重试 + debate 关闭已实证——"下一轮不再死循环"目标达成。
