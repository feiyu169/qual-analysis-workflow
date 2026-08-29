# Qual v10 问题根本性与长效化治理方案（v2.0）

> 版本：v2.0 | 日期：2026-08-27
> 基于：HeavySkill K8 审查意见（6 项 P0 整改）+ 投资专家/编程专家修改
> 目标：从"逐个修 bug"转向"系统性治理"

---

## 一、追溯矩阵（P0 整改第 1 项）

| ID | 问题描述 | 根因 | 防线层 | 控制措施 | 测试用例 | 状态 |
|----|---------|------|--------|---------|---------|------|
| P1 | 小鹏翻转阈值方向错误 | depth_enhancer 数学公式 | 估值引擎 | 方向验证 + 20% 敏感度降级 | test_flip_threshold_direction | ✅ 已修复 |
| P2 | 小鹏数据错位 | LLM 输出格式错误 | 检查前移 | Gate8 格式错位正则检测 | test_format_misplacement_fix | ✅ 已修复 |
| P3 | 协鑫净现比不一致 | cross_chapter 未覆盖 | 检查前移 | 净现比派生指标检查 | test_net_cashflow_ratio_check | ✅ 已修复 |
| P4 | 协鑫 DCF 目标价矛盾 | quality_enhancer 注入负 DCF | 估值引擎 | DCF 负值完全阻止注入 | test_dcf_negative_not_injected | ✅ 已修复 |
| P5 | Wind key 不匹配（63 处） | canonical 层绕过 | 数据契约 | wind_adapter 强制化 | test_wind_key_canonical | ✅ 已修复 |
| P6 | Gate4 级联失败 | 线性依赖 | 架构 | GateDAG HARD/SOFT | test_gate_dag_degraded | ✅ 已修复 |
| P7 | context 分裂 | run_analysis vs QualWorkflow | 架构 | decision_rating 写入 context | test_context_not_split | ✅ 已修复 |
| P8 | PGNB 盲区 | _METRIC_NUM_RE 不覆盖缩写 | 数据契约 | 扩展 regex + canonical alias | test_pgnb_abbreviated_forms | ✅ 已修复 |

---

## 二、四层防线

### 防线 1：数据契约层（源头治理）

**原则**：所有财务数据必须通过 Financials 契约传递，禁止 dict[str, Any] 直传。

**措施**：
1. **Wind 适配器强制化**：`wind_to_financials()` 作为唯一入口，缺失字段 fail-fast
2. **Canonical key 统一**：`canonical.py` 作为唯一真源，禁止绕过
3. **数据血缘追踪**：每个 Financials 字段记录 `source`/`timestamp`/`confidence`
4. **输入校验器扩展**：覆盖 12 项关键参数（WACC/g/PS/PB/EV-Rev/汇率/杠杆）

**验收标准**：任何财务数据可追溯到 Wind API 返回值。

### 防线 2：估值引擎层（逻辑治理）

**原则**：估值计算必须通过 ValuationArbiter 唯一出口，禁止 Gate 自行计算。

**估值自洽阈值**（分公司类型）：

| 公司类型 | 主方法 | 交叉验证阈值 | 行动 |
|----------|--------|-------------|------|
| 亏损公司（OCF 正） | EV/Revenue | 30% | 偏差 >30% 标注原因 |
| 亏损公司（OCF 负） | PS | 30% | 偏差 >30% 标注原因 |
| 盈利公司（高增长） | DCF | 25% | 偏差 >25% 触发人工复核 |
| 盈利公司（稳定） | PE | 20% | 偏差 >20% 触发人工复核 |
| 周期公司 | PB | 30% | 偏差 >30% 标注原因 |

**措施**：
1. **ValuationArbiter 唯一出口**：gate5.py 只消费 Arbiter 结论
2. **DCF 适用性判断**：亏损公司 + OCF 为负 → DCF 不适用
3. **翻转阈值方向验证**：所有翻转点必须 ≤ 当前值
4. **评级-目标价映射**：`_derive_rating()` 自动推导

### 防线 3：检查前移层（流程治理）

**原则**：致命问题必须在 Gate 5-7 拦截，不能到 Gate 8 才暴露。

