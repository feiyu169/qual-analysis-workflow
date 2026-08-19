# HGF + HeavySkill 结合技术文档（V2.0）

> 基于 HeavySkill 审查意见修复
> 日期：2026-06-21

---

# 第一部分：HGF 详细说明

## 1.1 HGF 概述

**HGF（Hermes Gate Flow）** 是一个标准化的代码质量门禁流程，用于确保代码变更的质量和安全性。

### 核心理念

- **流程标准化**：所有代码变更都经过统一的审查流程
- **质量可量化**：通过门禁机制量化评估代码质量
- **风险可控**：根据风险等级调整审查力度
- **可追溯性**：完整记录审查过程和结果

### 适用场景

- 代码提交前的质量检查
- 技术方案评审
- 架构设计审查
- API 设计审查
- 数据库设计审查
- 部署方案审查

---

## 1.2 HGF 架构

### 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                        HGF 架构                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐      │
│  │   Task      │    │    Risk     │    │    Gate     │      │
│  │ Classifier  │───▶│  Assessor   │───▶│  Executor   │      │
│  └─────────────┘    └─────────────┘    └─────────────┘      │
│         │                  │                  │              │
│         ▼                  ▼                  ▼              │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐      │
│  │   Level     │    │    Risk     │    │    Gate     │      │
│  │   (L0-L3)   │    │   (low/high)│    │ (pass/fail) │      │
│  └─────────────┘    └─────────────┘    └─────────────┘      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 核心组件

#### 1. Task Classifier（任务分类器）

**职责**：根据文件数量、行数、变更类型、关键模块、风险等级对任务进行分类。

**分类维度**：

| 维度 | 指标 | 分类 |
|------|------|------|
| 文件数量 | 变更文件数 | L0(1-3), L1(4-10), L2(11-30), L3(30+) |
| 行数 | 变更行数 | L0(<50), L1(50-200), L2(200-500), L3(500+) |
| 变更类型 | CODE/CONFIG/IAC/DOCS | 不同类型的门禁组合 |
| 关键模块 | auth/payment/core | 额外的安全检查 |

**输出**：

```python
@dataclass
class TaskClassification:
    level: str  # L0, L1, L2, L3
    type: str   # CODE, CONFIG, IAC, DOCS, REVIEW
    risk: str   # low, medium, high
    estimated_time: str
    files: List[str]
    lines: int
```

**接口定义**：

```python
class TaskClassifier:
    def classify(self, description: str, files: List[str], lines: int = 0) -> TaskClassification:
        """
        对任务进行分类
        
        Args:
            description: 任务描述
            files: 变更文件列表
            lines: 变更行数
            
        Returns:
            TaskClassification: 任务分类结果
        """
        pass
```

#### 2. Risk Assessor（风险评估器）

**职责**：评估任务的风险等级，使用关键词映射、组合加成、安全护栏。

**风险因子**：

| 风险因子 | 权重 | 关键词 |
|----------|------|--------|
| security | 3 | auth, login, password, token, jwt, encryption |
| payment | 3 | payment, checkout, stripe, billing |
| database | 2 | migration, schema, alter table |
| api | 1 | endpoint, route, controller |
| config | 1 | config, settings, environment |

**输出**：

```python
@dataclass
class RiskAssessment:
    risk_score: int  # 0-30
    risk_level: str  # low, medium, high
    risk_factors: Dict[str, int]
    affected_areas: List[str]
```

**接口定义**：

```python
class RiskAssessor:
    def assess(self, affected_areas: List[str], description: str = "") -> RiskAssessment:
        """
        评估任务风险
        
        Args:
            affected_areas: 影响区域列表
            description: 任务描述
            
        Returns:
            RiskAssessment: 风险评估结果
        """
        pass
```

#### 3. Gate Executor（门禁执行器）

**职责**：执行质量门禁检查，支持插件架构。

**门禁类型**：

| 门禁类型 | 说明 | 工具 |
|----------|------|------|
| static_analysis | 静态代码分析 | ruff, flake8 |
| unit_test | 单元测试 | pytest |
| security_scan | 安全扫描 | semgrep, bandit |
| dependency_scan | 依赖扫描 | safety |
| secret_scan | 密钥扫描 | detect-secrets |
| heavyskill_review | HeavySkill 审查 | HeavySkill |

**门禁级别**：

| 级别 | 说明 | 失败处理 |
|------|------|----------|
| MUST_PASS | 必须通过 | 阻断提交 |
| SHOULD_PASS | 应该通过 | 警告但允许 |
| OPTIONAL | 可选 | 仅记录 |

