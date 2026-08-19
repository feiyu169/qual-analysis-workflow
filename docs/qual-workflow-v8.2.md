# Qual流程技术方案 v8.2

## 一、版本更新说明

根据HeavySkill审查意见v8.1，主要更新：

| 更新项 | 说明 |
|--------|------|
| **可自动检查的规则** | 将模糊评分替换为确定性规则集合 |
| **异常处理与弹性设计** | 补全超时、熔断、回滚机制 |
| **人工介入时效保障** | 定义SLA和超时降级策略 |
| **工程化细节** | 状态机、持久化、日志、版本管理 |
| **数据源降级体验** | 列出具体备用数据源，增加数据质量评分 |

---

## 二、设计理念

- **Gate-Driven**：每步都有明确的前置条件和预期结果
- **强制门禁**：第三方监督（轻量级流程合规性检查）是下一步的前置条件
- **失败重试**：不满足则根据评估意见重新执行（最多3次）
- **数据源强制**：财报是必须使用的数据，严苛验证+人工同意
- **第三方监督**：轻量级流程合规性检查，检查是否严格按照流程要求一一执行
- **确定性规则**：将模糊评分替换为可自动检查的规则集合
- **弹性设计**：补全异常处理、超时、熔断、回滚机制

---

## 三、流程架构（9个Gate）

### Gate 0: 数据源验证（严苛模式+人工同意）

| 项目 | 内容 |
|------|------|
| **前置条件** | 无 |
| **预期结果** | 财报数据获取成功，Wind数据完整 |
| **执行内容** | 1. 财报获取（必须）<br>2. Wind数据获取<br>3. 严苛验证（5个条件） |
| **第三方监督** | 规则驱动检查数据完整性 |
| **通过标准** | **确定性规则**：<br>- 财报文件存在且可解析<br>- Wind字段覆盖率≥95%<br>- 必填字段（营收、净利、现金流）全部存在<br>- 数值类型正确（非字符串）<br>- 数据时间范围覆盖最近3年 |
| **人工介入** | 数据源不可用时必须人工同意才能降级 |
| **失败处理** | 重试3次→诊断分析→人工确认→执行决策 |
| **超时设置** | 单次获取超时30秒，总超时10分钟 |
| **熔断机制** | 连续3次永久性错误立即熔断，进入人工决策 |

**严苛的不可用判定条件**：
1. 连续3次获取失败，每次间隔≥30秒
2. 错误类型为永久性错误（403、404、格式严重损坏）
3. 尝试≥2个备用数据源均失败
4. 用户明确拒绝手动上传
5. 等待时间≥10分钟

**备用数据源**：
- Wind API（主数据源）
- Tushare（备用1）
- 东方财富API（备用2）
- 同花顺API（备用3）
- 公司官网IR页面（备用4）

**人工同意流程**：
1. 系统检测到数据源问题
2. 系统执行重试（3次）
3. 系统分析错误类型
4. 系统尝试备用数据源（≥2个）
5. 系统发送审批请求给人工
6. 人工决策：同意降级/同意终止/提供手动上传/要求继续重试
7. 系统执行人工决策
8. 记录决策原因和执行结果

**人工介入SLA**：
- 响应时限：30分钟
- 超时处理：自动提醒，再等15分钟
- 二次超时：自动挂起，通知管理员

---

### Gate 1: 类型推断 + 数据提取

| 项目 | 内容 |
|------|------|
| **前置条件** | Gate 0通过 |
| **预期结果** | 市场类型正确，事实提取完整 |
| **执行内容** | 1. 推断市场类型<br>2. 提取结构化事实<br>3. 交叉验证 |
| **第三方监督** | 规则驱动检查类型和事实 |
| **通过标准** | **确定性规则**：<br>- 市场类型字段存在且非空<br>- 市场类型值在预定义列表中（A股/港股/美股）<br>- 必填事实字段全部提取（营收、净利、总资产、现金流等）<br>- 数值与财报原始数据偏差≤2%<br>- 提取结果符合预定义Schema |
| **失败处理** | 重新推断类型，补充事实提取（最多3次） |
| **超时设置** | 单次提取超时60秒，总超时5分钟 |

**可自动检查的规则集合**：

