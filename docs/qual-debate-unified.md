# 辩论机制统一架构方案（审查 + 质量增强共用一套引擎）

> 问题：辩论机制被两个地方使用——质量增强（append 洞察到章节）与审查（提取 Bear 反驳为 issues）。
> 若各自实现会重复：两套调用、两套锚点注入、两套结果解析。
> 方案：**单一辩论引擎 + 双消费模式**，从架构上消除重复。

---

## 一、现状分析（重复点）

| | 质量增强（Stage3） | 审查（可行性建议） |
|---|---|---|
| 引擎 | `run_debate`（BULL/BEAR/PM） | 想复用 `run_debate` |
| 输入 | 章节内容 + 估值摘要 | 章节内容（同） |
| 锚点 | ❌ 无（BULL/BEAR 用幻觉数据风险） | 需注入（同缺） |
| 输出消费 | `_merge_debate_result` append 洞察 | Bear 反驳 → issues |
| 超时 | 60s 线程超时（有） | 需复用（同） |
| 状态 | `enable_debate=False` 被禁 | 未实现 |

**重复点**：run_debate 调用、锚点注入、超时处理、结果解析——两处都要写。
**根因**：辩论产出（BULL 论点/BEAR 反驳/PM 裁决）是**一份中间产物**，两个消费者应共享它，而非各自调用引擎。

---

## 二、统一方案：单一引擎 + 双消费模式

### 核心思想

**辩论只跑一次，产出结构化 DebateResult（中间产物），两个消费者按需使用**。

```
章节内容 + Wind 锚点
      │
      ▼
┌─────────────────────────────────────────────────┐
│ debate_coordinator.run_debate（唯一引擎，不动）    │
│   BULL 看多论点（锚点注入）                       │
│   BEAR 逐条反驳 + 替代估值（锚点注入）            │
│   PM   裁决（看多/看空/中性 + 支撑度）           │
│ 产出：DebateResult（bull/bear/pm/conviction...）  │
└──────────────┬──────────────────────────────────┘
               │ 一份中间产物，两个消费者
      ┌────────┴────────┐
      ▼                 ▼
┌─────────────┐  ┌──────────────────┐
│ 消费者A：    │  │ 消费者B：          │
│ 质量增强     │  │ 实质审查          │
│ append 辩论   │  │ 提取 Bear 反驳    │
│ 洞察到章节    │  │ → 审查 issues    │
│（增强深度）   │  │ → Patch 修复     │
└─────────────┘  └──────────────────┘
```

### 落地：新增 `quality/debate_service.py`（统一入口，消除重复）

```python
# quality/debate_service.py
class DebateService:
    """辩论服务：统一入口，注入锚点 + 超时 + 双消费模式"""

    def __init__(self, llm_caller, wind_data=None, timeout=60):
        self.llm_caller = llm_caller
        self.wind_anchor = _build_wind_anchor_table(wind_data)  # 唯一锚点构建
        self.timeout = timeout

    def run(self, chapter_num, chapter_title, chapter_content,
            contract=None, mode="enhance") -> DebateResult:
        """跑一次辩论（注入锚点），按模式消费"""
        debate = run_debate(
            chapter_num, chapter_title, chapter_content,
            base_valuation_summary=self.wind_anchor,  # 锚点当估值上下文
            llm_caller=self._anchored_caller,          # 注入锚点的 caller
            contract=contract,
            llm_timeout_seconds=self.timeout,
        )
        if mode == "enhance":
            return _merge_debate_result(chapter_content, debate)  # 增强：append
        if mode == "review":
            return _extract_review_issues(debate)                  # 审查：提取 issues
        return debate

    @staticmethod
    def _extract_review_issues(debate) -> list[str]:
        """审查模式：从 Bear 反驳/PM 裁决提取审查问题"""
        issues = []
        if debate.bear_argument:
            # 提取"被忽略风险/逻辑漏洞/替代估值"→ issues
            for marker in ("反驳", "风险", "漏洞", "不一致", "高估", "低估"):
                if marker in debate.bear_argument:
                    issues.append(f"[辩论-Bear] {_snippet(debate.bear_argument, marker)}")
        if debate.pm_synthesis and "看空" in debate.pm_synthesis:
            issues.append(f"[辩论-PM] 裁决倾向看空: {_snippet(debate.pm_synthesis)}")
        return issues
```

### 两处改造（消除各自实现）

