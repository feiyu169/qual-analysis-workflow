# Qual v9 技术方案：Gate 依赖解耦 + PGNB 覆盖扩展 + 形式审查分类

> 日期：2026-08-22
> 状态：方案设计（待评审）
> 基线：qual_v8 commit 7/7（Phase 0-6），小鹏 9868.HK 全流程结果

---

## 一、问题全景

| # | 问题 | 严重度 | 根因层 |
|---|------|--------|--------|
| P1 | 跨章净利润冲突（ch5=94.0, ch7=-103.76） | 🔴 P0 | PGNB regex 盲区 + 财年归因缺失 |
| P2 | Gate 5-8 级联失败（Gate4→prerequisites 阻断） | 🔴 P0 | 架构级：Gate 依赖是线性链 |
| P3 | Gate4 形式审查 98 issues | 🟡 P1 | 混合了真问题 + 误报，缺分类 |
| P4 | 公司名"小鹏汽车-W" | 🟢 P2 | 已修，等缓存失效 |
| P5 | Gate1 FY2023 NoneType | 🟢 P2 | fact_extractor 空值防护 |

---

## 二、问题 1：跨章净利润冲突（PGNB 覆盖盲区）

### 2.1 架构根因

当前 PGNB（Programmatic Grounded Number Binding）有 **两层防线**：

1. **bind_bare_numbers**：拦截 LLM 直接写的裸数字（`_METRIC_NUM_RE` 匹配 → 替换为占位符 → bind_placeholders 按锚点回填）
2. **validate_bare_numbers**：校验裸数字是否命中锚点（报问题但不替换）

**P1 根因链**：
```
ch5 LLM 写 "归母净利润94.0亿元"（幻觉）
  → _METRIC_NUM_RE 匹配到 "归母净利润" + "94.0" + "亿"
  → bind_bare_numbers 本应替换为 [{{归母净利润}}]
  → 但 ch5 的 Gate3 写作上下文可能没有正确传入 anchor
  → 或者 bind_bare_numbers 在 review_and_repair_single_pass 中运行时
     chapters dict 已经被 ch5 的 LLM 输出覆盖（post-LLM 但 pre-bind）

ch7 LLM 写 "归母净利润-103.76亿元"（FY2023 值被错引用为 FY2025）
  → _METRIC_NUM_RE 匹配到 "归母净利润" + "-103.76" + "亿"
  → 锚点中有 FY2023=-103.7578，命中（1% 容差内）→ 保留
  → 但 cross_chapter_consistency 发现 ch5=94.0 vs ch7=-103.76 冲突
  → 94.0 是幻觉（不命中任何财年），-103.76 是 FY2023（非最新财年）
```

**深层问题**：`_METRIC_NUM_RE` 的匹配逻辑是"指标名 + 非数字分隔 + 数字 + 单位"，但它**不检查财年上下文**。当 LLM 写"FY2023归母净利润-103.76亿"时，`-103.76` 命中 FY2023 锚点 → 合法保留。但当 LLM **不标注财年**直接写"归母净利润-103.76亿"时，系统无法区分这是"最新财年的值"还是"历史财年的值被错引"。

### 2.2 代码修改

#### 2.2.1 扩展 `_METRIC_NUM_RE` 上下文捕获

**文件**：`tools/finance/qual_v8/numeric_binder.py`

```python
# 当前（L340-344）：
_METRIC_NUM_RE = re.compile(
    r"(营业收入|营业利润|归母净利润|归母净资产|经营活动现金流量净额|"
    r"购建固定资产、无形资产和其他长期资产支付的现金|总资产|"
    r"年负债合计|年所有者权益合计|净利润|毛利率|净利率|营业利润率)\s*"
    r"[^\d\-]{0,8}(-?\d+\.?\d*)\s*(亿元|亿|万元|万|%)?"
)

# 修改为（增加前向上下文捕获，用于财年归因）：
_METRIC_NUM_RE = re.compile(
    r"(?:(FY\d{4}|20\d{2}年?|去年|上年|前年|当年|本年|最新财年)\s*)?"
    r"(营业收入|营业利润|归母净利润|归母净资产|经营活动现金流量净额|"
    r"购建固定资产、无形资产和其他长期资产支付的现金|总资产|"
    r"年负债合计|年所有者权益合计|净利润|毛利率|净利率|营业利润率)\s*"
    r"[^\d\-]{0,8}(-?\d+\.?\d*)\s*(亿元|亿|万元|万|%)?"
)
```