**输出**：

```python
@dataclass
class GateResult:
    name: str
    status: str  # PASSED, FAILED, SKIPPED, ERROR
    level: str   # MUST_PASS, SHOULD_PASS, OPTIONAL
    details: Dict[str, Any]
    duration: float
    message: str
```

**接口定义**：

```python
class GateExecutor:
    def execute(self, gates: List[str], context: Dict[str, Any]) -> List[GateResult]:
        """
        执行门禁检查
        
        Args:
            gates: 门禁列表
            context: 上下文信息（文件路径、任务类型等）
            
        Returns:
            List[GateResult]: 门禁执行结果列表
        """
        pass
```

#### 4. Failure Handler（失败处理器）

**职责**：处理门禁失败，支持重试、升级、超时管理。

**策略**：

```python
class FailureHandler:
    def handle_failure(self, gate_id: str, error: Exception) -> Dict:
        """
        处理门禁失败
        
        Args:
            gate_id: 门禁ID
            error: 异常信息
            
        Returns:
            Dict: 处理结果（retry, escalate, abort）
        """
        # 重试策略
        if self.retry_count < self.max_retries:
            return {"action": "retry", "delay": self.retry_delay}
        
        # 升级策略
        if self.can_escalate(gate_id):
            return {"action": "escalate", "owner": self.get_owner(gate_id)}
        
        # 终止
        return {"action": "abort", "reason": str(error)}
```

---

## 1.3 HGF 流程

### 标准流程

```
Phase 0: 需求分析
    ↓
Phase 1: 任务分类
    ↓
Phase 2: 风险评估
    ↓
Phase 3: 门禁执行
    ↓
Phase 4: 用户确认
    ↓
Phase 5: 提交代码
```

### 阶段详解

#### Phase 0: 需求分析

**输入**：用户提交的代码变更或技术方案

**处理**：
1. 读取变更文件
2. 分析变更内容
3. 识别变更类型

**输出**：变更元数据

#### Phase 1: 任务分类

**输入**：变更元数据

**处理**：
1. 统计文件数量和行数
2. 识别变更类型（CODE/CONFIG/IAC/DOCS）
3. 确定任务级别（L0-L3）

**输出**：TaskClassification

#### Phase 2: 风险评估

**输入**：TaskClassification

**处理**：
1. 识别影响区域
2. 计算风险分数
3. 确定风险等级

**输出**：RiskAssessment

#### Phase 3: 门禁执行

**输入**：TaskClassification + RiskAssessment

**处理**：
1. 根据任务级别和风险等级选择门禁
2. 执行门禁检查
3. 收集门禁结果

**输出**：List[GateResult]

#### Phase 4: 用户确认

**输入**：List[GateResult]

**处理**：
1. 生成审查报告
2. 展示门禁结果
3. 等待用户确认

**输出**：用户确认/拒绝

#### Phase 5: 提交代码

**输入**：用户确认

**处理**：
1. 执行 git commit
2. 记录审查日志
3. 更新审计数据库

**输出**：提交成功/失败

---

## 1.4 HGF 配置

### 门禁配置文件

```yaml
# ~/.hermes/workflow/config/mcp-gates.yaml

gates:
  # 静态分析
  static_analysis:
    tool: "ruff"
    level: "MUST_PASS"
    command: "ruff check {files}"
    timeout: 60
    
  # 单元测试
  unit_test:
    tool: "pytest"
    level: "MUST_PASS"
    command: "pytest tests/ -v"
    timeout: 300
    
  # 安全扫描
  security_scan:
    tool: "semgrep"
    level: "SHOULD_PASS"
    command: "semgrep --config=auto {files}"
    timeout: 120
    
  # 密钥扫描
  secret_scan:
    tool: "detect-secrets"
    level: "MUST_PASS"
    command: "detect-secrets scan {files}"
    timeout: 30
    
  # HeavySkill 审查
  heavyskill_review:
    tool: "heavyskill"
    level: "MUST_PASS"
    command: "python3 heavyskill_review.py {file}"
    timeout: 300
    trigger_conditions:
      - "type=REVIEW"
      - "risk_level=high"
```

### 风险映射配置

