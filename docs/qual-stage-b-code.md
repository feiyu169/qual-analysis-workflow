# Qual 流水线阶段 B（数据真实性改进）代码设计分册

日期：2026-08-19
依据：`docs/qual-expert-suggestions-adjudication.md`（综合审议意见）+ `docs/qual-implementation-roadmap.md`（统一路线图 v1.1）
前置：阶段 A（v3.1 死循环修复）已交付；所有阻断判据必须与 v3.1 单调守卫兼容（见 §10）
目标：本分册给出**可直接实施**的代码设计——修正点精确到文件:行号、完整新签名、伪代码、测试与副作用；消除全部硬编码；不引入新问题。

---

## 0. 总览

### 0.1 阶段 B 验收总纲（来自路线图 §五）

| 里程碑 | 验收 |
|---|---|
| M2（B1） | 章节级财年校验拦截 ch5 历史财年（ch6 合法引用豁免）；Critical 阻断出厂；数据源降级仍产出带标注报告 |
| M3（B2） | 无硬编码股价；目标价=程序输出（亏损公司走降级链）；币种断言生效；事实表无财务提取；无源字段显式标注 |
| M4（B3） | 事实表多财年 + 每行可翻原文复核（页码 null+unverified 而非编造） |
| M5（B4/B5） | 运营数据验证链通过（钩稽 warning 级+白名单）；行业判定正确；结论可复现（评级=规则输出+override 留痕）；无可比硬编码数据 |

### 0.2 硬编码清除清单（现状 → 修正）

| # | 硬编码 | 位置（文件:行号） | B 项 | 修正 |
|---|---|---|---|---|
| H1 | `current_price=21.48` | `run_qual_full.py:133` | B2a-1 | 从 `wind_data["quote"]["最新价"]` 动态取（见 §2.1） |
| H2 | `current_price=46.52` | `run_xpev_full.py:217` | B2a-1 | 同上 |
| H3 | `current_price=21.48` | `run_qual_v8.py:75` | B2a-1 | 同上（quick 模式同样动态取） |
| H4 | `current_price: float = 41.6` | `quality_enhancer.py:52` | B2a-1 | 改 `Optional[float]=None` + `resolve_current_price(wind_data)` |
| H5 | 顺丰专版可比数据 | `quality/peer_comparison.py:49-94` `create_sf_express_peers()` | B4-6 | 删除；改数据驱动 `build_peer_companies()`（§6.6） |
| H6 | 错误 ticker `002024.SZ`（实为分众传媒） | `peer_comparison.py:59` | B4-6 | 随 H5 删除；新数据源不再携带 |
| H7 | 物流特有字段 `express_volume/revenue_per_piece` | `peer_comparison.py:37-38` | B4-6 | 移出 `PeerCompany` 基类，改行业扩展字段 |
| H8 | 毛利率默认 50% | `fact_extractor.py:636` `op.gross_margin = 0.5` | B4-2 | 删除默认填充；缺口 → None + 标注（§6.2） |
| H9 | `wrong_years=[2023,2024,2026]` | `data_repair.py:230` | B2b-3 | 通用化：替换 `year != fiscal_year` 的任意年份（§2.7） |
| H10 | `快手` 专名 pattern | `data_repair.py:248` | B2b-3 | `company_name` 参数化 |
| H11 | 净负债启发式 `total_debt * 0.3` | `workflow.py:2165` | B2a-3/B5-1 | 删除；走 WindMissingFieldRegistry（§3） |
| H12 | `shares` 默认 1 | `workflow.py:2175` | B2a-3 | shares 必填；缺失 → 降级链/失败（不静默默认） |
| H13 | 增长率默认 5% | `workflow.py:2124-2131` | B2a-3 | 数据不足 → 显式降级原因（非静默默认） |
| H14 | CAPM 硬编码 rf=0.023/beta=1.2/erp=0.055 | `workflow.py:2140-2142`、`quality_enhancer.py:248-250`、`valuation_engine.py:146-148` | B2a-3 | β 动态取（Wind β/可比中位数）；rf/erp 入 config |
| H15 | `wacc=0.081` 写死 | `quality_enhancer.py:184`（UnifiedValuation assumptions） | B2a-3 | 由参数计算注入 |
| H16 | `year = 2026 + i` | `valuation_engine.py:199` | B2a-3 | `latest_fy + 1 + i`（从 financials 推） |
| H17 | 营业利润率为负回填 0.05 | `valuation_engine.py:185,189` | B2a-3 | fail-fast 分支（§2.3），不假设 5% |
| H18 | 可比常量表 `CORE/SUPPLEMENTARY_COMPARABLES` | `valuation_engine.py:102-113` | B4-6 | 删除默认；数据由调用方（Wind 动态）传入 |
| H19 | 阅文专名 `0772/00772` 校验 | `fact_extractor.py:610` | B2b-1 | 用 `ticker` 参数化（含 0 前缀推导） |
| H20 | `_year_labels=[2023,2024,2025]` 写死 | `assemble_wind_data.py:106` | B5-1 | 从 Wind 响应动态解析财年序列 |
| H21 | `行业="新能源汽车"` 默认 | `workflow.py:2933-2939`、`quality/review_repair_loop.py:37` | B4-3 | `industry_for` 数据驱动 + 降级"标注或年份未知"（§6.3） |
| H22 | `qual_mode` 默认 shadow | `mode_manager.py:117`、`workflow.py:223`、`workflow.py:2443` | B1-2 | A4 验收后翻转默认 enforce（分级阻断版） |

### 0.3 关键源文件行号索引（实施核对用）

| 文件 | 行号 | 内容 |
|---|---|---|
| `tools/finance/quality/numeric_guard.py` | 59 | `FISCAL_STRICT_CHAPTERS={4,5}`（B1-1 替换） |
| 同上 | 214-244 | `check_fiscal`（B1-1 扩展） |
| 同上 | 249-277 | `check_currency`（B2a-2 复用） |
| `tools/finance/qual_v8/data_anchor.py` | 152-181 | `validate_chapter_any_fy`（保留，作对比层） |
| 同上 | 331-348 | `CrossChapterValidator.validate_all_chapters`（接线点） |
| `tools/finance/qual_v8/gates/gate8.py` | 159-232 | `_check_critical_issues`（B1-1 接线） |
| `tools/finance/qual_v8/mode_manager.py` | 18-107 | `QualMode/ModeConfig/ModeManager`（B1-2 扩展） |
| `tools/finance/qual_v8/workflow.py` | 181 | 熔断 threshold=3（阶段 A 改 2） |
| 同上 | 222-223 | `qual_mode` 默认 shadow（B1-2 翻转） |
| 同上 | 350-359 | `critical_gates={0,2,4,8}` enforce 阻断（B1-2 分级化） |
| `tools/finance/workflow.py` | 476 | `_CHAPTER_WRITE_ORDER=[1..9]`（B1-3 扩至含 0/10） |
| 同上 | 1407-1486 | `_audit_and_fix`（B1-3/B4-4 legacy 覆盖） |
| 同上 | 1755-1799 | `_build_decision_prompt`（B4-5 锚点+元裁决注入） |
| 同上 | 2044-2192 | `extract_dcf_params`（B2a-3/B5-1 改造） |
| 同上 | 2530-2538 | legacy `extract_facts` 调用（B2b-1/B3 改造） |
| `tools/finance/fact_extractor.py` | 29-128 | 数据类（B3 增 FactSourceRef） |
| 同上 | 352-417 | `normalize_units`（B5-2 只标不改） |
| 同上 | 432-474 | `cross_validate_with_wind`（B2b-2 仲裁扩展） |
| 同上 | 481-538 | `EXTRACTION_PROMPT`（B2b-1 删财务块/B3-4 防杜撰） |
| 同上 | 626-665 | `_calculate_unit_economics`（B4-2 删 50% 默认） |
| 同上 | 667-790 | `extract_facts`（B3 多财年入口） |
| 同上 | 793-808 | `_inject_fiscal_year_instruction`（B3 页码约束） |
| 同上 | 815-878 | `_merge_chunk_data`（B3-3 冲突仲裁） |
| 同上 | 885-973 | `format_facts_as_context`（B2b-1 财务表改 Wind 源） |
| `tools/finance/canonical.py` | 16-23 | `CANONICAL_FIELDS`（B5-1 扩展） |
| 同上 | 29-67 | `ALIASES`（B5-1 扩展） |
| 同上 | 132-157 | `get_series/latest_value`（复用） |
| `tools/finance/valuation_engine.py` | 102-113 | 可比常量表（B4-6 删除） |
| 同上 | 120-271 | `compute_dcf`（B2a-3 改造） |
| 同上 | 318-365 | `build_comparable_analysis`（B4-6 数据化） |
| 同上 | 372-405 | `derive_target_prices`（B2a-3 补 PS/DCF 不可用分支） |
| 同上 | 412-494 | `compute_full_valuation`（B2a-3 降级链） |
| `tools/finance/quality_enhancer.py` | 45-58 | `enhance_report_quality` 签名（B2a-1 改造） |
| 同上 | 162-239 | Stage 4 估值（B2a-4 目标价注入） |
| 同上 | 241-280 | Stage 5 CAPM（B2a-3 去硬编码） |
| `tools/finance/data_repair.py` | 213-265 | `fix_source_annotations`（B2b-3） |
| 同上 | 575 | `_build_correct_values`（B2b-3 canonicalize） |
| `tools/finance/quality/peer_comparison.py` | 18-94 | `PeerCompany/create_sf_express_peers`（B4-6 重写） |
| `tools/finance/qual_v8/gates/gate0.py` | 45,57 | `wind_coverage threshold=0.95`（B1-2 分级） |
| `tools/finance/qual_v8/gates/gate1.py` | 15-21,55 | `_FACT_FIELD_MAP/required_fields`（B2b-1 改 Wind 源） |
| `tools/finance/qual_v8/gates/gate2.py` | 48-55 | DCF 参数范围（B2a-3 fail-fast） |
| `tools/finance/qual_v8/gates/gate6.py` | 16-22,247-274 | 评级映射/后验（B4-5 合并开发） |
| `tools/finance/quality/review_repair_loop.py` | 299-319 | Wind 锚点注入（B4-4 提公共函数） |
| `tools/finance/qual_v8/adapters.py` | 115-128 | `industry_for`（B4-3 动态化） |
| `assemble_wind_data.py` | 86-107 | quote/valuation 组装（B2a-1 依赖） |
| `run_xpev_full.py` | 42-129 | `fetch_multi_annuals`（B3-1 分组提取接线） |

---

## 1. B1 工作包：财年语义代码化 + 分级阻断 + 审计 11 章

### 1.1 B1-1 章节级当期财年语义（合并扩展 check_fiscal）

**现状**：
- `numeric_guard.py:59` `FISCAL_STRICT_CHAPTERS={4,5}`；`check_fiscal`（214-244）只做**单条启发式**：`prior_refs and not latest_refs → fail`，且不接线 Gate8。
- `data_anchor.py:152-181` `validate_chapter_any_fy`：命中任一财年即通过（无当期语义），docstring 明确其保护 ch6/ch7 合法历史引用（防止修复回滚）。
- `gate8.py:177` → `validate_all_chapters` 走 any-fy，无当期断言。

**修正设计（综合审议 B1-1 统一规则）**：**当期锚断言（阻断）全章节适用 + 历史引用上下文豁免（仅对比/趋势语境且强制 FY 标注，缺失→warning 可升级）+ 章节调参（ch5/7 从严、ch6/4 放行标注历史）**；**合并扩展 check_fiscal**（吸收其现有启发式），**不删 any-fy**（保留为对比层）。

#### 修正代码（`tools/finance/quality/numeric_guard.py`）