```python
GATE1_RULES = {
    "market_type": {
        "check": "field_exists_and_not_empty",
        "field": "market_type",
        "allowed_values": ["A股", "港股", "美股"],
    },
    "required_fields": {
        "check": "all_fields_exist",
        "fields": [
            "revenue", "net_income", "total_assets",
            "operating_cash_flow", "operating_income",
        ],
    },
    "data_accuracy": {
        "check": "value_deviation",
        "max_deviation": 0.02,  # 2%
        "source": "filing_data",
    },
    "schema_compliance": {
        "check": "schema_validation",
        "schema": "FactExtractionSchema",
    },
}
```

---

### Gate 2: 数据收集 + 参数提取（确定性计算）

| 项目 | 内容 |
|------|------|
| **前置条件** | Gate 1通过 |
| **预期结果** | Wind数据完整，DCF参数合理 |
| **执行内容** | 1. 收集Wind数据<br>2. 使用Python代码提取DCF参数<br>3. 参数校验 |
| **第三方监督** | 规则驱动检查参数合理性 |
| **通过标准** | **确定性规则**：<br>- FCF ≠ 0（使用Python代码计算）<br>- WACC ∈ [5%, 15%]<br>- 永续增长率 ∈ [1%, 5%]<br>- 营收增长率 ∈ [-30%, 100%]<br>- 税率 ∈ [10%, 35%]<br>- 所有参数有计算公式和数据来源 |
| **人工介入** | 参数异常时必须人工确认 |
| **失败处理** | 补充数据，修正参数（最多3次） |
| **超时设置** | 单次计算超时30秒，总超时3分钟 |

**确定性计算要求**：

```python
def extract_dcf_params(wind_data: dict) -> dict:
    """使用Python代码提取DCF参数（确定性计算）"""
    # 1. 计算FCF
    ocf = wind_data["cashflow"]["经营活动现金流量净额"][-1]
    capex = wind_data["cashflow"]["资本支出"][-1]
    fcf = ocf - capex
    
    # 2. 计算WACC（使用CAPM）
    risk_free_rate = 0.03  # 无风险利率
    beta = 1.2  # Beta系数
    market_risk_premium = 0.06  # 市场风险溢价
    cost_of_equity = risk_free_rate + beta * market_risk_premium
    
    debt_ratio = wind_data["balance"]["总负债"][-1] / wind_data["balance"]["总资产"][-1]
    cost_of_debt = 0.05  # 债务成本
    tax_rate = 0.25  # 税率
    
    wacc = (1 - debt_ratio) * cost_of_equity + debt_ratio * cost_of_debt * (1 - tax_rate)
    
    # 3. 计算永续增长率
    revenue_growth_rates = calculate_growth_rates(wind_data["income"]["营业收入"])
    terminal_growth = min(revenue_growth_rates) * 0.5  # 取历史增长率的一半
    
    # 4. 参数校验
    assert 0.05 <= wacc <= 0.15, f"WACC={wacc}超出合理范围"
    assert 0.01 <= terminal_growth <= 0.05, f"永续增长率={terminal_growth}超出合理范围"
    assert fcf != 0, "FCF不能为0"
    
    return {
        "fcf": fcf,
        "wacc": wacc,
        "terminal_growth": terminal_growth,
        "calculation_formula": "FCF = OCF - Capex",
        "data_source": "Wind API",
    }
```

**人工介入SLA**：
- 响应时限：15分钟
- 超时处理：自动提醒，再等10分钟
- 二次超时：使用默认参数（需人工确认）

---

### Gate 3: 逐章写作（大纲→分章→交叉验证→组装）

| 项目 | 内容 |
|------|------|
| **前置条件** | Gate 2通过 |
| **预期结果** | 11章内容生成，格式正确，一致性验证通过 |
| **执行内容** | 1. 生成大纲<br>2. 分章生成（并行）<br>3. 交叉一致性验证<br>4. 组装 |
| **第三方监督** | 规则驱动检查章节完整性和一致性 |
| **通过标准** | **确定性规则**：<br>- 11章全部生成（第0-10章）<br>- 每章字数≥500字<br>- 关键数据点在各章中引用一致（营收、净利、估值等）<br>- 必含章节结构齐全（目录、正文、图表）<br>- 格式符合模板要求<br>- 无明显的[Placeholder]或XX亿元占位符 |
| **失败处理** | 重新生成章节，修复一致性问题（最多3次） |
| **超时设置** | 单章生成超时120秒，总超时15分钟 |