```yaml
# ~/.hermes/workflow/config/risk_mapping.yaml

risk_factors:
  security:
    weight: 3
    keywords:
      - auth
      - login
      - password
      - token
      - jwt
      - encryption
      - 认证
      - 授权
      - 密码
  
  payment:
    weight: 3
    keywords:
      - payment
      - checkout
      - stripe
      - billing
      - 支付
      - 结算
  
  database:
    weight: 2
    keywords:
      - migration
      - schema
      - alter table
      - 数据库
      - 迁移
```

---

# 第二部分：HeavySkill 详细说明

## 2.1 HeavySkill 概述

**HeavySkill** 是一种创新的测试时扩展（Test-Time Extension）技术，通过模拟人类的"头脑风暴"与"批判性审查"过程，将复杂推理分解为并行推理与顺序审议两个阶段。

### 核心理念

- **并行推理**：生成 K 条独立推理轨迹，从不同角度探索问题
- **顺序审议**：对推理轨迹进行批判性审查，选择最佳答案
- **多样性优先**：通过多样性提高问题发现率
- **确定性校验**：使用规则引擎校验 LLM 结论

### 适用场景

- 技术方案审查
- 代码架构审查
- 安全漏洞审查
- 性能瓶颈审查
- API 设计审查
- 数据库设计审查

---

## 2.2 HeavySkill 架构

### 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                    HeavySkill 架构                           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Stage 1: Parallel Reasoning             │    │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │    │
│  │  │Traject 1│ │Traject 2│ │Traject 3│ │Traject K│   │    │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘   │    │
│  └─────────────────────────────────────────────────────┘    │
│                          ↓                                   │
│  ┌─────────────────────────────────────────────────────┐    │
│  │           Stage 2: Sequential Deliberation           │    │
│  │  ┌─────────────────────────────────────────────┐    │    │
│  │  │         Memory Cache + Deliberation          │    │    │
│  │  └─────────────────────────────────────────────┘    │    │
│  └─────────────────────────────────────────────────────┘    │
│                          ↓                                   │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Stage 3: Conclusion Validation          │    │
│  │  ┌─────────────────────────────────────────────┐    │    │
│  │  │         Rule Engine + Checklist              │    │    │
│  │  └─────────────────────────────────────────────┘    │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 核心组件

#### 1. Parallel Reasoning（并行推理）

**职责**：生成 K 条独立推理轨迹，从不同角度探索问题。

**配置参数**：

| 参数 | 说明 | 默认值 | 推荐值 |
|------|------|--------|--------|
| reason_k | 推理轨迹数 | 8 | 8 |
| temperature | 温度 | 1.0 | 1.0 |
| top_p | 核采样 | 0.95 | 0.95 |
| top_k | Top-K 采样 | 10 | 10 |
| max_tokens | 最大 token 数 | 32768 | 32768 |

**输出**：

```python
@dataclass
class Trajectory:
    id: str
    content: str
    tokens: int
    latency: float
    quality_score: float
```

**接口定义**：

```python
class ParallelReasoning:
    def run(self, query: str, file_path: str, k: int = 8) -> List[Trajectory]:
        """
        运行并行推理
        
        Args:
            query: 审查查询
            file_path: 待审查文件路径
            k: 推理轨迹数
            
        Returns:
            List[Trajectory]: 推理轨迹列表
        """
        pass
```

#### 2. Sequential Deliberation（顺序审议）

**职责**：对推理轨迹进行批判性审查，选择最佳答案。

**策略**：

| 策略 | 说明 | 适用场景 |
|------|------|----------|
| max_answer_frequency | 选择出现频率最高的答案 | 通用场景 |
| max_quality_score | 选择质量分数最高的答案 | 高质量要求 |
| weighted_average | 加权平均 | 综合评估 |

**输出**：

```python
@dataclass
class DeliberationResult:
    selected_trajectories: List[str]
    final_answer: str
    confidence: float
    reasoning: str
```

**接口定义**：

```python
class SequentialDeliberation:
    def run(self, trajectories: List[Trajectory], strategy: str = "max_answer_frequency") -> DeliberationResult:
        """
        运行顺序审议
        
        Args:
            trajectories: 推理轨迹列表
            strategy: 审议策略
            
        Returns:
            DeliberationResult: 审议结果
        """
        pass
```

#### 3. Conclusion Validation（结论校验）

**职责**：使用规则引擎校验 LLM 结论，确保准确性。

**规则引擎**：

| 规则 | 说明 | 触发条件 |
|------|------|----------|
| p0_veto | P0 一票否决 | 存在 P0 问题 |
| threshold_rule | 阈值规则 | 问题数超过阈值 |
| weighted_score | 加权评分 | 加权分数超过阈值 |
| domain_coverage | 领域覆盖率 | 覆盖率低于阈值 |