```python
# ---- 替换 59 行 FISCAL_STRICT_CHAPTERS ----
FISCAL_POLICY_CURRENT = "current"        # 当期断言：缺 latest 当期引用 → 阻断
FISCAL_POLICY_COMPARISON = "comparison"  # 对比豁免：历史引用须带 FY 标注/对比语境，缺失 → warning 可升级

# 章节级财年策略（综合审议：#3+#4 合并——当期锚全章节 + 章节调参）
FISCAL_CHAPTER_POLICY: dict[int, str] = {
    5: FISCAL_POLICY_CURRENT,      # 经营表现：从严（验收：ch5 写 FY2024 当期 → Gate8 fail）
    7: FISCAL_POLICY_CURRENT,      # 估值：当期锚 + DCF 程序输出
    4: FISCAL_POLICY_COMPARISON,   # 最近变化：YoY 对比语境放行（强制 FY 标注）
    6: FISCAL_POLICY_COMPARISON,   # 财务分析：三财年表放行（强制 FY 标注）
}
FISCAL_DEFAULT_POLICY = FISCAL_POLICY_CURRENT  # 1/2/3/8/9/0/10 默认当期断言

# 历史引用豁免上下文（对比/趋势/显式 FY 标注）
FISCAL_CONTEXT_EXEMPT = [
    r"同比|环比|较上年|上年同期|对比|历史|上一年|上年度|前值|趋势|近三年|近3年|三年",
    r"FY\s?\d{4}",                 # 显式 FY 标注
    r"(?<!\d)\d{4}[年财]度?",      # 显式年度标注（带年份即视为已标注）
]
```

**新签名（check_fiscal 扩展）**：

```python
def check_fiscal(
    self,
    chapter_num: int,
    content: str,
    wind_data: dict,
    severity: str = "critical",                     # critical=阻断 / warning=提示（B1-2 分级）
    policy_map: Optional[dict[int, str]] = None,    # 默认 FISCAL_CHAPTER_POLICY
) -> GateResult:
    """闸门3：章节级当期财年语义（两级判定）
    一级·当期断言（current 策略章节）：prior 引用且无 latest 当期引用且无对比语境 → 阻断
    二级·历史引用豁免（全章节）：prior 引用缺 FY 标注/对比语境 → severity 级提示（可升级）
    """
```

**伪代码**：

```
labels = _year_labels["财年"] or []
if not labels: return result(通过，无锚点)
latest, prior = labels[-1], labels[-1] - 1
policy = (policy_map or FISCAL_CHAPTER_POLICY).get(chapter_num, FISCAL_DEFAULT_POLICY)

prior_refs  = findall(f"{prior}[年财]度?|FY{prior}")          # 历史财年引用
latest_refs = findall(f"{latest}[年财]度?|FY{latest}")        # 当期引用

# ---- 一级：当期断言 ----
if policy == CURRENT:
    if prior_refs and not latest_refs:
        ctx_joined = content 前后各 60 字
        if not any(re.search(p, ctx_joined) for p in FISCAL_CONTEXT_EXEMPT):
            violation(gate="fiscal", severity="critical",
                      message=f"财年错位：本章 {len(prior_refs)} 处引用 FY{prior} 且无 FY{latest} 当期数据，"
                              f"须以 FY{latest} 为当期（FY{prior} 仅可作对比/历史）")

# ---- 二级：历史引用豁免（全章节，含 comparison 策略章）----
for m in prior_refs:
    ctx = content[max(0, m.start()-30):m.end()+30]
    if not any(re.search(p, ctx) for p in FISCAL_CONTEXT_EXEMPT):
        result.warnings.append(f"历史引用 FY{prior} 缺少对比/FY 标注（第{chapter_num}章）——"
                               f"建议标注'对比/上年'或显式 FY，缺失将按 {severity} 处理")
        if severity == "critical":
            result.violations.append(GateViolation(gate="fiscal", chapter=chapter_num,
                message=f"历史引用 FY{prior} 无对比/FY 标注（第{chapter_num}章）", severity="critical"))

# 兼容旧启发式：FISCAL_STRICT_CHAPTERS 行为由 policy=current + 一级判定完全覆盖
return result
```

**接线 Gate8**（`tools/finance/qual_v8/gates/gate8.py` `_check_critical_issues`，约 159-232 行，追加在第 1 步数字校验之后）：

```python
# 1b. 章节级当期财年语义（B1-1；severity 由 qual_mode 决定：enforce→critical，shadow/soft→warning）
try:
    from ...quality.numeric_guard import NumericGuard, FISCAL_CHAPTER_POLICY
    mode = str(context.get("qual_mode", "shadow")).lower()
    fiscal_severity = "critical" if mode == "enforce" else "warning"
    guard = NumericGuard()
    for ch_num, ch_content in (chapters or {}).items():
        fr = guard.check_fiscal(ch_num, ch_content, wind_data,
                                severity=fiscal_severity,
                                policy_map=FISCAL_CHAPTER_POLICY)
        for v in fr.violations:
            critical_found.append(f"财年语义: {v.message}")
        for w in fr.warnings:
            warnings.append(f"财年语义(warning): {w}")
except Exception as e:
    logger.warning(f"Gate8 财年语义校验异常: {e}")
```

**any-fy 保留为对比层**：`data_anchor.py:152-181` 与 `CrossChapterValidator.validate_all_chapters`（331-348）**不改动**——其职责变为"跨章数字与任一财年锚点一致"（对比层）；当期语义由新 check_fiscal 承担。两者互补，不冲突。

**测试**（回归单测，见 §8 B1-1 组）：
- ch5 写 FY2024 当期、无 FY2025、无对比语境 → fail（阻断）
- ch6 引用 FY2024 总资产 827.06 亿（any-fy 保护场景）→ 通过（不误判、不回滚）
- ch4 YoY 对比含"同比"与 FY 标注 → 通过
- ch7 引用 FY2024 历史 PE 带"FY2024"标注 → 通过；不带标注 → warning
- 无 `_year_labels` 锚点 → 通过（跳过）

**副作用**：`FISCAL_STRICT_CHAPTERS` 删除后，需全库 grep 确认无其他引用（现仅 check_fiscal:221 使用）。`check_all`（282-306）内 `check_fiscal` 调用不变（默认参数兼容）。

### 1.2 B1-2 分级阻断（mode_manager 扩展）

**现状**：
- `mode_manager.py:40-68` 三档只区分 `supervisor_blocking`；`workflow.py:350-359` `critical_gates={0,2,4,8}` 一刀切 enforce。
- 风险（综合审议 §修改2）：Gate0 coverage≥0.95 严苛 + 熔断 threshold=2 + 全量 enforce = 单字段缺失 → 整线停摆。

**修正设计（分级阻断）**：**Gate8（数据完整性）+ 财年语义检查：enforce；Gate0/2（数据源可用性）：soft/按错误类型分级（Critical 阻断，coverage 小缺降级+warning）**；保留 shadow/soft/enforce 三档；A4 验收通过后翻转默认。

#### 修正代码（`tools/finance/qual_v8/mode_manager.py` 追加）

```python
@dataclass
class GateBlockPolicy:
    """分级阻断策略（B1-2）"""
    gate: int
    block_on_critical: bool = True   # Critical 级错误 → 阻断
    block_on_warning: bool = False   # Warning 级 → 记录+标注，不阻断
    coverage_tolerance: float = 0.05 # Gate0/2 覆盖率小缺（<0.05）→ 降级 warning 而非阻断

GRADED_BLOCK_POLICY: dict[int, GateBlockPolicy] = {
    0: GateBlockPolicy(0, block_on_critical=True,  block_on_warning=False, coverage_tolerance=0.05),
    1: GateBlockPolicy(1, block_on_critical=False, block_on_warning=False),
    2: GateBlockPolicy(2, block_on_critical=True,  block_on_warning=False),
    3: GateBlockPolicy(3, block_on_critical=False, block_on_warning=False),
    4: GateBlockPolicy(4, block_on_critical=False, block_on_warning=False),
    5: GateBlockPolicy(5, block_on_critical=False, block_on_warning=False),
    6: GateBlockPolicy(6, block_on_critical=False, block_on_warning=False),
    7: GateBlockPolicy(7, block_on_critical=False, block_on_warning=False),
    8: GateBlockPolicy(8, block_on_critical=True,  block_on_warning=True),  # 财年/完整性双 enforce
}

# ModeManager 新增方法
def should_block_gate(self, gate_num: int, errors: list[str], warnings: list[str]) -> tuple[bool, str]:
    """分级判定：Gate8 任何错误（含 warning 级财年标注缺失）阻断；
    Gate0/2 仅 Critical 阻断，coverage 小缺降级 warning（错误类型分级用 ErrorClassifier）。"""
    policy = GRADED_BLOCK_POLICY.get(gate_num)
    if policy is None:
        return False, ""
    if self.current_mode == QualMode.SHADOW:
        return False, ""
    if self.current_mode == QualMode.SOFT:
        return (policy.block_on_critical and bool(errors)), "soft:critical"
    # enforce
    if gate_num == 8:
        return bool(errors) or bool(warnings), "enforce:gate8_all"
    if policy.block_on_critical and errors:
        return True, f"enforce:gate{gate_num}_critical"
    return False, ""
```

#### 修正代码（`tools/finance/qual_v8/workflow.py:350-359` 替换）

```python
# enforce 模式：分级阻断（B1-2，替代 critical_gates 一刀切）
from .mode_manager import GRADED_BLOCK_POLICY
if qual_mode == "enforce":
    block, reason = self.mode_manager.should_block_gate(gate_num, result.errors, result.warnings)
    if block:
        self.state_machine.transition_workflow(WorkflowState.FAILED)
        raise ComplianceBlockedException(
            f"Gate {gate_num} 分级阻断({reason}): {result.errors[:3]}"
        )
```

**Gate0 降级**（`gate0.py:45,57` 配套）：`wind_coverage` 从硬 threshold 0.95 改为：`coverage >= 0.95 → pass`；`0.95-0.05 > coverage >= 0.85 → 降级 warning + 报告标注"数据源部分缺失"`；`< 0.85 → Critical 阻断`（错误类型分级由 `core/error_classifier.py` 承接）。

**默认翻转**（A4 验收后）：`mode_manager.py:117` `get_initial_mode()` 的 env 默认 `"shadow"` → `"enforce"`；`workflow.py:223`、`workflow.py:2443` 同步；三个 run 脚本（`run_qual_full.py:135`、`run_xpev_full.py:219`、`run_qual_v8.py:77`）显式传 `qual_mode` 保持三档可选。

**测试**：见 §8 B1-2 组（Gate0 coverage 0.90 → 不阻断 + 标注；Gate8 warning 级财年标注缺失 → enforce 阻断；shadow/soft/enforce 三档矩阵）。

**副作用**：`ModeManager` 需在 `QualWorkflow.__init__` 实例化并挂到 `self.mode_manager`（现 workflow.py 未持实例，仅 workflow_context 使用；新增一个私有实例）。`should_block_gate` 依赖 errors/warnings 已按 Critical/Warning 分类——Gate 结果当前不区分严重级，实施时以 `ErrorClassifier.classify_from_exception` 对 errors 分类，覆盖不了时默认按 Critical 处理（不扩大放行面）。

### 1.3 B1-3 ch0/ch10 纳入审计

**现状**：`workflow.py:476` `_CHAPTER_WRITE_ORDER=[1..9]`；`_audit_and_fix:1454` 按它遍历 → ch0/ch10 不受审。

**修正**：`workflow.py:476` 改为

```python
_CHAPTER_WRITE_ORDER = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]   # 全 11 章（B1-3）
```

并核对 `_audit_and_fix`（1454-1463）超时跳过分支、`_generate_overview_chapter`/`_build_decision_prompt` 的断点恢复逻辑（1827、934 等 `sorted(previous_chapters.keys())` 不依赖该常量，安全）。v8 路径：Gate6 已生成 ch0/ch10（gate6.py:57-66），Gate8 红队已覆盖全文——B1-3 主要补 legacy 路径。

**测试**：legacy `_audit_and_fix` 对 ch0/ch10 产生审计记录；首尾一致性断言（ch0 评级 == ch10 评级）由 Gate6 后验（§6.5）承接。

---

## 2. B2 工作包：估值程序化先行 + 财务 100% Wind

### 2.1 B2a-1 current_price/shares 从 Wind quote 动态取