**可自动检查的规则集合**：

```python
GATE3_RULES = {
    "chapter_completeness": {
        "check": "all_chapters_exist",
        "chapters": list(range(0, 11)),  # 第0-10章
        "min_word_count": 500,
    },
    "data_consistency": {
        "check": "cross_chapter_data_match",
        "critical_fields": [
            "revenue", "net_income", "total_assets",
            "wacc", "terminal_growth", "target_price",
        ],
        "max_deviation": 0.01,  # 1%
    },
    "structure_completeness": {
        "check": "required_sections_exist",
        "sections": ["目录", "正文", "图表", "风险提示"],
    },
    "format_compliance": {
        "check": "template_validation",
        "template": "BuySideReportTemplate",
    },
    "no_placeholder": {
        "check": "no_placeholder_found",
        "patterns": ["[Placeholder]", "XX亿元", "待填写", " TBD"],
    },
}
```

**并行生成与一致性修复**：
1. 大纲生成：先生成11章大纲，明确每章内容
2. 分章并行生成：使用LLM并行生成各章
3. 一致性检查：提取各章关键数据点，检查一致性
4. 不一致修复：如果不一致，重新生成不一致的章节
5. 组装：将各章组装成完整报告

---

### Gate 4: 审计修复 + 深度审查（合并）

| 项目 | 内容 |
|------|------|
| **前置条件** | Gate 3通过 |
| **预期结果** | 所有审查问题修复，评分达标 |
| **执行内容** | 1. 形式审查（格式、数据引用）<br>2. 实质审查（逻辑、估值）<br>3. 修复循环 |
| **第三方监督** | 规则驱动检查审查结果 |
| **通过标准** | **确定性规则**：<br>- **形式审查**：<br>  - 格式错误数=0<br>  - 数据引用全部有来源<br>  - 日期锚点一致<br>  - 币种统一<br>- **实质审查**：<br>  - 估值参数与Gate 2一致<br>  - 营收数据与财报一致<br>  - 逻辑矛盾数≤2<br>  - 风险提示完整 |
| **失败处理** | 继续修复循环（最多3次），超限升级人工 |
| **超时设置** | 单次审查超时120秒，总超时20分钟 |

**可自动检查的规则集合**：

```python
GATE4_RULES = {
    "formal_review": {
        "format_errors": {
            "check": "count_equals_zero",
            "field": "format_error_count",
        },
        "data_references": {
            "check": "all_have_source",
            "field": "data_references",
        },
        "date_consistency": {
            "check": "date_anchor_consistent",
            "field": "date_mentions",
        },
        "currency_consistency": {
            "check": "currency_unified",
            "field": "currency_mentions",
            "allowed": ["人民币", "港元", "美元"],
        },
    },
    "substantive_review": {
        "valuation_consistency": {
            "check": "param_match",
            "source": "gate2_params",
            "fields": ["wacc", "terminal_growth", "fcf"],
        },
        "revenue_consistency": {
            "check": "value_match",
            "source": "filing_data",
            "max_deviation": 0.02,
        },
        "logic_contradiction": {
            "check": "count_lte",
            "field": "logic_contradiction_count",
            "threshold": 2,
        },
        "risk_disclosure": {
            "check": "section_exists",
            "section": "风险提示",
            "min_length": 200,
        },
    },
}
```

**修复循环机制**：
1. 执行形式审查
2. 执行实质审查
3. 如果发现问题，使用LLM修复
4. 重新审查
5. 重复直到通过或达到最大轮数（3次）
6. 如果3次修复仍不通过，升级人工处理

---

### Gate 5: 质量增强 + 组件集成（确定性计算）

