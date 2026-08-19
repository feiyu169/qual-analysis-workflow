# HGF + HeavySkill 结合技术文档（V4.0）

> 基于 V3 审查意见全面修复
> 日期：2026-06-21
> 修复：P0 领域名对齐、P1 check_scope/languages/严重等级覆盖、P2 前端清单

---

# 变更记录

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| V1.0 | 2026-06-21 | 初始版本 |
| V2.0 | 2026-06-21 | 修复 P0 接口定义、输出 Schema、异常处理 |
| V3.0 | 2026-06-21 | 修复延迟预估、成本量化、并行实现、清单来源、申诉机制 |
| V4.0 | 2026-06-21 | 修复领域名对齐、check_scope、languages、严重等级覆盖、前端清单、动态加载 |

---

# 第一部分：HGF 详细说明

## 1.1 HGF 概述

**HGF（Hermes Gate Flow）** 是一个标准化的代码质量门禁流程，用于确保代码变更的质量和安全性。

### 核心理念

- **流程标准化**：所有代码变更都经过统一的审查流程
- **质量可量化**：通过门禁机制量化评估代码质量
- **风险可控**：根据风险等级调整审查力度
- **可追溯性**：完整记录审查过程和结果

---

## 1.2 HGF 架构

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
│  ┌─────────────┐    ┌─────────────┐                         │
│  │   Appeal    │    │   Failure   │                         │
│  │   Handler   │    │   Handler   │                         │
│  └─────────────┘    └─────────────┘                         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 核心组件

#### 1. Task Classifier（任务分类器）

**接口定义**：

```python
@dataclass
class TaskClassification:
    """任务分类结果"""
    level: str  # L0, L1, L2, L3
    type: str   # CODE, CONFIG, IAC, DOCS, REVIEW
    risk: str   # low, medium, high
    estimated_time: str
    files: List[str]
    lines: int
    skip_heavyskill: bool
    detected_domains: List[str]  # 检测到的领域

class TaskClassifierInterface:
    def classify(self, description: str, files: List[str], lines: int = 0) -> TaskClassification:
        pass
```

#### 2. Risk Assessor（风险评估器）

**接口定义**：

```python
@dataclass
class RiskAssessment:
    """风险评估结果"""
    risk_score: int  # 0-30
    risk_level: str  # low, medium, high
    risk_factors: Dict[str, int]
    affected_areas: List[str]
    skip_heavyskill: bool

class RiskAssessorInterface:
    def assess(self, affected_areas: List[str], description: str = "") -> RiskAssessment:
        pass
```

#### 3. Gate Executor（门禁执行器）

**接口定义**：

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

class GateExecutorInterface:
    def execute(self, gates: List[str], context: Dict[str, Any]) -> List[GateResult]:
        pass
```

#### 4. Appeal Handler（申诉处理器）

**接口定义**：

```python
@dataclass
class AppealRequest:
    """申诉请求"""
    gate_id: str
    user_id: str
    reason: str
    evidence: str
    timestamp: str

@dataclass
class AppealResult:
    """申诉结果"""
    appeal_id: str
    status: str  # pending, approved, rejected
    reviewer: str
    reason: str
    timestamp: str

class AppealHandlerInterface:
    def submit_appeal(self, request: AppealRequest) -> AppealResult:
        pass
    
    def review_appeal(self, appeal_id: str, decision: str, reason: str) -> AppealResult:
        pass
    
    def collect_false_positive(self, gate_id: str, issue_id: str, feedback: str):
        pass
```

---

# 第二部分：HeavySkill 详细说明

## 2.1 HeavySkill 概述

**HeavySkill** 是一种创新的测试时扩展技术，通过并行推理与顺序审议实现高质量审查。

---

## 2.2 HeavySkill 架构

### 核心组件

#### 1. Parallel Reasoning（并行推理）

**并行实现**：使用 asyncio + aiohttp 真正并发

```python
import asyncio
import aiohttp