**关键变化**：增加可选的前向财年上下文组 `(?:(FY\d{4}|20\d{2}年?|去年|...)\s*)?`

- group(1) = 财年上下文（可选）
- group(2) = 指标名
- group(3) = 数值
- group(4) = 单位

#### 2.2.2 修改 `bind_bare_numbers` 增加财年感知

**文件**：`tools/finance/qual_v8/numeric_binder.py`，`_repl` 函数（L281-326）

```python
def _repl(m: re.Match) -> str:
    fy_context = m.group(1)  # 新增：财年上下文
    metric = m.group(2)      # 原 group(1) → group(2)
    try:
        value = float(m.group(3))  # 原 group(2) → group(3)
    except (TypeError, ValueError):
        return m.group(0)

    # 4 位年份豁免（不变）
    if 2020 <= value <= 2035 and value == int(value) and len(m.group(3).split(".")[0]) == 4:
        return m.group(0)

    unit = m.group(4) or "亿"  # 原 group(3) → group(4)
    v = value
    if unit in ("万元", "万"):
        v = value / 10000.0

    # 百分比指标（不变）
    if unit == "%":
        # ... 保持原有逻辑，但 group 编号调整 ...

    # 绝对额指标
    pts = anchor.get_metric_points(metric)
    if not pts:
        return m.group(0)

    # 新增：财年感知匹配
    explicit_fy = _parse_fy_context(fy_context)
    if explicit_fy is not None:
        # 有明确财年上下文 → 只匹配该财年锚点
        hit = any(
            dp.fiscal_year == explicit_fy
            and dp.value is not None
            and abs(v - dp.value) / max(abs(dp.value), 1e-9) <= 0.01
            for dp in pts
        )
        if hit:
            return m.group(0)  # 命中指定财年 → 合法
    else:
        # 无财年上下文 → 匹配最新财年（收紧策略）
        # P1 修复：无财年标注时，只允许最新财年值通过
        latest_dp = pts[-1]
        if (latest_dp.value is not None
                and abs(v - latest_dp.value) / max(abs(latest_dp.value), 1e-9) <= 0.01):
            return m.group(0)  # 命中最新财年 → 合法
        # 命中历史财年但未标注 → 替换为占位符（强制标注财年）
        if any(
            dp.value is not None
            and abs(v - dp.value) / max(abs(dp.value), 1e-9) <= 0.01
            for dp in pts
        ):
            # 找到匹配的历史财年
            matched_fy = next(
                dp.fiscal_year for dp in pts
                if dp.value is not None
                and abs(v - dp.value) / max(abs(dp.value), 1e-9) <= 0.01
            )
            head = m.group(0)[: m.start(3) - m.start(0)]
            tail = m.group(0)[m.end(3) - m.start(0):]
            fixes.append(
                f"{metric}: {value} → 占位符（历史财年 FY{matched_fy}，"
                f"未标注财年，强制占位符+标注）"
            )
            return head + f"[{{{{{metric}}}}}]" + tail

    # 不命中任何财年 → 幻觉替换
    head = m.group(0)[: m.start(3) - m.start(0)]
    tail = m.group(0)[m.end(3) - m.start(0):]
    latest = pts[-1]
    fixes.append(
        f"{metric}: {value} → 占位符（锚点 FY{latest.fiscal_year}={latest.value:.2f}）"
    )
    return head + f"[{{{{{metric}}}}}]" + tail
```

新增辅助函数：

