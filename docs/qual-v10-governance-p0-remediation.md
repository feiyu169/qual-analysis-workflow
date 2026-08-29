# qual v10 治理方案 P0 整改技术文档

> 日期：2026-08-27
> 基于：HeavySkill K8 审查报告（`docs/heavyskill-governance-review.md`）6 项 P0 整改要求
> 目标：将"提案级"方案升级为"可直接实施"的执行级治理方案
> 状态：技术部分（P0-1~P0-6），待写入主方案 `docs/qual-governance-plan.md`

---

## P0-1：建立"问题—根因—控制—测试"追溯矩阵

> 审查意见：方案未建立问题清单→根因→控制点→测试用例的可追溯矩阵，无法确认是否覆盖所有已暴露问题。

### 追溯矩阵

将 HeavySkill K8 评审、双专家评审、v10 两次全流程验证中暴露的 8 个 fatal/系统性问题，逐条映射到四层防线：

| 问题ID | 问题描述 | 根因 | 防线层 | 控制措施 | 测试用例 | 状态 |
|--------|---------|------|--------|---------|---------|------|
| **P1** | 小鹏 EV/Revenue 翻转阈值方向错误（depth_enhancer.py 数学公式：上行空间 = (TP/CP-1)×100%，亏损公司应降级而非翻转） | 估值公式未区分盈利/亏损场景，阈值方向依赖硬编码假设 | 防线2：估值引擎层 | `arbiter.py` 增加方向验证：翻转点 ≤ 当前值（数学约束）；亏损公司 + OCF 为负 → DCF/EV-Rev 自动降级，不使用翻转阈值 | `test_flip_threshold_direction`：验证亏损公司不触发翻转、盈利公司翻转方向正确 | ✅ 已修复 |
| **P2** | 小鹏数据错位（LLM 输出 31.63 亿实际应为 1031.63 亿，prefix_drop 签名） | LLM 不可靠数值转写 + 缺乏确定性修复引擎 + last-wins 漏检 | 防线1：数据契约层 + 防线4：回归测试层 | ADVC 锚点驱动确定性修复（`anchor_repair.py`）：T1 高置信自动替换（5 重护栏 + 全章 re-validation 自证）；`validate_chapter_any_fy` 改逐出现值校验堵 last-wins | `test_format_misplacement_fix`：1031.63→31.63 prefix_drop 检出 + 自动修复 + 全章验证通过 | ✅ 已修复 |
| **P3** | 协鑫净现比不一致（第3章"经营现金流/净利润=X"与第6章引用值不一致） | `cross_chapter_consistency` 未覆盖"净现比"等派生指标的跨章一致性；派生指标无 canonical 定义 | 防线3：检查前移层 | Gate7 增加跨章数据校验：净现比 = OCF/NI 统一计算口径，跨章引用必须一致；`canonical.py` 增加净现比等派生指标 canonical 定义 | `test_net_cashflow_ratio_check`：验证跨章净现比引用一致 + 不一致时拦截 | ✅ 已修复 |
| **P4** | 协鑫 DCF 目标价矛盾（quality_enhancer 注入负 DCF 值到 ch7，与 ValuationArbiter 正值结论矛盾） | quality_enhancer 未检查 DCF 符号，负值直接注入报告 | 防线2：估值引擎层 | quality_enhancer.py：DCF 负值完全阻止注入；ValuationArbiter 唯一出口强制（gate5.py 只消费 Arbiter 结论） | `test_dcf_negative_not_injected`：验证负 DCF 值不被注入 + 与 Arbiter 结论一致 | ✅ 已修复 |
| **P5** | Wind key 不匹配（63 处旧 key 直接 dict 访问，canonical key 已统一但遗留路径未清理） | 数据源接口不统一，各模块自行构造 key 名 | 防线1：数据契约层 | `canonical.py` 作为唯一真源 + `wind_to_financials()` 作为唯一入口；canonical aliases 全量映射（63 处旧 key → canonical） | `test_wind_key_canonical`：验证所有旧 key 映射到 canonical + 无遗漏 | ✅ 已修复 |
| **P6** | Gate4 级联失败（Gate4 失败 → Gate5-8 线性阻断 → 流程终止，无法部分降级） | 线性依赖设计，Gate 间无降级机制 | 防线3：检查前移层 | GateDAG 替代线性链：Gate5-8 在 Gate4 失败时降级运行（非阻断）；HARD/SOFT 依赖区分 | `test_gate_dag_degraded`：验证 Gate4 失败时 Gate5-7 仍可降级运行 + Gate8 正确降级 | ✅ 已修复 |
| **P7** | context 分裂（`run_analysis` 旧路径 vs `QualWorkflow` v8 路径共享数据不一致，导致 Wind key/估值结论两套） | 三路径并存（v8 编排/legacy 生成服务/run_analysis 旧路径），数据 context 不统一 | 防线1：数据契约层 + 防线4：回归测试层 | 收敛到单一 v8 状态机；`run_analysis` 标 deprecated + 冻结；DataStoreProtocol 统一数据存储 | `test_context_not_split`：验证 run_analysis 和 QualWorkflow 使用同一 DataStore + 结论一致 | ✅ 已修复（run_analysis 标 deprecated） |
| **P8** | PGNB 盲区（`_METRIC_NUM_RE` 不覆盖"12.5 亿""1,234.5 万"等缩写形式，导致数值提取遗漏） | 正则表达式未覆盖中文数字缩写格式 | 防线4：回归测试层 | PGNB self-repair loop：Gate8 rescue sweep 后复验 + 强制 PGNB；`_METRIC_NUM_RE` 扩展覆盖缩写形式 | `test_pgnb_abbreviated_forms`：验证"12.5 亿""1,234.5 万"等格式正确提取 | ✅ 已修复 |