**输出**：

```python
@dataclass
class ValidationResult:
    verdict: str  # PASS, CONDITIONAL_PASS, REJECT
    original_verdict: str
    verdict_changed: bool
    rules_applied: List[RuleResult]
    issues: List[Issue]
    confidence: float
```

**接口定义**：

```python
class ConclusionValidator:
    def validate(self, issues: List[Issue], llm_verdict: str) -> ValidationResult:
        """
        校验结论
        
        Args:
            issues: 问题列表
            llm_verdict: LLM 原始结论
            
        Returns:
            ValidationResult: 校验结果
        """
        pass
```

---

## 2.3 HeavySkill 流程

### 标准流程

```
输入: query + file_path
    ↓
Stage 1: Parallel Reasoning (K trajectories)
    ↓
Stage 2: Sequential Deliberation (select best)
    ↓
Stage 3: Conclusion Validation (rule engine)
    ↓
输出: validated_result
```

### 阶段详解

#### Stage 1: Parallel Reasoning

**输入**：query + file_path

**处理**：
1. 读取待审查文件
2. 构建 prompt
3. 并行生成 K 条推理轨迹
4. 过滤低质量轨迹

**输出**：List[Trajectory]

#### Stage 2: Sequential Deliberation

**输入**：List[Trajectory]

**处理**：
1. 加载轨迹到 Memory Cache
2. 选择审议策略
3. 执行审议
4. 生成最终答案

**输出**：DeliberationResult

#### Stage 3: Conclusion Validation

**输入**：DeliberationResult

**处理**：
1. 从轨迹中提取问题
2. 推断 LLM 结论
3. 运行规则引擎
4. 生成校验结果

**输出**：ValidationResult

---

## 2.4 HeavySkill 配置

### 主配置文件

```yaml
# ~/.hermes/skills/heavyskill/config.yaml

# API 配置
api_base: https://api.deepseek.com
api_key: ${DEEPSEEK_API_KEY}
model: deepseek-v4-pro

# 推理配置
reason_k: 8
summary_k: 4
temperature: 1.0
top_p: 0.95
top_k: 10
max_tokens: 32768

# 审议配置
iterations: 1
strategy: max_answer_frequency

# 输出配置
language: cn
output_dir: /tmp/heavyskill_output
save_trajectories: false

# 超时配置
timeout: 300
```

### 检查清单配置

```yaml
# ~/.hermes/skills/heavyskill-optimize/checklists/security.yaml

domain: security
name: "安全审查清单"
version: "1.0"

items:
  - id: "S-01"
    question: "是否存在SQL注入风险？"
    severity: "P0"
    category: "输入验证"
    check_points:
      - "是否使用参数化查询？"
      - "是否对用户输入进行验证？"
```

---

# 第三部分：HGF + HeavySkill 结合方案

## 3.1 结合架构

### 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                HGF + HeavySkill 结合架构                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    HGF 流程控制层                        │    │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐   │    │
│  │  │  Task   │  │  Risk   │  │  Gate   │  │ Failure │   │    │
│  │  │Classif. │─▶│Assessor │─▶│Executor │─▶│ Handler │   │    │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────┘   │    │
│  └─────────────────────────────────────────────────────────┘    │
│                          │                                       │
│                          ▼                                       │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                  HeavySkill 审查引擎                     │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │    │
│  │  │  Parallel   │  │ Sequential  │  │ Conclusion  │     │    │
│  │  │  Reasoning  │─▶│Deliberation │─▶│ Validation  │     │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘     │    │
│  └─────────────────────────────────────────────────────────┘    │
│                          │                                       │
│                          ▼                                       │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                  辅助组件层                              │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │    │
│  │  │   Query     │  │  Checklist  │  │   Report    │     │    │
│  │  │  Enhancer   │  │   Manager   │  │  Generator  │     │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘     │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3.2 接口契约定义

### 3.2.1 HGF 组件接口

#### TaskClassifier 接口

```python
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class TaskClassification:
    """任务分类结果"""
    level: str  # L0, L1, L2, L3
    type: str   # CODE, CONFIG, IAC, DOCS, REVIEW
    risk: str   # low, medium, high
    estimated_time: str
    files: List[str]
    lines: int
    metadata: dict  # 扩展字段

class TaskClassifierInterface:
    """任务分类器接口"""
    
    def classify(self, description: str, files: List[str], lines: int = 0) -> TaskClassification:
        """
        对任务进行分类
        
        Args:
            description: 任务描述
            files: 变更文件列表
            lines: 变更行数
            
        Returns:
            TaskClassification: 任务分类结果
            
        Raises:
            ClassificationError: 分类失败时抛出
        """
        pass
```

