# Qual流程技术方案 v8.4

## 一、版本更新说明

根据HeavySkill审查意见v8.3，主要更新：

| 优先级 | 更新项 | 说明 |
|--------|--------|------|
| **P0** | 逻辑矛盾检测实现方式 | 明确规则引擎+LLM辅助，避免"伪确定性" |
| **P0** | 错误分类字典 | 完整的错误码映射和降级策略 |
| **P0** | 审计日志外部锚定 | 外部根哈希锚定+定期校验 |
| **P0** | 数据库分区与迁移 | 分区策略、索引优化、迁移方案 |
| **P0** | RBAC与数据脱敏 | 细化权限控制和脱敏策略 |
| **P0** | 第三方监督压力测试 | 验证秒级响应承诺 |
| **P1** | 逻辑矛盾库扩展 | 跨期、行业对标、严重度权重 |
| **P1** | 告警分级与聚合 | 趋势告警、业务质量监控 |
| **P1** | 节假日日历 | 自动同步、调休处理 |
| **P1** | 运维Runbook | 故障演练、人工兜底 |

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

## 三、逻辑矛盾检测实现方案

### 3.1 实现架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     逻辑矛盾检测架构                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│ 第一层：规则引擎（确定性，秒级）                                              │
│   - 关键词匹配                                                                │
│   - 数值比较                                                                  │
│   - 模式匹配                                                                  │
│   ↓                                                                          │
│ 第二层：LLM辅助（非确定性，仅用于模糊场景）                                    │
│   - 仅当规则引擎无法判定时触发                                                │
│   - 输出置信度分数                                                            │
│   - 低置信度结果升级人工                                                      │
│   ↓                                                                          │
│ 第三层：人工复核（高置信度阈值）                                               │
│   - 仅当LLM置信度<70%时触发                                                  │
│   - 人工判定最终结果                                                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 规则引擎实现

```python
class LogicContradictionDetector:
    """逻辑矛盾检测器（规则引擎+LLM辅助）"""
    
    def __init__(self, rule_config_path: str):
        self.rules = self._load_rules(rule_config_path)
        self.llm_caller = None  # 可选的LLM调用器
    
    def detect(self, report_data: dict) -> List[ContradictionResult]:
        """检测逻辑矛盾"""
        results = []
        
        # 第一层：规则引擎检测
        for rule in self.rules:
            if rule["type"] == "deterministic":
                result = self._apply_deterministic_rule(rule, report_data)
                if result:
                    results.append(result)
        
        # 第二层：LLM辅助检测（仅用于模糊场景）
        ambiguous_results = []
        for rule in self.rules:
            if rule["type"] == "llm_assisted":
                result = self._apply_llm_rule(rule, report_data)
                if result:
                    if result.confidence >= 0.7:
                        results.append(result)
                    else:
                        ambiguous_results.append(result)
        
        # 第三层：人工复核（低置信度结果）
        if ambiguous_results:
            for result in ambiguous_results:
                result.requires_human_review = True
                results.append(result)
        
        return results
    
    def _apply_deterministic_rule(self, rule: dict, data: dict) -> Optional[ContradictionResult]:
        """应用确定性规则"""
        try:
            # 执行规则检查
            check_func = getattr(self, f"_check_{rule['id'].lower()}")
            passed, details = check_func(data)
            
            if not passed:
                return ContradictionResult(
                    rule_id=rule["id"],
                    rule_name=rule["name"],
                    severity=rule["severity"],
                    confidence=1.0,  # 确定性规则置信度为100%
                    details=details,
                    requires_human_review=False,
                )
        except Exception as e:
            logger.warning(f"规则{rule['id']}执行失败: {e}")
        
        return None
    
    def _apply_llm_rule(self, rule: dict, data: dict) -> Optional[ContradictionResult]:
        """应用LLM辅助规则"""
        if not self.llm_caller:
            return None
        
        try:
            # 构建prompt
            prompt = self._build_llm_prompt(rule, data)
            
            # 调用LLM
            response = self.llm_caller("logic_contradiction", prompt)
            
            # 解析响应
            result = self._parse_llm_response(response, rule)
            
            return result
        except Exception as e:
            logger.warning(f"LLM规则{rule['id']}执行失败: {e}")
            return None
```

### 3.3 矛盾模式库（扩展版）

