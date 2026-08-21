# HeavySkill 审查质量增强技术方案（双模型：deepseek + mimo）

> 版本：v1.0 | 日期：2026-08-21
> 背景：P54 审查结论"能保证不残缺、可采信，不能保证结论必然正确"。四条增强路径
> 补齐质量缺口：结论验证器 / 异质模型二审 / 动态 K+quality_score / 审查包分批。
> 双模型：deepseek（主生成/审议）+ mimo（验证/二审/仲裁），打破单模型自洽盲点。

---

## 0. 双模型事实（已实测，2026-08-21）

| | deepseek-v4-pro | deepseek-chat | mimo-v2.5-pro |
|---|---|---|---|
| 端点 | `https://api.deepseek.com` | 同左 | `https://token-plan-cn.xiaomimimo.com/v1` |
| key | `DEEPSEEK_API_KEY`（config\.env） | 同左 | `XIAOMI_TOKEN_PLAN_CN_API_KEY`（~/.dsh/.credentials.yaml） |
| 类型 | 推理模型（reasoning_content 计入 max_tokens） | 非推理 | **推理模型（行为同 v4-pro：小预算饿死 content）** |
| max_tokens=32768 | ✅ 接受（finish=stop） | ✅ | ✅ 接受（finish=stop，11.6s/次） |
| max_tokens=100 长任务 | finish=length、content 空 | 正常 | **finish=length、content 空（同 v4-pro）** |
| 单次延迟 | 慢（推理） | 快 | 中（11.6s 中等任务） |

**关键结论**：现有截断治理（truncated/content_fallback 标记、剔除、回退共识）对 mimo
**天然通用**——同一套机制覆盖两个推理模型，无需分支。

---

## 1. 路径1：结论验证器（Conclusion Validator）——mimo 规则+LLM 混合校验

**目标**：审议结论不直接交付，先过验证器——确定性规则捕获硬伤，mimo 异质校验捕获逻辑/覆盖盲点。

### 1.1 模块
新增 `skills/heavyskill/workflow/validator.py`：

```python
@dataclass
class ValidationResult:
    verdict: str                 # PASS / PASS_WITH_WARNING / FAIL（与 HGF verdict 对齐）
    original_verdict: str        # 审议原结论
    verdict_changed: bool
    issues: List[dict]           # [{severity: P0|P1|P2, rule: str, message: str, evidence: str}]
    warnings: List[str]
    confidence: float            # 0-1
    validator_model: str         # "mimo-v2.5-pro"

class ConclusionValidator:
    def __init__(self, config: HeavySkillConfig, client: OpenAICompatibleClient): ...

    def validate(
        self,
        deliberation_response: str,
        trajectories: List[str],
        query: str,
        checklists: Optional[List[str]] = None,
    ) -> ValidationResult: ...
```

### 1.2 两级校验
**A. 确定性规则（零成本，先跑，P0 硬伤直接 FAIL）**：
- `verdict_format`：结论含可识别的裁决词（通过/不通过/有条件/PASS/FAIL）且格式合法
- `issue_severity_consistency`：结论说"存在 P0"但裁决为 PASS → 矛盾 FAIL
- `coverage_complete`：query 要求的多维度（如审查 3 维度）在结论中均有对应段落（关键词匹配）
- `numeric_consistency`：结论引用的数字与轨迹/输入中数字交叉核对（简单：抽取数字集合求交）
- `truncation_guard`：验证器输入若来自 truncated 审议 → 强制 FAIL 并指向回退路径（防御性）

**B. LLM 校验（mimo，异质视角）**：把 {审议结论 + K 条轨迹摘要 + 审查请求} 交给 mimo：
```
你是独立结论验证员（与生成/审议模型不同源）。
以下是一份 LLM 审查结论与 K 条推理轨迹摘要。
请核查：1) 逻辑矛盾  2) 遗漏的审查维度  3) 过度自信/无证据支撑的判断
4) 严重度分级是否合理。输出 JSON：{issues: [{severity, message, evidence}], verdict: PASS|PASS_WITH_WARNING|FAIL}
```
- mimo 输出用 `response_format: {"type": "json_object"}`（若端点支持）或提示词约束 + 解析兜底

### 1.3 接入与输出
- `pipeline.run()` 在审议后调用；`HeavySkillResult` 增加 `validation: Optional[ValidationResult]`
- 输出 JSON 增加 `validation` 字段；验证 FAIL 时控制台告警 + exit 非 0（复用 `--accept-partial` 语义）
- 配置：`enable_validator: true`、`validator_model: mimo-v2.5-pro`、`validator_api_base/key`

### 1.4 成本 / 风险
- 成本：+1 次 mimo 调用/审查（~12s、~1K tokens）——占 K=8 总成本 <5%
- 风险：mimo 误报 → 用 `warnings` 与 `issues` 分离，仅 P0 级 issue 强制 FAIL；置信度低于阈值时"降级为 warning 而非 FAIL"
- 验证：单测（注入矛盾结论/缺维度结论 → 规则捕获）+ 真实双模型样例 3 组

