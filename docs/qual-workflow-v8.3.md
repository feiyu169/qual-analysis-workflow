# Qual流程技术方案 v8.3

## 一、版本更新说明

根据HeavySkill审查意见v8.2，主要更新：

| 优先级 | 更新项 | 说明 |
|--------|--------|------|
| **P0** | 逻辑矛盾检测模式库 | 定义10类常见矛盾模板 |
| **P0** | 异常处理策略矩阵 | 错误类型→重试策略→超阈值动作 |
| **P0** | 数据库升级 | SQLite→PostgreSQL/MySQL |
| **P1** | 工作时段配置 | 非工作时间暂停SLA计时 |
| **P1** | 监控告警 | 各Gate通过率、耗时、熔断次数 |
| **P1** | 审计日志防篡改 | 哈希链或只追加写入 |
| **P2** | 减少人工介入点 | 改为异常驱动的按需介入 |
| **P2** | 安全合规 | 密钥管理、数据脱敏、合规认证 |

---

## 二、设计理念

- **Gate-Driven**：每步都有明确的前置条件和预期结果
- **强制门禁**：第三方监督（轻量级流程合规性检查）是下一步的前置条件
- **失败重试**：不满足则根据评估意见重新执行（最多3次）
- **数据源强制**：财报是必须使用的数据，严苛验证+人工同意
- **第三方监督**：轻量级流程合规性检查，规则驱动，秒级响应
- **确定性规则**：将模糊评分替换为可自动检查的规则集合
- **弹性设计**：补全异常处理、超时、熔断、回滚机制
- **生产就绪**：数据库升级、监控告警、安全合规

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
| **人工介入** | 数据源不可用时必须人工同意才能降级（异常驱动） |
| **失败处理** | 重试3次→诊断分析→人工确认→执行决策 |
| **超时设置** | 单次获取超时30秒，总超时10分钟 |
| **熔断机制** | 连续3次永久性错误立即熔断，冷却期60秒 |

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

**异常驱动的人工介入**：
- 仅当自动验证失败时才触发人工介入
- 自动验证通过则直接进入下一Gate

**人工介入SLA**：
- 工作时间（9:00-18:00）：响应时限30分钟
- 非工作时间：响应时限4小时
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

---

### Gate 2: 数据收集 + 参数提取（确定性计算）

| 项目 | 内容 |
|------|------|
| **前置条件** | Gate 1通过 |
| **预期结果** | Wind数据完整，DCF参数合理 |
| **执行内容** | 1. 收集Wind数据<br>2. 使用Python代码提取DCF参数<br>3. 参数校验 |
| **第三方监督** | 规则驱动检查参数合理性 |
| **通过标准** | **确定性规则**：<br>- \|FCF\| > 0.01（容差判断）<br>- WACC ∈ [5%, 15%]<br>- 永续增长率 ∈ [1%, 5%]<br>- 营收增长率 ∈ [-30%, 100%]<br>- 税率 ∈ [10%, 35%]<br>- 所有参数有计算公式和数据来源 |
| **人工介入** | 参数异常时必须人工确认（异常驱动） |
| **失败处理** | 补充数据，修正参数（最多3次） |
| **超时设置** | 单次计算超时30秒，总超时3分钟 |

**异常驱动的人工介入**：
- 仅当参数超出合理范围时才触发人工介入
- 参数在合理范围内则直接进入下一Gate

**人工介入SLA**：
- 工作时间：响应时限20分钟
- 非工作时间：响应时限4小时

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

---

### Gate 4: 审计修复 + 深度审查（合并）

| 项目 | 内容 |
|------|------|
| **前置条件** | Gate 3通过 |
| **预期结果** | 所有审查问题修复，评分达标 |
| **执行内容** | 1. 形式审查（格式、数据引用）<br>2. 实质审查（逻辑、估值）<br>3. 修复循环 |
| **第三方监督** | 规则驱动检查审查结果 |
| **通过标准** | **确定性规则**：<br>- **形式审查**：<br>  - 格式错误数=0<br>  - 数据引用全部有来源<br>  - 日期锚点一致<br>  - 币种统一<br>- **实质审查**：<br>  - 估值参数与Gate 2一致<br>  - 营收数据与财报一致<br>  - 逻辑矛盾数≤2（基于矛盾模式库）<br>  - 风险提示覆盖≥8个风险类别 |
| **失败处理** | 继续修复循环（最多3次），超限升级人工 |
| **超时设置** | 单次审查超时120秒，总超时20分钟 |