```python
LOGIC_CONTRADICTION_PATTERNS = [
    # ===== 第一层：确定性规则（规则引擎） =====
    {
        "id": "LC01",
        "name": "营收增长但利润下降无解释",
        "type": "deterministic",
        "severity": "warning",
        "check": {
            "condition": "revenue_growth > 0 AND profit_growth < 0",
            "exception_keywords": ["成本上升", "费用增加", "投资增加", "一次性损失"],
        },
    },
    {
        "id": "LC02",
        "name": "评级上调但目标价下调",
        "type": "deterministic",
        "severity": "critical",
        "check": {
            "condition": "rating_upgrade AND target_price_downgrade",
        },
    },
    {
        "id": "LC04",
        "name": "现金流为负但推荐买入",
        "type": "deterministic",
        "severity": "critical",
        "check": {
            "condition": "ocf_negative AND rating_buy",
        },
    },
    {
        "id": "LC09",
        "name": "现金流与净利润严重背离",
        "type": "deterministic",
        "severity": "critical",
        "check": {
            "condition": "abs(ocf - net_income) / abs(net_income) > 0.5",
        },
    },
    {
        "id": "LC11",
        "name": "营收数据跨章节不一致",
        "type": "deterministic",
        "severity": "critical",
        "check": {
            "condition": "cross_chapter_data_mismatch",
            "fields": ["revenue", "net_income", "total_assets"],
            "tolerance": 0.01,
        },
    },
    {
        "id": "LC12",
        "name": "估值参数与Gate 2不一致",
        "type": "deterministic",
        "severity": "critical",
        "check": {
            "condition": "valuation_param_mismatch",
            "fields": ["wacc", "terminal_growth", "fcf"],
        },
    },
    
    # ===== 第二层：LLM辅助规则（模糊场景） =====
    {
        "id": "LC03",
        "name": "估值低估但评级中性",
        "type": "llm_assisted",
        "severity": "warning",
        "prompt_template": "分析报告中估值结论与投资评级是否一致。估值结论：{valuation_conclusion}，投资评级：{rating}。请判断是否存在矛盾，并给出置信度（0-1）。",
    },
    {
        "id": "LC05",
        "name": "营收预测增长但行业下行",
        "type": "llm_assisted",
        "severity": "warning",
        "prompt_template": "分析报告中公司营收预测与行业趋势是否矛盾。公司营收预测：{revenue_forecast}，行业趋势：{industry_trend}。请判断是否存在矛盾，并给出置信度（0-1）。",
    },
    {
        "id": "LC06",
        "name": "毛利率上升但营业利润率下降",
        "type": "llm_assisted",
        "severity": "warning",
        "prompt_template": "分析毛利率上升但营业利润率下降是否合理。毛利率变化：{gross_margin_change}，营业利润率变化：{operating_margin_change}。请判断是否存在矛盾，并给出置信度（0-1）。",
    },
    {
        "id": "LC07",
        "name": "资产增长但ROE提升",
        "type": "llm_assisted",
        "severity": "warning",
        "prompt_template": "分析资产增长但ROE提升是否合理。资产增长率：{asset_growth}，ROE变化：{roe_change}。请判断是否存在矛盾，并给出置信度（0-1）。",
    },
    {
        "id": "LC08",
        "name": "负债率上升但评级上调",
        "type": "llm_assisted",
        "severity": "warning",
        "prompt_template": "分析负债率上升但评级上调是否合理。负债率变化：{leverage_change}，评级变化：{rating_change}。请判断是否存在矛盾，并给出置信度（0-1）。",
    },
    {
        "id": "LC10",
        "name": "估值假设与历史趋势严重偏离",
        "type": "llm_assisted",
        "severity": "warning",
        "prompt_template": "分析估值假设与历史趋势是否严重偏离。估值假设增长率：{assumed_growth}，历史平均增长率：{historical_growth}。请判断是否存在矛盾，并给出置信度（0-1）。",
    },
    
    # ===== 扩展规则（P1） =====
    {
        "id": "LC13",
        "name": "行业竞争格局描述与市场份额数据矛盾",
        "type": "llm_assisted",
        "severity": "warning",
        "prompt_template": "分析行业竞争格局描述与市场份额数据是否矛盾。竞争格局描述：{competition_description}，市场份额数据：{market_share}。请判断是否存在矛盾，并给出置信度（0-1）。",
    },
    {
        "id": "LC14",
        "name": "不同估值方法给出的信号相反",
        "type": "deterministic",
        "severity": "critical",
        "check": {
            "condition": "valuation_methods_contradictory",
            "methods": ["dcf", "comparable", "scenario"],
        },
    },
    {
        "id": "LC15",
        "name": "管理层讨论与数据部分不一致",
        "type": "llm_assisted",
        "severity": "warning",
        "prompt_template": "分析管理层讨论与数据部分是否一致。管理层讨论：{mda_content}，数据部分：{data_content}。请判断是否存在矛盾，并给出置信度（0-1）。",
    },
    {
        "id": "LC16",
        "name": "风险评级为高但推荐买入",
        "type": "deterministic",
        "severity": "critical",
        "check": {
            "condition": "risk_level_high AND rating_buy",
        },
    },
]
```

### 3.4 严重度权重

```python
CONTRADICTION_SEVERITY_WEIGHTS = {
    "critical": 10,  # 致命矛盾：一票否决
    "warning": 1,    # 警告矛盾：累计计算
}

def calculate_contradiction_score(contradictions: List[ContradictionResult]) -> int:
    """计算矛盾分数"""
    score = 0
    critical_count = 0
    
    for contradiction in contradictions:
        weight = CONTRADICTION_SEVERITY_WEIGHTS.get(contradiction.severity, 1)
        score += weight
        
        if contradiction.severity == "critical":
            critical_count += 1
    
    return score, critical_count

def check_contradiction_threshold(contradictions: List[ContradictionResult]) -> bool:
    """检查矛盾阈值"""
    score, critical_count = calculate_contradiction_score(contradictions)
    
    # 致命矛盾=0，且加权分数≤10
    return critical_count == 0 and score <= 10
```

---

## 四、错误分类字典

### 4.1 错误码映射