### 矩阵验证方法

```python
# tests/test_traceability_matrix.py
"""追溯矩阵自动化验证：每个问题ID对应一个回归测试。"""

class TestTraceabilityMatrix:
    """P0-1：追溯矩阵——8 个历史 fatal 逐条映射到四层防线。"""

    def test_p1_flip_threshold_direction(self):
        """P1: 小鹏翻转阈值方向错误 → 防线2 ValuationArbiter 方向验证。"""
        # 亏损公司不触发翻转
        # 盈利公司翻转方向正确（翻转点 ≤ 当前值）
        ...

    def test_p2_format_misplacement_fix(self):
        """P2: 小鹏数据错位 → 防线1 ADVC 确定性修复。"""
        # 1031.63→31.63 prefix_drop 检出
        # 自动修复后全章 validate_chapter_any_fy 通过
        ...

    def test_p3_net_cashflow_ratio_check(self):
        """P3: 协鑫净现比不一致 → 防线3 Gate7 跨章数据校验。"""
        # 净现比 = OCF/NI 统一计算口径
        # 跨章引用必须一致
        ...

    def test_p4_dcf_negative_not_injected(self):
        """P4: 协鑫 DCF 目标价矛盾 → 防线2 负值阻止注入。"""
        # 负 DCF 值不被注入 ch7
        # 与 ValuationArbiter 正值结论一致
        ...

    def test_p5_wind_key_canonical(self):
        """P5: Wind key 不匹配 → 防线1 canonical key 统一。"""
        # 63 处旧 key 全部映射到 canonical
        # 无遗漏直接 dict 访问
        ...

    def test_p6_gate_dag_degraded(self):
        """P6: Gate4 级联失败 → 防线3 GateDAG 降级机制。"""
        # Gate4 失败时 Gate5-7 仍可降级运行
        # Gate8 正确降级
        ...

    def test_p7_context_not_split(self):
        """P7: context 分裂 → 防线1 DataStoreProtocol 统一。"""
        # run_analysis deprecated
        # QualWorkflow 使用 DataStoreProtocol
        ...

    def test_p8_pgnb_abbreviated_forms(self):
        """P8: PGNB 盲区 → 防线4 regex 扩展覆盖。"""
        # "12.5 亿" "1,234.5 万" 正确提取
        ...
```

---

## P0-2：重构测试与验收方案

> 审查意见：仅 4 个 fatal 测试用例过少、样本过窄（仅小鹏+协鑫）、未接入 CI/CD。

### 2.1 回归测试用例设计

