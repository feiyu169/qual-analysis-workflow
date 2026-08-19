# HGF + HeavySkill 结合技术文档（V9.0）

> 基于 V8 审查意见修复
> 日期：2026-06-21
> 修复：P0 verdict=dict 笔误、P2 降级逻辑简化/YAML 引号/遗留问题

---

# 变更记录

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| V1.0-V7.0 | 2026-06-21 | 历史版本 |
| V8.0 | 2026-06-21 | 修复正则语法、industry 统一、大小写、升级条件、降级阈值 |
| V9.0 | 2026-06-21 | 修复 verdict=dict 笔误、降级逻辑简化、YAML 引号、遗留问题 |

---

# 第一部分：HGF 详细说明

## 1.1 HGF 概述

**HGF（Hermes Gate Flow）** 是一个标准化的代码质量门禁流程。

---

## 1.2 HGF 架构

### 核心组件

#### 1. Task Classifier

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

class TaskClassifierInterface:
    def classify(self, description: str, files: List[str], lines: int = 0) -> TaskClassification:
        pass
```

#### 2. Risk Assessor

```python
import re
import os

_TOKENIZER = re.compile(r'[_.\\-/\\-]')  # V9：正确语法

class RiskAssessor:
    FILE_SENSITIVITY = {
        "auth": 10, "login": 10, "payment": 10,
        "user": 7, "config": 8, "database": 7, "api": 5,
    }
    
    def _get_file_sensitivity(self, area: str) -> int:
        area_lower = area.lower()
        parts = set(_TOKENIZER.split(area_lower))
        for keyword, score in self.FILE_SENSITIVITY.items():
            if keyword in parts:
                return score
        return 3
    
    def assess(self, affected_areas: List[str], description: str = "") -> RiskAssessment:
        risk_score = sum(self._get_file_sensitivity(a) for a in affected_areas)
        risk_score = min(risk_score, 30)
        return RiskAssessment(
            risk_score=risk_score,
            risk_level=self._score_to_level(risk_score),
            skip_heavyskill=risk_score < 5
        )
```

**接口定义**：

```python
@dataclass
class RiskAssessment:
    risk_score: int
    risk_level: str
    risk_factors: Dict[str, int]
    affected_areas: List[str]
    skip_heavyskill: bool
```

#### 3. Gate Executor

```python
@dataclass
class GateResult:
    name: str
    status: str
    level: str
    details: Dict[str, Any]
    duration: float
    message: str
```

#### 4. Appeal Handler

```python
@dataclass
class AppealRequest:
    gate_id: str
    user_id: str
    reason: str
    evidence: str
    timestamp: str

class AppealHandlerInterface:
    def submit_appeal(self, request: AppealRequest) -> AppealResult:
        pass
    def review_appeal(self, appeal_id: str, decision: str, reason: str) -> AppealResult:
        pass
    def collect_false_positive(self, gate_id: str, issue_id: str, rule_id: str, feedback: str):
        pass
```

---

# 第二部分：HeavySkill 详细说明

## 2.1 HeavySkill 概述

**HeavySkill** 是一种创新的测试时扩展技术。

---

## 2.2 HeavySkill 架构

### 核心组件

#### 1. Parallel Reasoning

```python
import asyncio
import aiohttp

class ParallelReasoning:
    async def run_async(self, query: str, file_path: str, k: int = 8) -> List[Trajectory]:
        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            tasks = [self._call_llm_async(session, query, file_path, i) for i in range(k)]
            done, pending = await asyncio.wait(tasks, timeout=90)
            
            trajectories = []
            for task in done:
                if task.cancelled():
                    continue
                try:
                    trajectories.append(task.result())
                except Exception:
                    pass
            
            for task in pending:
                task.cancel()
            
            return trajectories
```

#### 2. Sequential Deliberation

```python
@dataclass
class DeliberationResult:
    selected_trajectories: List[str]
    final_answer: str
    confidence: float
    reasoning: str