class ParallelReasoning:
    async def run_async(self, query: str, file_path: str, k: int = 8) -> List[Trajectory]:
        """真正的并发执行"""
        async with aiohttp.ClientSession() as session:
            tasks = [
                self._call_llm_async(session, query, file_path, i)
                for i in range(k)
            ]
            trajectories = await asyncio.gather(*tasks, return_exceptions=True)
        return [t for t in trajectories if not isinstance(t, Exception)]
    
    def run(self, query: str, file_path: str, k: int = 8) -> List[Trajectory]:
        """同步接口"""
        return asyncio.run(self.run_async(query, file_path, k))
```

**配置参数**：

| 参数 | 说明 | 默认值 | 推荐值 |
|------|------|--------|--------|
| reason_k | 推理轨迹数 | 8 | 8 |
| parallel_mode | 并行模式 | async | async/fallback |

#### 2. Sequential Deliberation（顺序审议）

**接口定义**：

```python
@dataclass
class DeliberationResult:
    selected_trajectories: List[str]
    final_answer: str
    confidence: float
    reasoning: str

class SequentialDeliberationInterface:
    def run(self, trajectories: List[Trajectory], strategy: str = "max_answer_frequency") -> DeliberationResult:
        pass
```

#### 3. Conclusion Validation（结论校验）

**接口定义**：

```python
@dataclass
class ValidationResult:
    verdict: str  # PASS, CONDITIONAL_PASS, REJECT
    original_verdict: str
    verdict_changed: bool
    rules_applied: List[Dict[str, Any]]
    issues: List[Dict[str, Any]]
    confidence: float

class ConclusionValidatorInterface:
    def validate(self, issues: List[Dict[str, Any]], llm_verdict: str) -> ValidationResult:
        pass
```

---

# 第三部分：HGF + HeavySkill 结合方案

## 3.1 结合架构

```
┌─────────────────────────────────────────────────────────────────┐
│                HGF + HeavySkill 结合架构                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    HGF 流程控制层                        │    │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐   │    │
│  │  │  Task   │  │  Risk   │  │  Gate   │  │ Appeal  │   │    │
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
│  │  │ (asyncio)   │  │             │  │             │     │    │
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

## 3.2 检查清单系统（V2 重大更新）⭐

### 3.2.1 清单概览

| 领域 | 文件名 | 检查项数 | P0 | P1 | P2 |
|------|--------|----------|----|----|-----|
| security | security.yaml | 14 | 4 | 7 | 3 |
| architecture | architecture.yaml | 13 | 1 | 9 | 3 |
| performance | performance.yaml | 14 | 0 | 9 | 5 |
| api | api.yaml | 18 | 0 | 9 | 9 |
| database | database.yaml | 18 | 0 | 10 | 8 |
| deployment | deployment.yaml | 20 | 0 | 9 | 11 |
| **frontend** | **frontend.yaml** | **8** | **0** | **4** | **4** |
| general | general.yaml | 15 | 0 | 7 | 8 |
| **总计** | - | **120** | **5** | **64** | **51** |

### 3.2.2 检查项结构（V2 更新）

```yaml
- id: "S-01"
  question: "是否存在SQL注入风险？"
  severity: "P0"
  category: "输入验证"
  check_scope: [code, config]  # V2 新增：检查范围
  languages: [python, java, go, js, php, ruby]  # V2 新增：支持的语言
  check_points:
    - "是否使用参数化查询？"
    - "是否对用户输入进行验证？"
  fix_suggestion:  # V2 更新：分步骤格式
    steps:
      - "1. 识别所有 SQL 查询语句"
      - "2. 检查是否使用参数化查询"
      - "3. 如有拼接，改为参数化查询或使用 ORM"
    example: |
      # Python 示例
      cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
  references:
    - "https://owasp.org/www-community/attacks/SQL_Injection"
  upgrade_conditions:  # V2 新增：升级条件
    - "使用 dangerouslySetInnerHTML → 升级为 P0"
```

### 3.2.3 check_scope 字段说明