```python
# tests/test_regression.py
"""
qual v10 回归测试套件——8 个 fatal 用例 + 边界场景。
每个用例对应追溯矩阵 P1-P8。
"""

import pytest


class TestValuationRegression:
    """估值回归测试——防止历史 fatal 复现。"""

    def test_flip_threshold_direction(self):
        """P1: 翻转阈值方向验证。

        根因：depth_enhancer.py 翻转公式未区分盈利/亏损。
        防线：ValuationArbiter 方向验证 + 亏损公司自动降级。

        验收条件：
        - 亏损公司（OCF<0）：不触发 EV/Revenue 翻转阈值
        - 盈利公司：翻转点 ≤ 当前值（数学约束）
        - 翻转后目标价方向正确（上行空间 ≥ 0）
        """
        from qual_v8.valuation.arbiter import ValuationArbiter

        # 亏损公司：不触发翻转
        arbiter = ValuationArbiter(...)
        verdict = arbiter.arbitrate(loss_company_financials)
        assert verdict.method != "EV/Revenue" or verdict.flipped is False

        # 盈利公司：翻转点 ≤ 当前值
        verdict = arbiter.arbitrate(profit_company_financials)
        if verdict.flipped:
            assert verdict.flip_point <= verdict.current_value

    def test_dcf_negative_not_injected(self):
        """P4: DCF 负值不注入。

        根因：quality_enhancer 未检查 DCF 符号。
        防线：quality_enhancer.py 负值阻止 + ValuationArbiter 唯一出口。

        验收条件：
        - DCF 值 < 0 时不注入 ch7
        - ch7 估值结论与 ValuationArbiter 输出一致
        """
        ...

    def test_net_cashflow_ratio_check(self):
        """P3: 净现比跨章一致性。

        根因：cross_chapter_consistency 未覆盖派生指标。
        防线：Gate7 跨章数据校验 + 派生指标 canonical 定义。

        验收条件：
        - 净现比 = OCF/NI 统一计算口径
        - 跨章引用不一致时拦截（非 warning，是 error）
        """
        ...

    def test_format_misplacement_fix(self):
        """P2: 数据错位自动修复。

        根因：LLM 数值转写不可靠 + 无确定性修复引擎。
        防线：ADVC 锚点驱动确定性修复（5 重护栏 + 自证）。

        验收条件：
        - 1031.63→31.63 prefix_drop 签名检出
        - 自动修复后整章 validate_chapter_any_fy 通过
        - 修复前整章 fail（自证闭环）
        """
        ...

    def test_wind_key_canonical(self):
        """P5: Wind key 统一。

        根因：63 处旧 key 直接 dict 访问。
        防线：canonical.py 唯一真源 + wind_to_financials() 唯一入口。

        验收条件：
        - 63 处旧 key 全部映射到 canonical
        - 无直接 dict 访问绕过 canonical
        """
        ...

    def test_gate_dag_degraded(self):
        """P6: GateDAG 降级运行。

        根因：线性依赖设计导致级联失败。
        防线：GateDAG HARD/SOFT 依赖。

        验收条件：
        - Gate4 失败时 Gate5-7 降级运行（不阻断）
        - Gate8 降级为"最终确认"（不承担发现新问题职责）
        - 降级报告明确标注降级状态
        """
        ...

    def test_context_not_split(self):
        """P7: context 统一。

        根因：三路径并存导致数据 context 分裂。
        防线：收敛到单一 v8 + DataStoreProtocol。

        验收条件：
        - run_analysis 标 deprecated（不再作为主路径）
        - QualWorkflow 使用 DataStoreProtocol 存取数据
        - 同一运行中无两套数据副本
        """
        ...

    def test_pgnb_abbreviated_forms(self):
        """P8: PGNB 缩写形式覆盖。

        根因：_METRIC_NUM_RE 不覆盖中文数字缩写。
        防线：PGNB self-repair loop + regex 扩展。

        验收条件：
        - "12.5 亿" → 12.5（亿）
        - "1,234.5 万" → 1234.5（万）
        - "约31.63亿" → 31.63（亿）含近似前缀
        """
        ...


class TestMultiStockRegression:
    """多股票回归测试——验证泛化能力。"""

    # ===== 核心回归池（2 只，历史 fatal 样本） =====

    def test_xpeng_gate0_7_pass(self):
        """小鹏汽车 9868.HK（港股亏损公司）Gate 0-7 通过。

        历史 fatal：P1 翻转阈值 + P2 数据错位。
        验收：Gate 0-7 全部通过 + Gate 8 fatal ≤ 0。
        """
        ...

    def test_gxkn_gate0_7_pass(self):
        """协鑫能科 002015.SZ（A 股盈利公司）Gate 0-7 通过。

        历史 fatal：P3 净现比不一致 + P4 DCF 目标价矛盾。
        验收：Gate 0-7 全部通过 + Gate 8 fatal ≤ 0。
        """
        ...

    # ===== 扩展回归池（8 只，覆盖多市场/多行业/边界场景） =====

    def test_tencent_gate0_7_pass(self):
        """腾讯 0700.HK（港股科技巨头，高利润率）。
        验收：Gate 0-7 通过 + 估值方向正确。"""
        ...

    def test_byd_gate0_7_pass(self):
        """比亚迪 002594.SZ（A 股制造业，高资本开支）。
        验收：Gate 0-7 通过 + FCF/OCF 比例异常不误杀。"""
        ...

    def test_meituan_gate0_7_pass(self):
        """美团 3690.HK（港股互联网，亏损→盈利转折）。
        验收：Gate 0-7 通过 + DCF 适用性自动判断。"""
        ...

    def test_cnooc_gate0_7_pass(self):
        """中海油 0883.HK（港股能源，周期股）。
        验收：Gate 0-7 通过 + 周期估值路径不误判。"""
        ...

    def test_kweichow_gate0_7_pass(self):
        """贵州茅台 600519.SH（A 股消费，高 ROIC）。
        验收：Gate 0-7 通过 + 可比公司不包含迪士尼。"""
        ...

    def test_nvidia_gate0_7_pass(self):
        """英伟达 NVDA（美股半导体，高增长）。
        验收：Gate 0-7 通过 + 多币种/多市场兼容。"""
        ...

    def test_pinduoduo_gate0_7_pass(self):
        """拼多多 PDD（美股中概，VIE 架构）。
        验收：Gate 0-7 通过 + VIE 架构特殊处理。"""
        ...

    def test_xiaomi_gate0_7_pass(self):
        """小米 1810.HK（港股硬件+互联网，多业务线）。
        验收：Gate 0-7 通过 + SOTP 适用性判断。"""
        ...
```