**逻辑矛盾检测模式库**（10类常见矛盾）：

```python
LOGIC_CONTRADICTION_PATTERNS = [
    {
        "id": "LC01",
        "name": "营收增长但利润下降无解释",
        "pattern": "revenue_growth > 0 AND profit_growth < 0 AND no_explanation",
        "severity": "warning",
    },
    {
        "id": "LC02",
        "name": "评级上调但目标价下调",
        "pattern": "rating_upgrade AND target_price_downgrade",
        "severity": "critical",
    },
    {
        "id": "LC03",
        "name": "估值低估但评级中性",
        "pattern": "valuation_undervalued AND rating_neutral",
        "severity": "warning",
    },
    {
        "id": "LC04",
        "name": "现金流为负但推荐买入",
        "pattern": "ocf_negative AND rating_buy",
        "severity": "critical",
    },
    {
        "id": "LC05",
        "name": "营收预测增长但行业下行",
        "pattern": "revenue_forecast_growth AND industry_decline",
        "severity": "warning",
    },
    {
        "id": "LC06",
        "name": "毛利率上升但营业利润率下降",
        "pattern": "gross_margin_up AND operating_margin_down",
        "severity": "warning",
    },
    {
        "id": "LC07",
        "name": "资产增长但ROE提升",
        "pattern": "asset_growth AND roe_improvement AND no_explanation",
        "severity": "warning",
    },
    {
        "id": "LC08",
        "name": "负债率上升但评级上调",
        "pattern": "leverage_increase AND rating_upgrade",
        "severity": "warning",
    },
    {
        "id": "LC09",
        "name": "现金流与净利润严重背离",
        "pattern": "abs(ocf - net_income) / net_income > 0.5",
        "severity": "critical",
    },
    {
        "id": "LC10",
        "name": "估值假设与历史趋势严重偏离",
        "pattern": "growth_assumption > 3 * historical_growth",
        "severity": "critical",
    },
]
```

**风险提示检查清单**（必须覆盖的风险类别）：

```python
RISK_DISCLOSURE_CHECKLIST = [
    {"category": "市场风险", "min_length": 50, "keywords": ["市场", "波动", "系统性"]},
    {"category": "经营风险", "min_length": 50, "keywords": ["经营", "管理", "运营"]},
    {"category": "财务风险", "min_length": 50, "keywords": ["财务", "负债", "现金流"]},
    {"category": "行业风险", "min_length": 50, "keywords": ["行业", "竞争", "政策"]},
    {"category": "估值风险", "min_length": 50, "keywords": ["估值", "假设", "预测"]},
    {"category": "数据风险", "min_length": 30, "keywords": ["数据", "来源", "准确性"]},
    {"category": "流动性风险", "min_length": 30, "keywords": ["流动性", "变现", "交易"]},
    {"category": "汇率风险", "min_length": 30, "keywords": ["汇率", "外汇", "跨境"]},
]
```

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

---

### Gate 6: 综合结论 + 决策章 + 概览章

| 项目 | 内容 |
|------|------|
| **前置条件** | Gate 5通过 |
| **预期结果** | 决策逻辑合理，概览完整 |
| **执行内容** | 1. 生成综合结论章<br>2. 生成第10章（决策章）<br>3. 生成第0章 |
| **第三方监督** | 规则驱动检查决策逻辑 |
| **通过标准** | **确定性规则**：<br>- 决策章存在且字数≥1000字<br>- 概览章存在且字数≥500字<br>- 投资评级在预定义列表中（买入/增持/中性/减持/卖出）<br>- 投资评级与估值结果逻辑一致（基于评级映射规则）<br>- 目标价与估值结果偏差≤20%<br>- 风险提示覆盖≥8个风险类别 |
| **人工介入** | 决策逻辑异常时必须人工确认（异常驱动） |
| **失败处理** | 重新生成决策章、概览章（最多3次） |
| **超时设置** | 单次生成超时120秒，总超时10分钟 |