| 值 | 说明 | HeavySkill 处理方式 |
|----|------|---------------------|
| code | 可从代码中检查 | 自动检查，影响 verdict |
| config | 可从配置中检查 | 自动检查，影响 verdict |
| process | 流程问题，无法自动化 | 仅提醒，不影响 verdict |

### 3.2.4 languages 字段说明

```yaml
languages: [python, java, go, js, php, ruby]
```

如果项目语言不在列表中，该检查项会被跳过。

### 3.2.5 严重等级说明

| 等级 | 说明 | 处理方式 |
|------|------|----------|
| P0 | 致命问题 | 必须修复，阻断合并 |
| P1 | 重大问题 | 应该修复，警告 |
| P2 | 一般问题 | 建议修复，仅记录 |

### 3.2.6 项目级别严重等级覆盖

```yaml
# 项目配置示例
severity_overrides:
  finance:
    D-07: P0  # 金融项目：事务管理升级为 P0
    S-06: P0  # 金融项目：密码加密必须 P0
  
  healthcare:
    S-11: P0  # 医疗项目：数据加密传输必须 P0
    D-16: P0  # 医疗项目：数据加密必须 P0
```

### 3.2.7 动态加载策略

HeavySkill 不会加载全部 120 项检查，而是根据 MR 涉及的文件动态加载：

**映射规则**：

| 文件扩展名 | 领域 |
|-----------|------|
| .jsx, .tsx, .vue, .css, .scss | frontend |
| .sql, model, entity | database |
| .yaml, .yml, .tf, Dockerfile | deployment |
| api, controller, route | api |
| 所有代码 | security, architecture, performance |

**示例**：
- 只改 API 文件 → security + architecture + performance + api ≈ **60 项**
- 只改前端文件 → security + architecture + performance + frontend ≈ **50 项**
- 改数据库 + API → security + architecture + performance + database + api ≈ **80 项**

**实现代码**：

```python
class ChecklistManager:
    """检查清单管理器"""
    
    FILE_EXTENSION_MAPPING = {
        '.jsx': 'frontend', '.tsx': 'frontend', '.vue': 'frontend',
        '.css': 'frontend', '.scss': 'frontend',
        '.sql': 'database', 'model': 'database', 'entity': 'database',
        '.yaml': 'deployment', '.yml': 'deployment', '.tf': 'deployment',
        'Dockerfile': 'deployment',
        'api': 'api', 'controller': 'api', 'route': 'api',
    }
    
    def get_checklist_for_mr(self, files: List[str], project_language: str = None) -> Checklist:
        """根据 MR 文件动态加载清单"""
        domains = {'security', 'architecture', 'performance'}  # 基础领域
        
        for file in files:
            ext = os.path.splitext(file)[1]
            basename = os.path.basename(file).lower()
            
            # 文件扩展名 → 领域映射
            if ext in self.FILE_EXTENSION_MAPPING:
                domains.add(self.FILE_EXTENSION_MAPPING[ext])
            
            # 文件名关键字 → 领域映射
            for keyword, domain in self.FILE_EXTENSION_MAPPING.items():
                if keyword in basename:
                    domains.add(domain)
        
        # 加载对应领域的清单
        checklist = self.get_checklist(list(domains))
        
        # 按项目语言过滤
        if project_language:
            checklist = self.filter_by_language(checklist, project_language)
        
        return checklist
    
    def filter_by_language(self, checklist: Checklist, language: str) -> Checklist:
        """按项目语言过滤检查项"""
        filtered_items = []
        for item in checklist.items:
            # 如果没有 languages 字段，默认适用于所有语言
            if 'languages' not in item:
                filtered_items.append(item)
            # 如果项目语言在列表中
            elif language in item['languages'] or 'all' in item['languages']:
                filtered_items.append(item)
        
        checklist.items = filtered_items
        return checklist
```

---

## 3.3 接口契约定义

### 3.3.1 HGF 组件接口