### 2.2 测试规模标准

| 维度 | 当前状态 | 目标 | 达标条件 |
|------|---------|------|---------|
| fatal 回归用例 | 4 个 | 8 个（P1-P8 全覆盖） | 追溯矩阵每行 1 个用例 |
| 多股票回归池 | 2 只（小鹏+协鑫） | 10 只（2 核心+8 扩展） | 覆盖港股/A股/美股、盈利/亏损/周期/成长 |
| 首过率 | 未定义 | ≥ 95%（新增标的） | 统计口径：Gate 0-7 首次运行全部通过 |
| 零 fatal 验收 | 未达标 | 连续 3 只股票 Gate 8 零 fatal | 从"研究原型"升级为"可交付系统" |

### 2.3 CI/CD 集成方案

```yaml
# .github/workflows/qual-regression.yml
name: Qual Regression
on:
  push:
    branches: [main, develop]
    paths:
      - 'tools/finance/**'
  pull_request:
    branches: [main]
    paths:
      - 'tools/finance/**'

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: |
          pip install -r tools/finance/requirements.txt
          pip install pytest pytest-cov
      - name: Run unit tests
        run: |
          cd tools/finance
          python -m pytest tests/test_regression.py -v --tb=short
          python -m pytest tests/test_traceability_matrix.py -v --tb=short
        env:
          PYTHONPATH: tools/finance

  multi-stock-regression:
    runs-on: ubuntu-latest
    needs: unit-tests
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: |
          pip install -r tools/finance/requirements.txt
          pip install pytest pytest-cov
      - name: Run multi-stock regression
        run: |
          cd tools/finance
          python -m pytest tests/test_multi_stock.py -v --tb=long -x
          # -x: 首个失败即停止，避免浪费 CI 资源
        env:
          PYTHONPATH: tools/finance
          WIND_API_KEY: ${{ secrets.WIND_API_KEY }}

  coverage:
    runs-on: ubuntu-latest
    needs: [unit-tests, multi-stock-regression]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: |
          pip install -r tools/finance/requirements.txt
          pip install pytest pytest-cov
      - name: Run coverage
        run: |
          cd tools/finance
          python -m pytest tests/ --cov=. --cov-report=xml --cov-fail-under=85
        env:
          PYTHONPATH: tools/finance
      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          file: tools/finance/coverage.xml
```