**评级映射规则**：

```python
RATING_VALUATION_MAPPING = {
    "买入": {"undervaluation": 0.30, "description": "DCF低估≥30%"},
    "增持": {"undervaluation": 0.15, "description": "DCF低估15-30%"},
    "中性": {"undervaluation": -0.15, "description": "DCF估值偏差±15%"},
    "减持": {"overvaluation": 0.15, "description": "DCF高估15-30%"},
    "卖出": {"overvaluation": 0.30, "description": "DCF高估≥30%"},
}
```

**异常驱动的人工介入**：
- 仅当评级与估值不一致时才触发人工介入
- 评级与估值一致则直接进入下一Gate

---

### Gate 7: 问题转化 + 记忆存储

| 项目 | 内容 |
|------|------|
| **前置条件** | Gate 6通过 |
| **预期结果** | 问题转化成功，记忆存储成功 |
| **执行内容** | 1. 问题转化<br>2. 记忆存储<br>3. 生成MCP指令 |
| **第三方监督** | 规则驱动检查问题转化和记忆存储 |
| **通过标准** | **确定性规则**：<br>- 本次任务中无问题转化错误<br>- 所有转化结果Schema校验通过<br>- MCP指令格式全部合法<br>- 记忆存储成功 |
| **失败处理** | 重新转化问题，重新存储记忆（最多3次） |
| **超时设置** | 单次转化超时30秒，总超时3分钟 |

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
| **超时设置** | 人工确认超时30分钟（工作时间） |

---

## 四、异常处理策略矩阵

### 错误分类

```python
class ErrorType(Enum):
    """错误类型"""
    TRANSIENT = "transient"  # 临时性错误（网络抖动、服务暂时不可用）
    PERMANENT = "permanent"  # 永久性错误（凭证失效、数据格式严重损坏）
    BUSINESS = "business"    # 业务错误（参数异常、逻辑矛盾）
```

### 异常处理策略矩阵

| 错误类型 | 重试策略 | 超时后动作 | 熔断条件 | 恢复策略 |
|----------|----------|------------|----------|----------|
| **临时性错误** | 指数退避重试（3次） | 降级或升级人工 | 连续5次 | 冷却期30秒后半开 |
| **永久性错误** | 不重试 | 立即升级人工 | 连续3次 | 人工重置 |
| **业务错误** | 重试3次 | 升级人工 | 不熔断 | 人工修复后继续 |

### 指数退避策略

```python
def calculate_backoff(attempt: int, base_delay: int = 1, max_delay: int = 60) -> int:
    """计算指数退避延迟"""
    delay = min(base_delay * (2 ** attempt), max_delay)
    jitter = random.uniform(0, delay * 0.1)  # 添加抖动
    return int(delay + jitter)
```

### 超时后行为定义

```python
TIMEOUT_BEHAVIOR = {
    "gate_0": {
        "single_timeout": {"action": "retry", "max_retries": 3},
        "total_timeout": {"action": "escalate_to_human", "notify_admin": True},
    },
    "gate_1": {
        "single_timeout": {"action": "retry", "max_retries": 3},
        "total_timeout": {"action": "fail_gate", "notify_admin": True},
    },
    "gate_2": {
        "single_timeout": {"action": "retry", "max_retries": 3},
        "total_timeout": {"action": "escalate_to_human", "notify_admin": True},
    },
    "gate_3": {
        "single_timeout": {"action": "retry_chapter", "max_retries": 3},
        "total_timeout": {"action": "fail_gate", "notify_admin": True},
    },
    "gate_4": {
        "single_timeout": {"action": "retry_repair", "max_retries": 3},
        "total_timeout": {"action": "escalate_to_human", "notify_admin": True},
    },
    "gate_5": {
        "single_timeout": {"action": "retry", "max_retries": 3},
        "total_timeout": {"action": "fail_gate", "notify_admin": True},
    },
    "gate_6": {
        "single_timeout": {"action": "retry", "max_retries": 3},
        "total_timeout": {"action": "escalate_to_human", "notify_admin": True},
    },
    "gate_7": {
        "single_timeout": {"action": "retry", "max_retries": 3},
        "total_timeout": {"action": "fail_gate", "notify_admin": True},
    },
    "gate_8": {
        "single_timeout": {"action": "remind_human", "interval": 900},
        "total_timeout": {"action": "suspend", "notify_admin": True},
    },
}
```