**措施**：
1. **Gate 5 增加估值一致性检查**：DCF vs 可比公司偏差 >阈值 → 警告
2. **Gate 6 增加评级-目标价校验**：评级与上行空间不一致 → 警告
3. **Gate 7 增加跨章数据校验**：关键指标跨章引用不一致 → 警告
4. **Gate 8 降级为"最终确认"**：fatal 来自 Gate 5-7 的 warning 升级

### 防线 4：回归测试层（长效治理）

**原则**：每个修复必须有对应的回归测试用例，防止复现。

**回归股票池**：

| 场景 | 代表股票 | 理由 |
|------|---------|------|
| 港股亏损 | 小鹏 9868.HK | 已验证，亏损+OCF 正 |
| A 股盈利 | 协鑫能科 002015.SZ | 已验证，盈利+稳定 |
| 港股高增长 | 美团 3690.HK | 高增长+盈利 |
| A 股周期 | 宁德时代 300750.SZ | 周期+高增长 |
| 美股中概 | 理想汽车 LI | 亏损→盈利过渡 |
| 港股蓝筹 | 腾讯 0700.HK | 蓝筹+盈利+高增长 |

**测试用例**（8 个核心 + 扩展）：

```python
class TestValuationRegression:
    def test_flip_threshold_direction(self): ...      # P1
    def test_dcf_negative_not_injected(self): ...     # P4
    def test_net_cashflow_ratio_check(self): ...      # P3
    def test_format_misplacement_fix(self): ...       # P2
    def test_wind_key_canonical(self): ...            # P5
    def test_gate_dag_degraded(self): ...             # P6
    def test_context_not_split(self): ...             # P7
    def test_pgnb_abbreviated_forms(self): ...        # P8

class TestMultiStockRegression:
    def test_xpeng_gate0_7_pass(self): ...            # 小鹏
    def test_gxkn_gate0_7_pass(self): ...             # 协鑫能科
    def test_meituan_gate0_7_pass(self): ...          # 美团
    def test_ningde_gate0_7_pass(self): ...           # 宁德时代
    def test_li_auto_gate0_7_pass(self): ...          # 理想汽车
    def test_tencent_gate0_7_pass(self): ...          # 腾讯
```

---

## 三、CFA 合规证据链（P0 整改第 4 项）

| CFA 标准 | 要求 | qual v10 状态 | 需补充证据 |
|----------|------|--------------|-----------|
| **V-A 勤勉** | 估值输入有合理来源 | Wind 锚点 + Financials 契约 | 每个字段 source/timestamp/confidence |
| **V-A 勤勉** | 关键假设有依据 | WACC/g/PS 有范围校验 | 假设来源说明（行业均值/公司历史） |
| **V-B 适当** | 方法选择有依据 | ValuationArbiter 自动选择 | 方法选择矩阵文档 + 排除理由 |
| **V-B 适当** | 重大差异有披露 | ValuationVerdict.reconciliation | 偏差来源说明（增长假设/折现率差异） |
| **V-C 一致** | 多方法 reconcile | ValuationArbiter 分档处理 | 仲裁记录（主方法/辅助/排除） |
| **V-C 一致** | 记录保存 | AuditLog（JSONL） | 保存期限依适用法规（建议 ≥3 年） |

---

## 四、实施路线图（细化版，P0 整改第 5 项）

### Phase 1：数据契约强化（3 天）

| 步骤 | 交付物 | 负责人 | 退出标准 | 依赖 | 回滚 |
|------|--------|--------|---------|------|------|
| 1.1 | wind_adapter.py 全必填 | agent | Wind→Financials 零静默降级 | 无 | git revert |
| 1.2 | canonical.py 别名统一 | agent | 63 处旧 key 全映射 | 无 | git revert |
| 1.3 | financials.py source/timestamp | agent | 每个字段可追溯 | 1.1 | git revert |
| 1.4 | validator.py 12 项检查 | agent | 所有参数有范围校验 | 无 | git revert |

### Phase 2：估值引擎加固（3 天）