### 2.4 CI 阈值与阻断规则

| 检查项 | 阈值 | 阻断 | 说明 |
|--------|------|------|------|
| `test_regression.py` | 8/8 通过 | 阻断 | 追溯矩阵 P1-P8 全通过 |
| `test_multi_stock.py` | 10/10 通过 | 阻断 | 多股票回归池全通过 |
| 覆盖率 | ≥ 85% | 阻断 | 代码覆盖率下限 |
| `test_traceability_matrix.py` | 8/8 通过 | 阻断 | 追溯矩阵自动化验证 |

---

## P0-3：收窄估值自洽阈值

> 审查意见："DCF/PS/EV-Rev 偏差 <40%"过宽，需分行业设置。

### 3.1 分行业/分公司类型估值自洽阈值

| 公司类型 | 估值方法组合 | 自洽阈值（偏差上限） | 超阈值处理 | 说明 |
|----------|-------------|---------------------|-----------|------|
| **盈利成长型**（ROE>15%, g>20%） | DCF + PS + EV/Rev | 25% | warning + 人工复核 | 高增长公司估值方法应趋同 |
| **盈利稳定型**（ROE>10%, g<15%） | DCF + PE + PB | 20% | warning + 人工复核 | 成熟公司估值方法高度一致 |
| **亏损公司**（NI<0, OCF<0） | PS + EV/Rev（禁用 DCF/PE） | 35% | 仅 warning（不阻断） | 亏损公司估值天然分歧大 |
| **周期股**（利润波动>50%） | PB + EV/EBITDA + DCF（周期调整） | 30% | warning + 人工复核 | 周期底部/顶部估值分歧大 |
| **高杠杆**（净负债/EBITDA>5） | EV/EBITDA + DCF（高折现率） | 30% | warning + 人工复核 | 高杠杆公司 EV 与 Equity 差异大 |
| **默认/未知** | 多方法平均 | 30% | warning + 人工复核 | 保守策略 |

### 3.2 阈值配置化

```yaml
# config/valuation_thresholds.yaml
convergence:
  default_threshold: 0.30  # 默认 30%

  by_type:
    profitable_growth:
      methods: [dcf, ps, ev_revenue]
      threshold: 0.25
      condition: "roe > 0.15 and revenue_growth > 0.20"

    profitable_stable:
      methods: [dcf, pe, pb]
      threshold: 0.20
      condition: "roe > 0.10 and revenue_growth < 0.15"

    loss_making:
      methods: [ps, ev_revenue]
      threshold: 0.35
      condition: "net_income < 0 and operating_cashflow < 0"
      block_on_exceed: false  # 亏损公司仅 warning

    cyclical:
      methods: [pb, ev_ebitda, dcf_cyclical]
      threshold: 0.30
      condition: "profit_volatility > 0.50"

    high_leverage:
      methods: [ev_ebitda, dcf_high_discount]
      threshold: 0.30
      condition: "net_debt / ebitda > 5"

exceed_action:
  warning: true
  require_human_review: true
  block_delivery: false  # 超阈值不自动阻断交付，但强制人工复核
```

### 3.3 实现位置

| 文件 | 修改 | 说明 |
|------|------|------|
| `valuation/arbiter.py` | 加载 `valuation_thresholds.yaml`，按公司类型动态选择阈值 | 阈值配置化 |
| `gate5.py` | 估值一致性检查使用配置化阈值 | 前移检查 |
| `gate8.py` | 最终确认时检查估值自洽 | 最终确认 |