```python
def _parse_fy_context(ctx: str | None) -> int | None:
    """从上下文字符串解析财年（FY2023/2023年/去年 等）"""
    if not ctx:
        return None
    m = re.search(r'(?:FY)?(\d{4})', ctx)
    if m:
        return int(m.group(1))
    # 相对财年需要 Wind 数据支持，此处返回 None 走默认路径
    return None
```

#### 2.2.3 同步修改 `validate_bare_numbers`

**文件**：`tools/finance/qual_v8/numeric_binder.py`，L370-411

同样的 group 编号调整 + 增加财年感知：

```python
for m in _METRIC_NUM_RE.finditer(content):
    fy_context = m.group(1)
    metric = m.group(2)
    try:
        value = float(m.group(3))
    except (TypeError, ValueError):
        continue
    # ... 年份豁免 ...
    unit = m.group(4) or "亿"
    # ... 单位转换 ...

    pts = anchor.get_metric_points(metric)
    if not pts:
        continue

    explicit_fy = _parse_fy_context(fy_context)
    if explicit_fy is not None:
        # 有明确财年 → 只校验该财年
        hit = any(
            dp.fiscal_year == explicit_fy
            and dp.value is not None
            and abs(value - dp.value) / max(abs(dp.value), 1e-9) <= 0.01
            for dp in pts
        )
    else:
        # 无财年标注 → 只允许最新财年
        latest_dp = pts[-1]
        hit = (latest_dp.value is not None
               and abs(value - latest_dp.value) / max(abs(latest_dp.value), 1e-9) <= 0.01)

    if not hit:
        problems.append(
            f"第{chapter_num}章 裸数字幻觉: {metric}={value}"
            f"（{'未标注财年' if explicit_fy is None else f'FY{explicit_fy}不匹配'}，"
            f"应用 [{{{{{metric}}}}}] 占位符）"
        )
```

### 2.3 验证方法

```bash
# 1. 单元测试：新增财年感知测试用例
cd tools/finance
python -m pytest test_pgnb.py -v -k "test_bind_bare_numbers"

# 2. 新增测试：历史财年未标注场景
# 内容："归母净利润-103.76亿元"（FY2023 值，无财年标注）
# 期望：替换为 [{{归母净利润}}]（强制占位符）
# 锚点：FY2023=-103.7578, FY2024=-57.9026, FY2025=-11.3946

# 3. 集成测试：小鹏全流程重跑
python run_xpev_full.py
# 期望：跨章净利润冲突 = 0 issues
```

### 2.4 风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| 合法历史引用被误替换 | ch7 引用 FY2023 总资产被替换为占位符 | 只对**未标注财年**的历史值收紧；已标注 FY2023 的保留 |
| regex group 编号变化 | 所有调用 `_METRIC_NUM_RE` 的代码需要调整 group 编号 | 全局搜索 `_METRIC_NUM_RE`，逐一调整 |
| 性能影响 | regex 增加前向可选组 | 影响极小（正则引擎优化） |

---

## 三、问题 2：Gate 5-8 级联失败（最大架构问题）

### 3.1 架构根因

当前 Gate 依赖是**严格线性链**：

```
Gate0 → Gate1 → Gate2 → Gate3 → Gate4 → Gate5 → Gate6 → Gate7 → Gate8
                                              ↑
                                         prerequisites=[4]
```

`gate_engine.py` L84-96：
```python
for prereq in gate.spec.prerequisites:
    if prereq not in self.results or not self.results[prereq].passed:
        return GateResult(passed=False, errors=[f"前置Gate {prereq} 未通过"])
```

**核心矛盾**：Gate 4（审计修复）失败 → Gate 5（质量增强）的 `prerequisites=[4]` 阻断 → Gate 6/7/8 级联跳过。但 Gate 5-8 的很多子任务（估值计算、PGNB 终局 sweep、决策章生成）**不依赖 Gate 4 的审计修复结果**，只依赖 Gate 3 的章节内容。