**现状**：`assemble_wind_data.py:86-98` 已把 `最新价` 组装进 `wind_data["quote"]["最新价"]`（wind_data.json 结构：`{"quote": {...}, "valuation": {...}, "income": ..., "_year_labels": ...}`）。但三个 run 脚本与 quality_enhancer 仍写死 H1-H4。

**修正代码**：

```python
# 新公共函数（放 tools/finance/valuation_engine.py 顶部或 workflow.py）
def resolve_current_price(wind_data: Optional[dict]) -> Optional[float]:
    """从 Wind quote 动态取最新价（删除 21.48/46.52/41.6 硬编码）。

    优先级：quote.最新价 → quote.最新成交价 → valuation.最新价 → valuation.price
    全部缺失 → 返回 None（调用方必须处理：降级链/显式标注，禁止默认常量）。
    """
    if not wind_data:
        return None
    quote = wind_data.get("quote") or {}
    for k in ("最新价", "最新成交价"):
        v = quote.get(k)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    val = wind_data.get("valuation") or {}
    for k in ("最新价", "price"):
        v = val.get(k)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return None
```

- `run_qual_full.py:133`：`"current_price": (wind_data.get("quote") or {}).get("最新价"),`（并加 `if current_price is None: log("[WARN] 无 Wind 报价，估值走降级链")`）
- `run_xpev_full.py:217`、`run_qual_v8.py:75`：同构替换。
- `quality_enhancer.py:45-58` 签名改造：

```python
def enhance_report_quality(
    chapters: dict[int, str],
    financials: dict,
    wind_valuation: Optional[dict] = None,
    wind_data: Optional[dict] = None,          # 新增：含 quote（B2a-1）
    company_name: str = "",
    ticker: str = "",
    shares: Optional[float] = None,            # 原 43.0 默认删除（H12 精神）
    current_price: Optional[float] = None,     # 原 41.6 默认删除（H4）
    fiscal_year: int = 2025,
    llm_caller: Optional[Callable] = None,
    enable_debate: bool = True,
    enable_valuation: bool = True,
    enable_depth: bool = True,
) -> tuple[dict[int, str], QualityEnhancementResult]:
```

Stage 2/4 内：`current_price = current_price if current_price is not None else resolve_current_price(wind_data)`；仍为 None → `upside` 记 `None` + warning（`quality_enhancer.py:207` 的 `if current_price > 0 else 0` 改为 `else None`，禁止伪造 0 上行空间）。`shares` 为 None → Stage 4 估值降级（走 §2.3 链，链内 fail-fast）。

### 2.2 B2a-2 币种断言

**现状**：`numeric_guard.py:249-277 check_currency` 只查 ch7 "元/股"是否缺人民币标注；估值链无统一币种。

**修正代码**（新模块 `tools/finance/quality/currency_guard.py`）：

```python
MARKET_CURRENCY = {"hk": "HKD", "cn": "CNY", "us": "USD"}

def assert_valuation_currency(wind_data: Optional[dict], market: str) -> list[str]:
    """币种断言（B2a-2）：quote/valuation 币种与市场一致；估值链统一币种或显式 fx 标注。

    返回问题列表（空=通过）。
    - 港股：quote 应为 HKD；若财务（人民币）与报价（港元）并存，估值必须显式 fx 标注，
      禁止无标注混用（numeric_guard.check_currency 的 ch7 检查保留并升级为调用本函数）。
    """
    issues = []
    expected = MARKET_CURRENCY.get((market or "").lower())
    if not expected:
        return issues
    quote = (wind_data or {}).get("quote") or {}
    cur = quote.get("币种") or quote.get("currency")
    if cur and cur.upper() != expected:
        issues.append(f"报价币种 {cur} 与市场 {market}（{expected}）不一致")
    # 估值输出契约：valuation_result 必须携带 currency/fx_note
    return issues

def valuation_currency_note(wind_data, market) -> str:
    """估值链显式币种标注（注入 ch7/ch10）：'估值币种：HKD（报价）／财务口径：CNY，FX≈x.xx'"""
```

接线：`extract_dcf_params` 返回增加 `"fx": ...`（B5-1 汇率字段）；`compute_valuation_chain` 输出 `ValuationResult.currency`；`gate5.py:152-199` 注入 ch7 的估值文本带币种标注。**测试**：港股 wind_data 报价无币种字段时 → 默认按 HKD 处理并标注"币种未披露，按市场默认 HKD"；财务人民币+报价港元并存 → fx_note 必填。

### 2.3 B2a-3 DCF 参数专业化 + 降级链（亏损公司 fail-fast）

**现状**：
- `workflow.py:2044-2192 extract_dcf_params`：H11（净负债 0.3 启发式 2165）、H12（shares 默认 1 于 2175）、H13（增长率默认 5%）、H14（CAPM 硬编码 2140-2142）。
- `valuation_engine.py compute_dcf`（120-271）：H16（year=2026+i 于 199）、H17（负营业利润率回填 0.05 于 185/189）、净负债用"年负债合计-现金"近似（246-252，且现金键 `现金及等价物` 不在 canonical）。
- `compute_full_valuation`（412-494）已有降级链注释 `full_dcf → comparable_only → pe_multiple`，但 DCF 失败仅靠异常捕获，**无 FCF≤0 fail-fast**；`derive_target_prices`（372-405）的 DCF 不可用分支只到 PE（亏损公司 EPS≤0 时 PE 无意义）。

**修正代码**（`workflow.py extract_dcf_params` 改造，行号 2044-2192 整体重写为）：

```python
def extract_dcf_params(wind_data: dict, shares: Optional[float] = None,
                       market: str = "hk") -> dict:
    """从 Wind 数据自动提取 DCF 参数（B2a-3/B5-1 版）。

    Returns: {fcf_base, dcf_available, reason, growth_rate, wacc, terminal_growth,
              net_debt, shares, fx, currency, warnings}
      dcf_available=False 且 reason 说明 → 调用方必须走降级链（§2.3 伪代码）。
      禁止：默认股价/默认股本/默认增长率/0.3 启发式净负债。
    """
    from .canonical import get_series, latest_value
    from .quality.wind_missing_field_registry import WindMissingFieldRegistry
    warnings = []
    reg = WindMissingFieldRegistry()

    ocf = latest_value(wind_data, "经营活动现金流量净额", default=None)
    capex = latest_value(wind_data, "购建固定资产、无形资产和其他长期资产支付的现金", default=None)
    if ocf is None or capex is None:
        return {"dcf_available": False, "reason": "现金流字段缺失（OCF/CAPEX）", "warnings": warnings, ...}
    fcf_base = ocf - capex

    # ---- fail-fast：FCF≤0 亏损/投资期（小鹏样本）----
    if fcf_base <= 0:
        return {"dcf_available": False,
                "reason": f"FCF={fcf_base:.2f}亿≤0，DCF 无意义（亏损/投资期），走降级链", ...}

    # ---- 增长率：3 年营收 CAGR，数据不足 → 显式降级原因（H13）----
    rev = [v for v in (get_series(wind_data, "营业收入") or []) if v]
    if len(rev) >= 2 and rev[0] > 0:
        cagr = (rev[-1] / rev[0]) ** (1/(len(rev)-1)) - 1
        growth_rate = max(0.01, min(cagr, 0.15))
    else:
        return {"dcf_available": False, "reason": "营收序列不足，无法计算 CAGR（不静默默认 5%）", ...}

    # ---- WACC：β 动态取（Wind β 或可比中位数），rf/erp 来自 config（H14）----
    beta = resolve_beta(wind_data)          # 新函数：wind beta → peer 中位数 → None
    rf, erp = load_capm_params()            # 新函数：config.yaml 读取，缺省 None
    if beta is None or rf is None or erp is None:
        return {"dcf_available": False, "reason": "CAPM 参数缺失（β/rf/erp）", ...}
    cost_of_equity = rf + beta * erp
    cost_of_debt = load_cost_of_debt() or 0.05   # config，非硬编码
    tax_rate = load_tax_rate() or 0.25
    equity_value = latest_value(wind_data, "年所有者权益合计", default=None)
    total_debt = latest_value(wind_data, "年负债合计", default=None)
    if equity_value is None or total_debt is None:
        return {"dcf_available": False, "reason": "权益/负债字段缺失", ...}
    total_value = equity_value + total_debt
    wacc = (equity_value/total_value*cost_of_equity +
            total_debt/total_value*cost_of_debt*(1-tax_rate))

    # ---- 净负债：B5-1 处置表（H11 删除 0.3 启发式）----
    net_debt = reg.resolve("净负债", wind_data, market)      # None=不可得 → 标注
    if net_debt is None:
        warnings.append("净负债数据缺失（有息负债/现金不可得），DCF 以 EV 口径输出并标注")

    # ---- 总股本：必填（H12）----
    if shares is None or shares <= 0:
        return {"dcf_available": False, "reason": "总股本未提供（禁止默认 1）", ...}

    fcf_projections = [fcf_base * (1 + growth_rate) ** i for i in range(1, 4)]
    return {"fcf_base": fcf_base, "fcf_projections": [round(x,2) for x in fcf_projections],
            "growth_rate": growth_rate, "wacc": wacc, "terminal_growth": 0.03,
            "net_debt": net_debt, "shares": shares, "dcf_available": True,
            "fx": reg.resolve("汇率", wind_data, market), "currency": MARKET_CURRENCY.get(market),
            "warnings": warnings}
```

**估值降级链**（`valuation_engine.py` 新增；`compute_full_valuation` 保持兼容包装）：

```python
def compute_valuation_chain(
    ticker: str, company_name: str, financials: dict, shares: Optional[float],
    current_price: Optional[float], market: str = "hk",
    wind_data: Optional[dict] = None,
    wacc: Optional[float] = None, terminal_growth: float = 0.02,
) -> ValuationResult:
    """估值降级链（B2a-3/B4-6 联动）：
    full_dcf → comparable（PE）→ PS（亏损/PE 无意义）→ 标注不可估值
    亏损公司（FCF≤0 或净利润≤0）DCF fail-fast，不输出无意义目标价。
    """
    result = ValuationResult(ticker=ticker, company_name=company_name)
    result.currency = MARKET_CURRENCY.get((market or "hk").lower(), "")

    dcf_params = extract_dcf_params(financials, shares, market)     # workflow.extract_dcf_params
    np_latest = latest_value(financials, "归母净利润", default=None)

    if dcf_params.get("dcf_available"):
        result.dcf = compute_dcf(financials, shares, wacc=wacc, terminal_growth=terminal_growth)
        if result.dcf.value_per_share and result.dcf.value_per_share > 0:
            result.value_per_share = result.dcf.value_per_share
        else:
            result.degraded, result.degradation_reason = True, "DCF 结果异常，走可比链"
    else:
        result.degraded = True
        result.degradation_reason = dcf_params.get("reason", "DCF 不可用")
        result.warnings.append(f"DCF fail-fast: {result.degradation_reason}")

    # ---- 可比链（B4-6 数据源化：wind_data 动态，禁默认常量表）----
    if result.value_per_share is None:
        peers, medians = build_peer_companies_from_wind(wind_data, market, ticker)   # §6.6
        if medians.get("pe") and np_latest and np_latest > 0 and shares:
            eps = np_latest / shares
            result.value_per_share = medians["pe"] * eps
            result.comparable_median_pe = medians["pe"]
        elif medians.get("ps") and shares and latest_value(financials, "营业收入"):
            rps = latest_value(financials, "营业收入") / shares
            result.value_per_share = medians["ps"] * rps
            result.comparable_median_ps = medians["ps"]
            result.degradation_reason += " → PS（PE 无意义：亏损）"
        else:
            result.warnings.append("可比数据不可用（Wind 缺失），降级'标注不可估值'")

    # ---- 目标价（derive_target_prices 扩展版：PS/DCF 不可用分支完备）----
    targets = derive_target_prices_v2(
        dcf_value=result.value_per_share, comparable_pe=result.comparable_median_pe,
        comparable_ps=result.comparable_median_ps, current_price=current_price,
        eps=eps, revenue_per_share=rps, shares=shares)
    result.target_price_bull, result.target_price_base, result.target_price_bear = \
        targets.get("bull"), targets.get("base"), targets.get("bear")
    if current_price and result.value_per_share:
        result.upside = (result.value_per_share - current_price) / current_price
    return result
```