### 熔断恢复策略

```python
class CircuitBreaker:
    """熔断器（带恢复机制）"""
    
    def __init__(
        self,
        failure_threshold: int = 3,
        reset_timeout: int = 60,
        half_open_max_attempts: int = 1,
    ):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.half_open_max_attempts = half_open_max_attempts
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half-open
        self.half_open_attempts = 0
    
    def record_failure(self, error_type: ErrorType):
        """记录失败"""
        if error_type == ErrorType.PERMANENT:
            self.failure_count += 1
        elif error_type == ErrorType.TRANSIENT:
            self.failure_count += 0.5  # 临时性错误权重较低
        
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "open"
            logger.warning(f"熔断器打开：连续{self.failure_count}次失败")
    
    def record_success(self):
        """记录成功"""
        self.failure_count = 0
        self.half_open_attempts = 0
        self.state = "closed"
    
    def can_execute(self) -> bool:
        """检查是否可以执行"""
        if self.state == "closed":
            return True
        
        if self.state == "open":
            # 检查冷却期是否已过
            if time.time() - self.last_failure_time > self.reset_timeout:
                self.state = "half-open"
                self.half_open_attempts = 0
                logger.info("熔断器半开：尝试恢复")
                return True
            return False
        
        # half-open状态
        if self.half_open_attempts < self.half_open_max_attempts:
            self.half_open_attempts += 1
            return True
        return False
    
    def reset(self):
        """人工重置熔断器"""
        self.failure_count = 0
        self.half_open_attempts = 0
        self.state = "closed"
        logger.info("熔断器已人工重置")
```

---

## 五、工作时段配置

```python
WORKING_HOURS_CONFIG = {
    "timezone": "Asia/Shanghai",
    "working_days": [0, 1, 2, 3, 4],  # 周一到周五
    "working_hours": {
        "start": "09:00",
        "end": "18:00",
    },
    "sla_multiplier": {
        "working_hours": 1.0,      # 工作时间：正常SLA
        "non_working_hours": 8.0,  # 非工作时间：SLA×8
    },
    "holiday_calendar": [
        "2026-01-01",  # 元旦
        "2026-01-26",  # 春节
        "2026-01-27",
        "2026-01-28",
        "2026-01-29",
        "2026-01-30",
        "2026-04-05",  # 清明
        "2026-05-01",  # 劳动节
        "2026-06-14",  # 端午
        "2026-10-01",  # 国庆
        "2026-10-02",
        "2026-10-03",
        "2026-10-04",
        "2026-10-05",
        "2026-10-06",
        "2026-10-07",
    ],
}

def calculate_sla_timeout(base_timeout: int, current_time: datetime) -> int:
    """根据工作时段计算SLA超时时间"""
    config = WORKING_HOURS_CONFIG
    
    # 检查是否为工作日
    if current_time.weekday() not in config["working_days"]:
        return int(base_timeout * config["sla_multiplier"]["non_working_hours"])
    
    # 检查是否为节假日
    if current_time.strftime("%Y-%m-%d") in config["holiday_calendar"]:
        return int(base_timeout * config["sla_multiplier"]["non_working_hours"])
    
    # 检查是否为工作时间
    working_start = datetime.strptime(config["working_hours"]["start"], "%H:%M").time()
    working_end = datetime.strptime(config["working_hours"]["end"], "%H:%M").time()
    
    if working_start <= current_time.time() <= working_end:
        return int(base_timeout * config["sla_multiplier"]["working_hours"])
    else:
        return int(base_timeout * config["sla_multiplier"]["non_working_hours"])
```