#### RiskAssessor 接口

```python
@dataclass
class RiskAssessment:
    """风险评估结果"""
    risk_score: int  # 0-30
    risk_level: str  # low, medium, high
    risk_factors: Dict[str, int]
    affected_areas: List[str]
    metadata: dict  # 扩展字段

class RiskAssessorInterface:
    """风险评估器接口"""
    
    def assess(self, affected_areas: List[str], description: str = "") -> RiskAssessment:
        """
        评估任务风险
        
        Args:
            affected_areas: 影响区域列表
            description: 任务描述
            
        Returns:
            RiskAssessment: 风险评估结果
            
        Raises:
            AssessmentError: 评估失败时抛出
        """
        pass
```

#### GateExecutor 接口

```python
@dataclass
class GateResult:
    """门禁执行结果"""
    name: str
    status: str  # PASSED, FAILED, SKIPPED, ERROR
    level: str   # MUST_PASS, SHOULD_PASS, OPTIONAL
    details: Dict[str, Any]
    duration: float
    message: str
    metadata: dict  # 扩展字段

class GateExecutorInterface:
    """门禁执行器接口"""
    
    def execute(self, gates: List[str], context: Dict[str, Any]) -> List[GateResult]:
        """
        执行门禁检查
        
        Args:
            gates: 门禁列表
            context: 上下文信息
            
        Returns:
            List[GateResult]: 门禁执行结果列表
            
        Raises:
            GateExecutionError: 执行失败时抛出
        """
        pass
```

### 3.2.2 HeavySkill 组件接口

#### ParallelReasoning 接口

```python
@dataclass
class Trajectory:
    """推理轨迹"""
    id: str
    content: str
    tokens: int
    latency: float
    quality_score: float
    metadata: dict  # 扩展字段

class ParallelReasoningInterface:
    """并行推理接口"""
    
    def run(self, query: str, file_path: str, k: int = 8) -> List[Trajectory]:
        """
        运行并行推理
        
        Args:
            query: 审查查询
            file_path: 待审查文件路径
            k: 推理轨迹数
            
        Returns:
            List[Trajectory]: 推理轨迹列表
            
        Raises:
            ReasoningError: 推理失败时抛出
        """
        pass
```

#### SequentialDeliberation 接口

```python
@dataclass
class DeliberationResult:
    """审议结果"""
    selected_trajectories: List[str]
    final_answer: str
    confidence: float
    reasoning: str
    metadata: dict  # 扩展字段

class SequentialDeliberationInterface:
    """顺序审议接口"""
    
    def run(self, trajectories: List[Trajectory], strategy: str = "max_answer_frequency") -> DeliberationResult:
        """
        运行顺序审议
        
        Args:
            trajectories: 推理轨迹列表
            strategy: 审议策略
            
        Returns:
            DeliberationResult: 审议结果
            
        Raises:
            DeliberationError: 审议失败时抛出
        """
        pass
```

#### ConclusionValidator 接口

```python
@dataclass
class ValidationResult:
    """校验结果"""
    verdict: str  # PASS, CONDITIONAL_PASS, REJECT
    original_verdict: str
    verdict_changed: bool
    rules_applied: List[Dict[str, Any]]
    issues: List[Dict[str, Any]]
    confidence: float
    metadata: dict  # 扩展字段

class ConclusionValidatorInterface:
    """结论校验器接口"""
    
    def validate(self, issues: List[Dict[str, Any]], llm_verdict: str) -> ValidationResult:
        """
        校验结论
        
        Args:
            issues: 问题列表
            llm_verdict: LLM 原始结论
            
        Returns:
            ValidationResult: 校验结果
            
        Raises:
            ValidationError: 校验失败时抛出
        """
        pass
```

### 3.2.3 辅助组件接口

#### QueryEnhancer 接口

```python
class QueryEnhancerInterface:
    """Query 增强器接口"""
    
    def enhance(self, query: str, file_content: str, domains: List[str] = None) -> str:
        """
        增强 query
        
        Args:
            query: 原始查询
            file_content: 待审查文件内容
            domains: 领域列表（可选，自动识别）
            
        Returns:
            str: 增强后的查询
        """
        pass
```

#### ChecklistManager 接口