`derive_target_prices_v2`（替代 372-405）：base 优先 DCF；DCF 不可用 → PE×EPS；PE 不可用（亏损）→ PS×RPS；都不可用 → base=None 且三情景全 None + 标注"目标价不可得"。bull/bear 一律 ±20% base（不再依赖 DCF 才给 bull/bear）。

`compute_dcf`（120-271）改造点：`year = 2026 + i`（199）→ `base_year = latest_fiscal_year(financials) + 1`（新函数 `_latest_fiscal_year`：取 income 序列长度对照 `_year_labels`，无则 None → 标注"预测年份基于最新财年"）；负 EBIT 回填（185/189）→ 直接 `return result`（value_per_share=None）+ warning（由链上 fail-fast 承接）；净负债（246-252）改走 B5-1 registry。

**接线**：
- `gate2.py:48-55`：`dcf_params["dcf_available"]==False` 时 Gate2 不再因"FCF 非零"判 fail（fcf 缺失属数据源问题 → Gate0 分级），改记 `details["dcf_failfast_reason"]` 并传 context 供 Gate5/6 降级。
- `quality_enhancer.py` Stage 4（162-239）：`UnifiedValuation` 分支删除 `wacc=0.081` 硬编码（H15），assumptions 由 `extract_dcf_params` 结果注入；`chapters[7] += val_text`（229-235）改为替换/追加含币种标注与降级原因的估值块（B2a-4）。
- Stage 5（241-280）：CAPM 参数（248-254）改从 `extract_dcf_params`/config 取（H14）。

**测试**：小鹏（FCF≤0）→ `dcf_available=False`、reason 明确、目标价走 PS 分支或"不可估值"标注、不输出无意义 DCF 目标价；阅文（FCF>0）→ full_dcf 正常；wind_data 缺 OCF → fail-fast 原因链完整。

### 2.4 B2a-4 目标价程序计算注入 ch7/ch10

**现状**：ch7 注入已存在（quality_enhancer.py:229-235、gate5.py:152-199）；ch10 无程序化估值锚。

**修正**：
1. `gate5.py`（或 quality_enhancer Stage 4）统一调用 `compute_valuation_chain`，把 `ValuationResult`（含 currency/fx/degradation_reason）写入 `context["valuation_result"]`。
2. `workflow.py:_build_decision_prompt`（1755-1799）增加 `valuation_block` 参数（§6.5 一并注入）；ch10 prompt 内嵌：

```
## 程序化估值锚（唯一真源，禁止改写）
- 目标价（牛/基/熊）：{bull}/{base}/{bear} 元（{currency}）
- 估值方法：{full_dcf|comparable|PS|不可估值}，降级原因：{reason}
- 当前价：{current_price} {currency}（Wind quote，日期 {asof}）
```

**测试**：报告中目标价与 `context["valuation_result"]` 数值一致（程序输出）；ch10 引用目标价偏差 >20% → Gate6 `target_price_deviation` 后验拦截（gate6.py:43 已存在）。

### 2.5 B2b-1 fact_extractor 移除财务提取（财务 100% Wind）

**现状**：`EXTRACTION_PROMPT`（481-538）含 `financial` 输出块（516-522）与"单位规范"财务条目；`_parse_chunk_response`（541-574）解析 financial；`cross_validate_with_wind`（432-474）比对提取财务 vs Wind（5% 容差）；`format_facts_as_context`（885-912）财务表来自 `facts.financial`；Gate1 必填字段查 `facts.financial`（gate1.py:231-245）；`_verify_company_identity` 硬编码 0772/00772（610）。

**修正设计**：财务数字唯一真源 = Wind canonical；事实表只保留运营/管理/业务。**FinancialFacts dataclass 保留（兼容布局）但不再填充**；删除 prompt 财务块与解析分支。

**修正代码**：
- `EXTRACTION_PROMPT`：删除 `financial` 块（516-522）与规则 3/4 中的财务单位条目；`financial` 字段任何出现 → 提示"财务数据以 Wind 为准，勿提取"。
- `_parse_chunk_response`（551-563）：`for section in ['operational', 'financial', 'management']` → `['operational', 'management']`；financial 残留键 → 丢弃 + warning。
- `format_facts_as_context`（885-912）：财务表改为从 `wind_data` canonical 取（`get_series` 最新值），来源标注 `Wind`；无 wind_data → 财务表整块省略 + "财务数据缺失（Wind 不可用）"标注。**调用签名增加 `wind_data: Optional[dict] = None`**。
- `_verify_company_identity`（610）：`code_found` 用 `ticker_code`、`"0"+ticker_code`、`ticker` 三变体（删除写死的 "0772"/"00772"）。
- `gate1.py`（B2b-1 配套）：
  - `_FACT_FIELD_MAP`（15-21）删除；`required_fields`（55）改为 canonical 键：`["营业收入", "归母净利润", "经营活动现金流量净额", "总资产"]`。
  - `_check_required_fields`（231-245）改查 `get_latest_wind_value(wind_data, canonical)`；无 wind_data → 跳过 + warning（不阻断，Gate0 已分级）。
  - `_check_value_deviation`（247-275）保留（对运营数据与 Wind 无冲突字段自动跳过）。
  - `_facts_to_dict`（278-298）financial 部分删除。
- `_is_facts_empty`（420-429）与 `validate_numerical_ranges`（328-349）中 financial 相关检查删除。

**测试**：事实表 JSON 无 financial 键；Gate1 必填校验在 financial 缺失时仍通过（Wind 有数据）；Wind 缺失时显式 warning 不阻断。

### 2.6 B2b-2 仲裁扩展到全部 canonical 字段（统一容差）

**现状**：`cross_validate_with_wind`（432-474）只比对净利润/营收（5% 容差）；v3.1 数据仲裁在 `_reconcile_facts_with_wind`（1% 容差）但未覆盖全部 canonical 字段；两处容差口径不一致（5% vs 1%）。

**修正**：统一为模块级常量，仲裁扩至全部 canonical 字段。

```python
# 统一容差（B2b-2）：5% = 交叉验证 warning 阈值；1% = 仲裁覆盖阈值；异财年 → 降级
RECONCILE_TOLERANCE = 0.01
CROSS_VALIDATE_WARN_TOLERANCE = 0.05

def arbitrate_facts_with_wind(facts_dict: dict, wind_data: Optional[dict],
                              fiscal_year: Optional[int] = None) -> list[str]:
    """仲裁全部 canonical 字段（B2b-2）：
    仅当 facts_dict 仍有财务键（legacy）或运营键与 Wind 重叠时执行。
    对每个字段：|extract-wind|/|wind| ≤1% → 保留（自洽）；
                >1% 且 ≤5% → Wind 覆盖 + warning 记录；
                >5% → Wind 覆盖 + warning 升级（数据冲突）；
                财年不一致 → 降级"异财年不可比"，标注不覆盖。
    """
    warnings = []
    if not wind_data:
        return warnings
    from .canonical import get_series
    for field, value in (facts_dict.get("financial") or {}).items():
        canonical = {"revenue": "营业收入", "net_profit": "归母净利润",
                     "gross_margin": "毛利率", ...}.get(field)
        if not canonical:
            continue
        series = get_series(wind_data, canonical)
        if not series:
            continue
        wind_latest = series[-1]
        if wind_latest is None:
            continue
        rel = abs(value - wind_latest) / max(abs(wind_latest), 1e-9)
        if rel <= RECONCILE_TOLERANCE:
            continue
        # >1%：Wind 为准（覆盖），按超差幅度记 warning
        level = "warning" if rel <= CROSS_VALIDATE_WARN_TOLERANCE else "critical-warning"
        warnings.append(f"仲裁覆盖: {field} 提取={value} Wind={wind_latest} (rel={rel:.1%} [{level}])")
    return warnings
```

接线：`extract_facts` 步骤 5（778-781）改调 `arbitrate_facts_with_wind`；`format_facts_as_context` 输出的财务数字一律为 Wind canonical 值（源头统一，1% 仲裁自然满足）。

**测试**：构造提取值 100 / Wind 99.5（0.5%→保留）；100 vs 103（3%→覆盖+warning）；100 vs 107（7%→覆盖+升级）；财年错位（提取 FY2024 值 vs Wind FY2025）→ 降级标注。

### 2.7 B2b-3 data_repair 走 canonicalize + 负号正则统一

**现状**：`data_repair.py:213-265 fix_source_annotations` 硬编码 `wrong_years=[2023,2024,2026]`（230）与 `快手`（248）；`_build_correct_values`（575）按原始键取 Wind 值（键契约脆弱）。

**修正代码**：

```python
def fix_source_annotations(report_content: str, fiscal_year: int = 2025,
                           company_name: str = "") -> tuple[str, int]:
    """修复数据来源标注年份（B2b-3 通用化：删除 wrong_years/快手 硬编码）。"""
    fixes = 0
    fixed = report_content
    # 1) 任意"来源：…YYYY年" 且 year != fiscal_year → 替换（含 2023/2024/2026 等一切年份）
    pat = re.compile(rf"(来源[：:][^\n]{{0,20}})(\d{{4}})(年)")
    def _fix_year(m):
        nonlocal fixes
        if int(m.group(2)) != fiscal_year:
            fixes += 1
            return m.group(1) + str(fiscal_year) + m.group(3)
        return m.group(0)
    fixed = pat.sub(_fix_year, fixed)
    # 2) 任意"<公司名>YYYY年年报"（company_name 参数化，不再硬编码'快手'）
    if company_name:
        pat2 = re.compile(rf"({re.escape(company_name)})(\d{{4}})(年年报)")
        fixed = pat2.sub(_fix_year, fixed)
    # 3) "[来源: 财报原文摘要]" → "[来源: FY{fiscal_year} 年报]"（保留）
    ...
    return fixed, fixes

def normalize_negative_signs(text: str) -> tuple[str, list[str]]:
    """负号正则统一（B2b-3）：'净亏损X亿'/'亏损X亿' → 统一为 '-X亿' 形态（与 Wind 符号一致），
    仅当语境为损益科目且无 '-' 时转换；记录每处转换。'净现金' 等非损益不转换。"""
```

`_build_correct_values`（575）：改 `canonicalize(wind_financials)` + `get_series/latest_value` 取正确值；`repair_report` 各修复函数键名一律 canonical（源头单一）。

**测试**：`来源：阅文2023年年报`（fiscal_year=2025）→ `2025`；`快手2024年年报` 且 company_name=快手 → 2025；company_name 为空 → 不误改；`净亏损5.4亿元` → `-5.4亿元`。

---

## 3. B5-1 Wind 缺失字段处置表

**定位**：B2b 的输入清单；新模块 `tools/finance/quality/wind_missing_field_registry.py`（可复用 `quality/wind_field_mapper.py` 的三市场原始码映射）。

**核心数据模型与签名**：

```python
from dataclasses import dataclass, field
from typing import Optional, Literal

@dataclass
class FieldResolution:
    """单字段处置结论（B5-1 三元处置）"""
    canonical: str
    availability: Literal["wind_direct", "derived", "unavailable"]
    value: Optional[float] = None            # wind_direct/derived 成功 → 值
    formula: Optional[str] = None            # derived 的公式+口径说明
    source_keys: tuple = ()                  # Wind 原始/别名键（派生输入键）
    per_market: dict = field(default_factory=dict)  # {"hk": "NET_DEBT", ...}
    annotation: str = ""                     # 报告标注模板（unavailable/部分派生时使用）

class WindMissingFieldRegistry:
    """Wind 缺失字段处置表（B5-1）：
    - 有源 → canonical（wind_direct）
    - 可派生 → 公式+标注（derived；输入键齐备才可派生，缺一 → unavailable）
    - 不可得 → 空缺+标注（unavailable）
    禁止任何启发式回填（如 0.3 倍负债、默认毛利率）。"""
    def resolve(self, canonical: str, wind_data: Optional[dict],
                market: str = "hk") -> Optional[float]: ...
    def resolve_full(self, canonical: str, wind_data, market) -> FieldResolution: ...
    def get_available_fields(self, wind_data, market) -> list[str]: ...
    def format_missing_notes(self, wind_data, market) -> list[str]:
        """报告标注：'有息负债：未披露' 等（注入事实表/报告脚注，禁止静默消失）"""
```