```python
ERROR_CODE_MAPPING = {
    # ===== 网络错误（临时性） =====
    "NETWORK_TIMEOUT": {"type": "transient", "retry": True, "max_retries": 3},
    "NETWORK_CONNECTION_ERROR": {"type": "transient", "retry": True, "max_retries": 3},
    "HTTP_429": {"type": "transient", "retry": True, "max_retries": 3, "backoff": True},
    "HTTP_502": {"type": "transient", "retry": True, "max_retries": 3},
    "HTTP_503": {"type": "transient", "retry": True, "max_retries": 3},
    "HTTP_504": {"type": "transient", "retry": True, "max_retries": 3},
    
    # ===== 认证错误（永久性） =====
    "HTTP_401": {"type": "permanent", "retry": False, "escalate": True},
    "HTTP_403": {"type": "permanent", "retry": False, "escalate": True},
    "AUTH_FAILED": {"type": "permanent", "retry": False, "escalate": True},
    "TOKEN_EXPIRED": {"type": "permanent", "retry": False, "escalate": True},
    
    # ===== 数据错误（永久性） =====
    "HTTP_404": {"type": "permanent", "retry": False, "escalate": True},
    "DATA_NOT_FOUND": {"type": "permanent", "retry": False, "escalate": True},
    "DATA_FORMAT_ERROR": {"type": "permanent", "retry": False, "escalate": True},
    "DATA_PARSE_ERROR": {"type": "permanent", "retry": False, "escalate": True},
    
    # ===== 业务错误 =====
    "COVERAGE_BELOW_THRESHOLD": {"type": "business", "retry": True, "max_retries": 1},
    "PARAMETER_OUT_OF_RANGE": {"type": "business", "retry": False, "escalate": True},
    "LOGIC_CONTRADICTION": {"type": "business", "retry": False, "escalate": True},
    "VALIDATION_FAILED": {"type": "business", "retry": True, "max_retries": 1},
    
    # ===== 系统错误（临时性） =====
    "DATABASE_CONNECTION_ERROR": {"type": "transient", "retry": True, "max_retries": 3},
    "DATABASE_TIMEOUT": {"type": "transient", "retry": True, "max_retries": 3},
    "MEMORY_ERROR": {"type": "transient", "retry": True, "max_retries": 1},
    "LLM_TIMEOUT": {"type": "transient", "retry": True, "max_retries": 2},
    "LLM_RATE_LIMIT": {"type": "transient", "retry": True, "max_retries": 3, "backoff": True},
}
```

### 4.2 降级策略

```python
DEGRADATION_STRATEGIES = {
    # ===== 数据源降级 =====
    "data_source": {
        "primary": "wind_api",
        "fallback_chain": [
            {"source": "tushare", "condition": "wind_unavailable"},
            {"source": "eastmoney", "condition": "tushare_unavailable"},
            {"source": "company_ir", "condition": "eastmoney_unavailable"},
        ],
        "final_fallback": "human_upload",
    },
    
    # ===== Gate降级 =====
    "gate_0": {
        "data_incomplete": {
            "action": "partial_accept",
            "condition": "coverage >= 0.80",
            "mark_as": "limited_data",
        },
        "data_unavailable": {
            "action": "escalate_human",
            "timeout": 1800,
        },
    },
    "gate_1": {
        "extraction_failed": {
            "action": "retry_with_simpler_prompt",
            "max_retries": 1,
        },
        "extraction_partial": {
            "action": "accept_with_warning",
            "condition": "required_fields_complete",
        },
    },
    "gate_3": {
        "chapter_generation_failed": {
            "action": "retry_single_chapter",
            "max_retries": 2,
        },
        "consistency_check_failed": {
            "action": "regenerate_inconsistent_chapters",
            "max_retries": 1,
        },
    },
    "gate_4": {
        "logic_contradiction_found": {
            "action": "attempt_auto_fix",
            "max_retries": 1,
            "fallback": "escalate_human",
        },
    },
}
```

### 4.3 熔断恢复流程

```python
CIRCUIT_BREAKER_RECOVERY = {
    "transient": {
        "failure_threshold": 5,
        "reset_timeout": 30,  # 冷却期30秒
        "half_open_max_attempts": 1,
        "recovery_action": "auto_retry",
    },
    "permanent": {
        "failure_threshold": 3,
        "reset_timeout": None,  # 需要人工重置
        "half_open_max_attempts": 0,
        "recovery_action": "human_reset",
        "notification": ["email", "dingtalk", "sms"],
    },
    "business": {
        "failure_threshold": None,  # 不熔断
        "reset_timeout": None,
        "half_open_max_attempts": 0,
        "recovery_action": "escalate_human",
    },
}
```

---

## 五、审计日志外部锚定

### 5.1 外部锚定架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     审计日志外部锚定架构                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│ 应用层                                                                        │
│   ↓ 写入                                                                      │
│ 数据库（PostgreSQL）                                                          │
│   - audit_logs表（只追加）                                                    │
│   - 哈希链（previous_hash + current_hash）                                    │
│   ↓ 定时同步                                                                  │
│ 外部锚定服务                                                                  │
│   - WORM存储（Write Once Read Many）                                          │
│   - 可信时间戳服务                                                            │
│   - 区块链存证（可选）                                                        │
│   ↓ 定期验证                                                                  │
│ 验证服务                                                                      │
│   - 验证哈希链完整性                                                          │
│   - 验证外部锚定一致性                                                        │
│   - 告警异常                                                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 外部锚定实现