**v8 的补丁尝试**：在 `workflow.py` Step 4.7 增加了独立于 Gate 4 结果的终局 rescue sweep。但这只是绕过了 Gate 8 的 PGNB 部分，Gate 5-7 的核心功能（估值、决策章）仍然被阻断。

### 3.2 架构方案：Gate 依赖图重构（DAG 替代线性链）

#### 3.2.1 设计原则

1. **数据依赖 vs 质量门禁分离**：Gate 间的依赖应该是"需要哪些数据"，而非"前一个 Gate 是否通过"
2. **降级执行**：前置 Gate 失败时，后续 Gate 应该能降级运行（使用已有数据），而非完全跳过
3. **终局 sweep 独立化**：PGNB/ADVC 等程序化修复应该是独立于所有 Gate 的终局管线

#### 3.2.2 新依赖图

```
Phase 1: 数据准备（严格顺序，数据依赖）
  Gate0 (数据源验证) ──→ Gate1 (类型推断+事实提取) ──→ Gate2 (数据收集)

Phase 2: 内容生成（严格顺序，数据依赖）
  Gate2 ──→ Gate3 (逐章写作)

Phase 3: 审计修复（依赖 Gate3 输出）
  Gate3 ──→ Gate4 (审计修复)

Phase 4: 增强 & 决策（**降级依赖 Gate3，不依赖 Gate4**）
  Gate3 ──→ Gate5 (质量增强)     ← 降级：Gate4 失败时仍运行，跳过 Gate4 修复后的校验
  Gate3 ──→ Gate6 (综合结论)     ← 降级：Gate4 失败时仍运行，报告标注质量受限
  Gate3 ──→ Gate7 (问题转化)     ← 降级：Gate4 失败时仍运行

Phase 5: 终局验证（依赖所有前置，但降级运行）
  Gate4 ∪ Gate5 ∪ Gate6 ∪ Gate7 ──→ Gate8 (终局验证 + rescue sweep)
```

#### 3.2.3 实现方案：`GateSpec` 增加降级策略

**文件**：`tools/finance/qual_v8/core/gate_engine.py`

```python
@dataclass
class GateSpec:
    gate_num: int
    name: str
    description: str
    prerequisites: list[int]           # 硬依赖（必须通过）
    soft_prerequisites: list[int]      # 软依赖（失败则降级运行）
    timeout: int
    max_retries: int
    pass_criteria: dict[str, Any]
    degrade_on_soft_fail: bool = True  # 软依赖失败时是否降级
```

**文件**：`tools/finance/qual_v8/core/gate_engine.py`，`execute_gate` 方法

```python
def execute_gate(self, gate_num: int, context: dict[str, Any]) -> GateResult:
    gate = self.gates[gate_num]

    # 硬依赖检查（不变）
    for prereq in gate.spec.prerequisites:
        if prereq not in self.results or not self.results[prereq].passed:
            return GateResult(
                gate_num=gate_num, passed=False, score=0.0,
                details={"error": f"硬依赖 Gate {prereq} 未通过"},
                errors=[f"硬依赖 Gate {prereq} 未通过"],
                warnings=[], execution_time=0.0,
                timestamp=datetime.now().isoformat(),
            )

    # 软依赖检查（新增）
    degraded = False
    for soft_prereq in gate.spec.soft_prerequisites:
        if soft_prereq in self.results and not self.results[soft_prereq].passed:
            degraded = True
            context.setdefault("degraded_from", []).append(soft_prereq)
            logger.warning(
                f"Gate {gate_num}: 软依赖 Gate {soft_prereq} 未通过，降级运行"
            )

    # 执行 Gate
    start_time = datetime.now()
    result = gate.execute(context)
    result.execution_time = (datetime.now() - start_time).total_seconds()

    # 降级标记
    if degraded:
        result.details["degraded"] = True
        result.details["degraded_from"] = context.get("degraded_from", [])
        result.warnings.append(
            f"降级运行：软依赖 {context.get('degraded_from', [])} 未通过"
        )

    return result
```