| 步骤 | 交付物 | 负责人 | 退出标准 | 依赖 | 回滚 |
|------|--------|--------|---------|------|------|
| 2.1 | gate5.py 统一 Arbiter | agent | 全报告一套估值 | 1.3 | git revert |
| 2.2 | arbiter.py 方向验证 | agent | 翻转点 ≤ 当前值 | 无 | git revert |
| 2.3 | quality_enhancer.py DCF 阻止 | agent | ch7 无负 DCF | 2.1 | git revert |
| 2.4 | depth_enhancer.py 敏感度 | agent | 无信息量时降级 | 无 | git revert |

### Phase 3：检查前移（2 天）

| 步骤 | 交付物 | 负责人 | 退出标准 | 依赖 | 回滚 |
|------|--------|--------|---------|------|------|
| 3.1 | gate5 估值一致性检查 | agent | DCF vs 可比偏差 >阈值警告 | 2.1 | git revert |
| 3.2 | gate6 评级校验 | agent | 评级与上行空间不一致警告 | 无 | git revert |
| 3.3 | gate7 跨章数据校验 | agent | 关键指标跨章不一致警告 | 无 | git revert |
| 3.4 | gate8 降级为最终确认 | agent | fatal 来自 Gate 5-7 warning | 3.1-3.3 | git revert |

### Phase 4：回归测试（2 天）

| 步骤 | 交付物 | 负责人 | 退出标准 | 依赖 | 回滚 |
|------|--------|--------|---------|------|------|
| 4.1 | test_regression.py | agent | 8 个 fatal 测试通过 | P1-P8 | git revert |
| 4.2 | test_multi_stock.py | agent | 6 只股票 Gate 0-7 通过 | 4.1 | git revert |
| 4.3 | test_data_trace.py | agent | 数据血缘审计通过 | 1.3 | git revert |
| 4.4 | CI/CD 集成 | agent | fatal 失败阻断发布 | 4.1-4.2 | git revert |

---

## 五、文档包清单（P0 整改第 6 项）

| 文档 | 内容 | 优先级 | 状态 |
|------|------|--------|------|
| RCA | 8 个问题的根因分析报告 | P0 | ✅ 已有（追溯矩阵） |
| 数据字典 | Wind key → canonical 映射规则 | P0 | 需补充 |
| 接口规范 | ValuationArbiter/Financials API | P1 | 需补充 |
| Runbook | 全流程运行手册 | P1 | 需补充 |
| RACI | 角色职责矩阵（agent/人工） | P2 | 需补充 |
| 架构图 | 四层防线 + GateDAG + 数据流 | P1 | 需补充 |
| ADR | 架构决策记录 | P2 | 需补充 |

---

## 六、验收标准

| 标准 | 检查方法 | 升级条件 |
|------|---------|---------|
| Gate 8 零 fatal | 6 只股票连续 3 次 | 从"研究原型"升级为"可交付系统" |
| 数据可追溯 | 每个财务字段有 source/timestamp | 数据血缘审计通过 |
| 估值自洽 | 分类型阈值（20-30%） | 估值仲裁器输出无矛盾 |
| 回归覆盖 | 8 个 fatal + 6 只股票回归 | 新增标的首过率 ≥95% |
| CFA 合规 | V-A/V-B/V-C 证据链完整 | 人工复核通过 |

---

## 七、与 dayu-agent 的差距收敛

| 维度 | dayu | qual v10 | 优化后 | 差距 |
|------|------|----------|--------|------|
| 数据控制 | 仓储协议 | PGNB regex | Financials 契约 | **基本对齐** |
| 估值仲裁 | 多方法 reconcile | ValuationArbiter | 唯一出口+方向验证 | **基本对齐** |
| Gate 依赖 | 无 Gate | GateDAG | HARD/SOFT 依赖 | **基本对齐** |
| 检查前移 | audit/confirm/repair | 后置检查 | Gate 5-7 前移 | **需实施** |
| 回归测试 | 完整测试集 | 4 个 fatal | 8+6 回归 | **需实施** |
| 交付可靠性 | 生产级 | 研究原型 | Gate 8 零 fatal | **需验证** |