```python
class AuditLogAnchor:
    """审计日志外部锚定"""
    
    def __init__(self, db_path: str, anchor_service_url: str):
        self.db_path = db_path
        self.anchor_service_url = anchor_service_url
        self.last_anchor_hash = None
        self.anchor_interval = 3600  # 每小时锚定一次
    
    def anchor_chain(self):
        """锚定哈希链到外部存储"""
        # 1. 获取当前链尾哈希
        current_tail_hash = self._get_chain_tail_hash()
        
        if current_tail_hash == self.last_anchor_hash:
            return  # 链未变化，无需锚定
        
        # 2. 构建锚定数据
        anchor_data = {
            "chain_tail_hash": current_tail_hash,
            "timestamp": datetime.now().isoformat(),
            "log_count": self._get_log_count(),
            "chain_length": self._get_chain_length(),
        }
        
        # 3. 签名
        signature = self._sign_anchor_data(anchor_data)
        anchor_data["signature"] = signature
        
        # 4. 发送到外部锚定服务
        success = self._send_to_anchor_service(anchor_data)
        
        if success:
            self.last_anchor_hash = current_tail_hash
            logger.info(f"审计日志链已锚定: {current_tail_hash}")
        else:
            logger.error("审计日志链锚定失败")
    
    def verify_chain_integrity(self) -> bool:
        """验证链完整性"""
        # 1. 验证内部哈希链
        internal_valid = self._verify_internal_chain()
        
        # 2. 验证外部锚定一致性
        external_valid = self._verify_external_anchor()
        
        return internal_valid and external_valid
    
    def _verify_internal_chain(self) -> bool:
        """验证内部哈希链"""
        conn = psycopg2.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT log_id, previous_hash, current_hash, details
            FROM audit_logs
            ORDER BY timestamp
        """)
        
        rows = cursor.fetchall()
        conn.close()
        
        previous_hash = "0" * 64
        for row in rows:
            log_id, stored_previous_hash, stored_current_hash, details = row
            
            # 验证previous_hash
            if stored_previous_hash != previous_hash:
                logger.error(f"哈希链断裂: log_id={log_id}")
                return False
            
            # 验证current_hash
            hash_input = self._build_hash_input(log_id, details, previous_hash)
            calculated_hash = hashlib.sha256(hash_input.encode()).hexdigest()
            
            if calculated_hash != stored_current_hash:
                logger.error(f"哈希不匹配: log_id={log_id}")
                return False
            
            previous_hash = stored_current_hash
        
        return True
    
    def _verify_external_anchor(self) -> bool:
        """验证外部锚定一致性"""
        # 从外部锚定服务获取最新锚定
        latest_anchor = self._get_latest_anchor()
        
        if not latest_anchor:
            logger.warning("无外部锚定记录")
            return True  # 无锚定记录时视为通过
        
        # 验证锚定数据
        chain_tail_hash = self._get_chain_tail_hash()
        
        if latest_anchor["chain_tail_hash"] != chain_tail_hash:
            logger.error("外部锚定与内部链不一致")
            return False
        
        # 验证签名
        if not self._verify_signature(latest_anchor):
            logger.error("外部锚定签名验证失败")
            return False
        
        return True
    
    def _sign_anchor_data(self, data: dict) -> str:
        """签名锚定数据"""
        # 使用私钥签名
        data_str = json.dumps(data, sort_keys=True)
        signature = hmac.new(
            self.signing_key.encode(),
            data_str.encode(),
            hashlib.sha256,
        ).hexdigest()
        return signature
```

### 5.3 定期校验任务

```python
class AuditLogVerifier:
    """审计日志定期校验"""
    
    def __init__(self, anchor: AuditLogAnchor):
        self.anchor = anchor
        self.verify_interval = 3600  # 每小时验证一次
    
    def run_verification(self):
        """运行验证"""
        try:
            # 验证链完整性
            is_valid = self.anchor.verify_chain_integrity()
            
            if not is_valid:
                # 发送告警
                self._send_alert("审计日志链完整性验证失败")
                
                # 记录验证结果
                self._log_verification_result(False)
            else:
                # 记录验证结果
                self._log_verification_result(True)
                
        except Exception as e:
            logger.error(f"审计日志验证异常: {e}")
            self._send_alert(f"审计日志验证异常: {e}")
    
    def _send_alert(self, message: str):
        """发送告警"""
        # 发送到告警系统
        alert = {
            "level": "critical",
            "source": "audit_log_verifier",
            "message": message,
            "timestamp": datetime.now().isoformat(),
        }
        # 发送到钉钉/邮件/短信
        send_alert(alert)
```

---

## 六、数据库分区与迁移

### 6.1 分区策略

```sql
-- audit_logs按月分区
CREATE TABLE audit_logs (
    log_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    gate_num INTEGER,
    action TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    details JSONB,
    user_id TEXT,
    previous_hash TEXT NOT NULL,
    current_hash TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) PARTITION BY RANGE (timestamp);

-- 创建月度分区
CREATE TABLE audit_logs_2026_01 PARTITION OF audit_logs
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
CREATE TABLE audit_logs_2026_02 PARTITION OF audit_logs
    FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');
-- ... 继续创建分区

-- 自动创建分区的函数
CREATE OR REPLACE FUNCTION create_audit_log_partition()
RETURNS void AS $$
DECLARE
    next_month DATE;
    partition_name TEXT;
    start_date TEXT;
    end_date TEXT;
BEGIN
    next_month := date_trunc('month', CURRENT_DATE + INTERVAL '1 month');
    partition_name := 'audit_logs_' || to_char(next_month, 'YYYY_MM');
    start_date := to_char(next_month, 'YYYY-MM-DD');
    end_date := to_char(next_month + INTERVAL '1 month', 'YYYY-MM-DD');
    
    EXECUTE format('CREATE TABLE IF NOT EXISTS %I PARTITION OF audit_logs FOR VALUES FROM (%L) TO (%L)',
                   partition_name, start_date, end_date);
END;
$$ LANGUAGE plpgsql;

-- 每月自动创建分区
SELECT cron.schedule('create-audit-partition', '0 0 1 * *', 'SELECT create_audit_log_partition()');
```

### 6.2 索引优化