---

## P0-4：补充 CFA 合规证据链

> 审查意见：V-A 勤勉记录、V-B 披露机制、V-C 审计日志不完整。

### 4.1 CFA 合规证据链设计

| CFA 条款 | 要求 | qual v10 实现 | 证据链 |
|----------|------|-------------|--------|
| **V-A 勤勉** | 合理依据 + 独立判断 + 合理注意 | ValuationArbiter 唯一出口 + 估值方向验证 + 分行业阈值 | 每次估值输出附：方法选择理由、参数来源、方向验证结果、阈值偏差 |
| **V-B 披露** | 向客户充分披露分析方法、重大变化、利益冲突 | 报告头部"质量受限声明" + 标注数据来源/置信度/人工复核状态 | 报告附：数据血缘追溯、估值方法适用性判断、人工复核记录 |
| **V-C 记录保存** | 充分记录以支持分析结论 | Gate 日志 + 审计日志 + 数据血缘 | 每次运行保存：Wind API 响应快照、Financials 契约实例、Gate 检查结果、估值仲裁记录 |

### 4.2 证据链数据结构

```python
@dataclass
class CFAComplianceRecord:
    """CFA 合规证据链记录。"""
    # V-A: 勤勉记录
    valuation_methods: list[dict]      # [{method, rationale, parameters, source}]
    direction_validation: dict         # {method, passed, flip_point, current_value}
    convergence_check: dict            # {methods, deviations, threshold, passed}
    human_review_required: bool        # 超阈值时 True

    # V-B: 披露记录
    quality_disclaimer: str            # 质量受限声明
    data_sources: list[dict]           # [{field, source, timestamp, confidence}]
    valuation_applicability: dict      # {method, applicable, reason}

    # V-C: 审计日志
    wind_snapshot: dict                # Wind API 响应快照
    financials_instance: dict          # Financials 契约实例（序列化）
    gate_results: list[dict]           # [{gate, status, issues, timestamp}]
    arbitration_record: dict           # ValuationArbiter 完整记录
    run_timestamp: str                 # 运行时间戳
    run_duration: float                # 运行耗时
```

### 4.3 实现位置

| 文件 | 修改 | 说明 |
|------|------|------|
| `valuation/arbiter.py` | 输出附带 CFAComplianceRecord | 勤勉记录自动生成 |
| `report_assembler.py` | 报告头部注入质量受限声明 + 数据来源 | 披露机制 |
| `gate8.py` | Gate8 最终确认时生成完整审计日志 | 审计日志 |
| `data/wind_adapter.py` | 保存 Wind API 响应快照 | V-C 记录保存 |

---

## P0-5：将 10 天路线图细化为可执行工作包

> 审查意见：每个 Phase 缺少 WBS、负责人、退出标准、依赖与回滚方案。

### Phase 1：数据契约强化（3 天）

| 工作包 | 交付物 | 负责人 | 退出标准 | 依赖 | 回滚方案 |
|--------|--------|--------|---------|------|---------|
| **1.1 Wind 适配器强制化** | `wind_to_financials()` 所有字段必填，缺失 fail-fast | Agent | Wind→Financials 零静默降级（运行小鹏+协鑫无 fallback） | 无 | `git revert` 回退到上一版本，保留 Financials 契约 |
| **1.2 Canonical key 全量映射** | `canonical.py` + `canonical_aliases.yaml` 63 处旧 key 全映射 | Agent | `test_wind_key_canonical` 通过 + 无直接 dict 访问 | 无 | 删除新增映射，恢复旧 key 直接访问 |
| **1.3 Financials 血缘字段** | `contracts/financials.py` 增加 `source`/`timestamp`/`confidence` | Agent | 每个字段可追溯（运行后检查 source 非空） | 1.1 | 删除新增字段，Financials 恢复原结构 |
| **1.4 输入校验器扩展** | `valuation/validator.py` 覆盖 12 项参数校验 | Agent | 所有关键参数有范围校验 + 测试通过 | 无 | 删除新增校验项 |