#### 3.2.4 Gate 5/6/7 的 Spec 修改

**文件**：`tools/finance/qual_v8/gates/gate5.py`（新建）

```python
spec = GateSpec(
    gate_num=5,
    name="质量增强 + 组件集成",
    prerequisites=[3],           # 硬依赖：Gate3（需要章节内容）
    soft_prerequisites=[4],      # 软依赖：Gate4（审计修复结果，降级可用）
    ...
)
```

**文件**：`tools/finance/qual_v8/gates/gate6.py`（新建）

```python
spec = GateSpec(
    gate_num=6,
    name="综合结论 + 决策章",
    prerequisites=[3],           # 硬依赖：Gate3
    soft_prerequisites=[4, 5],   # 软依赖：Gate4 + Gate5
    ...
)
```

**文件**：`tools/finance/qual_v8/gates/gate7.py`（已有，修改 spec）

```python
spec = GateSpec(
    gate_num=7,
    name="问题转化 + 记忆存储",
    prerequisites=[3],           # 硬依赖：Gate3
    soft_prerequisites=[4, 5, 6], # 软依赖：Gate4/5/6
    ...
)
```

**文件**：`tools/finance/qual_v8/gates/gate8.py`（修改 spec）

```python
spec = GateSpec(
    gate_num=8,
    name="终局验证 + rescue sweep",
    prerequisites=[3],                              # 硬依赖：Gate3
    soft_prerequisites=[4, 5, 6, 7],               # 软依赖：Gate4-7
    ...
)
```

#### 3.2.5 Gate8 降级模式增强

**文件**：`tools/finance/qual_v8/gates/gate8.py`

当 Gate8 降级运行时（Gate4 失败），需要：
1. 强制执行 rescue sweep（PGNB + ADVC + 日期绑定）
2. 跳过 Gate4 修复后的校验（因为没有修复）
3. 在报告中添加质量受限标注

```python
def execute(self, context: dict[str, Any]) -> GateResult:
    degraded = context.get("degraded_from") or []

    # 降级模式：强制执行 rescue sweep（不依赖 Gate4 的修复结果）
    if 4 in degraded:
        logger.warning("Gate8 降级模式：Gate4 未通过，强制执行终局 rescue sweep")
        self._run_rescue_sweep(context)
        # 降级模式下，形式审查 issues 从 Gate4 context 读取（如果有）
        formal_issues = context.get("gate_4_formal_issues", [])
        if formal_issues:
            context["gate8_formal_issues_from_g4"] = formal_issues

    # ... 正常执行逻辑 ...
```

#### 3.2.6 workflow.py 线性循环改为 DAG 执行

**文件**：`tools/finance/qual_v8/workflow.py`，`execute` 方法

```python
# 当前（L295）：for gate_num in range(9):
# 改为：按 Phase 分组执行

_PHASES = [
    {"name": "数据准备", "gates": [0, 1, 2], "mode": "strict"},      # 严格顺序
    {"name": "内容生成", "gates": [3], "mode": "strict"},             # 严格顺序
    {"name": "审计修复", "gates": [4], "mode": "strict"},             # 严格顺序
    {"name": "增强决策", "gates": [5, 6, 7], "mode": "degradable"},  # 可降级
    {"name": "终局验证", "gates": [8], "mode": "degradable"},         # 可降级
]

def execute(self, context: dict[str, Any]) -> dict[str, Any]:
    # ... 初始化不变 ...

    for phase in _PHASES:
        logger.info(f"执行 Phase: {phase['name']}")
        for gate_num in phase["gates"]:
            # ... 现有 Gate 执行逻辑不变 ...
            # GateEngine.execute_gate 内部处理软依赖降级
            pass

    # ... 后续逻辑不变 ...
```

### 3.3 验证方法

```bash
# 1. 模拟 Gate4 失败场景：注入 Gate4 强制失败
# 期望：Gate5/6/7/8 降级运行，报告产出（带质量受限标注）

# 2. 小鹏全流程重跑
python run_xpev_full.py
# 期望：Gate4 失败 → Gate5-8 降级运行 → 报告产出（15分钟内）

# 3. Gate4 通过场景：正常运行
# 期望：Gate5-8 正常运行（无降级标注）
```