---

## 六、监控告警

### 监控指标

```python
MONITORING_METRICS = {
    "gate_metrics": {
        "pass_rate": {"description": "各Gate通过率", "threshold": 0.8},
        "avg_duration": {"description": "平均耗时（秒）", "threshold": 300},
        "failure_count": {"description": "失败次数", "threshold": 10},
        "retry_count": {"description": "重试次数", "threshold": 5},
        "circuit_break_count": {"description": "熔断次数", "threshold": 3},
    },
    "human_metrics": {
        "response_time": {"description": "人工响应时间（秒）", "threshold": 1800},
        "sla_violation_count": {"description": "SLA违规次数", "threshold": 5},
        "pending_count": {"description": "待处理数量", "threshold": 10},
    },
    "system_metrics": {
        "api_latency": {"description": "API延迟（毫秒）", "threshold": 1000},
        "error_rate": {"description": "错误率", "threshold": 0.05},
        "queue_depth": {"description": "队列深度", "threshold": 100},
    },
}
```

### 告警规则

```python
ALERT_RULES = [
    {
        "name": "Gate通过率过低",
        "condition": "gate_pass_rate < 0.8",
        "severity": "warning",
        "notification": ["email", "dingtalk"],
    },
    {
        "name": "Gate连续失败",
        "condition": "gate_consecutive_failures >= 3",
        "severity": "critical",
        "notification": ["email", "dingtalk", "sms"],
    },
    {
        "name": "人工SLA违规",
        "condition": "human_sla_violation_count >= 5",
        "severity": "warning",
        "notification": ["email", "dingtalk"],
    },
    {
        "name": "熔断器打开",
        "condition": "circuit_breaker_state == 'open'",
        "severity": "critical",
        "notification": ["email", "dingtalk", "sms"],
    },
    {
        "name": "API延迟过高",
        "condition": "api_latency > 1000",
        "severity": "warning",
        "notification": ["email"],
    },
    {
        "name": "队列积压",
        "condition": "queue_depth > 100",
        "severity": "warning",
        "notification": ["email", "dingtalk"],
    },
]
```

---

## 七、审计日志防篡改

### 哈希链实现

```python
import hashlib
import json

class AuditLogger:
    """审计日志记录器（防篡改）"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.previous_hash = "0" * 64  # 初始哈希
        self._init_db()
    
    def _init_db(self):
        """初始化数据库"""
        conn = psycopg2.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                log_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                gate_num INTEGER,
                action TEXT NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                details JSONB,
                user_id TEXT,
                previous_hash TEXT NOT NULL,
                current_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 创建索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_logs_run_id ON audit_logs(run_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp)
        """)
        
        conn.commit()
        conn.close()
    
    def log(
        self,
        run_id: str,
        gate_num: int,
        action: str,
        details: dict,
        user_id: str = None,
    ):
        """记录审计日志（带哈希链）"""
        log_id = str(uuid.uuid4())
        timestamp = datetime.now()
        
        # 计算当前哈希
        hash_input = json.dumps({
            "log_id": log_id,
            "run_id": run_id,
            "gate_num": gate_num,
            "action": action,
            "timestamp": timestamp.isoformat(),
            "details": details,
            "user_id": user_id,
            "previous_hash": self.previous_hash,
        }, sort_keys=True)
        
        current_hash = hashlib.sha256(hash_input.encode()).hexdigest()
        
        # 保存到数据库
        conn = psycopg2.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO audit_logs (
                log_id, run_id, gate_num, action, timestamp,
                details, user_id, previous_hash, current_hash
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            log_id, run_id, gate_num, action, timestamp,
            json.dumps(details), user_id, self.previous_hash, current_hash,
        ))
        
        conn.commit()
        conn.close()
        
        # 更新previous_hash
        self.previous_hash = current_hash
    
    def verify_chain(self, run_id: str) -> bool:
        """验证哈希链完整性"""
        conn = psycopg2.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT log_id, previous_hash, current_hash, details
            FROM audit_logs
            WHERE run_id = %s
            ORDER BY timestamp
        """, (run_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        previous_hash = "0" * 64
        for row in rows:
            log_id, stored_previous_hash, stored_current_hash, details = row
            
            # 验证previous_hash
            if stored_previous_hash != previous_hash:
                return False
            
            # 验证current_hash
            hash_input = json.dumps({
                "log_id": log_id,
                "run_id": run_id,
                "details": details,
                "previous_hash": previous_hash,
            }, sort_keys=True)
            
            calculated_hash = hashlib.sha256(hash_input.encode()).hexdigest()
            if calculated_hash != stored_current_hash:
                return False
            
            previous_hash = stored_current_hash
        
        return True
```