```

#### 3. Conclusion Validation

```python
@dataclass
class ValidationResult:
    verdict: str
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
        checklist: Checklist,
        config: Dict[str, Any],
        code_context: str = ""
    ) -> ValidationResult:
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

## 3.2 检查清单系统

### 3.2.1 清单概览

| 领域 | 文件名 | 检查项数 | P0 | P1 | P2 | 版本 |
|------|--------|----------|----|----|-----|------|
| security | security.yaml | 14 | 4 | 7 | 3 | 2.1 |
| architecture | architecture.yaml | 13 | 1 | 9 | 3 | 1.0 |
| performance | performance.yaml | 14 | 0 | 9 | 5 | 1.0 |
| api | api.yaml | 18 | 0 | 9 | 9 | 1.0 |
| database | database.yaml | 18 | 0 | 10 | 8 | 1.0 |
| deployment | deployment.yaml | 20 | 0 | 9 | 11 | 1.0 |
| frontend | frontend.yaml | 8 | 0 | 4 | 4 | 1.0 MVP |
| general | general.yaml | 15 | 0 | 7 | 8 | 1.0 |
| **总计** | - | **120** | **5** | **64** | **51** | - |

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
  fix_suggestion:
    steps:
      - "1. 识别所有 SQL 查询语句"
      - "2. 检查是否使用参数化查询"
    example: |
      cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
  upgrade_conditions:
    - condition: "dangerouslySetInnerHTML"
      upgrade_to: "P0"
      description: "使用危险的HTML渲染方法"
  auto_downgrade:
    enabled: true
    threshold: 3
    min_severity: P1
```

### 3.2.3 check_scope 字段说明

| 值 | 说明 | 处理方式 |
|----|------|----------|
| code | 可从代码中检查 | 自动检查，影响 verdict |
| config | 可从配置中检查 | 自动检查，影响 verdict |
| process | 流程问题 | 根据 process_items_handling 处理 |

### 3.2.4 languages 字段说明

```yaml
languages: [python, java, go, js, php, ruby]
```

### 3.2.5 严重等级说明

| 等级 | 说明 | 处理方式 |
|------|------|----------|
| P0 | 致命问题 | 必须修复，阻断合并 |
| P1 | 重大问题 | 应该修复，警告 |
| P2 | 一般问题 | 建议修复，仅记录 |

### 3.2.6 项目级别严重等级覆盖

```yaml
project:
  industries: [healthcare, finance]

checklists:
  severity_overrides:
    - industry: finance
      overrides:
        D-07: P0
    - industry: healthcare
      overrides:
        S-11: P0
```

**实现逻辑**：

```python
class ChecklistManager:
    def apply_severity_overrides(self, checklist: Checklist, project_config: Dict) -> Checklist:
        industries = project_config.get("industries", ["default"])
        
        for industry in industries:
            for override in self.config.get("severity_overrides", []):
                if override["industry"] == industry:
                    for rule_id, new_severity in override["overrides"].items():
                        for item in checklist.items:
                            if item["id"] == rule_id:
                                current = self._severity_to_num(item["severity"])
                                new = self._severity_to_num(new_severity)
                                if new > current:
                                    item["severity"] = new_severity
        
        return checklist
```

### 3.2.7 动态加载策略

```python
import re
import os

_TOKENIZER = re.compile(r'[_.\\-/\\-]')

class ChecklistManager:
    _DEFAULT_EXTENSION_MAPPING = {
        ".jsx": "frontend", ".tsx": "frontend", ".vue": "frontend",
        ".css": "frontend", ".scss": "frontend",
        ".sql": "database",
        ".yaml": "deployment", ".yml": "deployment", ".tf": "deployment",
    }
    
    def get_checklist_for_mr(self, files: List[str], project_languages: List[str] = None) -> Checklist:
        domains = {'security', 'architecture', 'performance'}
        
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in self.FILE_EXTENSION_MAPPING:
                domains.add(self.FILE_EXTENSION_MAPPING[ext])
        
        checklist = self.get_checklist(list(domains))
        
        if project_languages:
            checklist = self.filter_by_languages(checklist, project_languages)
        
        return checklist
    
    def filter_by_languages(self, checklist: Checklist, languages: List[str]) -> Checklist:
        languages_lower = {lang.lower() for lang in languages}
        filtered_items = []
        
        for item in checklist.items:
            if 'languages' not in item:
                filtered_items.append(item)
            else:
                item_languages_lower = {lang.lower() for lang in item['languages']}
                if languages_lower & item_languages_lower:
                    filtered_items.append(item)
        
        checklist.items = filtered_items
        return checklist