### 3.4 风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| 降级运行产出低质量报告 | Gate5 估值基于未修复的章节 | Gate8 rescue sweep 兜底修复 |
| 软依赖逻辑复杂化 | 调试困难 | 增加 `degraded_from` 到 audit log |
| Gate5/6/7 需要适配降级模式 | 部分子功能在降级时不可用 | 每个 Gate 内部检查 `degraded` 标记，跳过依赖 Gate4 输出的子功能 |

---

## 四、问题 3：Gate4 形式审查 98 issues 分类

### 4.1 问题分类

根据 Gate4 `_formal_review` 的检查项，98 issues 可分为：

| 类别 | 典型问题 | 数量估计 | 处理策略 |
|------|----------|----------|----------|
| **真问题：占位符残留** | `[{经营活动现金流量净额}]`（单花括号） | ~10 | PGNB regex 已支持单花括号，bind_placeholders 应回填 |
| **真问题：模板指纹** | "沪深300/组合构建/夏普比率" | ~5 | prompt 优化 + 模板词过滤 |
| **真问题：格式问题** | H1 标题自造、小节缺失 | ~10 | 结构检查器修复 |
| **误报：数据引用缺来源** | "营收767.20亿元"（句末有来源但被 split 切开） | ~50 | 来源检查窗口优化 |
| **误报：币种混用** | "港元+人民币"（港股常态） | ~10 | 已降为 warning，不计入 errors |
| **误报：元/股** | 发行价/港元上下文的合法使用 | ~13 | 已有豁免逻辑，可能未完全覆盖 |

### 4.2 代码修改

#### 4.2.1 来源检查窗口优化（减少误报）

**文件**：`tools/finance/qual_v8/gates/gate4.py`，`_formal_review` 方法（L213-221）

```python
# 当前：按句 split，检查本句+下一句
sentences = re.split(r"[。\n]", content)
for idx, sent in enumerate(sentences):
    if not re.search(r"\d+\.?\d*\s*亿", sent):
        continue
    window = sent + (sentences[idx + 1] if idx + 1 < len(sentences) else "")
    if not any(kw in window for kw in ("来源", "Wind", "年报", ...)):
        warnings.append(...)

# 修改为：扩大窗口到本句+前后各一句，且检查段落级来源标注
for idx, sent in enumerate(sentences):
    if not re.search(r"\d+\.?\d*\s*亿", sent):
        continue
    # 扩大窗口：前一句 + 本句 + 后两句（来源可能在段落末尾）
    start = max(0, idx - 1)
    end = min(len(sentences), idx + 3)
    window = "".join(sentences[start:end])
    # 增加更多来源关键词
    source_keywords = (
        "来源", "Wind", "年报", "报告", "公告", "测算", "估计", "数据",
        "披露", "公开信息", "公司资料", "招股书", "季报", "半年报",
    )
    if not any(kw in window for kw in source_keywords):
        warnings.append(f"第{ch_num}章数据引用可能缺来源: '{sent[:40]}...'")
```

#### 4.2.2 占位符 regex 增强（减少遗漏）

**文件**：`tools/finance/quality/placeholder_rules.py`

```python
# 确保 PLACEHOLDER_PATTERNS 覆盖所有变体：
PLACEHOLDER_PATTERNS = [
    "[{{...}}]",      # 标准双花括号
    "[{...}]",        # 单花括号（LLM 格式错误）
    "[[...]]",        # 双方括号（LLM 格式错误）
    "{{...}}",        # 无方括号的花括号
    "[...]",          # 纯方括号（需排除合法 markdown 链接）
]
```

#### 4.2.3 形式审查结果分类输出

**文件**：`tools/finance/qual_v8/gates/gate4.py`，`_formal_review` 返回值