---

## 八、数据库升级（PostgreSQL）

### 数据库Schema

```sql
-- 工作流运行表
CREATE TABLE workflow_runs (
    run_id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    company_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'initialized',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    state JSONB,
    metadata JSONB
);

-- Gate执行表
CREATE TABLE gate_executions (
    id SERIAL PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES workflow_runs(run_id),
    gate_num INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    result JSONB,
    error_details JSONB,
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(run_id, gate_num)
);

-- 人工介入表
CREATE TABLE human_interventions (
    id SERIAL PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES workflow_runs(run_id),
    gate_num INTEGER NOT NULL,
    intervention_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    requested_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    responded_at TIMESTAMP,
    response JSONB,
    user_id TEXT,
    sla_deadline TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 审计日志表（只追加，防篡改）
CREATE TABLE audit_logs (
    log_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    gate_num INTEGER,
    action TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    details JSONB,
    user_id TEXT,
    previous_hash TEXT NOT NULL,
    current_hash TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX idx_workflow_runs_status ON workflow_runs(status);
CREATE INDEX idx_workflow_runs_ticker ON workflow_runs(ticker);
CREATE INDEX idx_gate_executions_run_id ON gate_executions(run_id);
CREATE INDEX idx_gate_executions_status ON gate_executions(status);
CREATE INDEX idx_human_interventions_run_id ON human_interventions(run_id);
CREATE INDEX idx_human_interventions_status ON human_interventions(status);
CREATE INDEX idx_audit_logs_run_id ON audit_logs(run_id);
CREATE INDEX idx_audit_logs_timestamp ON audit_logs(timestamp);

-- 创建更新时间触发器
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_workflow_runs_updated_at
    BEFORE UPDATE ON workflow_runs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_gate_executions_updated_at
    BEFORE UPDATE ON gate_executions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_human_interventions_updated_at
    BEFORE UPDATE ON human_interventions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
```

---

## 九、安全合规

### 密钥管理

```python
class KeyManager:
    """密钥管理器"""
    
    def __init__(self, kms_client=None):
        self.kms_client = kms_client
        self._cache = {}
    
    def get_key(self, key_id: str) -> str:
        """获取密钥"""
        if key_id in self._cache:
            return self._cache[key_id]
        
        if self.kms_client:
            # 从KMS获取
            response = self.kms_client.decrypt(
                CiphertextBlob=base64.b64decode(key_id),
            )
            key = response['Plaintext'].decode()
        else:
            # 从环境变量获取
            key = os.environ.get(key_id)
        
        self._cache[key_id] = key
        return key
    
    def encrypt(self, plaintext: str, key_id: str) -> str:
        """加密数据"""
        key = self.get_key(key_id)
        # 使用AES加密
        cipher = AES.new(key.encode(), AES.MODE_GCM)
        ciphertext, tag = cipher.encrypt_and_digest(plaintext.encode())
        return base64.b64encode(cipher.nonce + tag + ciphertext).decode()
    
    def decrypt(self, ciphertext: str, key_id: str) -> str:
        """解密数据"""
        key = self.get_key(key_id)
        # 解码
        data = base64.b64decode(ciphertext)
        nonce = data[:16]
        tag = data[16:32]
        ciphertext_bytes = data[32:]
        # 使用AES解密
        cipher = AES.new(key.encode(), AES.MODE_GCM, nonce=nonce)
        plaintext = cipher.decrypt_and_verify(ciphertext_bytes, tag)
        return plaintext.decode()
```