| 项目 | 内容 |
|------|------|
| **前置条件** | Gate 4通过 |
| **预期结果** | 估值计算正确，组件集成成功 |
| **执行内容** | 1. 使用Python代码计算估值<br>2. 组件集成（T9-T14）<br>3. 交叉验证 |
| **第三方监督** | 规则驱动检查估值合理性和组件状态 |
| **通过标准** | **确定性规则**：<br>- 估值计算使用Python代码执行<br>- DCF估值结果在合理范围内（±50%当前股价）<br>- 可比公司估值结果在合理范围内<br>- 组件集成成功率100%<br>- 估值结果与Gate 2参数一致 |
| **失败处理** | 重新计算估值，修复组件（最多3次） |
| **超时设置** | 单次计算超时60秒，总超时5分钟 |

**确定性计算要求**：

```python
def calculate_valuation(dcf_params: dict, wind_data: dict) -> dict:
    """使用Python代码计算估值（确定性计算）"""
    # 1. DCF估值
    fcf = dcf_params["fcf"]
    wacc = dcf_params["wacc"]
    terminal_growth = dcf_params["terminal_growth"]
    
    # 计算终值
    terminal_value = fcf * (1 + terminal_growth) / (wacc - terminal_growth)
    
    # 折现
    pv_terminal_value = terminal_value / ((1 + wacc) ** 5)
    
    # 计算股权价值
    equity_value = pv_terminal_value
    
    # 计算每股价值
    shares = wind_data["balance"]["总股本"][-1]
    per_share_value = equity_value / shares
    
    # 2. 估值范围检查
    current_price = wind_data["quote"]["最新价"]
    deviation = abs(per_share_value - current_price) / current_price
    
    assert deviation <= 0.5, f"估值偏差{deviation*100:.1f}%超过50%"
    
    # 3. 组件集成检查
    components = ["T9_FactTable", "T10_ComparableConfig", "T11_MarketData",
                  "T12_FlipThreshold", "T13_InsightAuditor", "T14_ROICChecker"]
    
    for component in components:
        assert check_component_ready(component), f"组件{component}未就绪"
    
    return {
        "dcf_value": per_share_value,
        "comparable_value": calculate_comparable_valuation(wind_data),
        "valuation_range": (per_share_value * 0.8, per_share_value * 1.2),
        "calculation_method": "DCF + 可比公司",
        "components_integrated": components,
    }
```

---

### Gate 6: 综合结论 + 决策章 + 概览章

| 项目 | 内容 |
|------|------|
| **前置条件** | Gate 5通过 |
| **预期结果** | 决策逻辑合理，概览完整 |
| **执行内容** | 1. 生成综合结论章<br>2. 生成第10章（决策章）<br>3. 生成第0章 |
| **第三方监督** | 规则驱动检查决策逻辑 |
| **通过标准** | **确定性规则**：<br>- 决策章存在且字数≥1000字<br>- 概览章存在且字数≥500字<br>- 投资评级在预定义列表中（买入/增持/中性/减持/卖出）<br>- 投资评级与估值结果逻辑一致<br>- 目标价与估值结果偏差≤20%<br>- 风险提示完整 |
| **人工介入** | 决策逻辑异常时必须人工确认 |
| **失败处理** | 重新生成决策章、概览章（最多3次） |
| **超时设置** | 单次生成超时120秒，总超时10分钟 |

**可自动检查的规则集合**：

```python
GATE6_RULES = {
    "decision_chapter": {
        "check": "chapter_exists_and_length",
        "chapter": 10,
        "min_length": 1000,
    },
    "overview_chapter": {
        "check": "chapter_exists_and_length",
        "chapter": 0,
        "min_length": 500,
    },
    "investment_rating": {
        "check": "value_in_list",
        "field": "investment_rating",
        "allowed_values": ["买入", "增持", "中性", "减持", "卖出"],
    },
    "rating_consistency": {
        "check": "rating_valuation_consistent",
        "rating_field": "investment_rating",
        "valuation_field": "valuation_deviation",
    },
    "target_price": {
        "check": "deviation_lte",
        "field": "target_price",
        "reference": "dcf_value",
        "max_deviation": 0.20,
    },
    "risk_disclosure": {
        "check": "section_exists",
        "section": "风险提示",
        "min_length": 300,
    },
}
```

**人工介入SLA**：
- 响应时限：15分钟
- 超时处理：自动提醒，再等10分钟
- 二次超时：使用默认评级（需人工确认）

---

### Gate 7: 问题转化 + 记忆存储