```python
return {
    "passed": len(errors) == 0,
    "errors": errors,                    # 真问题（阻断）
    "warnings": warnings,                # 误报/低风险（不阻断）
    "format_errors": format_errors,
    # 新增：分类统计
    "categories": {
        "placeholder": placeholder_count,
        "template_leak": template_count,
        "source_missing": source_count,
        "currency_mix": currency_count,
        "format_issue": format_count,
    },
}
```

### 4.3 验证方法

```bash
# 1. 运行 Gate4 形式审查，检查分类统计
# 期望：误报占比 < 20%（当前估计 60%+）

# 2. 对比修改前后 issues 数量
# 修改前：98 issues
# 修改后目标：< 30 issues（真问题）
```

### 4.4 风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| 放宽来源检查导致真实遗漏 | 数据引用无来源的段落漏检 | 保留 warning，只从 errors 降级 |
| 占位符 regex 过宽 | 合法 markdown 链接 `[text](url)` 被误匹配 | 排除 `](` 模式 |

---

## 五、问题 4：公司名"小鹏汽车-W"

### 5.1 状态

已修（`run_xpev_full.py` fallback），Python 模块缓存导致旧代码运行。

### 5.2 验证

```bash
# 清除缓存后重跑
python -c "import tools.finance.workflow; print(tools.finance.workflow.__file__)"
python run_xpev_full.py
# 检查报告中公司名是否为"小鹏汽车-W"
```

---

## 六、问题 5：Gate1 FY2023 NoneType

### 6.1 架构根因

`fact_extractor` 在 FY2023 sections 调用时，某个返回值为 `None`，后续 `.get()` 调用失败。

### 6.2 代码修改

**文件**：`tools/finance/fact_extractor.py`

```python
# 在 extract_facts_from_sections 或类似函数中增加空值防护
# 查找所有 .get() 调用链，确保上游为 None 时安全降级

# 示例（需要定位具体出错行）：
# 当前：
result = some_dict.get("key").get("nested_key")
# 修改为：
result = (some_dict.get("key") or {}).get("nested_key")
```

### 6.3 验证

```bash
# 重跑 Gate1，检查 FY2023 事实表是否正常提取
# 期望：无 NoneType 异常
```

---

## 七、实施优先级

| 阶段 | 内容 | 预估工时 | 依赖 |
|------|------|----------|------|
| **Phase 7** | P2: Gate 依赖图重构（DAG） | 4h | 无 |
| **Phase 8** | P1: PGNB 财年感知扩展 | 3h | 无 |
| **Phase 9** | P3: 形式审查分类 + 误报过滤 | 2h | 无 |
| **Phase 10** | P5: fact_extractor 空值防护 | 1h | 无 |
| **Phase 11** | P4: 公司名缓存验证 | 0.5h | 无 |
| **Phase 12** | 集成测试 + 全流程重跑 | 2h | Phase 7-11 |

**总预估**：12.5 小时（2 个工作日）

**推荐顺序**：Phase 7（最大架构问题）→ Phase 8（最大数据问题）→ Phase 9（最大噪音源）→ Phase 10-12

---

## 八、测试矩阵

| 测试场景 | 覆盖问题 | 预期结果 |
|----------|----------|----------|
| 小鹏全流程重跑 | P1-P5 | Gate 0-8 全通过（或 Gate4 失败时 Gate5-8 降级通过） |
| Gate4 强制失败 | P2 | Gate5-8 降级运行，报告产出 |
| ch5 写"归母净利润94.0亿" | P1 | bind_bare_numbers 替换为 [{{归母净利润}}] |
| ch7 写"归母净利润-103.76亿"（无 FY 标注） | P1 | bind_bare_numbers 替换为 [{{归母净利润}}]（收紧策略） |
| ch7 写"FY2023归母净利润-103.76亿" | P1 | 保留（有明确财年标注） |
| 形式审查来源检查 | P3 | 误报率 < 20% |
| fact_extractor FY2023 | P5 | 无 NoneType 异常 |