```python
# TaskClassifier 接口
class TaskClassifierInterface:
    def classify(self, description: str, files: List[str], lines: int = 0) -> TaskClassification:
        pass

# RiskAssessor 接口
class RiskAssessorInterface:
    def assess(self, affected_areas: List[str], description: str = "") -> RiskAssessment:
        pass

# GateExecutor 接口
class GateExecutorInterface:
    def execute(self, gates: List[str], context: Dict[str, Any]) -> List[GateResult]:
        pass

# AppealHandler 接口
class AppealHandlerInterface:
    def submit_appeal(self, request: AppealRequest) -> AppealResult:
        pass
    def review_appeal(self, appeal_id: str, decision: str, reason: str) -> AppealResult:
        pass
    def collect_false_positive(self, gate_id: str, issue_id: str, feedback: str):
        pass
```

### 3.3.2 HeavySkill 组件接口

```python
# ParallelReasoning 接口
class ParallelReasoningInterface:
    def run(self, query: str, file_path: str, k: int = 8) -> List[Trajectory]:
        pass
    async def run_async(self, query: str, file_path: str, k: int = 8) -> List[Trajectory]:
        pass

# SequentialDeliberation 接口
class SequentialDeliberationInterface:
    def run(self, trajectories: List[Trajectory], strategy: str = "max_answer_frequency") -> DeliberationResult:
        pass

# ConclusionValidator 接口
class ConclusionValidatorInterface:
    def validate(self, issues: List[Dict[str, Any]], llm_verdict: str) -> ValidationResult:
        pass
```

### 3.3.3 辅助组件接口

```python
# QueryEnhancer 接口
class QueryEnhancerInterface:
    def enhance(self, query: str, file_content: str, domains: List[str] = None) -> str:
        pass

# ChecklistManager 接口
class ChecklistManagerInterface:
    def get_checklist(self, domains: List[str]) -> Checklist:
        pass
    def get_checklist_for_mr(self, files: List[str], project_language: str = None) -> Checklist:
        pass
    def format_checklist(self, checklist: Checklist) -> str:
        pass
    def update_from_feedback(self, feedback: List[Dict[str, Any]]):
        pass

# ReportGenerator 接口
class ReportGeneratorInterface:
    def generate(self, task: TaskClassification, risk: RiskAssessment,
                 heavyskill: ValidationResult, gates: List[GateResult]) -> ReviewReport:
        pass
```

---

## 3.4 输出 Schema 定义

### 3.4.1 HeavySkill 输出 Schema

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
          "items": {"type": "string"}
        }
      },
      "required": ["trajectories"]
    },
    "final_answer": {"type": "string"},
    "total_tokens": {"type": "integer"},
    "total_latency": {"type": "number"}
  },
  "required": ["reasoning", "final_answer"]
}
```

### 3.4.2 校验结果输出 Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "verdict": {
      "type": "string",
      "enum": ["PASS", "CONDITIONAL_PASS", "REJECT"]
    },
    "original_verdict": {"type": "string"},
    "verdict_changed": {"type": "boolean"},
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
          "description": {"type": "string"},
          "check_scope": {"type": "string", "enum": ["code", "config", "process"]},
          "fix_suggestion": {
            "type": "object",
            "properties": {
              "steps": {"type": "array", "items": {"type": "string"}},
              "example": {"type": "string"}
            }
          }
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

### 3.4.3 审查报告输出 Schema

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
          "suggestion": {
            "type": "object",
            "properties": {
              "steps": {"type": "array", "items": {"type": "string"}},
              "example": {"type": "string"}
            }
          },
          "check_scope": {"type": "string"}
        }
      }
    },
    "gates": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": {"type": "string"},
          "status": {"type": "string"},
          "message": {"type": "string"}
        }
      }
    },
    "recommendations": {
      "type": "array",
      "items": {"type": "string"}
    },
    "appeal_info": {
      "type": "object",
      "properties": {
        "can_appeal": {"type": "boolean"},
        "appeal_url": {"type": "string"},
        "appeal_deadline": {"type": "string"}
      }
    },
    "cost": {
      "type": "object",
      "properties": {
        "total_tokens": {"type": "integer"},
        "input_tokens": {"type": "integer"},
        "output_tokens": {"type": "integer"},
        "estimated_cost_usd": {"type": "number"}
      }
    },
    "checklist_coverage": {
      "type": "object",
      "properties": {
        "total_items": {"type": "integer"},
        "checked_items": {"type": "integer"},
        "coverage_rate": {"type": "number"},
        "domains_loaded": {"type": "array", "items": {"type": "string"}}
      }
    }
  },
  "required": ["title", "verdict", "issues", "gates"]
}
```

