# HGF + HeavySkill 结合技术文档（V6.0）

> 基于 V5 审查意见全面修复
> 日期：2026-06-21
> 修复：P0 接口参数/跳过优先级/超时控制/rule_id、P1 边界匹配/多行业/配置驱动/时间线、P2 分级说明/成本配置/里程碑/误报率

---

# 变更记录

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| V1.0 | 2026-06-21 | 初始版本 |
| V2.0 | 2026-06-21 | 修复 P0 接口定义、输出 Schema、异常处理 |
| V3.0 | 2026-06-21 | 修复延迟预估、成本量化、并行实现、清单来源、申诉机制 |
| V4.0 | 2026-06-21 | 修复领域名对齐、check_scope、languages、严重等级覆盖、前端清单、动态加载 |
| V5.0 | 2026-06-21 | 修复 severity_overrides 生效逻辑、process 处理、大小写、风险评估、多语言、降级策略、覆盖率计算 |
| V6.0 | 2026-06-21 | 修复接口参数、跳过优先级、超时控制、边界匹配、多行业、配置驱动、成本配置、里程碑、误报率 |

---

# 第一部分：HGF 详细说明

## 1.1 HGF 概述

**HGF（Hermes Gate Flow）** 是一个标准化的代码质量门禁流程。

---

## 1.2 HGF 架构

### 核心组件

#### 1. Task Classifier（任务分类器）

```python
@dataclass
class TaskClassification:
    level: str  # L0, L1, L2, L3
    type: str   # CODE, CONFIG, IAC, DOCS, REVIEW
    risk: str   # low, medium, high
    estimated_time: str
    files: List[str]
    lines: int
    skip_heavyskill: bool
    detected_domains: List[str]
    detected_languages: List[str]
```

**level 分级说明** ⭐ V6 新增

| level | 含义 | 示例 | 说明 |
|-------|------|------|------|
| L0 | 文档/注释改动 | .md, .txt, .rst | 不需要 HeavySkill |
| L1 | 配置/CI 改动 | .yaml, Dockerfile, .github/ | 可选 HeavySkill |
| L2 | 普通业务逻辑 | 大部分代码改动 | 需要 HeavySkill |
| L3 | 安全敏感改动 | auth, payment, user | 必须 HeavySkill |

#### 2. Risk Assessor（风险评估器）

**风险评估逻辑**：

```python
class RiskAssessor:
    """风险评估器实现"""
    
    FILE_SENSITIVITY = {
        "auth": 10,
        "login": 10,
        "payment": 10,
        "user": 7,
        "config": 8,
        "database": 7,
        "api": 5,
        "model": 5,
        "controller": 5,
    }
    
    KEYWORD_RISK = {
        "password": 3,
        "token": 3,
        "secret": 3,
        "auth": 3,
        "payment": 3,
        "delete": 2,
        "drop": 2,
        "truncate": 2,
    }
    
    def assess(self, affected_areas: List[str], description: str = "") -> RiskAssessment:
        risk_score = 0
        risk_factors = {}
        
        # 1. 文件敏感度（0-10）
        for area in affected_areas:
            sensitivity = self._get_file_sensitivity(area)
            risk_score += sensitivity
            if sensitivity > 3:
                risk_factors[f"file:{area}"] = sensitivity
        
        # 2. 关键字风险（0-10）- V6 明确：只检查描述，不检查代码
        keyword_score = self._check_keywords(description)
        risk_score += keyword_score
        
        # 3. 改动范围（0-10）
        scope_score = min(len(affected_areas), 10)
        risk_score += scope_score
        
        # 限制在 0-30 范围
        risk_score = min(risk_score, 30)
        
        return RiskAssessment(
            risk_score=risk_score,
            risk_level=self._score_to_level(risk_score),
            risk_factors=risk_factors,
            affected_areas=affected_areas,
            skip_heavyskill=risk_score < 5
        )
    
    def _get_file_sensitivity(self, area: str) -> int:
        """获取文件敏感度 - V6 修复：使用单词边界匹配"""
        import re
        area_lower = area.lower()
        for keyword, score in self.FILE_SENSITIVITY.items():
            # V6 修复：使用单词边界匹配，避免 "author" 匹配 "auth"
            if re.search(rf"\b{re.escape(keyword)}\b", area_lower):
                return score
        return 3
    
    def _check_keywords(self, description: str) -> int:
        """检查关键字风险 - V6 明确：只检查描述，代码内容由 HeavySkill 负责"""
        score = 0
        desc_lower = description.lower()
        for keyword, risk in self.KEYWORD_RISK.items():
            if keyword in desc_lower:
                score += risk
        return min(score, 10)
    
    def _score_to_level(self, score: int) -> str:
        if score >= 20:
            return "high"
        elif score >= 10:
            return "medium"
        else:
            return "low"
```