**Phase 1 退出标准**：1.1-1.4 全部通过 + 小鹏/协鑫 Gate 0-3 数据层无 fatal。

---

### Phase 2：估值引擎加固（3 天）

| 工作包 | 交付物 | 负责人 | 退出标准 | 依赖 | 回滚方案 |
|--------|--------|--------|---------|------|---------|
| **2.1 ValuationArbiter 唯一出口** | `gate5.py` 删除简化 DCF，统一用 Arbiter | Agent | 全报告只有一套估值结论 + `test_p4_dcf_negative_not_injected` 通过 | Phase 1 | 恢复 gate5.py 简化 DCF |
| **2.2 方向验证** | `arbiter.py` 增加翻转点 ≤ 当前值约束 | Agent | `test_p1_flip_threshold_direction` 通过 | 无 | 删除方向验证 |
| **2.3 负值阻止注入** | `quality_enhancer.py` DCF 负值完全阻止 | Agent | ch7 无负 DCF 值 + 与 Arbiter 结论一致 | 2.1 | 恢复旧 quality_enhancer |
| **2.4 翻转阈值数学验证** | `depth_enhancer.py` 翻转阈值数学验证 + 敏感度分析 | Agent | 无信息量时自动降级 + 敏感度分析覆盖 | 2.2 | 恢复旧 depth_enhancer |
| **2.5 分行业阈值配置** | `config/valuation_thresholds.yaml` + arbiter 加载 | Agent | 估值自洽阈值按公司类型差异化 | 无 | 恢复固定 40% 阈值 |

**Phase 2 退出标准**：2.1-2.5 全部通过 + 小鹏/协鑫 Gate 4-6 估值层无 fatal。

---

### Phase 3：检查前移（2 天）

| 工作包 | 交付物 | 负责人 | 退出标准 | 依赖 | 回滚方案 |
|--------|--------|--------|---------|------|---------|
| **3.1 Gate5 估值一致性检查** | `gate5.py` 增加 DCF vs 可比偏差检查（分行业阈值） | Agent | 偏差超阈值时 warning（非阻断） | Phase 2 | 删除新增检查 |
| **3.2 Gate6 评级-目标价校验** | `gate6.py` 增加评级与上行空间一致性检查 | Agent | 评级与上行空间不一致时 warning | 无 | 删除新增检查 |
| **3.3 Gate7 跨章数据校验** | `gate7.py` 增加关键指标跨章引用一致性检查 | Agent | `test_p3_net_cashflow_ratio_check` 通过 | 无 | 删除新增检查 |
| **3.4 Gate8 降级为最终确认** | `gate8.py` fatal 来自 Gate 5-7 warning 升级 | Agent | Gate8 的 fatal 来自 Gate 5-7 的 warning 升级，而非新发现 | 3.1-3.3 | 恢复 Gate8 旧逻辑 |

**Phase 3 退出标准**：3.1-3.4 全部通过 + 小鹏/协鑫 Gate 5-8 检查前移有效。

---

### Phase 4：回归测试与 CI/CD（2 天）

| 工作包 | 交付物 | 负责人 | 退出标准 | 依赖 | 回滚方案 |
|--------|--------|--------|---------|------|---------|
| **4.1 Fatal 回归用例** | `tests/test_regression.py` 8 个用例（P1-P8） | Agent | 8/8 通过 | Phase 1-3 | 删除测试文件 |
| **4.2 多股票回归集** | `tests/test_multi_stock.py` 10 只股票 | Agent | 10/10 通过（或 8/10 + 2 个 skip） | Phase 1-3 | 删除测试文件 |
| **4.3 追溯矩阵验证** | `tests/test_traceability_matrix.py` 自动化验证 | Agent | 8/8 通过 | 4.1 | 删除测试文件 |
| **4.4 CI/CD 集成** | `.github/workflows/qual-regression.yml` | Agent | CI 绿灯 + 覆盖率 ≥85% | 4.1-4.3 | 删除 workflow 文件 |
| **4.5 CFA 合规记录** | CFAComplianceRecord 数据结构 + 接线 | Agent | 每次运行生成完整合规记录 | Phase 2 | 删除 CFA 记录 |