| 项目 | 内容 |
|------|------|
| **前置条件** | Gate 6通过 |
| **预期结果** | 问题转化成功，记忆存储成功 |
| **执行内容** | 1. 问题转化<br>2. 记忆存储<br>3. 生成MCP指令 |
| **第三方监督** | 规则驱动检查问题转化和记忆存储 |
| **通过标准** | **确定性规则**：<br>- 问题转化成功率≥90%<br>- 问题格式符合Schema<br>- 记忆存储成功<br>- MCP指令格式正确 |
| **失败处理** | 重新转化问题，重新存储记忆（最多3次） |
| **超时设置** | 单次转化超时30秒，总超时3分钟 |

**问题转化格式**：

```python
@dataclass
class ReviewIssue:
    """审查问题"""
    issue_id: str
    issue_type: str  # "data_error", "logic_contradiction", "format_issue"
    severity: str  # "critical", "warning", "info"
    chapter: int
    description: str
    suggestion: str
    data_source: str  # 数据来源
    verification_method: str  # 验证方法
```

**记忆存储格式**：

```python
@dataclass
class AnalysisMemory:
    """分析记忆"""
    ticker: str
    company_name: str
    analysis_date: str
    key_findings: List[str]
    review_issues: List[ReviewIssue]
    lessons_learned: List[str]
    data_sources: List[str]
```

---

### Gate 8: 最终验证（人工确认）

| 项目 | 内容 |
|------|------|
| **前置条件** | Gate 7通过 |
| **预期结果** | 报告质量达标，可交付 |
| **执行内容** | 1. 最终质量评估<br>2. 人工确认<br>3. 生成交付报告 |
| **第三方监督** | 规则驱动检查最终质量 |
| **通过标准** | **确定性规则**：<br>- 所有Gate检查通过<br>- 无Critical级别问题<br>- 人工确认通过<br>- 报告格式正确<br>- 报告大小合理（50KB-500KB） |
| **人工介入** | 必须人工确认才能交付 |
| **失败处理** | 返回Gate 4重新审查 |
| **超时设置** | 人工确认超时30分钟 |

**人工介入SLA**：
- 响应时限：30分钟
- 超时处理：自动提醒，再等15分钟
- 二次超时：自动挂起，通知管理员

---

## 四、第三方监督机制（轻量级）

### 设计理念

| 项目 | 说明 |
|------|------|
| **目的** | 检查是否严格按照流程要求一一执行 |
| **方式** | 规则驱动检查，无LLM推理 |
| **速度** | 秒级响应 |
| **成本** | 低（无Token消耗） |

### 职责

1. **前置条件检查**：检查前置Gate是否通过，必需数据是否可用
2. **执行内容检查**：检查每个执行步骤是否完成，执行顺序是否正确
3. **通过标准检查**：检查量化指标是否达到，通过条件是否满足
4. **失败处理检查**：检查失败是否被正确处理，重试是否执行
5. **人工介入检查**：检查人工介入点是否设置，人工同意是否获取

### 实现

```python
class FlowComplianceChecker:
    """流程合规性检查器（轻量级）"""
    
    def __init__(self, flow_definition: dict):
        self.flow_definition = flow_definition
    
    def check_gate(self, gate_num: int, execution_log: dict) -> ComplianceResult:
        """检查单个Gate的合规性"""
        gate_spec = self.flow_definition[f"gate_{gate_num}"]
        checks = []
        
        # 1. 检查前置条件
        checks.extend(self._check_preconditions(gate_spec, execution_log))
        
        # 2. 检查执行内容
        checks.extend(self._check_execution_content(gate_spec, execution_log))
        
        # 3. 检查通过标准（确定性规则）
        checks.extend(self._check_pass_criteria(gate_spec, execution_log))
        
        # 4. 检查失败处理
        checks.extend(self._check_failure_handling(gate_spec, execution_log))
        
        # 5. 检查人工介入
        checks.extend(self._check_human_intervention(gate_spec, execution_log))
        
        # 计算合规性
        passed = all(check.passed for check in checks)
        failed_checks = [check for check in checks if not check.passed]
        
        return ComplianceResult(
            gate_num=gate_num,
            passed=passed,
            checks=checks,
            failed_checks=failed_checks,
        )
```

---