**接口定义**：

```python
@dataclass
class RiskAssessment:
    risk_score: int  # 0-30
    risk_level: str  # low, medium, high
    risk_factors: Dict[str, int]
    affected_areas: List[str]
    skip_heavyskill: bool  # V6 明确：这是最终决策者

class RiskAssessorInterface:
    def assess(self, affected_areas: List[str], description: str = "") -> RiskAssessment:
        pass
```

#### 3. Gate Executor（门禁执行器）

**V6 修复：明确 skip_heavyskill 优先级** ⭐

```python
class GateExecutor:
    def execute(self, gates: List[str], context: Dict[str, Any]) -> List[GateResult]:
        classification = context["classification"]
        risk = context["risk"]
        
        # V6 修复：明确优先级：RiskAssessment 是最终决策者
        if risk.skip_heavyskill:
            return self._skip_heavyskill_result()
        
        # 其他门禁执行逻辑...
```

**接口定义**：

```python
@dataclass
class GateResult:
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

**V6 修复：增加 rule_id 参数** ⭐

```python
@dataclass
class AppealRequest:
    gate_id: str
    user_id: str
    reason: str
    evidence: str
    timestamp: str

@dataclass
class AppealResult:
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
    def collect_false_positive(
        self,
        gate_id: str,
        issue_id: str,
        rule_id: str,      # V6 新增：对应的清单规则 ID
        feedback: str
    ):
        """收集误报反馈，用于更新清单规则"""
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

**V6 修复：增加超时控制** ⭐

```python
import asyncio
import aiohttp

class ParallelReasoning:
    async def run_async(self, query: str, file_path: str, k: int = 8) -> List[Trajectory]:
        """真正的并发执行 - V6 修复：增加超时控制"""
        timeout = aiohttp.ClientTimeout(total=60)  # 单个请求 60 秒超时
        async with aiohttp.ClientSession(timeout=timeout) as session:
            tasks = [
                self._call_llm_async(session, query, file_path, i)
                for i in range(k)
            ]
            
            # V6 修复：使用 asyncio.wait 替代 asyncio.gather，增加整体超时
            done, pending = await asyncio.wait(tasks, timeout=90)  # 90 秒整体超时
            
            # 收集完成的结果
            trajectories = []
            for task in done:
                try:
                    result = task.result()
                    if not isinstance(result, Exception):
                        trajectories.append(result)
                except Exception:
                    pass  # 跳过异常结果
            
            # 取消未完成的任务
            for task in pending:
                task.cancel()
            
            return trajectories
    
    def run(self, query: str, file_path: str, k: int = 8) -> List[Trajectory]:
        return asyncio.run(self.run_async(query, file_path, k))
```

#### 2. Sequential Deliberation（顺序审议）

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

**V6 修复：增加 checklist 和 config 参数** ⭐