```sql
-- audit_logs索引
CREATE INDEX idx_audit_logs_run_id ON audit_logs(run_id);
CREATE INDEX idx_audit_logs_timestamp ON audit_logs(timestamp);
CREATE INDEX idx_audit_logs_action ON audit_logs(action);
CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id);

-- workflow_runs索引
CREATE INDEX idx_workflow_runs_status ON workflow_runs(status);
CREATE INDEX idx_workflow_runs_ticker ON workflow_runs(ticker);
CREATE INDEX idx_workflow_runs_created_at ON workflow_runs(created_at);

-- gate_executions索引
CREATE INDEX idx_gate_executions_run_id ON gate_executions(run_id);
CREATE INDEX idx_gate_executions_status ON gate_executions(status);
CREATE INDEX idx_gate_executions_gate_num ON gate_executions(gate_num);

-- human_interventions索引
CREATE INDEX idx_human_interventions_run_id ON human_interventions(run_id);
CREATE INDEX idx_human_interventions_status ON human_interventions(status);
CREATE INDEX idx_human_interventions_sla_deadline ON human_interventions(sla_deadline);
```

### 6.3 数据迁移方案

```python
class DatabaseMigration:
    """数据库迁移管理"""
    
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.migrations_dir = "migrations"
    
    def migrate(self):
        """执行迁移"""
        # 1. 获取当前版本
        current_version = self._get_current_version()
        
        # 2. 获取待执行迁移
        pending_migrations = self._get_pending_migrations(current_version)
        
        # 3. 执行迁移
        for migration in pending_migrations:
            try:
                self._execute_migration(migration)
                self._record_migration(migration)
                logger.info(f"迁移完成: {migration['version']}")
            except Exception as e:
                logger.error(f"迁移失败: {migration['version']}, 错误: {e}")
                raise
    
    def rollback(self, target_version: str):
        """回滚到指定版本"""
        current_version = self._get_current_version()
        
        # 获取需要回滚的迁移
        migrations_to_rollback = self._get_migrations_to_rollback(current_version, target_version)
        
        for migration in migrations_to_rollback:
            try:
                self._execute_rollback(migration)
                self._remove_migration_record(migration)
                logger.info(f"回滚完成: {migration['version']}")
            except Exception as e:
                logger.error(f"回滚失败: {migration['version']}, 错误: {e}")
                raise
```

### 6.4 归档策略

```python
class DataArchiver:
    """数据归档管理"""
    
    def __init__(self, db_url: str, archive_storage: str):
        self.db_url = db_url
        self.archive_storage = archive_storage
        self.retention_days = 365 * 3  # 保留3年
    
    def archive_old_data(self):
        """归档旧数据"""
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)
        
        # 1. 归档audit_logs
        self._archive_audit_logs(cutoff_date)
        
        # 2. 归档workflow_runs
        self._archive_workflow_runs(cutoff_date)
        
        # 3. 清理已归档数据
        self._cleanup_archived_data(cutoff_date)
    
    def _archive_audit_logs(self, cutoff_date: datetime):
        """归档审计日志"""
        # 导出到冷存储
        query = """
            SELECT * FROM audit_logs
            WHERE timestamp < %s
            ORDER BY timestamp
        """
        
        # 执行导出
        export_path = f"{self.archive_storage}/audit_logs_{cutoff_date.strftime('%Y%m')}.parquet"
        self._export_to_parquet(query, (cutoff_date,), export_path)
        
        # 发布链终态快照
        self._publish_chain_snapshot(cutoff_date)
```

---

## 七、RBAC与数据脱敏

### 7.1 细化RBAC权限

```python
PERMISSION_MATRIX = {
    "admin": {
        "workflow": ["create", "read", "update", "delete", "cancel", "retry", "rollback"],
        "gate": ["read", "retry", "skip", "rollback", "override"],
        "human_intervention": ["read", "respond", "escalate", "reassign"],
        "audit_log": ["read", "export", "verify"],
        "config": ["read", "update"],
        "user": ["create", "read", "update", "delete"],
        "system": ["monitor", "alert", "backup", "restore"],
    },
    "analyst": {
        "workflow": ["create", "read"],
        "gate": ["read"],
        "human_intervention": ["read", "respond"],
        "audit_log": ["read"],
        "config": ["read"],
        "user": [],
        "system": [],
    },
    "reviewer": {
        "workflow": ["read"],
        "gate": ["read"],
        "human_intervention": ["read", "respond", "escalate"],
        "audit_log": ["read"],
        "config": ["read"],
        "user": [],
        "system": [],
    },
    "viewer": {
        "workflow": ["read"],
        "gate": ["read"],
        "human_intervention": ["read"],
        "audit_log": ["read"],
        "config": [],
        "user": [],
        "system": [],
    },
}
```

### 7.2 数据脱敏规则

```python
DATA_MASKING_RULES = {
    # ===== 高敏感数据 =====
    "api_key": {
        "level": "high",
        "mask_type": "full",
        "replacement": "***",
        "log_level": "none",  # 不记录到日志
    },
    "password": {
        "level": "high",
        "mask_type": "full",
        "replacement": "***",
        "log_level": "none",
    },
    "secret_key": {
        "level": "high",
        "mask_type": "full",
        "replacement": "***",
        "log_level": "none",
    },
    
    # ===== 中敏感数据 =====
    "email": {
        "level": "medium",
        "mask_type": "partial",
        "keep_chars": 3,
        "replacement": "***",
        "log_level": "masked",
    },
    "phone": {
        "level": "medium",
        "mask_type": "partial",
        "keep_chars": 4,
        "replacement": "***",
        "log_level": "masked",
    },
    "id_card": {
        "level": "medium",
        "mask_type": "partial",
        "keep_chars": 4,
        "replacement": "***",
        "log_level": "masked",
    },
    "bank_card": {
        "level": "medium",
        "mask_type": "partial",
        "keep_chars": 4,
        "replacement": "***",
        "log_level": "masked",
    },
    
    # ===== 低敏感数据 =====
    "user_name": {
        "level": "low",
        "mask_type": "none",
        "log_level": "full",
    },
    "company_name": {
        "level": "low",
        "mask_type": "none",
        "log_level": "full",
    },
}
```