```python
@dataclass
class Checklist:
    """检查清单"""
    name: str
    domain: str
    items: List[Dict[str, Any]]
    metadata: dict  # 扩展字段

class ChecklistManagerInterface:
    """检查清单管理器接口"""
    
    def get_checklist(self, domains: List[str]) -> Checklist:
        """
        获取检查清单
        
        Args:
            domains: 领域列表
            
        Returns:
            Checklist: 检查清单
        """
        pass
    
    def format_checklist(self, checklist: Checklist) -> str:
        """
        格式化检查清单
        
        Args:
            checklist: 检查清单
            
        Returns:
            str: 格式化后的文本
        """
        pass
```

#### ReportGenerator 接口

```python
@dataclass
class ReviewReport:
    """审查报告"""
    title: str
    summary: str
    verdict: str
    issues: List[Dict[str, Any]]
    gates: List[Dict[str, Any]]
    recommendations: List[str]
    metadata: dict

class ReportGeneratorInterface:
    """报告生成器接口"""
    
    def generate(self, 
                 task: TaskClassification,
                 risk: RiskAssessment,
                 heavyskill: ValidationResult,
                 gates: List[GateResult]) -> ReviewReport:
        """
        生成审查报告
        
        Args:
            task: 任务分类
            risk: 风险评估
            heavyskill: HeavySkill 校验结果
            gates: 门禁执行结果
            
        Returns:
            ReviewReport: 审查报告
        """
        pass
```

---

## 3.3 输出 Schema 定义

### 3.3.1 HeavySkill 输出 Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "reasoning": {
      "type": "object",
      "properties": {
        "trajectories": {
          "type": "array",
          "items": {
            "type": "string"
          }
        }
      },
      "required": ["trajectories"]
    },
    "final_answer": {
      "type": "string"
    },
    "total_tokens": {
      "type": "integer"
    },
    "total_latency": {
      "type": "number"
    }
  },
  "required": ["reasoning", "final_answer"]
}
```

### 3.3.2 校验结果输出 Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "verdict": {
      "type": "string",
      "enum": ["PASS", "CONDITIONAL_PASS", "REJECT"]
    },
    "original_verdict": {
      "type": "string"
    },
    "verdict_changed": {
      "type": "boolean"
    },
    "rules_applied": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "rule": {"type": "string"},
          "triggered": {"type": "boolean"},
          "verdict": {"type": "string"},
          "reason": {"type": "string"}
        }
      }
    },
    "issues": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "id": {"type": "string"},
          "title": {"type": "string"},
          "severity": {"type": "string", "enum": ["P0", "P1", "P2"]},
          "domain": {"type": "string"},
          "description": {"type": "string"}
        }
      }
    },
    "confidence": {
      "type": "number",
      "minimum": 0,
      "maximum": 1
    }
  },
  "required": ["verdict", "original_verdict", "verdict_changed", "rules_applied", "issues"]
}
```

### 3.3.3 审查报告输出 Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "title": {"type": "string"},
    "summary": {"type": "string"},
    "verdict": {
      "type": "string",
      "enum": ["PASS", "CONDITIONAL_PASS", "REJECT"]
    },
    "issues": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "level": {"type": "string", "enum": ["P0", "P1", "P2"]},
          "title": {"type": "string"},
          "description": {"type": "string"},
          "location": {"type": "string"},
          "suggestion": {"type": "string"}
        }
      }
    },
    "gates": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": {"type": "string"},
          "status": {"type": "string", "enum": ["PASSED", "FAILED", "SKIPPED"]},
          "message": {"type": "string"}
        }
      }
    },
    "recommendations": {
      "type": "array",
      "items": {"type": "string"}
    }
  },
  "required": ["title", "verdict", "issues", "gates"]
}
```

---

## 3.4 异常处理设计

### 3.4.1 异常类型定义

```python
class HGFHeavySkillError(Exception):
    """HGF + HeavySkill 基础异常"""
    pass

class TaskClassificationError(HGFHeavySkillError):
    """任务分类异常"""
    pass

class RiskAssessmentError(HGFHeavySkillError):
    """风险评估异常"""
    pass

class GateExecutionError(HGFHeavySkillError):
    """门禁执行异常"""
    pass

class HeavySkillError(HGFHeavySkillError):
    """HeavySkill 执行异常"""
    pass

class ReasoningError(HeavySkillError):
    """推理异常"""
    pass

class DeliberationError(HeavySkillError):
    """审议异常"""
    pass