## 五、异常处理与弹性设计

### 超时机制

| Gate | 单次超时 | 总超时 | 超时处理 |
|------|----------|--------|----------|
| Gate 0 | 30秒 | 10分钟 | 熔断，进入人工决策 |
| Gate 1 | 60秒 | 5分钟 | 重试，最多3次 |
| Gate 2 | 30秒 | 3分钟 | 重试，最多3次 |
| Gate 3 | 120秒/章 | 15分钟 | 重试，最多3次 |
| Gate 4 | 120秒 | 20分钟 | 升级人工 |
| Gate 5 | 60秒 | 5分钟 | 重试，最多3次 |
| Gate 6 | 120秒 | 10分钟 | 重试，最多3次 |
| Gate 7 | 30秒 | 3分钟 | 重试，最多3次 |
| Gate 8 | - | 30分钟 | 挂起，通知管理员 |

### 熔断机制

```python
class CircuitBreaker:
    """熔断器"""
    
    def __init__(self, failure_threshold: int = 3, reset_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half-open
    
    def record_failure(self):
        """记录失败"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "open"
            logger.warning(f"熔断器打开：连续{self.failure_count}次失败")
    
    def record_success(self):
        """记录成功"""
        self.failure_count = 0
        self.state = "closed"
    
    def can_execute(self) -> bool:
        """检查是否可以执行"""
        if self.state == "closed":
            return True
        
        if self.state == "open":
            # 检查是否可以半开
            if time.time() - self.last_failure_time > self.reset_timeout:
                self.state = "half-open"
                return True
            return False
        
        # half-open状态
        return True
```

### 回滚机制

```python
class RollbackManager:
    """回滚管理器"""
    
    def __init__(self):
        self.checkpoints = {}
    
    def save_checkpoint(self, gate_num: int, state: dict):
        """保存检查点"""
        self.checkpoints[gate_num] = {
            "state": state,
            "timestamp": time.time(),
        }
    
    def rollback_to(self, gate_num: int) -> dict:
        """回滚到指定Gate"""
        if gate_num not in self.checkpoints:
            raise ValueError(f"Gate {gate_num}没有检查点")
        
        return self.checkpoints[gate_num]["state"]
    
    def get_latest_checkpoint(self) -> Tuple[int, dict]:
        """获取最新检查点"""
        if not self.checkpoints:
            return None, None
        
        latest_gate = max(self.checkpoints.keys())
        return latest_gate, self.checkpoints[latest_gate]["state"]
```

---

## 六、状态机与持久化

### 状态机定义

```python
class GateState(Enum):
    """Gate状态"""
    PENDING = "pending"  # 待执行
    RUNNING = "running"  # 执行中
    PASSED = "passed"  # 通过
    FAILED = "failed"  # 失败
    SKIPPED = "skipped"  # 跳过
    WAITING_HUMAN = "waiting_human"  # 等待人工
    ROLLBACK = "rollback"  # 回滚中

class WorkflowState(Enum):
    """工作流状态"""
    INITIALIZED = "initialized"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
```

### 持久化存储

```python
class WorkflowPersistence:
    """工作流持久化"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workflow_runs (
                run_id TEXT PRIMARY KEY,
                ticker TEXT,
                company_name TEXT,
                status TEXT,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                state_json TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gate_executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT,
                gate_num INTEGER,
                status TEXT,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                result_json TEXT,
                FOREIGN KEY (run_id) REFERENCES workflow_runs(run_id)
            )
        """)
        
        conn.commit()
        conn.close()
    
    def save_state(self, run_id: str, state: dict):
        """保存工作流状态"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE workflow_runs
            SET status = ?, updated_at = ?, state_json = ?
            WHERE run_id = ?
        """, (state["status"], datetime.now(), json.dumps(state), run_id))
        
        conn.commit()
        conn.close()
    
    def load_state(self, run_id: str) -> dict:
        """加载工作流状态"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT state_json FROM workflow_runs WHERE run_id = ?
        """, (run_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return json.loads(row[0])
        return None
```

---

## 七、日志与审计追踪

### 日志格式

```python
@dataclass
class AuditLog:
    """审计日志"""
    log_id: str
    run_id: str
    gate_num: int
    action: str  # "start", "complete", "fail", "retry", "human_intervention"
    timestamp: datetime
    details: dict
    user_id: Optional[str]  # 人工介入时记录
```