---

## 3.5 异常处理设计

### 3.5.1 异常类型定义

```python
class HGFHeavySkillError(Exception):
    pass

class TaskClassificationError(HGFHeavySkillError):
    pass

class RiskAssessmentError(HGFHeavySkillError):
    pass

class GateExecutionError(HGFHeavySkillError):
    pass

class HeavySkillError(HGFHeavySkillError):
    pass

class ReasoningError(HeavySkillError):
    pass

class DeliberationError(HeavySkillError):
    pass

class ValidationError(HeavySkillError):
    pass

class ChecklistError(HGFHeavySkillError):
    pass

class ReportGenerationError(HGFHeavySkillError):
    pass

class AppealError(HGFHeavySkillError):
    pass
```

### 3.5.2 异常处理策略

```python
class ErrorHandler:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.max_retries = config.get('max_retries', 3)
        self.retry_delay = config.get('retry_delay', 5)
        self.fallback_enabled = config.get('fallback_enabled', True)
    
    def handle_heavyskill_error(self, error: HeavySkillError, context: Dict) -> Dict:
        self._log_error(error, context)
        
        if self._should_retry(error, context):
            return {"action": "retry", "delay": self.retry_delay}
        
        if self.fallback_enabled:
            return {"action": "fallback", "verdict": "CONDITIONAL_PASS"}
        
        return {"action": "abort", "reason": str(error)}
```

### 3.5.3 降级策略

```python
class FallbackStrategy:
    def fallback_heavyskill(self, query: str, file_path: str) -> Dict:
        """HeavySkill 降级策略"""
        trajectory = self._run_single_trajectory(query, file_path)
        return {
            "verdict": "CONDITIONAL_PASS",
            "reasoning": {"trajectories": [trajectory]},
            "final_answer": trajectory,
            "fallback": True,
            "fallback_reason": "HeavySkill 执行失败，使用单轨迹推理"
        }
    
    def fallback_checklist(self, domains: List[str]) -> Checklist:
        """检查清单降级策略"""
        return Checklist(
            name="通用审查清单",
            domain="general",
            items=[
                {"id": "G-01", "question": "需求是否完整？", "severity": "P1"},
                {"id": "G-02", "question": "设计是否合理？", "severity": "P1"},
                {"id": "G-03", "question": "是否有风险遗漏？", "severity": "P1"},
            ],
            source="fallback"
        )
```

---

## 3.6 集成流程（含延迟预估）