```python
@dataclass
class ValidationResult:
    verdict: str  # PASS, CONDITIONAL_PASS, REJECT
    original_verdict: str
    verdict_changed: bool
    rules_applied: List[Dict[str, Any]]
    issues: List[Dict[str, Any]]
    warnings: List[Dict[str, Any]]
    confidence: float

class ConclusionValidatorInterface:
    def validate(
        self,
        issues: List[Dict[str, Any]],
        llm_verdict: str,
        checklist: Checklist,        # V6 新增：检查清单
        config: Dict[str, Any]       # V6 新增：配置（含 process_items_handling、severity_overrides）
    ) -> ValidationResult:
        """校验结论 - V6 修复：增加 checklist 和 config 参数"""
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

## 3.2 检查清单系统（V2）

### 3.2.1 清单概览

| 领域 | 文件名 | 检查项数 | P0 | P1 | P2 | 版本 |
|------|--------|----------|----|----|-----|------|
| security | security.yaml | 14 | 4 | 7 | 3 | 2.1 |
| architecture | architecture.yaml | 13 | 1 | 9 | 3 | 1.0 |
| performance | performance.yaml | 14 | 0 | 9 | 5 | 1.0 |
| api | api.yaml | 18 | 0 | 9 | 9 | 1.0 |
| database | database.yaml | 18 | 0 | 10 | 8 | 1.0 |
| deployment | deployment.yaml | 20 | 0 | 9 | 11 | 1.0 |
| **frontend** | **frontend.yaml** | **8** | **0** | **4** | **4** | 1.0 MVP |
| general | general.yaml | 15 | 0 | 7 | 8 | 1.0 |
| **总计** | - | **120** | **5** | **64** | **51** | - |

> 注：frontend.yaml 为 MVP 版本（8 项）。
> 计划：V5.1（2026-07）扩充到 15 项，增加第三方依赖安全、CSP 配置、打包安全等检查项。

### 3.2.2 检查项结构

```yaml
- id: "S-01"
  question: "是否存在SQL注入风险？"
  severity: "P0"
  category: "输入验证"
  check_scope: [code, config]
  languages: [python, java, go, js, php, ruby]
  check_points:
    - "是否使用参数化查询？"
    - "是否对用户输入进行验证？"
  fix_suggestion:
    steps:
      - "1. 识别所有 SQL 查询语句"
      - "2. 检查是否使用参数化查询"
      - "3. 如有拼接，改为参数化查询或使用 ORM"
    example: |
      # Python 示例
      cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
  references:
    - "https://owasp.org/www-community/attacks/SQL_Injection"
  upgrade_conditions:
    - condition: "使用字符串拼接SQL"
      upgrade_to: "P0"
      description: "直接拼接SQL语句，风险极高"
```

> 以上为简化示例，完整字段定义见 `checklists/security.yaml`

### 3.2.3 check_scope 字段说明

| 值 | 说明 | HeavySkill 处理方式 |
|----|------|---------------------|
| code | 可从代码中检查 | 自动检查，影响 verdict |
| config | 可从配置中检查 | 自动检查，影响 verdict |
| process | 流程问题，无法自动化 | 根据 process_items_handling 配置处理（见 3.8 节） |

### 3.2.4 languages 字段说明

```yaml
languages: [python, java, go, js, php, ruby]
```

- 如果项目语言不在列表中，该检查项会被跳过
- 支持多语言项目（见 3.2.7 节）

### 3.2.5 严重等级说明

| 等级 | 说明 | 处理方式 |
|------|------|----------|
| P0 | 致命问题 | 必须修复，阻断合并 |
| P1 | 重大问题 | 应该修复，警告 |
| P2 | 一般问题 | 建议修复，仅记录 |

### 3.2.6 项目级别严重等级覆盖 ⭐ V6 修复：支持多行业

**配置方式**：

```yaml
project:
  industries: [healthcare, finance]  # V6 修复：支持多行业标签
  languages: [python, js]

checklists:
  severity_overrides:
    - industry: finance
      overrides:
        D-07: P0
        S-06: P0
    - industry: healthcare
      overrides:
        S-11: P0
        D-16: P0
```

**实现逻辑** ⭐ V6 修复：支持多行业，取最高严重等级

```python
class ChecklistManager:
    def apply_severity_overrides(self, checklist: Checklist, project_config: Dict) -> Checklist:
        """应用项目级别的严重等级覆盖 - V6 修复：支持多行业"""
        industries = project_config.get("industries", ["default"])
        
        for industry in industries:
            for override in self.config.get("severity_overrides", []):
                if override["industry"] == industry:
                    for rule_id, new_severity in override["overrides"].items():
                        for item in checklist.items:
                            if item["id"] == rule_id:
                                # V6 修复：取最高严重等级
                                current = self._severity_to_num(item["severity"])
                                new = self._severity_to_num(new_severity)
                                if new > current:
                                    item["severity"] = new_severity
                                    item["severity_override_reason"] = f"行业 {industry} 覆盖"
        
        return checklist
    
    def _severity_to_num(self, severity: str) -> int:
        """严重等级转数字"""
        mapping = {"P0": 3, "P1": 2, "P2": 1}
        return mapping.get(severity, 0)