### 7.3 合规差距分析

```python
COMPLIANCE_GAP_ANALYSIS = {
    "等保2.0": {
        "requirements": [
            {"id": "L1-01", "name": "身份鉴别", "status": "implemented", "detail": "RBAC+MFA"},
            {"id": "L1-02", "name": "访问控制", "status": "implemented", "detail": "细粒度权限控制"},
            {"id": "L1-03", "name": "安全审计", "status": "implemented", "detail": "哈希链+外部锚定"},
            {"id": "L1-04", "name": "入侵防范", "status": "partial", "detail": "需要补充WAF"},
            {"id": "L1-05", "name": "数据完整性", "status": "implemented", "detail": "哈希校验"},
            {"id": "L1-06", "name": "数据保密性", "status": "implemented", "detail": "加密存储+传输"},
        ],
    },
    "个人信息保护法": {
        "requirements": [
            {"id": "PIPL-01", "name": "知情同意", "status": "not_applicable", "detail": "不涉及个人数据"},
            {"id": "PIPL-02", "name": "数据最小化", "status": "implemented", "detail": "仅收集必要数据"},
            {"id": "PIPL-03", "name": "存储限制", "status": "implemented", "detail": "3年归档策略"},
            {"id": "PIPL-04", "name": "安全保障", "status": "implemented", "detail": "加密+访问控制"},
        ],
    },
    "证券行业合规": {
        "requirements": [
            {"id": "SEC-01", "name": "研究报告审核", "status": "implemented", "detail": "Gate 4/8人工审核"},
            {"id": "SEC-02", "name": "利益冲突披露", "status": "partial", "detail": "需要补充披露模块"},
            {"id": "SEC-03", "name": "数据来源合规", "status": "implemented", "detail": "Wind API授权"},
            {"id": "SEC-04", "name": "审计追踪", "status": "implemented", "detail": "完整审计日志"},
        ],
    },
}
```

---

## 八、告警分级与聚合

### 8.1 告警分级

```python
ALERT_LEVELS = {
    "critical": {
        "description": "严重告警，需要立即处理",
        "notification": ["sms", "phone", "dingtalk", "email"],
        "escalation_timeout": 300,  # 5分钟无响应升级
        "auto_action": "suspend_workflow",
    },
    "warning": {
        "description": "警告告警，需要尽快处理",
        "notification": ["dingtalk", "email"],
        "escalation_timeout": 1800,  # 30分钟无响应升级
        "auto_action": "none",
    },
    "info": {
        "description": "信息告警，仅供参考",
        "notification": ["email"],
        "escalation_timeout": None,
        "auto_action": "none",
    },
}
```

### 8.2 告警规则（细化版）

```python
ALERT_RULES = [
    # ===== Gate级别告警 =====
    {
        "name": "Gate 0通过率过低",
        "condition": "gate_0_pass_rate < 0.95",
        "level": "critical",
        "window": "1h",
        "notification": ["sms", "dingtalk"],
    },
    {
        "name": "Gate 1-8通过率过低",
        "condition": "gate_pass_rate < 0.80",
        "level": "warning",
        "window": "1h",
        "notification": ["dingtalk"],
    },
    {
        "name": "Gate连续失败",
        "condition": "gate_consecutive_failures >= 3",
        "level": "critical",
        "window": "immediate",
        "notification": ["sms", "dingtalk"],
    },
    
    # ===== 人工SLA告警 =====
    {
        "name": "人工SLA违规",
        "condition": "human_sla_violation_count >= 3",
        "level": "warning",
        "window": "1h",
        "notification": ["dingtalk"],
    },
    {
        "name": "人工SLA严重违规",
        "condition": "human_sla_violation_count >= 5",
        "level": "critical",
        "window": "1h",
        "notification": ["sms", "dingtalk"],
    },
    
    # ===== 熔断器告警 =====
    {
        "name": "熔断器打开",
        "condition": "circuit_breaker_state == 'open'",
        "level": "critical",
        "window": "immediate",
        "notification": ["sms", "dingtalk"],
    },
    
    # ===== 系统告警 =====
    {
        "name": "API延迟过高",
        "condition": "api_latency_p99 > 5000",
        "level": "warning",
        "window": "5m",
        "notification": ["dingtalk"],
    },
    {
        "name": "数据库连接池耗尽",
        "condition": "db_connection_pool_usage > 0.90",
        "level": "critical",
        "window": "immediate",
        "notification": ["sms", "dingtalk"],
    },
    {
        "name": "队列积压",
        "condition": "queue_depth > 100",
        "level": "warning",
        "window": "5m",
        "notification": ["dingtalk"],
    },
    
    # ===== 审计日志告警 =====
    {
        "name": "审计日志链验证失败",
        "condition": "audit_log_chain_valid == false",
        "level": "critical",
        "window": "immediate",
        "notification": ["sms", "dingtalk", "email"],
    },
    
    # ===== 数据源告警 =====
    {
        "name": "数据源覆盖率下降",
        "condition": "data_source_coverage < 0.90",
        "level": "warning",
        "window": "1h",
        "notification": ["dingtalk"],
    },
    {
        "name": "备用数据源切换",
        "condition": "fallback_source_used == true",
        "level": "info",
        "window": "immediate",
        "notification": ["email"],
    },
]
```