### 数据脱敏

```python
class DataMasker:
    """数据脱敏器"""
    
    MASKING_RULES = {
        "api_key": {"type": "full", "replacement": "***"},
        "password": {"type": "full", "replacement": "***"},
        "email": {"type": "partial", "keep_chars": 3},
        "phone": {"type": "partial", "keep_chars": 4},
        "id_card": {"type": "partial", "keep_chars": 4},
        "bank_card": {"type": "partial", "keep_chars": 4},
    }
    
    def mask(self, data: dict, field_type: str) -> dict:
        """对数据进行脱敏"""
        masked_data = data.copy()
        
        for key, value in masked_data.items():
            if field_type in self.MASKING_RULES:
                rule = self.MASKING_RULES[field_type]
                if rule["type"] == "full":
                    masked_data[key] = rule["replacement"]
                elif rule["type"] == "partial":
                    keep_chars = rule["keep_chars"]
                    if isinstance(value, str) and len(value) > keep_chars:
                        masked_data[key] = value[:keep_chars] + "***"
        
        return masked_data
```

### RBAC权限控制

```python
PERMISSION_MATRIX = {
    "admin": {
        "workflow": ["create", "read", "update", "delete", "cancel"],
        "gate": ["read", "retry", "skip", "rollback"],
        "human_intervention": ["read", "respond", "escalate"],
        "audit_log": ["read", "export"],
        "config": ["read", "update"],
    },
    "analyst": {
        "workflow": ["create", "read"],
        "gate": ["read"],
        "human_intervention": ["read", "respond"],
        "audit_log": ["read"],
        "config": ["read"],
    },
    "viewer": {
        "workflow": ["read"],
        "gate": ["read"],
        "human_intervention": ["read"],
        "audit_log": ["read"],
        "config": [],
    },
}
```

---

## 十、第三方监督机制（轻量级）

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

## 十一、状态机与持久化

### 状态定义

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

### 状态转换约束

```python
VALID_TRANSITIONS = {
    GateState.PENDING: [GateState.RUNNING, GateState.SKIPPED],
    GateState.RUNNING: [GateState.PASSED, GateState.FAILED, GateState.WAITING_HUMAN],
    GateState.PASSED: [],  # 终态
    GateState.FAILED: [GateState.RUNNING, GateState.ROLLBACK],  # 可重试或回滚
    GateState.SKIPPED: [],  # 终态
    GateState.WAITING_HUMAN: [GateState.RUNNING, GateState.FAILED],
    GateState.ROLLBACK: [GateState.PENDING],
}
```

---

## 十二、总结

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
| **日志审计** | 增加日志、版本管理和审计追踪（哈希链防篡改） |
| **安全合规** | 密钥管理、数据脱敏、RBAC权限控制 |
| **监控告警** | 各Gate通过率、耗时、熔断次数等指标 |
| **工作时段** | 非工作时间暂停SLA计时 |
| **数据库** | PostgreSQL/MySQL，支持高并发和高可用 |

---

## 十三、与v8.2对比

| 项目 | v8.2 | v8.3 |
|------|------|------|
| **逻辑矛盾检测** | 模糊定义 | 10类矛盾模式库 |
| **风险提示检查** | 模糊定义 | 8类风险检查清单 |
| **异常处理** | 基本框架 | 完整策略矩阵 |
| **熔断恢复** | 无 | 冷却期+半开+人工重置 |
| **重试策略** | 固定次数 | 指数退避+抖动 |
| **工作时段** | 无 | 工作时间/非工作时间配置 |
| **监控告警** | 无 | 完整指标和告警规则 |
| **审计日志** | 基础 | 哈希链防篡改 |
| **数据库** | SQLite | PostgreSQL/MySQL |
| **安全合规** | 基础 | 密钥管理+数据脱敏+RBAC |
| **人工介入** | 强制介入 | 异常驱动的按需介入 |