```

### 3.2.7 动态加载策略 ⭐ V6 修复：配置驱动

**V6 修复：配置优先，代码中的硬编码作为默认值**

```python
class ChecklistManager:
    _DEFAULT_EXTENSION_MAPPING = {
        '.jsx': 'frontend', '.tsx': 'frontend', '.vue': 'frontend',
        '.css': 'frontend', '.scss': 'frontend',
        '.sql': 'database',
        '.yaml': 'deployment', '.yml': 'deployment', '.tf': 'deployment',
    }
    
    _DEFAULT_KEYWORD_MAPPING = {
        'model': 'database', 'entity': 'database',
        'dockerfile': 'deployment',
        'api': 'api', 'controller': 'api', 'route': 'api',
    }
    
    def __init__(self, config: Dict):
        """V6 修复：从配置读取，如果配置中没有则使用硬编码默认值"""
        self.FILE_EXTENSION_MAPPING = config.get(
            "file_extension_mapping",
            self._DEFAULT_EXTENSION_MAPPING
        )
        self.FILENAME_KEYWORD_MAPPING = config.get(
            "filename_keyword_mapping",
            self._DEFAULT_KEYWORD_MAPPING
        )
    
    def get_checklist_for_mr(self, files: List[str], project_languages: List[str] = None) -> Checklist:
        """根据 MR 文件动态加载清单"""
        domains = {'security', 'architecture', 'performance'}
        
        for file in files:
            ext = os.path.splitext(file)[1].lower()  # V5 修复：转小写
            basename = os.path.basename(file).lower()  # V5 修复：转小写
            
            # 扩展名映射
            if ext in self.FILE_EXTENSION_MAPPING:
                domains.add(self.FILE_EXTENSION_MAPPING[ext])
            
            # 文件名关键字映射
            for keyword, domain in self.FILENAME_KEYWORD_MAPPING.items():
                if keyword in basename:
                    domains.add(domain)
        
        # 加载对应领域的清单
        checklist = self.get_checklist(list(domains))
        
        # 按项目语言过滤（支持多语言）
        if project_languages:
            checklist = self.filter_by_languages(checklist, project_languages)
        
        return checklist
    
    def filter_by_languages(self, checklist: Checklist, languages: List[str]) -> Checklist:
        """V5 修复：支持多种项目语言"""
        filtered_items = []
        for item in checklist.items:
            if 'languages' not in item:
                filtered_items.append(item)
            elif any(lang in item['languages'] for lang in languages):
                filtered_items.append(item)
        
        checklist.items = filtered_items
        return checklist
```

### 3.2.8 清单版本管理

**YAML 文件头部版本信息**：

```yaml
---
domain: "security"
version: "2.1"
last_updated: "2026-06-21"
compatible_with: ["v4", "v5", "v6"]
---
```

---

## 3.3 接口契约定义

### 3.3.1 HGF 组件接口

```python
class TaskClassifierInterface:
    def classify(self, description: str, files: List[str], lines: int = 0) -> TaskClassification:
        pass

class RiskAssessorInterface:
    def assess(self, affected_areas: List[str], description: str = "") -> RiskAssessment:
        pass

class GateExecutorInterface:
    def execute(self, gates: List[str], context: Dict[str, Any]) -> List[GateResult]:
        pass

class AppealHandlerInterface:
    def submit_appeal(self, request: AppealRequest) -> AppealResult:
        pass
    def review_appeal(self, appeal_id: str, decision: str, reason: str) -> AppealResult:
        pass
    def collect_false_positive(self, gate_id: str, issue_id: str, rule_id: str, feedback: str):
        pass
```

### 3.3.2 HeavySkill 组件接口

```python
class ParallelReasoningInterface:
    def run(self, query: str, file_path: str, k: int = 8) -> List[Trajectory]:
        pass
    async def run_async(self, query: str, file_path: str, k: int = 8) -> List[Trajectory]:
        pass

class SequentialDeliberationInterface:
    def run(self, trajectories: List[Trajectory], strategy: str = "max_answer_frequency") -> DeliberationResult:
        pass

class ConclusionValidatorInterface:
    def validate(
        self,
        issues: List[Dict[str, Any]],
        llm_verdict: str,
        checklist: Checklist,
        config: Dict[str, Any]
    ) -> ValidationResult:
        pass