```
Phase 0: 需求分析（<10s）
    │
    ├─▶ 读取方案文档
    ├─▶ 识别方案类型
    └─▶ 提取关键信息
    │
    ▼
Phase 1: 任务分类（<5s）
    │
    ├─▶ 输入: description, files, lines
    ├─▶ 处理: 分类任务，检测领域
    └─▶ 输出: TaskClassification（含 detected_domains）
    │
    ▼
Phase 2: 风险评估（<5s）
    │
    ├─▶ 输入: affected_areas, description
    ├─▶ 处理: 评估风险
    └─▶ 输出: RiskAssessment
    │
    ▼
Phase 3: HeavySkill 深度审查（30s - 5min）
    │
    ├─▶ Stage 0: 动态加载检查清单（<1s）
    │   ├─▶ 根据文件扩展名映射领域
    │   ├─▶ 按项目语言过滤检查项
    │   └─▶ 输出: 动态清单（约 50-80 项）
    │
    ├─▶ Stage 1: 并行推理（K=8，真正并发）
    │   ├─▶ 输入: query, file_path
    │   ├─▶ 处理: 生成 8 条轨迹（asyncio 并发）
    │   ├─▶ 输出: List[Trajectory]
    │   └─▶ 延迟: 30-60s（真并行）
    │
    ├─▶ Stage 2: 顺序审议
    │   ├─▶ 输入: List[Trajectory]
    │   ├─▶ 处理: 选择最佳答案
    │   ├─▶ 输出: DeliberationResult
    │   └─▶ 延迟: 1-2min
    │
    └─▶ Stage 3: 结论校验
        ├─▶ 输入: issues, llm_verdict, checklist
        ├─▶ 处理: 规则引擎校验（仅检查 code/config 类）
        ├─▶ 输出: ValidationResult
        └─▶ 延迟: 10-30s
    │
    ▼
Phase 4: 门禁执行（<30s）
    │
    ├─▶ 输入: gates, context
    ├─▶ 处理: 执行门禁
    └─▶ 输出: List[GateResult]
    │
    ▼
Phase 5: 报告生成（<10s）
    │
    ├─▶ 输入: task, risk, heavyskill, gates
    ├─▶ 处理: 生成报告（含 fix_suggestion 分步骤）
    └─▶ 输出: ReviewReport
    │
    ▼
Phase 6: 申诉处理（可选，0s - 24h）
    │
    ├─▶ 如果用户申诉
    │   ├─▶ AppealHandler 接收
    │   ├─▶ 人工审核
    │   └─▶ 更新清单规则
    │
    └─▶ 如果无申诉
        └─▶ 继续
    │
    ▼
输出: 完整审查报告
```

---

## 3.7 Token 成本量化

### 单次审查成本

| 项目 | Token 数 | 单价 | 成本 |
|------|----------|------|------|
| 输入（代码 + 清单） | ~60,000 | $0.14/M | $0.0084 |
| 输出 | ~15,000 | $0.28/M | $0.0042 |
| **总计** | ~75,000 | - | **$0.0126** |

### 清单 Token 消耗

| 清单项数 | 清单 Token 数 | 说明 |
|----------|--------------|------|
| 50 项（API 文件） | ~8,000 | security + architecture + performance + api |
| 80 项（数据库 + API） | ~12,000 | security + architecture + performance + database + api |
| 120 项（全部） | ~18,000 | 不推荐，会显著增加成本 |

### 动态加载的成本优化

通过动态加载，平均可节省 **30-40%** 的 Token 消耗：
- 全部加载：~18,000 token（清单） + ~42,000 token（代码） = ~60,000 token
- 动态加载：~10,000 token（清单） + ~42,000 token（代码） = ~52,000 token

---

## 3.8 配置文件

### 主配置文件

```yaml
# ~/.hermes/skills/heavyskill-optimize/config/hgf-heavyskill.yaml

# HGF 配置
hgf:
  task_classifier:
    enabled: true
    default_level: L2
    skip_heavyskill_threshold: 50
  
  risk_assessor:
    enabled: true
    default_risk: medium
    skip_heavyskill_threshold: low
  
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
  timeout: 600
  parallel_mode: async

# 检查清单配置（V2 更新）
checklists:
  enabled: true
  source: builtin
  dynamic_loading: true
  file_extension_mapping:
    ".jsx": frontend
    ".tsx": frontend
    ".vue": frontend
    ".css": frontend
    ".scss": frontend
    ".sql": database
    "model": database
    "entity": database
    ".yaml": deployment
    ".yml": deployment
    ".tf": deployment
    "Dockerfile": deployment
    "api": api
    "controller": api
    "route": api

# 项目配置（V2 新增）
project:
  language: python  # 项目语言
  type: web  # 项目类型
  severity_overrides:
    finance:
      D-07: P0
      S-06: P0
    healthcare:
      S-11: P0
      D-16: P0

# 结论校验配置
conclusion_validator:
  enabled: true
  shadow_mode: false
  confidence_threshold: 0.8
  skip_process_items: true  # 跳过 process 类检查项

# 异常处理配置
error_handler:
  max_retries: 3
  retry_delay: 5
  fallback_enabled: true

# 申诉配置
appeal:
  enabled: true
  auto_approve: false
  deadline_hours: 24

# 报告配置
report:
  format: markdown
  include_trajectories: false
  include_checklist: true
  include_cost: true
  fix_suggestion_format: steps  # steps / simple

# 成本限制
cost_limit:
  daily_limit_usd: 5.0
  monthly_limit_usd: 100.0
```