### 8.3 告警聚合

```python
class AlertAggregator:
    """告警聚合器"""
    
    def __init__(self):
        self.pending_alerts = {}
        self.aggregation_window = 300  # 5分钟聚合窗口
    
    def process_alert(self, alert: dict):
        """处理告警"""
        alert_key = self._get_alert_key(alert)
        
        if alert_key in self.pending_alerts:
            # 聚合已有告警
            self.pending_alerts[alert_key]["count"] += 1
            self.pending_alerts[alert_key]["last_occurrence"] = datetime.now()
        else:
            # 新告警
            self.pending_alerts[alert_key] = {
                "alert": alert,
                "count": 1,
                "first_occurrence": datetime.now(),
                "last_occurrence": datetime.now(),
            }
        
        # 检查是否需要发送
        if self._should_send(alert_key):
            self._send_aggregated_alert(alert_key)
            del self.pending_alerts[alert_key]
    
    def _should_send(self, alert_key: str) -> bool:
        """检查是否应该发送告警"""
        pending = self.pending_alerts[alert_key]
        
        # 首次出现的critical告警立即发送
        if pending["alert"]["level"] == "critical" and pending["count"] == 1:
            return True
        
        # 聚合窗口到期
        if datetime.now() - pending["first_occurrence"] > timedelta(seconds=self.aggregation_window):
            return True
        
        # 重复次数超过阈值
        if pending["count"] >= 5:
            return True
        
        return False
    
    def _send_aggregated_alert(self, alert_key: str):
        """发送聚合告警"""
        pending = self.pending_alerts[alert_key]
        
        aggregated = {
            "level": pending["alert"]["level"],
            "name": pending["alert"]["name"],
            "count": pending["count"],
            "first_occurrence": pending["first_occurrence"].isoformat(),
            "last_occurrence": pending["last_occurrence"].isoformat(),
            "message": f"{pending['alert']['name']} 发生{pending['count']}次",
        }
        
        send_alert(aggregated)
```

---

## 九、节假日日历

### 9.1 自动同步实现

```python
class HolidayCalendar:
    """节假日日历管理"""
    
    def __init__(self):
        self.holidays = set()
        self.workdays = set()  # 调休工作日
        self._sync_holidays()
    
    def _sync_holidays(self):
        """同步节假日数据"""
        try:
            # 方案1：使用chinese-calendar包
            import chinese_calendar
            self._sync_from_chinese_calendar(chinese_calendar)
        except ImportError:
            # 方案2：使用API
            self._sync_from_api()
    
    def _sync_from_chinese_calendar(self, cal):
        """从chinese-calendar包同步"""
        year = datetime.now().year
        
        for month in range(1, 13):
            for day in range(1, 32):
                try:
                    date = datetime(year, month, day).date()
                    if cal.is_holiday(date):
                        self.holidays.add(date)
                    elif cal.is_workday(date):
                        self.workdays.add(date)
                except ValueError:
                    continue
    
    def _sync_from_api(self):
        """从API同步"""
        # 调用节假日API
        response = requests.get("https://api.example.com/holidays")
        if response.status_code == 200:
            data = response.json()
            for holiday in data["holidays"]:
                self.holidays.add(datetime.strptime(holiday["date"], "%Y-%m-%d").date())
            for workday in data["workdays"]:
                self.workdays.add(datetime.strptime(workday["date"], "%Y-%m-%d").date())
    
    def is_working_day(self, date: datetime) -> bool:
        """判断是否为工作日"""
        date_only = date.date()
        
        # 检查是否为调休工作日
        if date_only in self.workdays:
            return True
        
        # 检查是否为节假日
        if date_only in self.holidays:
            return False
        
        # 检查是否为周末
        if date.weekday() >= 5:
            return False
        
        return True
    
    def get_working_hours_multiplier(self, date: datetime) -> float:
        """获取工作时段SLA倍率"""
        if not self.is_working_day(date):
            return 8.0  # 非工作日
        
        hour = date.hour
        if 9 <= hour < 18:
            return 1.0  # 工作时间
        else:
            return 8.0  # 非工作时间
```

---

## 十、运维Runbook

### 10.1 故障场景与处理

```python
RUNBOOK = {
    "data_source_failure": {
        "description": "数据源不可用",
        "symptoms": ["Gate 0失败", "数据源覆盖率下降告警"],
        "steps": [
            "1. 检查Wind API状态",
            "2. 检查网络连接",
            "3. 尝试备用数据源",
            "4. 如所有数据源不可用，通知人工上传",
            "5. 记录故障原因和处理过程",
        ],
        "escalation": "如30分钟内无法恢复，通知技术负责人",
    },
    "circuit_breaker_open": {
        "description": "熔断器打开",
        "symptoms": ["熔断器打开告警", "相关Gate连续失败"],
        "steps": [
            "1. 检查熔断原因",
            "2. 如果是临时性错误，等待冷却期后自动恢复",
            "3. 如果是永久性错误，人工修复后重置熔断器",
            "4. 验证修复后重新触发工作流",
        ],
        "escalation": "如1小时内无法恢复，通知技术负责人",
    },
    "human_sla_violation": {
        "description": "人工SLA违规",
        "symptoms": ["人工SLA违规告警", "工作流阻塞"],
        "steps": [
            "1. 检查人工任务队列",
            "2. 通知待处理人员",
            "3. 如人员不可用，转派给备岗",
            "4. 如无备岗，通知管理员",
        ],
        "escalation": "如超过最大等待时间，自动挂起并通知",
    },
    "audit_log_chain_broken": {
        "description": "审计日志链断裂",
        "symptoms": ["审计日志链验证失败告警"],
        "steps": [
            "1. 立即停止写入",
            "2. 检查断裂位置",
            "3. 从外部锚定点恢复",
            "4. 如无法恢复，通知安全团队",
            "5. 记录事故报告",
        ],
        "escalation": "立即通知安全团队",
    },
}
```