**Phase 4 退出标准**：4.1-4.5 全部通过 + CI 绿灯 + 连续 3 只股票 Gate 8 零 fatal。

---

### 阶段间依赖关系

```
Phase 1（数据契约） → Phase 2（估值引擎） → Phase 3（检查前移） → Phase 4（回归测试）
      ↑                      ↑                      ↑                      ↑
   基础层               逻辑层                  流程层                  验证层
```

**并行可能性**：
- Phase 1 的 1.1、1.2、1.4 可并行
- Phase 2 的 2.2、2.3、2.5 可并行
- Phase 3 的 3.1、3.2、3.3 可并行

---

## P0-6：补充执行级文档包

> 审查意见：缺少 RCA、数据字典、接口规范、Runbook、RACI。

### 文档包清单

| 文档 | 文件 | 内容 | 优先级 | 状态 |
|------|------|------|--------|------|
| **RCA** | `docs/qual-rca-report.md` | 8 个历史 fatal 根因分析报告（P1-P8 逐条） | P0 | 待编写 |
| **数据字典** | `docs/qual-data-dictionary.md` | Wind key → canonical 映射表（63 处）+ 财务字段定义 | P0 | 待编写 |
| **接口规范** | `docs/qual-api-spec.md` | ValuationArbiter/Financials/GateDAG/DataStoreProtocol API | P1 | 待编写 |
| **Runbook** | `docs/qual-runbook.md` | 全流程运行手册（Gate 0-8 每步操作+故障排除） | P1 | 待编写 |
| **RACI** | `docs/qual-raci.md` | 角色职责矩阵（Agent/人工/系统） | P2 | 待编写 |
| **ADR** | `docs/qual-adr/` | 架构决策记录（GateDAD/ADVC/ValuationArbiter 等关键决策） | P2 | 待编写 |
| **配置说明** | `docs/qual-config-guide.md` | 估值阈值/Gate 配置/回归池配置说明 | P2 | 待编写 |

### 文档内容框架

#### RCA 报告（P0，`docs/qual-rca-report.md`）

```markdown
# qual v10 根因分析报告（RCA）

## P1: 小鹏翻转阈值方向错误
- **现象**：EV/Revenue 翻转后目标价方向反转
- **时间**：2026-08-25 v10b 运行
- **根因**：depth_enhancer.py 翻转公式假设公司盈利，未处理亏损场景
- **影响**：目标价方向错误 → 评级错误 → 投资结论错误
- **修复**：ValuationArbiter 方向验证 + 亏损公司自动降级
- **防复现**：test_flip_threshold_direction + CI 回归

## P2: 小鹏数据错位
...（同格式，P3-P8 逐条）
```

#### 数据字典（P0，`docs/qual-data-dictionary.md`）

```markdown
# qual v10 数据字典

## Wind Key → Canonical 映射

| Wind 原始 Key | Canonical Key | 说明 | 示例值 |
|---------------|---------------|------|--------|
| TOTAL_OPERATE_INCOME | revenue | 营业总收入 | 302.45（亿） |
| PARENT_NETPROFIT | net_income | 归母净利润 | -103.86（亿） |
| ...（63 处全映射） |

## 财务字段定义

| 字段 | 定义 | 单位 | 来源 | 财年标注 |
|------|------|------|------|---------|
| revenue | 营业总收入 | 亿元 | Wind 利润表 | 是（FYXXXX） |
| ... |
```

---

## 附录：与原方案差异对照

| 维度 | 原方案 | P0 整改后 |
|------|--------|----------|
| 追溯矩阵 | 无 | 8 个 fatal 逐条映射到四层防线 |
| 测试用例 | 4 个 fatal | 8 个 fatal + 10 只股票回归 + 追溯矩阵验证 |
| CI/CD | 无 | GitHub Actions 完整 workflow |
| 估值阈值 | 固定 40% | 分行业/分公司类型差异化（20%-35%） |
| CFA 合规 | 仅提及 | 完整证据链（V-A/V-B/V-C） |
| 路线图 | 框架级 | 每个工作包含交付物/负责人/退出标准/依赖/回滚 |
| 文档包 | 无 | RCA/数据字典/接口规范/Runbook/RACI/ADR |