| 调用点 | 之前 | 之后 |
|---|---|---|
| `quality_enhancer.py` Stage3 | 直接调 run_debate（9 章、无锚点、append） | `DebateService(mode="enhance").run(...)`（复用锚点/超时） |
| `review_repair_loop._run_substantive_review` | 无辩论（建议新增第 5 项） | `DebateService(mode="review").run(...)`（仅 3 关键章） |

---

## 三、关键决策（精简点）

1. **锚点构建唯一化**：`_build_wind_anchor_table` 从 review_integrator 提升为 DebateService 内部复用（一处实现，全链路共用）
2. **超时唯一化**：`llm_caller_with_timeout` 留在 debate_coordinator（引擎层），DebateService 只传 timeout 参数
3. **消费分离**：enhance（append 洞察）与 review（提取 issues）是**纯函数**，互不依赖
4. **启用开关统一**：`enable_debate` 一个开关控制 DebateService 是否运行（质量增强+审查共用），不再各自开关
5. **章节范围可配**：增强=全 9 章；审查=3 关键章（ch4/ch5/ch10）——DebateService 接受 chapter 白名单参数

---

## 四、成本与收益

| | 收益 |
|---|---|
| 架构 | 消除两套辩论实现 → 单一引擎 + 双纯消费函数（减少 ~100 行重复） |
| 锚点 | 两处共用同一锚点表 → 辩论不再用幻觉数据 |
| 超时/降级 | 统一 60s + degraded 兜底 → 历史卡死彻底规避 |
| 审查能力 | 实质审查获得"对抗性验证"（Bear 抓 R5 型"中性 vs 买入"矛盾） |
| 增强能力 | 质量增强辩论恢复可用（enable_debate=True + 锚点） |

成本：DebateService ~60 行 + 两处调用点各改 ~10 行；验证 +1-2 次单测。

---

## 五、实施顺序

1. **新建 `quality/debate_service.py`**（锚点 + 超时 + enhance/review 双模式）
2. **改 `quality_enhancer.py` Stage3** → DebateService(mode="enhance")（9 章）
3. **改 `review_repair_loop._run_substantive_review`** → 新增第 5 项 DebateService(mode="review")（3 章）
4. **单测**：mock LLM → 验证 enhance 输出 append、review 输出 issues、超时降级
5. **回归**：quick 模式（无 LLM 时辩论跳过）+ 全编译

---

## 六、风险与边界

- **历史卡死**：debate_coordinator 的 `llm_caller_with_timeout` 线程超时已存在；DebateService 严格 1 轮 + 60s + degraded 兜底，不引入多轮迭代
- **成本**：审查模式仅 3 章 × 3 次调用（+3-5min）；增强模式 9 章（完整跑时 +10-15min，可用开关控制）
- **兼容**：DebateService 不修改 run_debate 接口，debate_coordinator 保持原样（引擎层不动）

---

## 七、结论

**统一方案可行且必要**：辩论的重复点（引擎调用/锚点/超时/解析）本质是"一份中间产物的多消费者"问题。
用 `DebateService`（单一入口 + enhance/review 双纯消费函数）即可消除重复、统一锚点与超时，
同时让质量增强（恢复可用）与实质审查（新增对抗验证）**共用同一套辩论引擎**，架构更精简。

## 八、落地状态（2026-08-18）

| 项 | 状态 |
|---|---|
| `debate_coordinator` 超时 60→240s + stages + 部分成功降级（Bull 可独立利用 / Bear 缺失标记 partial / PM 超时 `_auto_pm_synthesis` 自动裁决） | ✅ |
| 新增 `quality/debate_service.py`（统一入口：锚点表构建唯一化 + timeout 可配 + enhance/review 双消费 + retries） | ✅ |
| `quality_enhancer.py` Stage3 → DebateService(mode="enhance")（关键 5 章 ch1/4/5/7/10，成本控制） | ✅ |
| `review_repair_loop._run_substantive_review` 新增第 5 项 → DebateService(mode="review")（3 关键章 ch10/5/4） | ✅ |
| 单测：review 提取 Bear 问题 ✅ / enhance append 洞察 ✅ / Bear 失败 partial 保留 Bull ✅ | ✅ |
| quick 回归：Gate0-7 PASS，Gate8 正确拒绝 R5 ✅ | ✅ |

### 超时/降级修订（docs/qual-debate-timeout-redesign.md）
- 层2 角色线程超时：60 → 240s（默认，可配）——推理模型思考+生成
- 部分成功：Bull 成功即可增强；Bear 缺失标记 partial；PM 超时 `_auto_pm_synthesis` 自动裁决（不退回 Bull 草稿）
- 成本：增强 5 章（原 9 章）+ 审查 3 章，白名单可配