### 日志记录

```python
class AuditLogger:
    """审计日志记录器"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()
    
    def log(self, run_id: str, gate_num: int, action: str, details: dict, user_id: str = None):
        """记录审计日志"""
        log_entry = AuditLog(
            log_id=str(uuid.uuid4()),
            run_id=run_id,
            gate_num=gate_num,
            action=action,
            timestamp=datetime.now(),
            details=details,
            user_id=user_id,
        )
        
        self._save_log(log_entry)
    
    def get_logs(self, run_id: str) -> List[AuditLog]:
        """获取审计日志"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM audit_logs WHERE run_id = ? ORDER BY timestamp
        """, (run_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_log(row) for row in rows]
```

---

## 八、安全合规

### 数据安全

| 项目 | 措施 |
|------|------|
| **数据传输** | 使用HTTPS加密传输 |
| **数据存储** | 敏感数据加密存储 |
| **数据访问** | 基于角色的访问控制 |
| **数据保留** | 定期清理过期数据 |

### 凭证管理

| 项目 | 措施 |
|------|------|
| **Wind API Key** | 使用环境变量存储，不硬编码 |
| **财报数据** | 临时存储，使用后删除 |
| **人工凭证** | 使用OAuth2认证 |

---

## 九、流程定义示例

```python
FLOW_DEFINITION_V8_2 = {
    "gate_0": {
        "name": "数据源验证",
        "preconditions": [],
        "execution_steps": [
            {"name": "财报获取", "order": 1, "required": True},
            {"name": "Wind数据获取", "order": 2, "required": True},
            {"name": "严苛验证", "order": 3, "required": True},
        ],
        "pass_criteria": {
            "filing_exists": {"type": "file_exists", "path": "filing_path"},
            "wind_coverage": {"type": "gte", "value": 0.95},
            "required_fields": {"type": "all_exist", "fields": ["revenue", "net_income", "cash_flow"]},
            "value_types": {"type": "all_numeric", "fields": ["revenue", "net_income", "cash_flow"]},
            "data_range": {"type": "covers_years", "years": 3},
        },
        "retry_specs": [{"name": "数据获取重试", "max_retries": 3}],
        "timeout": {"single": 30, "total": 600},
        "circuit_breaker": {"failure_threshold": 3, "reset_timeout": 60},
        "human_interventions": [{
            "name": "数据源降级同意",
            "required": True,
            "trigger": "data_unavailable",
            "sla": {"response_timeout": 1800, "reminder_timeout": 900},
        }],
    },
    # ... 其他Gate定义
}
```

---

## 十、总结

| 特性 | 说明 |
|------|------|
| **Gate-Driven** | 每步都有明确的前置条件和预期结果 |
| **强制门禁** | 第三方监督评估是下一步的前置条件 |
| **失败重试** | 不满足则根据评估意见重新执行（最多3次） |
| **数据源强制** | 财报是必须使用的数据，严苛验证+人工同意 |
| **审查修复循环** | 多轮次审查，直至通过，超限升级人工 |
| **第三方监督** | 轻量级流程合规性检查 |
| **确定性规则** | 将模糊评分替换为可自动检查的规则集合 |
| **弹性设计** | 补全异常处理、超时、熔断、回滚机制 |
| **人工介入** | 关键节点设置人工确认，定义SLA |
| **状态机** | 实现完整的状态机与持久化 |
| **日志审计** | 增加日志、版本管理和审计追踪 |
| **安全合规** | 明确安全合规要求 |

---

## 十一、与v8.1对比

| 项目 | v8.1 | v8.2 |
|------|------|------|
| **通过标准** | 模糊评分（≥95%、≥80%） | 确定性规则集合 |
| **异常处理** | 基本重试 | 超时+熔断+回滚 |
| **人工介入** | 无SLA | 定义SLA和超时降级 |
| **状态管理** | 无 | 状态机+持久化 |
| **日志审计** | 无 | 完整审计追踪 |
| **数据源** | 基本备用源 | 具体备用源列表+数据质量评分 |
| **安全合规** | 无 | 明确安全合规要求 |