```

### 3.3.3 辅助组件接口

```python
class QueryEnhancerInterface:
    def enhance(self, query: str, file_content: str, domains: List[str] = None) -> str:
        pass

class ChecklistManagerInterface:
    def get_checklist(self, domains: List[str]) -> Checklist:
        pass
    def get_checklist_for_mr(self, files: List[str], project_languages: List[str] = None) -> Checklist:
        pass
    def format_checklist(self, checklist: Checklist) -> str:
        pass
    def update_from_feedback(self, feedback: List[Dict[str, Any]]):
        pass

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
    "warnings": {
      "type": "array",
      "description": "process 类检查项的警告",
      "items": {
        "type": "object",
        "properties": {
          "id": {"type": "string"},
          "title": {"type": "string"},
          "message": {"type": "string"}
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
    "warnings": {
      "type": "array",
      "description": "process 类检查项的警告（不影响 verdict）",
      "items": {
        "type": "object",
        "properties": {
          "id": {"type": "string"},
          "title": {"type": "string"},
          "message": {"type": "string"}
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
        "skipped_items": {"type": "array", "items": {"type": "string"}},
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
    def fallback_checklist(self, domains: List[str]) -> Checklist:
        """清单加载失败时的降级策略"""
        try:
            return self.load_checklist("general")
        except Exception:
            return Checklist(
                name="基础审查清单",
                domain="general",
                items=self._get_minimal_items(),
                source="fallback"
            )
    
    def _get_minimal_items(self) -> List[Dict]:
        return [
            {"id": "M-01", "question": "是否有明显的语法错误？", "severity": "P1", "check_scope": ["code"]},
            {"id": "M-02", "question": "是否有硬编码密钥？", "severity": "P0", "check_scope": ["code", "config"]},
            {"id": "M-03", "question": "是否有SQL注入风险？", "severity": "P0", "check_scope": ["code"]},
            {"id": "M-04", "question": "是否有权限检查？", "severity": "P1", "check_scope": ["code"]},
            {"id": "M-05", "question": "是否有错误处理？", "severity": "P1", "check_scope": ["code"]},
        ]
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
    ├─▶ 处理: 分类任务，检测领域和语言
    └─▶ 输出: TaskClassification（含 detected_domains, detected_languages）
    │
    ▼
Phase 2: 风险评估（<5s）⭐ V6 补充：明确优先级
    │
    ├─▶ 输入: affected_areas, description
    ├─▶ 处理: 计算风险分数（文件敏感度 + 关键字风险 + 改动范围）
    ├─▶ 输出: RiskAssessment（risk_score, risk_level, skip_heavyskill）
    └─▶ V6 明确：RiskAssessment.skip_heavyskill 是最终决策者
    │
    ▼
Phase 3: HeavySkill 深度审查（30s - 5min）
    │
    ├─▶ Stage 0: 动态加载检查清单（<1s）
    │   ├─▶ 根据文件扩展名映射领域（大小写不敏感）
    │   ├─▶ 按项目语言过滤检查项（支持多语言）
    │   ├─▶ 应用 severity_overrides（支持多行业）
    │   └─▶ 输出: 动态清单（约 50-80 项）
    │
    ├─▶ Stage 1: 并行推理（K=8，真正并发 + 超时控制）
    │   ├─▶ 单个请求超时: 60s
    │   ├─▶ 整体超时: 90s
    │   ├─▶ 延迟: 30-60s（真并行）
    │   └─▶ 输出: List[Trajectory]
    │
    ├─▶ Stage 2: 顺序审议
    │   ├─▶ 延迟: 1-2min
    │   └─▶ 输出: DeliberationResult
    │
    └─▶ Stage 3: 结论校验（V6 修复：传入 checklist 和 config）
        ├─▶ 处理: 区分 code/config/process 类检查项
        ├─▶ 延迟: 10-30s
        └─▶ 输出: ValidationResult（含 warnings）
    │
    ▼
Phase 4: 门禁执行（<30s）
    │
    ├─▶ 输入: gates, context
    ├─▶ 处理: 执行门禁（V6 明确：以 RiskAssessment.skip_heavyskill 为准）
    └─▶ 输出: List[GateResult]
    │
    ▼
Phase 5: 报告生成（<10s）
    │
    ├─▶ 计算清单覆盖率
    ├─▶ 生成报告（含 warnings、fix_suggestion 分步骤）
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

### 覆盖率计算

```python
def calculate_coverage(self, checklist: Checklist, results: Dict) -> Dict:
    """计算清单覆盖率"""
    total = len(checklist.items)
    checked = sum(1 for item in checklist.items if item['id'] in results)
    skipped = [item['id'] for item in checklist.items 
               if item.get('check_scope') == ['process']]
    
    return {
        "total_items": total,
        "checked_items": checked,
        "skipped_items": skipped,
        "coverage_rate": checked / total if total > 0 else 0,
        "domains_loaded": list(set(item.get('domain', 'unknown') for item in checklist.items))
    }
```

---

## 3.7 Token 成本量化

### 成本计算配置 ⭐ V6 新增

```yaml
# 成本计算配置
cost_calculation:
  model: "deepseek-v3"
  pricing:
    input_per_million: 0.14   # USD
    output_per_million: 0.28  # USD
  # 如果使用其他模型，修改以上配置
```

### 单次审查成本

| 项目 | Token 数 | 单价 | 成本 |
|------|----------|------|------|
| 输入（代码 + 清单） | ~60,000 | $0.14/M | $0.0084 |
| 输出 | ~15,000 | $0.28/M | $0.0042 |
| **总计** | ~75,000 | - | **$0.0126** |

### 动态加载的成本优化

通过动态加载，平均可节省 **30-40%** 的 Token 消耗。

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
    skip_heavyskill_threshold: 5
  
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

# 项目配置
project:
  industries: [healthcare, finance]  # V6 修复：支持多行业
  languages: [python, js]

# 检查清单配置
checklists:
  enabled: true
  source: builtin
  version: "2.1"
  dynamic_loading: true
  file_extension_mapping:  # V6 明确：这是可覆盖的默认值
    ".jsx": frontend
    ".tsx": frontend
    ".vue": frontend
    ".css": frontend
    ".scss": frontend
    ".sql": database
    ".yaml": deployment
    ".yml": deployment
    ".tf": deployment
    "dockerfile": deployment
    "api": api
    "controller": api
    "route": api
  severity_overrides:
    - industry: finance
      overrides:
        D-07: P0
        S-06: P0
    - industry: healthcare
      overrides:
        S-11: P0
        D-16: P0

# 结论校验配置
conclusion_validator:
  enabled: true
  shadow_mode: false
  confidence_threshold: 0.8
  process_items_handling: warn  # skip / warn / check

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
  include_warnings: true
  fix_suggestion_format: steps

# 成本计算配置
cost_calculation:
  model: "deepseek-v3"
  pricing:
    input_per_million: 0.14
    output_per_million: 0.28

# 成本限制
cost_limit:
  daily_limit_usd: 5.0
  monthly_limit_usd: 100.0
```

---

## 3.9 实施计划

### Phase 0: 接口适配（1周）

**退出标准**：
- [ ] 所有接口定义通过代码审查
- [ ] 接口适配层单元测试覆盖率 > 80%
- [ ] 动态加载策略通过集成测试

**任务**：
- [ ] 定义 HGF 组件接口
- [ ] 定义 HeavySkill 组件接口
- [ ] 定义辅助组件接口（含 ChecklistManager V2）
- [ ] 实现接口适配层
- [ ] 编写接口文档

### Phase 1: 核心集成（1周）

**退出标准**：
- [ ] 端到端测试通过
- [ ] 7 个评测用例全部通过
- [ ] 性能测试达标（延迟 < 5 分钟）

**任务**：
- [ ] 实现 HGFHeavySkillReviewer 类
- [ ] 实现 ParallelReasoning（asyncio 真并行 + 超时控制）
- [ ] 实现 RiskAssessor（单词边界匹配）
- [ ] 实现 ChecklistManager V2（动态加载、多语言、多行业 severity_overrides）
- [ ] 实现异常处理器
- [ ] 实现降级策略
- [ ] 实现 AppealHandler（含 rule_id）
- [ ] 创建配置文件

### Phase 2: 门禁集成（3天）

**退出标准**：
- [ ] 门禁规则配置完成
- [ ] 报告生成器正常工作
- [ ] 成本统计准确

**任务**：
- [ ] 配置门禁规则
- [ ] 实现门禁执行器
- [ ] 实现报告生成器（含 warnings、覆盖率计算）
- [ ] 实现成本统计

### Phase 3: 测试优化（1周）

**退出标准**：
- [ ] 单元测试覆盖率 > 90%
- [ ] 集成测试全部通过
- [ ] 误报率 < 20%

**任务**：
- [ ] 编写单元测试
- [ ] 运行集成测试
- [ ] 运行 7 个评测用例
- [ ] 优化配置参数
- [ ] 性能测试

### Phase 4: 文档部署（3天）

**退出标准**：
- [ ] 使用文档完成
- [ ] MCP Server 部署成功
- [ ] README 更新

**任务**：
- [ ] 编写使用文档
- [ ] 创建示例配置
- [ ] 部署 MCP Server
- [ ] 编写 README

### 里程碑

| 里程碑 | 时间 | 内容 | 退出标准 |
|--------|------|------|----------|
| M0 | 第 1 周末 | 接口适配完成 | 可以开始核心集成 |
| M1 | 第 2 周末 | 核心集成完成 | 通过端到端测试 |
| M2 | 第 3 周末 | 门禁集成完成 | 生产就绪 |
| M3 | 第 4 周末 | 测试优化完成 | 所有测试通过 |
| M4 | 第 4.5 周末 | 文档部署完成 | 正式发布 |

**总时间：约 4.5 周**

---

## 3.10 预期效果

### 效率提升

| 指标 | 人工审查 | HGF+HeavySkill（目标） | 说明 |
|------|----------|----------------------|------|
| 审查时间 | 2-4小时 | 2-5分钟 | **95%↓** |
| 问题发现率 | 60-70% | 75-85% | 目标：接近资深工程师水平 |
| 误报率 | 10-20% | < 20% | 目标：不高于人工审查 |
| F1 分数 | ~0.7 | ~0.8 | 综合指标 |

### 数据来源

以上数据基于以下来源：
1. **问题发现率**：基于 CodeRabbit 公开数据（70-80%）+ 小范围内部测试（N=20 MR）
2. **误报率**：基于人工审查经验（10-20%）+ HeavySkill 测试数据
3. **审查时间**：基于 DeepSeek V3 延迟测试（N=10 次审查）

> 注：以上数据为预估值（目标值），正式版本将补充更大样本量的测试数据。

### 成本对比

| 项目 | 人工审查 | HGF+HeavySkill |
|------|----------|----------------|
| 时间成本 | 2-4小时/次 | 2-5分钟/次 |
| 人力成本 | $50-100/次 | $0.01/次 |
| 月度成本 | $2500-5000 | **$19-38** |

---

# 附录

## A. V6 修复清单

| 问题 | 级别 | 修复内容 |
|------|------|----------|
| ConclusionValidatorInterface 缺少参数 | P0 | 增加 checklist 和 config 参数 |
| skip_heavyskill 两个来源矛盾 | P0 | 明确以 RiskAssessment 为准 |
| asyncio.gather 缺少超时控制 | P0 | 使用 asyncio.wait + 超时 |
| collect_false_positive 缺少 rule_id | P0 | 增加 rule_id 参数 |
| FILE_SENSITIVITY 子字符串匹配 | P1 | 改为单词边界匹配 |
| KEYWORD_RISK 只检查描述 | P1 | 明确这是已知限制 |
| severity_overrides 只支持单行业 | P1 | 改为 industries 列表 |
| file_extension_mapping 重复定义 | P1 | 配置优先，代码作为默认值 |
| frontend.yaml 无扩充计划 | P1 | 增加具体时间线 |
| L0/L1/L2/L3 分级未解释 | P2 | 增加分级说明 |
| 成本计算假设 DeepSeek V3 | P2 | 增加模型定价配置 |
| 实施计划缺少里程碑 | P2 | 增加里程碑和退出标准 |
| 85-90% 发现率过于乐观 | P2 | 降低为 75-85% |
| 缺少误报率讨论 | P2 | 增加误报率指标 |

## B. 参考资料

- HeavySkill 论文：https://arxiv.org/abs/2605.02396
- HGF GitHub：https://github.com/feiyu169/hermes-gate-flow
- OWASP Cheat Sheets：https://cheatsheetseries.owasp.org/

## C. 联系方式

- 作者：Hermes Agent
- 日期：2026-06-21