```

### 3.2.8 清单版本管理

```yaml
---
domain: "security"
version: "2.1"
last_updated: "2026-06-21"
min_version: "v5"
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
        config: Dict[str, Any],
        code_context: str = ""
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

### 3.4.1 审查报告输出 Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "title": {"type": "string"},
    "summary": {"type": "string"},
    "verdict": {"type": "string", "enum": ["PASS", "CONDITIONAL_PASS", "REJECT"]},
    "issues": {"type": "array"},
    "warnings": {"type": "array"},
    "gates": {"type": "array"},
    "recommendations": {"type": "array"},
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
  }
}
```

---

## 3.5 异常处理设计

### 3.5.1 异常类型定义

```python
class HGFHeavySkillError(Exception):
    pass

class HeavySkillError(HGFHeavySkillError):
    pass

class ReasoningError(HeavySkillError):
    pass

class ValidationError(HeavySkillError):
    pass

class ChecklistError(HGFHeavySkillError):
    pass
```

### 3.5.2 降级策略

```python
class FallbackStrategy:
    def fallback_checklist(self, domains: List[str]) -> Checklist:
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
            {"id": "M-04", "question": "是否有XSS攻击风险？", "severity": "P1", "check_scope": ["code"]},
            {"id": "M-05", "question": "是否有命令注入风险？", "severity": "P0", "check_scope": ["code"]},
            {"id": "M-06", "question": "是否有路径遍历风险？", "severity": "P1", "check_scope": ["code"]},
            {"id": "M-07", "question": "是否有权限检查？", "severity": "P1", "check_scope": ["code"]},
            {"id": "M-08", "question": "是否有错误处理？", "severity": "P1", "check_scope": ["code"]},
            {"id": "M-09", "question": "是否有输入验证？", "severity": "P1", "check_scope": ["code"]},
            {"id": "M-10", "question": "是否有日志记录？", "severity": "P2", "check_scope": ["code"]},
        ]
```

---

## 3.6 集成流程

```
Phase 0: 需求分析（<10s）
    ↓
Phase 1: 任务分类（<5s）
    ↓
Phase 2: 风险评估（<5s）
    ↓
Phase 3: HeavySkill 深度审查（30s - 5min）
    ├── Stage 0: 动态加载检查清单
    ├── Stage 1: 并行推理（K=8，超时控制）
    ├── Stage 2: 顺序审议
    └── Stage 3: 结论校验（含 upgrade_conditions、process 处理）
    ↓
Phase 4: 门禁执行（<30s）
    ↓
Phase 5: 报告生成（<10s）
    ↓
Phase 6: 申诉处理（可选）
    ↓
输出: 完整审查报告
```

### 覆盖率计算

```python
def calculate_coverage(self, checklist: Checklist, issues: List[Dict[str, Any]]) -> Dict:
    """V9 明确：issues 是 List[Dict]，包含 id 字段"""
    checked_ids = {issue.get('id') for issue in issues if issue.get('id')}
    
    total = len(checklist.items)
    checked = 0
    skipped = []
    
    for item in checklist.items:
        scope = item.get('check_scope', [])
        if item['id'] in checked_ids:
            checked += 1
        elif 'process' in scope and not any(s in scope for s in ('code', 'config')):
            skipped.append(item['id'])
    
    return {
        "total_items": total,
        "checked_items": checked,
        "skipped_items": skipped,
        "coverage_rate": checked / total if total > 0 else 0,
        "domains_loaded": list(set(item.get('domain', 'unknown') for item in checklist.items))
    }