**处置表（首批，路线图 B5-1 明确字段）**：

| canonical | availability | 派生公式/口径 | 源键（Wind/别名） | 标注模板 |
|---|---|---|---|---|
| 营业收入 | wind_direct | — | 年营业总收入 | — |
| 归母净利润 | wind_direct | — | 年归母净利润 | — |
| 经营活动现金流量净额 | wind_direct | — | 年经营活动现金流量净额 | — |
| 资本开支 | wind_direct | — | 购建固定资产…支付的现金 | — |
| 总资产/负债/权益 | wind_direct | — | 年资产总计/年负债合计/年所有者权益合计 | — |
| 有息负债 | wind_direct | —（Wind 有专门字段则直取） | 短期借款/长期借款/一年内到期的非流动负债 | 直取失败 → derived；再失败 → unavailable |
| 有息负债（派生） | derived | 短期借款+长期借款+一年内到期非流动负债（口径：含租赁负债须在公式注明） | 上述三键 | "有息负债=短借+长借+一年内到期（口径：不含租赁）" |
| 现金及现金等价物 | wind_direct | — | 货币资金/现金及现金等价物 | — |
| 净负债 | derived | 有息负债 − 现金及现金等价物 | 上两行 | 任一无源 → None+"净负债未披露，估值以 EV 口径并标注" |
| ΔWC（净营运资本变动） | derived | ΔWC = Δ(流动资产−流动负债)，期末−期初 | 流动资产合计/流动负债合计（期初期末） | 缺期初 → unavailable+"ΔWC 未披露，FCF 以 CFO−CAPEX 口径" |
| 汇率 | wind_direct | —（Wind FX 行情） | Wind FX | "汇率未披露，估值以报价币种（HKD）为准" |
| 每股股息 | wind_direct | —（Wind DPS） | Wind DPS | "每股股息未披露"（**禁止** 股息总额/股本 启发式） |
| FCF | derived | 经营现金流 − 资本开支（CFO 口径） | 上两行 | 任一缺失 → None + 标注 |

**接线**：
- `extract_dcf_params`（§2.3）：net_debt/汇率/FCF 全走 registry（删除 workflow.py:2159-2169 的 0.3 启发式与"总负债近似"）。
- `compute_dcf`（valuation_engine.py:246-252）：现金/负债走 registry。
- `assemble_wind_data.py:106`：`_year_labels` 从 Wind 响应动态解析（H20）；`FIELD_MAP` 增补 B5-1 源键。
- `canonical.py` 扩展（B5-1 契约）：

```python
CANONICAL_FIELDS = frozenset({
    "营业收入", "营业利润", "归母净利润", "净利润",
    "总资产", "归母净资产", "年负债合计", "年所有者权益合计",
    "经营活动现金流量净额", "购建固定资产、无形资产和其他长期资产支付的现金",
    # B5-1 新增
    "有息负债", "现金及现金等价物", "货币资金",
    "短期借款", "长期借款", "一年内到期的非流动负债",
    "流动资产合计", "流动负债合计",
    "汇率", "每股股息",
})
# ALIASES 对应追加（如 "年有息负债":"有息负债"、"现金及现金等价物_TTM":"现金及现金等价物" 等，
# 全部单向别名 → canonical，遵守 canonicalize_table 现有合并逻辑）
```

**测试**：有息负债三键齐备 → derived 值正确；缺"一年内到期" → unavailable + 标注；net_debt 无源 → None 且报告含"未披露"标注；任何字段**不出现**启发式默认值（单测断言 registry 永不返回猜测值）。

---

## 4. B3 工作包：事实表多财年化 + 可复核

### 4.1 B3-1 按年报分组提取 → 程序化合并

**现状**：`run_xpev_full.py:42-129 fetch_multi_annuals` 已下载多份年报，但只把**最新财年** sections 喂 fact_extractor（114 行），旧年只存 `metadata["prior_years"]`（115-117，无消费点）。`extract_facts`（667）单财年入口。

**修正设计**：每份年报独立 `extract_facts`（各自 fiscal_year）→ 3 张单年表**程序化合并**（不经过 LLM）；fetch 3 份年报成本计入预算（v3.1 预算 200，超限转惰性分财年提取）。

**新签名（多财年 extract_facts）**：

```python
@dataclass
class MultiYearFacts:
    """多财年事实表（B3-1）：程序化合并结果"""
    company_name: str = ""
    ticker: str = ""
    per_fy: dict[int, "ExtractedFacts"] = field(default_factory=dict)      # {fy: 单年事实表}
    latest_fy: int = 0
    merged_series: dict[str, dict[int, Optional[float]]] = field(default_factory=dict)
    # 形如 {"dau": {2024: 4.1, 2025: 5.0}}——纯程序化，不经过 LLM
    merge_warnings: list[str] = field(default_factory=list)

def extract_facts_multi_year(
    reports: dict[int, dict[str, str]],      # {fiscal_year: sections}（≤3 份）
    company_name: str,
    ticker: str,
    market: str,
    llm_caller: Callable[[str, str], str],
    wind_data: Optional[dict] = None,
    max_chars: int = 300000,
    chunk_size: int = 30000,
    budget_cap: int = 200,                   # v3.1 预算联动（含 3 份 fetch 成本）
    lazy: bool = False,                      # 超限 → 惰性分财年（只取最新）
) -> MultiYearFacts:
    """按年报份数分组提取：每份独立 fiscal_year，最后 merge_multi_year_facts 程序化合并。"""

def merge_multi_year_facts(per_fy: dict[int, "ExtractedFacts"]) -> MultiYearFacts:
    """纯程序化合并（B3-1）：不调用 LLM。
    merged_series[metric][fy] = 值；同一 metric 跨年冲突（同 fy 双值已在单年层仲裁）→ 记 merge_warnings。"""
```

**伪代码**（`extract_facts_multi_year`）：

```
budget = 0
per_fy = {}
for fy in sorted(reports):
    if budget >= budget_cap:
        if lazy: break                       # 惰性：停止更早财年
        else: raise BudgetExceeded("多财年提取超预算 200，转惰性分财年")
    facts = extract_facts(sections=reports[fy], ..., fiscal_year=fy, wind_data=wind_data)
    budget += facts.meta.llm_calls
    per_fy[fy] = facts
return merge_multi_year_facts(per_fy)
```

接线：`run_xpev_full.py` 把 `fetch_multi_annuals` 返回值改造为 `{"reports": {fy: sections}, ...}`（每份都进提取，不再丢弃 prior_years）；legacy `workflow.py:2530-2538` 与 `gate1.py:216-226` 保持单财年调用（兼容），多财年入口仅由 run 脚本/显式调用启用。

**测试**：3 份年报 → `per_fy` 含 3 键、`merged_series` 三财年列；budget 超 200 → 惰性截断 + warning；`merge_multi_year_facts` 零 LLM 调用（单测注入计数 caller）。

### 4.2 B3-2 页码字段（null + unverified）

**现状**：事实表无页码；`_inject_fiscal_year_instruction`（793-808）无页码约束。

**修正**（fact_extractor.py 数据层）：

```python
@dataclass
class FactSourceRef:
    """事实行来源引用（B3-2/B4-1 复核锚）"""
    page: Optional[int] = None        # MinerU 章节 page 元数据；不可得 → None
    page_verified: bool = False       # 仅当 sections 结构带 page 元数据且正则校验通过 → True
    quote: str = ""                   # 原文片段（≤80 字）
    confidence: float = 0.5           # 原文复核命中 → 0.9+；未命中 → ≤0.3
    arbitrated: bool = False          # 是否经批次/Wind 仲裁
    fiscal_year: Optional[int] = None
    comparison_period: bool = False   # 对比期数据（不得放入当期字段）
```

- **前置 MinerU 结构验证**：新函数 `verify_page_metadata(sections) -> tuple[bool, dict[int,int]]`——检查 sections 是否携带 `page` 键/元数据；无 → 全部 `page=None, page_verified=False`。
- `EXTRACTION_PROMPT` 增补（B3-2/B3-4）：

```
## 页码与原文约束（必须遵守）
- 页码字段（page）只允许从结构元数据填充；**禁止 LLM 猜测/编造页码**。
- 每个数据点必须附 ≤80 字原文片段（quote）；无法引用原文 → 填 null 并标 confidence=low。
- **宁可缺失不可杜撰**：原文未明确写出 → null，禁止用前批/历史值补当前批。
- 对比期（上年）数据 → comparison_period=true，不得写入当期字段。
```

- `_parse_chunk_response`：LLM 输出含 `page` 键 → 忽略 + warning（防编造）；`quote` 超 80 字截断。

**测试**：sections 无 page 元数据 → 全部 null+unverified；LLM 输出 page=42 → 被丢弃 + warning；quote 超长截断 ≤80。

### 4.3 B3-3 批次一致性仲裁（_merge_chunk_data）

**现状**：`_merge_chunk_data`（815-878）"后批次覆盖"（833/843）**静默覆盖**同字段冲突值。

**修正**（替换 operational/financial 合并循环内 826-843 覆盖逻辑）：

```python
def _merge_value(current, new, key, warnings, section):
    """批次冲突仲裁（B3-3）：同值保留；≤1% 保留 current（自洽）；
    >1% → 保留 confidence/出现次数高者，另一值写入 warnings（不静默覆盖）。"""
    if current is None:
        return new
    if current == new:
        return current
    rel = abs(new - current) / max(abs(current), 1e-9)
    if rel <= RECONCILE_TOLERANCE:           # 1%（复用 §2.6 常量）
        return current
    warnings.append(f"{section}.{key} 批次冲突: {current} vs {new} (rel={rel:.1%})，"
                    f"保留出现次数多者，请人工复核")
    return new                               # 默认保留后值但必须已记 warning
```

**测试**：两批 4.10/4.11（<1%）→ 保留前值无 warning；4.1 vs 4.9（>1%）→ 记 warning 不静默；`facts.meta.warnings` 含冲突记录。

---

## 5. B5-2 数值转写归一预处理器

**定位**：拦截"4.102亿→410.2亿"类单位错误于转写阶段；承接 `normalize_units`"只标不改"；与 B4-1 原文正则复核配对。

**新模块 `tools/finance/quality/number_transcription_normalizer.py`**：

```python
@dataclass
class NormalizedNumber:
    raw: str                       # 原文片段（含上下文）
    value: float                   # 统一为亿/元/% 基数值
    unit: str                      # "亿"/"万元"/"元"/"港元"/"美元"/"%"
    currency: str                  # CNY/HKD/USD/""（单位判定）
    qualifier: str                 # "精确"/"约"/"以上"/"以下"/"区间下界"/"区间上界"
    span: tuple[int, int]          # 原文位置（供复核定位）

@dataclass
class MatchResult:
    matched: bool
    normalized: Optional[NormalizedNumber]
    reason: str = ""               # 未命中原因（单位不符/千分位/语境）

class NumberTranscriptionNormalizer:
    """数值转写归一预处理器（B5-2）：
    约/以上/区间/千分位/单位归一 → 供原文正则复核配对。"""
    def extract(self, text: str) -> list[NormalizedNumber]:
        """确定性归一（不调用 LLM）：
        - 千分位：'1,598,070.7' → 1598070.7
        - 单位：万亿→亿×10000；万元→亿÷10000；元→亿÷1e8；港元/美元 → 值不变+currency 标注
        - 修饰：约/约合/大约 → qualifier='约'（保留原值不四舍五入）
                以上/以下/不低于/不超过 → 边界 qualifier
                'X-Y亿'/'X到Y亿' → 两个 NormalizedNumber（区间上下界）
        - 正负：'净亏损5.4亿' → 值 -5.4（配合 data_repair.normalize_negative_signs）"""
    def match_extracted(self, value: float, unit: str, source_text: str,
                        tolerance: float = 0.01) -> MatchResult:
        """提取值复核（B4-1 配对）：在 source_text 中找同量级归一数字；
        命中（含约/区间边界）→ matched=True；未命中 → matched=False（confidence=low）。"""
```