---

## 2. 路径2：二审/异质模型交叉（deepseek 审议 + mimo 独立二审）

**目标**：打破"8/8 轨迹一致但存在相关盲点"（HGF 教训：内部全绿≠外部可信）。mimo 与
deepseek 不同源，对同一批轨迹独立判断，分歧即信号。

### 2.1 流程（阶段 A-D）
```
A. deepseek 并行 K 轨迹（现有）
B. deepseek 顺序审议（现有）→ 一审结论 C1（含 selected 轨迹）
C. mimo 独立二审：不喂 C1，喂「selected 轨迹 + 审查请求 + 独立性强调」→ 二审结论 C2
D. 仲裁（确定性规则，不引入第三次 LLM）：
   - C1 == C2（裁决词一致）→ 采用，confidence 提升（×1.2，封顶 0.95）
   - C1 ≠ C2：
     a. 任一为 FAIL/P0 → 结论取 FAIL（安全优先）
     b. 均为 PASS 系但表述分歧 → 合并输出 + `consensus_conflict: true` 标记
     c. 分歧达 N 次（配置）→ 标记"需人工复核"
```

### 2.2 模块与接口
- `workflow/second_review.py`：`SecondReviewer`，复用 `OpenAICompatibleClient`（换 api_base/key/model）
- `HeavySkillResult` 增加 `second_review: Optional[SecondReviewResult]`
  ```python
  @dataclass
  class SecondReviewResult:
      second_conclusion: str
      second_model: str
      conflict: bool
      final_verdict: str          # 仲裁后
      confidence: float
  ```
- 配置：`enable_second_review: true`、`second_review_model: mimo-v2.5-pro`（独立于 validator，可复用同一 mimo 实例）

### 2.3 独立性保证（关键）
- 二审 prompt 明确"独立判断，不参考其他模型的结论"；**不注入 C1 文本**（只注入轨迹与请求）
- 二审 temperature 略低（0.3）保证稳定，一审 0.7 保证探索
- 轨迹输入用**同一批**（selected 集合），保证对比公平

### 2.4 成本 / 验证
- +1 次 mimo 调用/审查；与路径1 可合并为"二审即验证"（C2 兼作 validator 的 LLM 层，省一次调用）——**推荐合并**
- 验证：构造"盲点样例"（如轨迹全部遗漏某维度）→ 断言 C1 与 C2 分歧被捕获；真实样例 5 组对比仲裁正确率

---

## 3. 路径3：动态 K + quality_score 落地

**目标**：替换死字段 `quality_score`（现恒 1.0，memory_cache.py:40）；K 值从"任务无关固定"
变为"按复杂度自适应"。

### 3.1 quality_score 公式（确定性，零 LLM 成本）
```python
def score_trajectory(text: str, answer: Optional[str], meta: dict) -> float:
    s = 0.0
    # 完整性（0-40）
    s += min(len(text) / 2000, 1.0) * 20                 # 长度覆盖
    s += 20 if is_terminated(text) else 0                # 完整收尾（复用 P54 工具）
    # 有效性（0-40）
    s += 30 if ("最终答案" in text or "Final Answer" in text) else 0
    s += 10 if answer is not None else 0                 # extract_answer 成功
    # 退化惩罚
    if meta.get("truncated"): s = 0.0                    # 截断：直接剔除（已有 is_valid）
    if meta.get("content_fallback"): s *= 0.3            # 思维链回退：降权
    return round(min(s, 100.0), 1)
```
- 在 `memory_cache.add_trajectories` 中计算并赋值 `Trajectory.quality_score`（替换恒 1.0）
- `select_trajectories` 改造：按策略选出的候选**再按 quality_score 排序**（同答案组内取高分者）；`summary_k` 优先吃高分段
- 提供 `--no-quality-ranking` 开关保留旧行为（可回退）

### 3.2 动态 K（`--auto-k`）
```python
def auto_k(query: str, config: HeavySkillConfig) -> int:
    n = len(query)
    if n > 8000:   return 8    # 大审查包：标准
    if n > 3000:   return 6
    if n > 800:    return 4    # 常规
    return 2                    # 简单问题
```
- 自适应补跑：首轮 K=4，若 `valid_trajectories < summary_k` 或平均 quality_score < 60
  → 自动补一轮（+2 条）并标记 `k_extended: true`（预算内，token_budget 为硬约束）
- 配置：`auto_k: true`、`auto_k_scale: {short: 2, medium: 4, long: 8}`（可调）

### 3.3 验证
- 单测：分数公式各因子、选择排序、auto_k 分档、补跑触发条件
- 真实样例：同一 query 下 auto_k vs 固定 K 的质量分分布对比

---

## 4. 路径4：审查包分批（>20000 字符拆包）

**目标**：消除 `review.py build_pack` 的 20000 字符截断——被审内容不完整直接限制结论质量上限。