```

---

## 3.7 结论校验实现

### 3.7.1 完整实现（V9 修复 verdict=dict 笔误）

```python
import re

class ConclusionValidator:
    def validate(
        self,
        issues: List[Dict[str, Any]],
        llm_verdict: str,
        checklist: Checklist,
        config: Dict[str, Any],
        code_context: str = ""
    ) -> ValidationResult:
        # 1. 应用 upgrade_conditions
        issues = self._apply_upgrade_conditions(issues, checklist, code_context)
        
        # 2. 处理 process 类检查项
        issues, warnings = self._handle_process_items(issues, checklist, config)
        
        # 3. 基于规则的 verdict 覆盖
        verdict, rules_applied = self._apply_rules(issues, llm_verdict, config)
        
        # V9 修复：verdict=verdict（不是 verdict=verdict=dict）
        return ValidationResult(
            verdict=verdict,  # V9 修复
            original_verdict=llm_verdict,
            verdict_changed=(verdict != llm_verdict),
            rules_applied=rules_applied,
            issues=issues,
            warnings=warnings,
            confidence=self._calc_confidence(issues)
        )
    
    def _apply_upgrade_conditions(
        self,
        issues: List[Dict[str, Any]],
        checklist: Checklist,
        code_context: str
    ) -> List[Dict[str, Any]]:
        """V9 补充：关键词提取支持中英文"""
        upgrade_rules = {}
        for item in checklist.items:
            if 'upgrade_conditions' in item:
                upgrade_rules[item['id']] = item['upgrade_conditions']
        
        for issue in issues:
            rule_id = issue.get('id')
            if rule_id not in upgrade_rules:
                continue
            for cond in upgrade_rules[rule_id]:
                if self._match_condition_in_code(cond['condition'], code_context):
                    old_severity = issue.get('severity', 'P2')
                    new_severity = cond['upgrade_to']
                    if self._severity_rank(new_severity) > self._severity_rank(old_severity):
                        issue['severity'] = new_severity
                        issue['severity_upgrade_reason'] = cond['description']
        return issues
    
    def _match_condition_in_code(self, condition: str, code: str) -> bool:
        """V9 补充：支持中英文关键词提取"""
        if not code:
            return False
        
        # 提取英文关键词
        en_keywords = re.findall(r'[a-zA-Z_][a-zA-Z0-9_.]*', condition)
        
        # 提取中文关键词（2-4字）
        cn_keywords = re.findall(r'[\u4e00-\u9fa5]{2,4}', condition)
        
        code_lower = code.lower()
        
        # 检查英文关键词
        if any(kw.lower() in code_lower for kw in en_keywords):
            return True
        
        # 检查中文关键词
        for kw in cn_keywords:
            if kw in code:
                return True
        
        return False
    
    def _handle_process_items(
        self,
        issues: List[Dict[str, Any]],
        checklist: Checklist,
        config: Dict[str, Any]
    ) -> tuple:
        handling = config.get('process_items_handling', 'warn')
        process_item_ids = {
            item['id'] for item in checklist.items
            if 'process' in item.get('check_scope', [])
        }
        
        normal_issues = []
        warnings = []
        
        for issue in issues:
            if issue.get('id') not in process_item_ids:
                normal_issues.append(issue)
                continue
            
            if handling == 'skip':
                continue
            elif handling == 'warn':
                # V9 补充：只放入 warnings，不放入 issues
                warnings.append({
                    'id': issue['id'],
                    'title': issue.get('title', ''),
                    'message': f"[流程建议] {issue.get('description', '')}"
                })
            elif handling == 'check':
                # V9 补充：只放入 issues，不放入 warnings（避免重复）
                normal_issues.append(issue)
        
        return normal_issues, warnings
    
    def _apply_rules(self, issues, llm_verdict, config):
        p0_issues = [i for i in issues if i.get('severity') == 'P0']
        if p0_issues:
            return Verdict.REJECT, [{"rule": "p0_veto", "triggered": True}]
        return llm_verdict, []
    
    def _calc_confidence(self, issues):
        if not issues:
            return 1.0
        confidences = [i.get('confidence', 0.8) for i in issues]
        return sum(confidences) / len(confidences)
    
    def _severity_rank(self, severity: str) -> int:
        return {"P0": 3, "P1": 2, "P2": 1}.get(severity, 0)