**规则要点（伪代码）**：

```
extract(text):
  for m in 千分位数字模式 (\d[\d,]*\.?\d*): 去逗号
  for m in 单位模式 (数字)(万亿|亿元|亿|万元|万|元|港元|港币|美元): 统一基数值
  for m in 修饰模式: 约(?=数字) → qualifier=约；数字(以上|以下|不低于|不超过) → 边界
  for m in 区间模式: (\d+\.?\d*)[-~至到](\d+\.?\d*)(单位) → 双 NormalizedNumber
```

**接线**：
1. `fact_extractor._parse_chunk_response`（541-574）：提取值经 `NumberTranscriptionNormalizer.match_extracted(value, unit, chunk_text)` 复核——未命中 → `confidence=low` + warning（不自动改值）。
2. `normalize_units`（352-417）改为**只标不改**：

```python
# B5-2 版 normalize_units：删除自动 ÷100/×100 修正（357-415 各分支），改为：
#   超范围 → 追加 warning "DAU=410.2 超出合理范围[0.01,20]亿，原文待复核（B5-2）"
#            并置 confidence=low；数值原样保留，由下游以原文为准。
```

3. `format_facts_as_context`（885+）：事实表数字带 `confidence`/`arbitrated` 标注列。

**测试**：`4.102亿`（原文）→ extract 得 4.102；提取值 410.2 → match_extracted 未命中（置信低）；`约5.4亿`、`3-5亿`、`1,598,070.7万元`、`30港元` 各归一正确；normalize_units 不再改值只标注。

---

## 6. B4 工作包：运营数据验证链 + 行业/结论修正

### 6.1 B4-1 运营数据验证链

**新模块 `tools/finance/quality/operational_validator.py`**（或并入 fact_extractor）：

```python
@dataclass
class OperationalValidationResult:
    passed: bool
    iron_violations: list[str]      # 结构铁律 → 阻断（仅此级阻断）
    warnings: list[str]             # 交叉披露/钩稽 → warning 级
    confidence: dict[str, float]    # {metric: confidence}

# 钩稽规则（warning 级）+ 口径例外白名单
DERIVED_RECONCILIATIONS = [
    {"name": "LTV≈月ARPU×毛利率×生命周期",
     "check": lambda f: f.ltv is None or abs(f.ltv - f.arpu/12*f.gross_margin*f.user_lifetime)
              / max(abs(f.ltv), 1e-9) <= 0.20,
     "exempt": ["non-IFRS调整", "一次性项目", "口径差异"]},     # 命中豁免词 → 不报
    {"name": "GMV增速≈电商收入增速（同口径）", "check": ..., "exempt": [...]},
    {"name": "CAC×新增用户≈营销费用", "check": ..., "exempt": [...]},
]
# 结构铁律（仅此级阻断）
IRON_RULES = [
    ("MAU", ">=", "DAU"),
    ("付费用户", "<=", "MAU"),
    ("毛利率", "in", "[0, 100]"),
]

def validate_operational_chain(
    facts: "ExtractedFacts",
    source_texts: dict[str, str],          # 各章节原文（B5-2 复核配对）
) -> OperationalValidationResult:
    """1) 原文正则复核（B5-2 match_extracted）→ confidence
       2) 多批次一致性（B3-3 已仲裁）→ 复核 warnings
       3) 交叉披露：同指标不同章节数值 >5% 差 → warning
       4) 派生钩稽：DERIVED_RECONCILIATIONS（warning 级+白名单）
       5) 结构铁律：IRON_RULES 违规 → iron_violations（阻断）"""
```

接线：`extract_facts` 末尾（790 前）调用并把结果写入 `facts.meta`；报告附"运营数据验证链"小节。

**测试**：LTV 钩稽 20% 内 → 通过；含"non-IFRS调整"上下文 → 豁免；MAU<DAU → 阻断；提取值原文未命中 → confidence=low。

### 6.2 B4-2 删除默认值填充 + normalize_units 只标不改

- `_calculate_unit_economics`（626-665）：删除 632-637 的 `op.gross_margin = 0.5`（H8）；毛利率缺口 → `op.gross_margin=None` + assumptions 记"毛利率未披露（不填充默认）"。LTV/CAC 计算依赖 None → 跳过并标注。
- `normalize_units`（352-417）：见 §5 接线 2（只标不改）。

**测试**：无毛利率年报 → 事实表毛利率 null + 标注"未披露"，无 50% 出现。

### 6.3 B4-3 行业判定动态化 + ch2 数据年份标注

**现状**：`qual_v8/adapters.py:115-128 industry_for` 关键词白名单（"综合"兜底）；legacy `workflow.py:2933-2939` 硬编码（H21）；`quality/review_repair_loop.py:37` 默认 `industry="新能源汽车"`。

**修正**：
1. `workflow.py:2933-2939` 删除硬编码分支 → `from .qual_v8.adapters import industry_for; industry = industry_for(company_name)`。
2. `quality/review_repair_loop.py:37` 默认改 `industry: Optional[str] = None`；None 且无法推导 → 降级"标注或年份未知"（ch2 数据年份标注缺失时强制降级）。
3. `adapters.industry_for` 增强：优先查 Wind 行业字段（`wind_data["valuation"]` 或 quote 的行业/证监会行业），次选关键词，均无 → `"综合"` + 标注"行业为兜底判定"。

**测试**：阅文（关键词命中"数字内容"）不落"新能源汽车"；Wind 行业字段优先；无任何线索 → "综合"+标注。

### 6.4 B4-4 修复循环锚点注入（转验收收尾）

**现状（已验收）**：`quality/review_repair_loop.py:299-319` 已注入 Wind 锚点表；v8 gate4 已接线（gate4.py:257-258）。

**收尾两项**：
1. **提公共函数**：把 299-319 的锚点表构建提取为 `tools/finance/quality/wind_anchor.py::build_wind_anchor_table(wind_data) -> str`，`review_repair_loop`、`gate4`、`_build_decision_prompt`（§6.5）三处复用（消除复制）。
2. **事实表注入 + legacy 覆盖**：修复 prompt 追加 `format_facts_as_context(facts, wind_data)`（B2b-1 改造后含 Wind 财务表+运营复核标注）；legacy 路径 `quality/v3/review_repair_loop.py` 与 `workflow.py:1407 _audit_and_fix`（`semantic_audit`/`repair_chapter` 的 prompt）同样注入锚点表。

**测试**：修复 prompt 含"Wind 验证锚点"与"事实表"两节；legacy 修复调用带锚点（对比修复前后文本）。

### 6.5 B4-5 ch10 锚点注入 + 元裁决规则（与 Gate6 合并开发）

**现状**：`_build_decision_prompt`（workflow.py:1755-1799）无锚点注入、无评级规则、无否决联动；Gate6 后验已有 `RATING_VALUATION_MAPPING`（gate6.py:16-22）与 `_check_rating_valuation_consistency`（247-274）。

**修正（前置+后验双保险）**：

```python
# workflow.py:_build_decision_prompt 新签名
def _build_decision_prompt(
    chapters: dict[int, str],
    ctx: DataContext,
    wind_anchor: str = "",           # build_wind_anchor_table(wind_data)（§6.4）
    valuation_block: str = "",       # §2.4 程序化估值锚
    rating_rules: str = "",          # RATING_VALUATION_MAPPING 文本化
    veto_notes: str = "",            # 否决项联动规则
) -> str:
    """构建决策章提示（B4-5）：
    注入 Wind 锚点表 + 程序化目标价 + 评级-估值映射规则 + 否决项联动；
    评级=规则输出（可人工 override 并留痕，非绝对禁止）。"""
```

prompt 增补段（追加在"输出要求"前）：

```
## 数据锚点（唯一真源）
{wind_anchor}

## 程序化估值锚（禁止改写数值）
{valuation_block}

## 评级规则（元裁决）
评级必须与程序化目标价一致：
- 目标价/现价 ≥1.30 → 买入；1.15-1.30 → 增持；0.85-1.15 → 中性；0.70-0.85 → 减持；≤0.70 → 卖出
- **否决项联动**：若第9章风险/否决项未消除（{veto_notes}），评级不得为买入/增持
- 人工 override 必须显式标注"override+理由"（留痕）
```

`gate6.py` 合并开发（后验强化，246-274 之后追加）：

```python
def _check_rating_veto(self, chapters, context) -> Dict[str, Any]:
    """否决项联动（B4-5 新开发点）：Gate6/9 否决项未消除 → 评级不得为买入/增持"""
    veto = context.get("veto_issues") or context.get("gate_9_vetoes") or []
    rating = self._extract_rating(chapters)
    errors = []
    if rating in ("买入", "增持") and veto:
        errors.append(f"否决项未消除（{len(veto)} 项），评级'{rating}'被规则否决：{veto[:2]}")
    return {"passed": len(errors) == 0, "errors": errors}
```

接线：`gate6.execute` 的 `_generate_decision_overview` 前调用 `_build_decision_prompt(..., wind_anchor=..., valuation_block=..., rating_rules=..., veto_notes=...)`；后验 `_check_rating_valuation_consistency` 与 `_check_rating_veto` 均纳入 errors。

**测试**：ch10 写"买入"但目标价/现价=1.0（中性区间）→ Gate6 fail；否决项存在 + 买入 → fail；override 标注 → 通过（留痕）。

### 6.6 B4-6 可比公司矩阵重写 + 数据源化

**现状**：`peer_comparison.py` 顺丰专版（49-94）+ 错误 ticker（59）+ 物流字段（37-38）；`valuation_engine.py` 快手专版常量表（102-113）。

**修正（重写+数据源化）**：

```python
# quality/peer_comparison.py 重写（删除 create_sf_express_peers 全部硬编码）
@dataclass
class PeerCompany:
    """同行公司（B4-6：删除物流专有字段 express_volume/revenue_per_piece）"""
    name: str
    ticker: str
    market: str
    revenue: Optional[float] = None
    revenue_growth: Optional[float] = None
    net_income: Optional[float] = None
    net_margin: Optional[float] = None
    roe: Optional[float] = None
    pe: Optional[float] = None
    pb: Optional[float] = None
    ps: Optional[float] = None
    # 行业扩展字段由子类/扩展 dict 承载（如物流件量），不进基类

@dataclass
class PeerData:
    ok: bool
    target: PeerCompany
    peers: list[PeerCompany] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    note: str = ""                                   # 降级/排除说明

def build_peer_companies(
    wind_data: Optional[dict], market: str, target_ticker: str,
    peer_tickers: Optional[list[str]] = None,        # 显式可比清单（可配）
    shareholding: Optional[dict] = None,             # {peer_ticker: 持股比例}（B4-6 排除用）
) -> PeerData:
    """可比公司数据源化（B4-6）：
    1) 前置 Wind 可用性验证：可比 quote/财务覆盖（validate_peer_availability）
    2) 数据全部来自 Wind 动态（quote/income/valuation），禁止 LLM 自选填充
    3) 控股股东排除硬规则（exclude_controlling_shareholders）
    4) 验证不过 → degrade_not_comparable('标注不可比')"""

def validate_peer_availability(wind_data, market) -> tuple[bool, list[str]]:
    """港股/美股可比 quote/财务覆盖面验证；<2 家可比 → (False, missing)"""

def exclude_controlling_shareholders(peers, target_ticker, shareholding) -> tuple[list[PeerCompany], list[str]]:
    """控股股东排除硬规则：peer 为目标公司股东且持股 ≥50% → 排除；
    ≥20% 且为第一大股东 → 排除+标注（腾讯 70.05% 持股阅文 → '腾讯当可比'根因消除）"""

def degrade_not_comparable(target, reason) -> PeerData:
    """降级：返回 ok=False + note='可比数据不可用（原因），标注不可比'"""
```