### 4.1 智能切分
```python
def split_pack(content: str, max_chars: int = 18000, overlap: int = 500) -> List[str]:
    """按章节边界切分：markdown 标题 / def|class / 空行，块间重叠 500 字符保上下文。"""
    # 1) 找边界点（^#{1,6} 、^def |^class |^async def 行首）
    # 2) 贪心累积到 max_chars，在最近边界处切断
    # 3) 每块末尾附加下一块前 500 字符（重叠，去重标记）
    # 4) 单块仍超限 → 硬切 + 标记
```
- 复用：`workflow/review.py` 的 `build_pack` 拆分逻辑抽出为 `split_pack`，`build_pack` 增加 `chunk: bool` 参数

### 4.2 分批审查 + 元审议
```
A. 块 i → 独立 heavyskill（K=4 或 auto_k）→ 分块结论 Bi（含 validator/second_review）
B. 元审议：把 {B1..Bn + 审查请求} 作为"轨迹"喂给审议层（deepseek）→ 最终结论
   （元审议与单块审议同构，复用 SequentialDeliberator；B 块结论就是轨迹文本）
```
- 元审议的 quality_score：分块结论天然是"完整文本"，直接可审
- 块数 n 与总成本：n×(K+1) 次调用；`--max-chunks` 限制（默认 5，超出告警）

### 4.3 验证
- 单测：切分边界正确性、重叠内容不重复、块数上限、单块超限硬切标记
- 真实样例：20000+ 字符方案 → 分块审查 vs 截断审查的发现项对比（应多出被截断部分的问题）

---

## 5. 集成与实施顺序

```
依赖：P54 截断治理（已完成）→ 路径3（quality_score，纯代码，先行）
  → 路径4（split_pack，纯代码，可并行）→ 路径1（validator，需要 mimo 客户端）
  → 路径2（second_review，依赖 validator 客户端复用，可与 1 合并实施）
```

| 顺序 | 路径 | 改动量 | 独立可交付 |
|---|---|---|---|
| 1 | 路径3 quality_score + auto_k | 中（cache/select/config） | ✅ |
| 2 | 路径4 split_pack + 元审议 | 中（review.py/pipeline） | ✅ |
| 3 | 路径1 validator（mimo） | 中（新模块 + config） | ✅ |
| 4 | 路径2 二审（合并 validator 客户端） | 小-中 | ✅ |

### 配置总览（HeavySkillConfig 新增）
```yaml
# config.yaml 新增段（示例）
quality:
  enabled: true
  auto_k: true
  auto_k_scale: {short: 2, medium: 4, long: 8}
validator:
  enabled: true
  provider: xiaomi          # mimo
  model: mimo-v2.5-pro
  api_base: https://token-plan-cn.xiaomimimo.com/v1
  api_key: ${XIAOMI_TOKEN_PLAN_CN_API_KEY}
  fail_on_p0: true
second_review:
  enabled: true
  merge_with_validator: true   # 二审结论兼作验证器 LLM 层（省一次调用）
  conflict_action: fail_on_p0
pack:
  chunk: true
  max_chars: 18000
  overlap: 500
  max_chunks: 5
```

## 6. 双模型分工表

| 环节 | 模型 | 理由 |
|---|---|---|
| K 路轨迹生成 | deepseek-v4-pro（或 chat） | 主生成，现有配置默认 |
| 顺序审议 | deepseek（summary_model） | 主审议 |
| 结论验证（路径1） | **mimo-v2.5-pro** | 异质校验，独立视角 |
| 独立二审（路径2） | **mimo-v2.5-pro** | 异质，打破自洽盲点 |
| 元审议（路径4） | deepseek | 与单块审议同构 |
| 确定性规则（路径1A/仲裁） | 无（纯代码） | 零成本硬校验 |

**双模型冗余价值**：deepseek 与 mimo 不同源、不同训练分布——同一批轨迹的两份独立判断
若分歧，是"相关盲点"的最强信号；若一致，置信度显著高于单模型。

## 7. 风险与缓解

| 风险 | 缓解 |
|---|---|
| mimo 误报导致误 FAIL | issues 仅 P0 强制 FAIL；置信度阈值降级为 warning |
| 二审成本 | 与 validator 合并调用；`merge_with_validator: true` 默认 |
| 动态 K 不稳定 | `--no-auto-k` 回退固定 K；token_budget 硬约束 |
| 分批丢上下文 | 重叠 500 字符 + 元审议聚合；`--max-chunks` 防爆炸 |
| mimo key 失效/限流 | validator/second_review 失败 → 降级为"仅规则校验"并告警（fail-open，不阻断主链路） |

## 8. 验收标准

- 四路径全部落地后：单测新增 ≥20（validator 规则×6、second_review 仲裁×4、quality_score×5、split_pack×5、auto_k×3，去重后）
- 真实双模型样例：10 组审查中 validator 捕获 ≥3 处审议遗漏/矛盾；二审分歧 ≥2 组被正确仲裁
- 门禁：ruff 全绿（新代码零新增债，沿用 scoped 配置）、HGF CLI MUST_PASS 全通过