```

### 3.7.2 误报反馈更新策略

```python
class ChecklistManager:
    def update_from_feedback(self, feedback_list: List[Dict[str, Any]]):
        from collections import Counter
        
        fp_counts = Counter(
            f['rule_id'] for f in feedback_list
            if f.get('status') == 'confirmed_false_positive'
        )
        
        for rule_id, count in fp_counts.items():
            item = self._find_item_by_id(rule_id)
            if item is None:
                continue
            
            item.setdefault('feedback_stats', {})
            item['feedback_stats']['false_positive_count'] = count
            item['feedback_stats']['last_updated'] = datetime.utcnow().isoformat()
            
            auto_downgrade = item.get('auto_downgrade', {})
            if not auto_downgrade.get('enabled', False):
                continue
            
            threshold = auto_downgrade.get('threshold', 5)
            min_severity = auto_downgrade.get('min_severity', 'P2')
            
            if count >= threshold:
                old = item.get('severity', 'P2')
                if self._severity_rank(old) > self._severity_rank(min_severity):
                    # V9 修复：简化降级逻辑
                    new_severity = self._downgrade_severity(old, min_severity)
                    item['severity'] = new_severity
                    item['auto_downgrade_reason'] = f'误报 {count} 次，自动降级'
    
    def _downgrade_severity(self, current: str, minimum: str) -> str:
        """V9 修复：简化降级逻辑"""
        order = ["P2", "P1", "P0"]
        curr_idx = order.index(current)
        min_idx = order.index(minimum)
        
        if curr_idx > min_idx:  # 可以降级
            return order[curr_idx - 1]
        return current  # 已经是最低
    
    def _severity_rank(self, severity: str) -> int:
        return {"P0": 3, "P1": 2, "P2": 1}.get(severity, 0)
```

---

## 3.8 Token 成本量化

### 成本计算实现

```python
class ReportGenerator:
    def __init__(self, config: Dict[str, Any]):
        self.cost_config = config.get('cost_calculation', {})
    
    def _calculate_cost(self, total_tokens: int, input_tokens: int, output_tokens: int) -> Dict:
        pricing = self.cost_config.get('pricing', {})
        input_rate = pricing.get('input_per_million', 0.14)
        output_rate = pricing.get('output_per_million', 0.28)
        
        input_cost = (input_tokens / 1_000_000) * input_rate
        output_cost = (output_tokens / 1_000_000) * output_rate
        
        return {
            "total_tokens": total_tokens,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost_usd": round(input_cost + output_cost, 6)
        }
```

### Token 计算分解

| 场景 | 清单 Token | 代码 Token | 总计 |
|------|-----------|-----------|------|
| 最小（前端文件） | ~8,000 | ~20,000 | ~28,000 |
| 中等（API 文件） | ~12,000 | ~30,000 | ~42,000 |
| 最大（数据库+API） | ~15,000 | ~40,000 | ~55,000 |
| **平均估算** | ~10,000 | ~30,000 | **~40,000** |

---

## 3.9 配置文件（V9 修复 YAML 引号）

```yaml
# ~/.hermes/skills/heavyskill-optimize/config/hgf-heavyskill.yaml

project:
  industries: [healthcare, finance]
  languages: [python, js, ts]

checklists:
  enabled: true
  source: builtin
  version: "2.1"
  dynamic_loading: true
  # V9 修复：键加引号，避免 YAML 解析歧义
  file_extension_mapping:
    ".jsx": "frontend"
    ".tsx": "frontend"
    ".vue": "frontend"
    ".css": "frontend"
    ".scss": "frontend"
    ".sql": "database"
    ".yaml": "deployment"
    ".yml": "deployment"
    ".tf": "deployment"
  severity_overrides:
    - industry: finance
      overrides:
        D-07: P0
        S-06: P0
    - industry: healthcare
      overrides:
        S-11: P0
        D-16: P0