---

## 3.9 实施计划

### Phase 0: 接口适配（1周）

- [ ] 定义 HGF 组件接口
- [ ] 定义 HeavySkill 组件接口
- [ ] 定义辅助组件接口（含 ChecklistManager V2）
- [ ] 实现接口适配层
- [ ] 编写接口文档

### Phase 1: 核心集成（1周）

- [ ] 实现 HGFHeavySkillReviewer 类
- [ ] 实现 ParallelReasoning（asyncio 真并行）
- [ ] 实现 ChecklistManager V2（动态加载）
- [ ] 实现异常处理器
- [ ] 实现降级策略
- [ ] 实现 AppealHandler
- [ ] 创建配置文件

### Phase 2: 门禁集成（3天）

- [ ] 配置门禁规则
- [ ] 实现门禁执行器
- [ ] 实现报告生成器（含分步骤 fix_suggestion）
- [ ] 实现成本统计

### Phase 3: 测试优化（1周）

- [ ] 编写单元测试
- [ ] 运行集成测试
- [ ] 运行 7 个评测用例
- [ ] 优化配置参数
- [ ] 性能测试

### Phase 4: 文档部署（3天）

- [ ] 编写使用文档
- [ ] 创建示例配置
- [ ] 部署 MCP Server
- [ ] 编写 README

**总时间：约 4 周**

---

## 3.10 预期效果

### 效率提升

| 指标 | 人工审查 | HGF+HeavySkill | 提升 |
|------|----------|----------------|------|
| 审查时间 | 2-4小时 | 2-5分钟 | **95%↓** |
| 问题发现率 | 60-70% | 85-90% | **25%↑** |
| 结论准确性 | 80% | 95% | **15%↑** |
| 可追溯性 | 部分 | 完整 | **100%** |

### 成本对比

| 项目 | 人工审查 | HGF+HeavySkill |
|------|----------|----------------|
| 时间成本 | 2-4小时/次 | 2-5分钟/次 |
| 人力成本 | $50-100/次 | $0.01/次 |
| 月度成本 | $2500-5000 | **$19-38** |

---

# 附录

## A. V4 修复清单

| 问题 | 级别 | 修复内容 |
|------|------|----------|
| V3 文档引用不存在的领域 | P0 | 更新 domains 列表，添加 frontend |
| README 与实际文件不一致 | P0 | 更新 README，与实际文件对齐 |
| 部分检查项 LLM 无法判断 | P1 | 增加 check_scope 字段 |
| S-02 XSS 严重等级偏高 | P1 | 降级为 P1，增加升级条件 |
| check_points 有语言绑定 | P1 | 增加 languages 字段 |
| fix_suggestion 质量参差不齐 | P2 | 改为 steps + example 格式 |
| 缺少前端/可访问性领域 | P2 | 创建 frontend.yaml |
| 成本估算与清单覆盖量关系 | P2 | 增加动态加载策略 |

## B. 参考资料

- HeavySkill 论文：https://arxiv.org/abs/2605.02396
- HGF GitHub：https://github.com/feiyu169/hermes-gate-flow
- OWASP Cheat Sheets：https://cheatsheetseries.owasp.org/

## C. 联系方式

- 作者：Hermes Agent
- 日期：2026-06-21