### 10.2 故障演练计划

```python
DRILL_PLAN = {
    "monthly": [
        {
            "name": "数据源故障演练",
            "description": "模拟Wind API不可用，验证备用数据源切换",
            "duration": 30,
            "participants": ["运维", "开发"],
        },
        {
            "name": "熔断器演练",
            "description": "模拟连续失败，验证熔断和恢复机制",
            "duration": 20,
            "participants": ["运维"],
        },
    ],
    "quarterly": [
        {
            "name": "全链路故障演练",
            "description": "模拟多组件故障，验证整体恢复能力",
            "duration": 120,
            "participants": ["运维", "开发", "业务"],
        },
        {
            "name": "审计日志恢复演练",
            "description": "模拟审计日志链断裂，验证恢复流程",
            "duration": 60,
            "participants": ["运维", "安全"],
        },
    ],
}
```

---

## 十一、第三方监督压力测试

### 11.1 测试场景

```python
PRESSURE_TEST_SCENARIOS = [
    {
        "name": "并发Gate检查",
        "description": "同时检查多个工作流的多个Gate",
        "concurrent_flows": 10,
        "gates_per_flow": 9,
        "expected_latency_ms": 100,  # 期望100ms内完成
    },
    {
        "name": "高频规则匹配",
        "description": "大量规则同时匹配",
        "rules_count": 100,
        "data_size_kb": 100,
        "expected_latency_ms": 50,
    },
    {
        "name": "长时间运行稳定性",
        "description": "连续运行24小时，检查内存泄漏和性能下降",
        "duration_hours": 24,
        "check_interval_minutes": 5,
        "max_memory_growth_mb": 100,
    },
]
```

### 11.2 测试实现

```python
class ComplianceCheckerPressureTest:
    """第三方监督压力测试"""
    
    def __init__(self, checker: FlowComplianceChecker):
        self.checker = checker
        self.results = []
    
    def run_concurrent_test(self, concurrent_flows: int, gates_per_flow: int):
        """并发测试"""
        import concurrent.futures
        
        start_time = time.time()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_flows) as executor:
            futures = []
            for flow_id in range(concurrent_flows):
                for gate_num in range(gates_per_flow):
                    future = executor.submit(
                        self._check_gate,
                        flow_id,
                        gate_num,
                    )
                    futures.append(future)
            
            # 等待所有任务完成
            concurrent.futures.wait(futures)
        
        end_time = time.time()
        total_latency = (end_time - start_time) * 1000  # 转换为毫秒
        
        # 计算统计信息
        latencies = [f.result() for f in futures]
        avg_latency = sum(latencies) / len(latencies)
        p99_latency = sorted(latencies)[int(len(latencies) * 0.99)]
        
        return {
            "total_latency_ms": total_latency,
            "avg_latency_ms": avg_latency,
            "p99_latency_ms": p99_latency,
            "total_checks": len(futures),
            "success_rate": sum(1 for l in latencies if l > 0) / len(latencies),
        }
    
    def _check_gate(self, flow_id: int, gate_num: int) -> float:
        """检查单个Gate"""
        start_time = time.time()
        
        # 构建模拟数据
        execution_log = self._build_mock_execution_log(flow_id, gate_num)
        
        # 执行检查
        result = self.checker.check_gate(gate_num, execution_log)
        
        end_time = time.time()
        return (end_time - start_time) * 1000  # 返回延迟（毫秒）
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
| **第三方监督** | 轻量级流程合规性检查，秒级响应 |
| **确定性规则** | 将模糊评分替换为可自动检查的规则集合 |
| **弹性设计** | 补全异常处理、超时、熔断、回滚机制 |
| **人工介入** | 关键节点设置人工确认，定义SLA |
| **状态机** | 实现完整的状态机与持久化 |
| **日志审计** | 哈希链+外部锚定，防篡改 |
| **安全合规** | 密钥管理、数据脱敏、RBAC、合规分析 |
| **监控告警** | 告警分级、聚合、趋势监控 |
| **工作时段** | 节假日自动同步、调休处理 |
| **运维支持** | Runbook、故障演练、压力测试 |

---

## 十三、与v8.3对比

| 项目 | v8.3 | v8.4 |
|------|------|------|
| **逻辑矛盾检测** | 10类模式，实现方式不明确 | 规则引擎+LLM辅助，三层架构 |
| **错误分类** | 基本分类 | 完整错误码映射+降级策略 |
| **审计日志** | 哈希链 | 哈希链+外部锚定+定期校验 |
| **数据库** | 基本表结构 | 分区策略+索引优化+迁移方案 |
| **RBAC** | 基本权限 | 细化权限+合规差距分析 |
| **告警** | 基本规则 | 分级+聚合+趋势监控 |
| **节假日** | 静态列表 | 自动同步+调休处理 |
| **运维** | 无 | Runbook+故障演练+压力测试 |