`valuation_engine.py`：`CORE_COMPARABLES/SUPPLEMENTARY_COMPARABLES`（102-113）**删除**；`build_comparable_analysis`（318-365）签名改 `build_comparable_analysis(comp_data: Optional[list[dict]] = None)`——无参数 → 空列表 + warning（不允许静默回退到常量表）；`compute_comparable_valuation`（676）已接受 `list[dict]`，直接接线 `build_peer_companies` 输出。

**接线**：ch2/ch7 prompt 注入 `PeerData` 格式化表；无数据 → "标注不可比"（禁止 LLM 自选）。

**测试**：顺丰对标场景 → 无任何硬编码行；控股股东（腾讯 70.05%）被排除；Wind 无可比数据 → ok=False + 标注不可比；可比表数值全部可追溯到 wind_data。

### 6.7 B4-7 ROIC vs WACC / FCF 含 ΔWC 程序化支撑

- `quality/roic_wacc_checker.py` 与 `fcf_calculator.py` 改造：输入走 canonical（B5-1）；FCF 口径支持 CFO−CAPEX（基础）与 CFO−CAPEX−ΔWC（含 ΔWC，公式来自 registry）。
- 接线：报告 ch7/质量增强注入"价值创造门槛（ROIC vs WACC）"程序化判定块。

**测试**：ROIC>WACC → "创造价值"；FCF 两口径输出与公式标注一致；ΔWC 无源 → 用基础口径+标注。

---

## 7. 完整新签名汇总

| 模块 | 新签名 | B 项 |
|---|---|---|
| `quality/numeric_guard.py` | `check_fiscal(self, chapter_num, content, wind_data, severity="critical", policy_map=None) -> GateResult` | B1-1 |
| `quality/numeric_guard.py` | 常量 `FISCAL_CHAPTER_POLICY` / `FISCAL_DEFAULT_POLICY` / `FISCAL_CONTEXT_EXEMPT`（替换 `FISCAL_STRICT_CHAPTERS`） | B1-1 |
| `qual_v8/mode_manager.py` | `GateBlockPolicy` / `GRADED_BLOCK_POLICY` / `ModeManager.should_block_gate(gate_num, errors, warnings) -> (bool, str)` | B1-2 |
| `qual_v8/workflow.py` | `execute()` 内 enforce 分支改用 `should_block_gate`（替换 350-359） | B1-2 |
| `workflow.py` | `_CHAPTER_WRITE_ORDER = [0..10]` | B1-3 |
| `valuation_engine.py` | `resolve_current_price(wind_data) -> Optional[float]` | B2a-1 |
| `quality_enhancer.py` | `enhance_report_quality(..., wind_data=None, shares=None, current_price=None, ...)` | B2a-1 |
| `quality/currency_guard.py`（新） | `assert_valuation_currency(wind_data, market) -> list[str]` / `valuation_currency_note(...) -> str` | B2a-2 |
| `workflow.py` | `extract_dcf_params(wind_data, shares=None, market="hk") -> dict`（含 `dcf_available/reason/fx/currency`） | B2a-3 |
| `valuation_engine.py` | `compute_valuation_chain(ticker, company_name, financials, shares, current_price, market, wind_data=None, wacc=None, terminal_growth=0.02) -> ValuationResult` | B2a-3/4 |
| `valuation_engine.py` | `derive_target_prices_v2(dcf_value, comparable_pe, comparable_ps, current_price, eps, revenue_per_share, shares) -> dict` | B2a-3 |
| `fact_extractor.py` | `extract_facts_multi_year(reports, company_name, ticker, market, llm_caller, wind_data=None, max_chars=300000, chunk_size=30000, budget_cap=200, lazy=False) -> MultiYearFacts` | B3-1 |
| `fact_extractor.py` | `merge_multi_year_facts(per_fy) -> MultiYearFacts`（纯程序化） | B3-1 |
| `fact_extractor.py` | `FactSourceRef(page=None, page_verified=False, quote="", confidence=0.5, arbitrated=False, fiscal_year=None, comparison_period=False)` | B3-2 |
| `fact_extractor.py` | `verify_page_metadata(sections) -> (bool, dict)` | B3-2 |
| `fact_extractor.py` | `format_facts_as_context(facts, wind_data=None) -> str` | B2b-1 |
| `fact_extractor.py` | `arbitrate_facts_with_wind(facts_dict, wind_data, fiscal_year=None) -> list[str]`（替换 cross_validate_with_wind） | B2b-2 |
| `canonical.py` | `CANONICAL_FIELDS` 扩展（+有息负债/现金/汇率/每股股息/短借/长借/一年内到期/流动资产/流动负债/货币资金） | B5-1 |
| `quality/wind_missing_field_registry.py`（新） | `FieldResolution` / `WindMissingFieldRegistry.resolve/resolve_full/get_available_fields/format_missing_notes` | B5-1 |
| `quality/number_transcription_normalizer.py`（新） | `NormalizedNumber` / `NumberTranscriptionNormalizer.extract(text) / match_extracted(value, unit, source_text, tolerance=0.01)` | B5-2 |
| `quality/operational_validator.py`（新） | `OperationalValidationResult` / `validate_operational_chain(facts, source_texts)` | B4-1 |
| `workflow.py` | `_build_decision_prompt(chapters, ctx, wind_anchor="", valuation_block="", rating_rules="", veto_notes="") -> str` | B4-5 |
| `qual_v8/gates/gate6.py` | `_check_rating_veto(chapters, context) -> dict` | B4-5 |
| `quality/peer_comparison.py` | `build_peer_companies(wind_data, market, target_ticker, peer_tickers=None, shareholding=None) -> PeerData` / `validate_peer_availability(...)` / `exclude_controlling_shareholders(...)` / `degrade_not_comparable(...)` | B4-6 |
| `valuation_engine.py` | `build_comparable_analysis(comp_data: Optional[list[dict]] = None)`（删除常量默认） | B4-6 |
| `quality/wind_anchor.py`（新） | `build_wind_anchor_table(wind_data) -> str`（自 review_repair_loop.py:299-319 提取） | B4-4/4-5 |
| `data_repair.py` | `fix_source_annotations(report_content, fiscal_year, company_name="")` / `normalize_negative_signs(text) -> (str, list[str])` | B2b-3 |

### 7.1 逐工作包副作用总览

| 工作包 | 副作用（须在提交时一并处理） |
|---|---|
| B1-1 | 删除 `FISCAL_STRICT_CHAPTERS` 前全库 grep 确认无其他引用；`check_all` 内 `check_fiscal` 调用走默认参数不受影响；any-fy/CrossChapterValidator 不改动（回归单测锁定） |
| B1-2 | `QualWorkflow` 需实例化 `ModeManager` 挂到 `self.mode_manager`（workflow.py 现无实例）；errors 需按 Critical/Warning 分类（ErrorClassifier 兜底，默认按 Critical 不扩大放行面）；三 run 脚本显式传 `qual_mode` |
| B1-3 | `_CHAPTER_WRITE_ORDER` 扩至 11 章仅影响 legacy 审计遍历与断点跳过分支；v8 Gate6 已生成 ch0/10，无重复生成风险 |
| B2a-1 | `quality_enhancer` 调用方（workflow.py run_analysis / gate5）需补传 `wind_data`；`upside=0` 改 `None` 会影响下游格式（报告显示"N/A"而非 0%） |
| B2a-2 | 估值输出新增 `currency/fx_note` 字段，`format_valuation_for_report`/ch7 注入模板同步；`check_currency` 保留旧行为，新断言并入估值链 |
| B2a-3 | `extract_dcf_params` 返回键扩展（`dcf_available/reason/fx/currency`），旧字段保留；gate2 判据改为按 `dcf_available` 分支（FCF≤0 不再误 fail）；`compute_full_valuation` 保持兼容包装指向新链 |
| B2a-4 | ch7/ch10 估值块由"追加"改"替换+标注"需回归文案比对；Gate6 `target_price_deviation` 阈值 0.20 不变 |
| B2b-1 | `FinancialFacts` 保留但不再填充，任何读取方（gate1/gate3/format）必须切 Wind 源，否则出现全 None；`_facts_to_dict` financial 段删除影响 gate1 详情展示 |
| B2b-2 | 仲裁从"仅净利/营收"扩至全字段后，运营字段与 Wind 重叠（如毛利率）会进入仲裁——需白名单过滤非财务键；容差常量统一后既有 reconcile 行为不变（1%） |
| B2b-3 | `fix_source_annotations` 通用化后对"来源：证监会年报 YYYY"等非公司年报标注同样生效（语义正确）；`company_name` 缺失时不匹配第二类 pattern（保守） |
| B5-1 | canonical 键扩展后 `assemble_wind_data` 的 `FIELD_MAP` 需同步补源键；既有 `canonicalize_table` 对非财务键原样保留，不破坏旧数据 |
| B3-1 | 多财年提取增加 LLM 调用量（预算 200 内）；`run_xpev_full` 的 `filing_data["metadata"]["prior_years"]` 不再是无消费点（改由 reports 承载）；legacy 单财年路径不受影响 |
| B3-2 | 页码元数据依赖 MinerU 输出结构，无结构时全部 null+unverified（不降级提取）；quote 字段新增会增大事实表体积（每行 ≤80 字可控） |
| B3-3 | 冲突仲裁"保留后值+warning"改变 v2.0"后批次覆盖"语义——下游若依赖后者需回归 |
| B5-2 | 提取值复核未命中 → confidence=low 会使部分运营字段降置信（报告标注变多）；normalize_units 不再自动修正后，历史依赖自动修正的路径需人工复核 |
| B4-1 | 铁律仅 MAU≥DAU≥付费等结构级阻断；钩稽全部 warning 级+白名单，避免新增阻断面触发 v3.1 回滚 |
| B4-2 | 毛利率缺口从 50% 变 null 后，LTV/CAC/回收期计算自动跳过——单位经济小节输出变短属预期（标注原因） |
| B4-3 | 行业兜底"综合"+标注会改变 ch2 措辞；legacy `review_repair_loop` 默认 None 需调用方必传 |
| B4-4 | 锚点表提公共函数后三处注入格式统一；修复 prompt 增事实表后 token 成本上升（计入预算 200） |
| B4-5 | `_build_decision_prompt` 增参后 legacy 调用点（workflow.py 生成 ch10 处）需补传；评级规则化后原"自由评级"报告会被 Gate6 后验拦截（预期行为变化） |
| B4-6 | 删除常量表后，未接 Wind 可比数据的调用方得到空可比表+标注（不再有假数据）；`PeerCompany` 字段删除影响既有构造点（grep 确认仅 peer_comparison.py 内部） |
| B4-7 | FCF 双口径输出增加事实表列；ΔWC 无源时用基础口径并标注，不改变既有 FCF 使用点 |

---

## 8. B 阶段测试清单

### 8.1 单元测试（新增/修改，与源码同目录 `tests/` 或 `quality/test_*.py`）