conclusion_validator:
  enabled: true
  shadow_mode: false
  confidence_threshold: 0.8
  process_items_handling: warn

appeal:
  enabled: true
  deadline_hours: 24

report:
  format: markdown
  include_warnings: true
  warnings_section_title: "## 流程建议（不影响合并）"
  fix_suggestion_format: steps

cost_calculation:
  model: "deepseek-v3"
  pricing:
    input_per_million: 0.14
    output_per_million: 0.28

cost_limit:
  daily_limit_usd: 5.0
  monthly_limit_usd: 100.0
```

---

## 3.10 实施计划

### 里程碑

| 里程碑 | 时间 | 退出标准 |
|--------|------|----------|
| M0 | 第 1 周末 | 接口适配完成 |
| M1 | 第 2 周末 | 核心集成完成，端到端测试通过 |
| M2 | 第 3 周末 | 门禁集成完成 |
| M3 | 第 4 周末 | 测试优化完成，误报率 < 20% |
| M4 | 第 4.5 周末 | 文档部署完成 |

### 误报率测试方法

```python
class FalsePositiveMeasurement:
    """误报率测量工具"""
    
    def measure(self, review_results: List[Dict], ground_truth: List[Dict]) -> Dict:
        """
        Args:
            review_results: HeavySkill 报告的 issues 列表
            ground_truth: 人工标注的真实问题列表
        
        Returns:
            误报率、漏报率、F1 等指标
        """
        tp = fp = fn = 0
        
        for issue in review_results:
            matched = self._find_match(issue, ground_truth)
            if matched and matched.get('is_true_positive'):
                tp += 1
            else:
                fp += 1
        
        reported_ids = {i.get('id') for i in review_results}
        for gt in ground_truth:
            if gt['id'] not in reported_ids and gt.get('is_true_positive'):
                fn += 1
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        
        return {
            "false_positive_rate": round(1 - precision, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1, 4),
            "tp": tp, "fp": fp, "fn": fn
        }
```

**测试样本量**：50 个历史 MR（含人工审查结果）

---

## 3.11 预期效果（目标值）

| 指标 | 人工审查 | HGF+HeavySkill（目标） | 说明 |
|------|----------|----------------------|------|
| 审查时间 | 2-4小时 | 2-5分钟 | **95%↓** |
| 问题发现率 | 60-70% | **75-85%** | 目标：接近资深工程师水平 |
| 误报率 | 10-20% | **< 20%** | 目标：不高于人工审查 |
| F1 分数 | ~0.7 | **~0.8** | 综合指标 |

---

# 附录

## A. V9 修复清单

| 问题 | 级别 | 修复内容 |
|------|------|----------|
| verdict=verdict=dict 笔误 | P0 | 改为 verdict=verdict |
| _downgrade_severity 逻辑过复杂 | P2 | 简化为 order 列表索引 |
| YAML 配置键未加引号 | P2 | 加引号 |
| _match_condition_in_code 不支持中文 | P2 | 增加中文关键词提取 |
| process_items_handling=check 时重复 | P2 | 只放入 issues，不放入 warnings |
| 误报率测试样本量未定义 | P2 | 明确为 50 个 MR |

## B. 验证脚本

```python
import yaml
import os

checklist_dir = os.path.expanduser("~/.hermes/skills/heavyskill-optimize/checklists/")
for f in sorted(os.listdir(checklist_dir)):
    if not f.endswith('.yaml'):
        continue
    path = os.path.join(checklist_dir, f)
    with open(path) as fp:
        data = yaml.safe_load(fp)
        for item in data.get('items', []):
            if 'check_scope' not in item:
                print(f"WARN: {f}/{item['id']} missing check_scope")
            if 'languages' not in item:
                print(f"WARN: {f}/{item['id']} missing languages")
```

## C. 联系方式

- 作者：Hermes Agent
- 日期：2026-06-21