class ValidationError(HeavySkillError):
    """校验异常"""
    pass

class ChecklistError(HGFHeavySkillError):
    """检查清单异常"""
    pass

class ReportGenerationError(HGFHeavySkillError):
    """报告生成异常"""
    pass
```

### 3.4.2 异常处理策略

```python
class ErrorHandler:
    """异常处理器"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.max_retries = config.get('max_retries', 3)
        self.retry_delay = config.get('retry_delay', 5)
        self.fallback_enabled = config.get('fallback_enabled', True)
    
    def handle_heavyskill_error(self, error: HeavySkillError, context: Dict) -> Dict:
        """
        处理 HeavySkill 异常
        
        Args:
            error: 异常信息
            context: 上下文信息
            
        Returns:
            Dict: 处理结果
        """
        # 记录异常
        self._log_error(error, context)
        
        # 重试策略
        if self._should_retry(error, context):
            return {"action": "retry", "delay": self.retry_delay}
        
        # 降级策略
        if self.fallback_enabled:
            return {"action": "fallback", "verdict": "CONDITIONAL_PASS"}
        
        # 终止
        return {"action": "abort", "reason": str(error)}
    
    def handle_checklist_error(self, error: ChecklistError, context: Dict) -> Dict:
        """
        处理检查清单异常
        
        Args:
            error: 异常信息
            context: 上下文信息
            
        Returns:
            Dict: 处理结果
        """
        # 记录异常
        self._log_error(error, context)
        
        # 使用默认清单
        return {"action": "use_default", "checklist": "general"}
    
    def _should_retry(self, error: Exception, context: Dict) -> bool:
        """判断是否应该重试"""
        retry_count = context.get('retry_count', 0)
        return retry_count < self.max_retries
    
    def _log_error(self, error: Exception, context: Dict):
        """记录异常日志"""
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error: {error}, Context: {context}")
```

### 3.4.3 降级策略

```python
class FallbackStrategy:
    """降级策略"""
    
    def fallback_heavyskill(self, query: str, file_path: str) -> Dict:
        """
        HeavySkill 降级策略
        
        当 HeavySkill 执行失败时，使用简化版本
        """
        # 使用单轨迹推理
        trajectory = self._run_single_trajectory(query, file_path)
        
        return {
            "verdict": "CONDITIONAL_PASS",
            "reasoning": {"trajectories": [trajectory]},
            "final_answer": trajectory,
            "fallback": True,
            "fallback_reason": "HeavySkill 执行失败，使用单轨迹推理"
        }
    
    def fallback_checklist(self, domains: List[str]) -> Checklist:
        """
        检查清单降级策略
        
        当检查清单加载失败时，使用默认清单
        """
        return Checklist(
            name="通用审查清单",
            domain="general",
            items=[
                {"id": "G-01", "question": "需求是否完整？", "severity": "P1"},
                {"id": "G-02", "question": "设计是否合理？", "severity": "P1"},
                {"id": "G-03", "question": "是否有风险遗漏？", "severity": "P1"},
            ]
        )
```

---

## 3.5 集成流程

### 完整流程

```
Phase 0: 需求分析
    │
    ├─▶ 读取方案文档
    ├─▶ 识别方案类型
    └─▶ 提取关键信息
    │
    ▼
Phase 1: 任务分类（HGF TaskClassifier）
    │
    ├─▶ 输入: description, files, lines
    ├─▶ 处理: 分类任务
    └─▶ 输出: TaskClassification
    │
    ▼
Phase 2: 风险评估（HGF RiskAssessor）
    │
    ├─▶ 输入: affected_areas, description
    ├─▶ 处理: 评估风险
    └─▶ 输出: RiskAssessment
    │
    ▼
Phase 3: HeavySkill 深度审查
    │
    ├─▶ Stage 1: 并行推理（K=8）
    │   ├─▶ 输入: query, file_path
    │   ├─▶ 处理: 生成 8 条轨迹
    │   └─▶ 输出: List[Trajectory]
    │
    ├─▶ Stage 2: 顺序审议
    │   ├─▶ 输入: List[Trajectory]
    │   ├─▶ 处理: 选择最佳答案
    │   └─▶ 输出: DeliberationResult
    │
    └─▶ Stage 3: 结论校验
        ├─▶ 输入: issues, llm_verdict
        ├─▶ 处理: 规则引擎校验
        └─▶ 输出: ValidationResult
    │
    ▼
Phase 4: 门禁执行（HGF GateExecutor）
    │
    ├─▶ 输入: gates, context
    ├─▶ 处理: 执行门禁
    └─▶ 输出: List[GateResult]
    │
    ▼
Phase 5: 报告生成
    │
    ├─▶ 输入: task, risk, heavyskill, gates
    ├─▶ 处理: 生成报告
    └─▶ 输出: ReviewReport
    │
    ▼
输出: 完整审查报告
```

---

## 3.6 配置文件

### 主配置文件

```yaml
# ~/.hermes/skills/heavyskill-optimize/config/hgf-heavyskill.yaml

# HGF 配置
hgf:
  task_classifier:
    enabled: true
    default_level: L2
  
  risk_assessor:
    enabled: true
    default_risk: medium
  
  gate_executor:
    enabled: true
    gates:
      - heavyskill_review
      - checklist_coverage

# HeavySkill 配置
heavyskill:
  reason_k: 8
  summary_k: 4
  temperature: 1.0
  top_p: 0.95
  timeout: 300

# 检查清单配置
checklists:
  enabled: true
  domains:
    - security
    - architecture
    - performance
    - api
    - database
    - deployment

# 结论校验配置
conclusion_validator:
  enabled: true
  shadow_mode: false
  confidence_threshold: 0.8

# 异常处理配置
error_handler:
  max_retries: 3
  retry_delay: 5
  fallback_enabled: true

# 报告配置
report:
  format: markdown
  include_trajectories: false
  include_checklist: true
```

### 门禁配置文件

```yaml
# ~/.hermes/skills/heavyskill-optimize/config/gates.yaml

gates:
  # HeavySkill 审查门禁
  heavyskill_review:
    tool: "heavyskill"
    level: "MUST_PASS"
    criteria:
      - "verdict != REJECT"
      - "issue_count.p0 == 0"
      - "confidence >= 0.7"
    timeout: 300
  
  # 检查清单覆盖门禁
  checklist_coverage:
    tool: "checklist_validator"
    level: "MUST_PASS"
    criteria:
      - "coverage_rate >= 0.6"
      - "p0_items_covered == true"
  
  # 专家审查门禁（可选）
  expert_review:
    tool: "delegate_task"
    level: "SHOULD_PASS"
    criteria:
      - "expert_score >= 3.5"
    trigger_conditions:
      - "risk_level == high"
      - "heavyskill_verdict == REJECT"
```

---

## 3.7 实施计划

### Phase 0: 接口适配（3天）

- [ ] 定义 HGF 组件接口
- [ ] 定义 HeavySkill 组件接口
- [ ] 定义辅助组件接口
- [ ] 实现接口适配层

### Phase 1: 核心集成（1周）

- [ ] 实现 HGFHeavySkillReviewer 类
- [ ] 实现异常处理器
- [ ] 实现降级策略
- [ ] 创建配置文件

### Phase 2: 门禁集成（3天）

- [ ] 配置门禁规则
- [ ] 实现门禁执行器
- [ ] 实现报告生成器

### Phase 3: 测试优化（1周）

- [ ] 编写单元测试
- [ ] 运行集成测试
- [ ] 运行 7 个评测用例
- [ ] 优化配置参数

### Phase 4: 文档部署（3天）

- [ ] 编写使用文档
- [ ] 创建示例配置
- [ ] 部署 MCP Server
- [ ] 编写 README

---

## 3.8 预期效果

### 效率提升

| 指标 | 人工审查 | HGF+HeavySkill | 提升 |
|------|----------|----------------|------|
| 审查时间 | 2-4小时 | 10-15分钟 | **90%↓** |
| 问题发现率 | 60-70% | 85-90% | **25%↑** |
| 结论准确性 | 80% | 95% | **15%↑** |
| 可追溯性 | 部分 | 完整 | **100%** |

### 质量提升

- **系统化**：检查清单确保全面覆盖
- **可量化**：评分体系提供客观指标
- **可重复**：标准化流程确保一致性
- **可改进**：数据驱动持续优化

---

# 附录

## A. 参考资料

- HeavySkill 论文：https://arxiv.org/abs/2605.02396
- HGF GitHub：https://github.com/feiyu169/hermes-gate-flow
- HeavySkill 官网：https://sd114.wiki/sites/29321.html

## B. 变更记录

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| V1.0 | 2026-06-21 | 初始版本 |
| V2.0 | 2026-06-21 | 根据 HeavySkill 审查意见修复 P0/P1 问题 |

## C. 联系方式

- 作者：Hermes Agent
- 日期：2026-06-21