| 组 | 用例 | 断言 |
|---|---|---|
| B1-1 | ch5 只写 FY2024、无 FY2025、无对比语境 | `check_fiscal` fail（critical） |
| B1-1 | ch6 引用 FY2024 总资产 827.06（any-fy 保护场景） | 通过（不误判、不回滚） |
| B1-1 | ch4 YoY 含"同比"+FY 标注 | 通过 |
| B1-1 | ch7 引 FY2024 PE 带"FY2024" | 通过；不带标注 → warning（enforce → critical） |
| B1-1 | 无 `_year_labels` | 跳过通过 |
| B1-1 | any-fy 回归（data_anchor 原测试全绿） | 不删不改，原行为保持 |
| B1-2 | Gate0 coverage=0.90 | soft/enforce 均不阻断 + 标注（降级） |
| B1-2 | Gate8 warning 级财年标注缺失（enforce） | 阻断 |
| B1-2 | shadow/soft/enforce 三档矩阵 × Gate0/2/8 | 阻断面符合 `GRADED_BLOCK_POLICY` |
| B2a-1 | wind_data 有 quote.最新价 | `resolve_current_price` 返回动态值 |
| B2a-1 | 无 quote | 返回 None（无默认常量） |
| B2a-2 | 港股 quote 币种缺失 | 默认 HKD+标注；币种=CNY → 报问题 |
| B2a-3 | 小鹏样本（FCF≤0） | `extract_dcf_params.dcf_available=False` + reason；`compute_valuation_chain` 走 PS/不可估值 |
| B2a-3 | 阅文样本（FCF>0） | full_dcf 正常；目标价三数自洽（±20%） |
| B2a-3 | OCF/股本缺失 | fail-fast 原因链完整，无默认 1/5% |
| B2a-3 | `compute_dcf` 年份 | `latest_fy+1+i`（删除 2026+i） |
| B2a-4 | ch10 引用目标价 vs 程序输出 | Gate6 `target_price_deviation` 拦截 >20% |
| B2b-1 | 提取输出无 financial 键 | 事实表 JSON 键集合不含 financial |
| B2b-1 | Gate1 必填校验（financial 空） | 以 Wind canonical 通过 |
| B2b-1 | `_verify_company_identity` 非阅文 ticker | 不再误用 0772 |
| B2b-2 | 提取 100 vs Wind 99.5 / 103 / 107 | 保留 / 覆盖+warning / 覆盖+升级 |
| B2b-2 | 异财年提取值 | 降级标注，不覆盖 |
| B2b-3 | `来源：阅文2023年年报`（fy=2025） | → 2025 |
| B2b-3 | `快手2024年年报` + company_name=快手 | → 2025 |
| B2b-3 | `净亏损5.4亿` → `-5.4亿` | 负号统一 |
| B5-1 | 有息负债三键齐备 | derived 值正确 |
| B5-1 | 缺"一年内到期" | unavailable + "未披露"标注 |
| B5-1 | 全字段扫描 | 无任何启发式默认（0.3/50%/默认股本） |
| B3-1 | 3 份年报 | `per_fy` 3 键、`merged_series` 三财年列 |
| B3-1 | 预算超 200 | 惰性截断 + warning（或 BudgetExceeded） |
| B3-1 | `merge_multi_year_facts` | 零 LLM 调用（计数 caller 断言） |
| B3-2 | sections 无 page 元数据 | 全部 page=None+unverified |
| B3-2 | LLM 输出 page=42 | 丢弃 + warning |
| B3-3 | 批次 4.1 vs 4.11 | 保留前值无 warning；4.1 vs 4.9 → warning 不静默 |
| B5-2 | `4.102亿` 提取 | 4.102；提取 410.2 → match 未命中（conf low） |
| B5-2 | `约5.4亿`/`3-5亿`/`1,598,070.7万元`/`30港元` | 各归一正确 |
| B5-2 | normalize_units | 只标注不改值 |
| B4-1 | LTV 钩稽 20% 内 | 通过；含"non-IFRS调整" → 豁免 |
| B4-1 | MAU<DAU | iron_violations（阻断） |
| B4-2 | 无毛利率年报 | 毛利率 null+"未披露"，无 50% |
| B4-3 | 阅文 | "数字内容"（非"新能源汽车"） |
| B4-4 | 修复 prompt | 含"Wind 验证锚点"+"事实表"两节 |
| B4-5 | ch10 买入但偏差 0%（中性区） | Gate6 fail |
| B4-5 | 否决项存在+买入 | fail；override 标注 → 通过 |
| B4-6 | 顺丰对标 | 无硬编码行；控股股东（腾讯 70.05%）排除 |
| B4-6 | Wind 无可比数据 | ok=False + "标注不可比" |
| B4-7 | FCF 双口径 | CFO−CAPEX 与含 ΔWC 输出一致于公式标注 |

### 8.2 集成/回归测试

- `quality/test_*.py` 既有 20 测试（阶段 A 验收集）全绿：确保 B1-1 的 check_fiscal 改动、B2b 的 fact_extractor 改动不破坏 gate 链。
- v8 全链 smoke：`run_qual_v8.py quick_verify`（含断言 Gate0/Gate2 通过）在 B2a-3 后重跑——Gate2 对 FCF≤0 样本不再误 fail（`dcf_available` 分支）。
- 小鹏 9868.HK 重跑（M2-M5 验收）：财年错位 Critical 0、目标价=程序输出、事实表每行可翻原文、运营验证链通过、无硬编码股价/行业/可比数据。
- 阅文 00772.HK 回归：报告中不再出现 21.48/41.6；`grep -r "21\.48\|46\.52\|41\.6\|002024\.SZ" tools/finance run_*.py` 为空。

---

## 9. 实施顺序与提交分组

按综合审议优先级：**B1 → B2a → B5-1 → B2b → B3 → B5-2 → B4**。提交分组与依赖：

| 提交 | 内容 | 依赖 | 验收门 |
|---|---|---|---|
| **B1**（合并提交 #5） | B1-1 check_fiscal 扩展 + Gate8 接线 + any-fy 回归测试；B1-2 分级阻断（GRADED_BLOCK_POLICY + should_block_gate）；B1-3 `_CHAPTER_WRITE_ORDER` 全 11 章 | 阶段 A（Gate8 接线、单调守卫） | 单测 B1 组绿；M2 验收项 |
| **B2a**（提交 #6） | B2a-1 resolve_current_price + 三 run 脚本 + quality_enhancer 签名；B2a-2 currency_guard；B2a-3 extract_dcf_params 重写 + compute_valuation_chain + fail-fast + derive_target_prices_v2；B2a-4 ch7/ch10 程序化注入 | B1（无实质依赖，可与 B1 并行，但提交顺序在 B1 后以保持验收节奏） | 单测 B2a 组绿；`grep 21.48/46.52/41.6` 为空 |
| **B5-1**（提交 #7） | WindMissingFieldRegistry + canonical 扩展 + assemble_wind_data 动态 _year_labels | 独立（B2b 输入前置） | 单测 B5-1 组绿；registry 无启发式 |
| **B2b**（提交 #8） | B2b-1 prompt/解析/format/Gate1 改 Wind 源；B2b-2 arbitrate_facts_with_wind 全字段；B2b-3 data_repair 通用化 + canonicalize + 负号正则 | B5-1（处置表输入） | 单测 B2b 组绿；事实表无财务行 |
| **B3**（提交 #9） | B3-1 extract_facts_multi_year + merge_multi_year_facts + run_xpev_full 接线；B3-2 FactSourceRef + 页码验证；B3-3 批次冲突仲裁；B3-4 prompt 防杜撰 | B2b（财务移出后事实表专注运营/定性） | 单测 B3 组绿；M4 验收项 |
| **B5-2**（提交 #10） | NumberTranscriptionNormalizer + normalize_units 只标不改 + _parse_chunk_response 复核 | B3（事实表重构后接线） | 单测 B5-2 组绿 |
| **B4**（提交 #11） | B4-1 运营验证链；B4-2 删 50% 默认；B4-3 行业动态化；B4-4 锚点公共函数+事实表注入+legacy 覆盖；B4-5 _build_decision_prompt 扩展 + gate6 veto 联动；B4-6 可比重写+数据源化；B4-7 ROIC/FCF 支撑 | B2a-4（结论锚依赖估值程序化）、B5-2（复核链配对）、B3 | 单测 B4 组绿；M5 验收项 |
| **B5 收口**（提交 #12） | 护栏复核：全库硬编码扫描、事实表/报告标注完备性、审计日志锚定 | 全部 | 阶段 B 验收总纲（M2-M5 全绿） |

**关键依赖**：B1-1 ← 阶段 A（A2 的 fail-closed/deadline）；B2b ← B5-1；B3 ← B2b；B4-2 ← B3；B4-5 ← B2a-4；B4-1 ← B5-2。**并行许可**：B5-1 与 B2a 互不依赖可并行开发；B3-2（页码验证）可与 B5-2 并行。

---

## 10. 与 v3.1 兼容性分析

| v3.1 机制 | 交互点 | 兼容性结论 |
|---|---|---|
| **四重有界 + 单调守卫**（防死循环） | B1-1 新增阻断判据（当期断言） | ✅ 设计为"两栖"：历史引用豁免（对比语境+FY 标注）全量放行合法引用；any-fy 保护场景进回归单测；"修复验证通过即不再回滚"不因新判据触发回滚。`check_fiscal` 默认 severity=critical 仅在 enforce 下接线（shadow/soft 只记 warning），运行节奏不变 |
| **熔断 threshold=2 + 重试** | B1-2 分级阻断 | ✅ Gate0/2 小缺不再触发 Gate fail → 不消耗熔断计数；Gate8 财年 enforce 为确定性检查（非数据源调用），不经过熔断器。**翻转默认必须在 A4 小鹏验收通过后**，翻转后重跑验收不劣化 |
| **预算 200 + S5 计入** | B3 多财年提取 | ✅ 3 份年报 fetch+提取成本统一计入预算；超限 `lazy=True` 转惰性分财年提取（只取最新）——v3.1 预算机制不变，仅增加入口 |
| **deadline/逃生直连** | B3/B4 新增 LLM 调用点 | ✅ 多财年提取与验证链均挂 harness deadline（沿用阶段 A 的 deadline 参数）；新增调用计入各册预算 |
| **canonical/仲裁（A1 P0-A）** | B2b/B5-1 | ✅ canonical 扩展为增量（追加键+别名，`canonicalize_table` 现有合并逻辑不变）；仲裁容差统一为 1%/5% 常量，`RECONCILE_TOLERANCE` 与既有 reconcile 逻辑一致 |
| **fail-closed** | B2a-3 fail-fast | ✅ 数据缺失 → 显式降级/标注，绝不回填默认——fail-closed 精神一致（宁可缺失不可杜撰） |
| **20 测试验收集** | 全部 | ✅ 设计不改动阶段 A 已验收行为：check_fiscal 扩展向后兼容（默认参数）；any-fy 不动；gate 链签名不变；`extract_dcf_params` 返回值新增键（调用方按 `dcf_available` 分支，旧字段保留） |
| **ch0/ch10 生成与断点** | B1-3 | ✅ `_CHAPTER_WRITE_ORDER` 扩至 11 章仅影响审计遍历；断点恢复按 chapter_id 独立，不受影响 |
| **审计锚点（gate4 生效）** | B4-4 | ✅ 提公共函数不改注入语义；legacy 覆盖为增量 |

**兼容性护栏（编码纪律）**：
1. 所有新阻断判据必须**单调**：通过即不再回滚（B1-1 的 warning 可升级仅在新增判据上生效，不与 gate4 修复循环交互触发二次修复）。
2. `check_fiscal`/`extract_dcf_params`/`format_facts_as_context` 等签名变更采用**可选参数向后兼容**（默认值保持旧行为）；调用方不传新参数时行为不劣化。
3. 删除常量前全库 grep 确认无其他引用（`FISCAL_STRICT_CHAPTERS`、`CORE_COMPARABLES`、`create_sf_express_peers`）。
4. 新模块（currency_guard/wind_missing_field_registry/number_transcription_normalizer/operational_validator/wind_anchor）不引入 import 环：只依赖 canonical + 纯数据，不 import workflow/qual_v8。

---

## 11. 风险与护栏（实施期）

| 风险 | 护栏 |
|---|---|
| 死循环复发（最高） | §10 单调性；any-fy 回归单测；B1-1 只在 enforce 下 critical |
| 整线停摆 | B1-2 分级；Gate0 coverage 降级阈值；A4 后翻转默认 |
| 页码幻觉 | B3-2 前置 MinerU 结构验证；LLM page 输出丢弃 |
| 可比虚假精确 | B4-6 可用性验证 + 控股股东排除 + 降级"标注不可比" |
| 亏损公司 DCF 无意义 | B2a-3 fail-fast + PS 降级 + 三数自洽（含 DCF 不可用分支） |
| 派生钩稽误报 | B4-1 钩稽 warning 级 + 口径例外白名单（non-IFRS/一次性） |
| Wind 化后字段空洞 | B5-1 先行；unavailable 字段显式标注，不静默消失 |
| 转写单位错误漏出 | B5-2 预处理器 + B4-1 原文复核配对；normalize_units 只标不改 |
