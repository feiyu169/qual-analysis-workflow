# HeavySkill 优化技术文档

> **文档版本**: v1.0  
> **审查状态**: 待实施  
> **基于**: HeavySkill 7-Case 批量评估审查发现

---

## 目录

1. [模块架构优化](#1-模块架构优化)
2. [接口定义](#2-接口定义)
3. [错误处理策略](#3-错误处理策略)
4. [Feature Flag 设计](#4-feature-flag-设计)
5. [集成方案](#5-集成方案)

---

## 1. 模块架构优化

### 1.1 问题分析

**当前问题**:
- 数据验证与内核验证分离，集成点过多（4个独立验证点）
- 降级传播逻辑分散在各模块
- 缺少统一的门面封装

**优化目标**:
- 合并数据验证与内核验证为"内容审核器"（ContentAuditor）
- 降级传播收拢至异常处理框架
- 封装为单一门面（HeavySkillFacade）

### 1.2 优化后架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          HeavySkillFacade                                   │
│                     (单一集成点，对外接口)                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
         ┌──────────────────────────┼──────────────────────────┐
         │                          │                          │
         ▼                          ▼                          ▼
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│  ContentAuditor │      │  PipelineEngine │      │  ConfigManager  │
│  (内容审核器)    │      │  (管道引擎)      │      │  (配置管理)      │
└─────────────────┘      └─────────────────┘      └─────────────────┘
         │                          │                          │
         │                          │                          │
         ▼                          ▼                          ▼
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│  DataValidator  │      │  ParallelReasoner│     │  FeatureFlags   │
│  (数据校验)     │      │  (并行推理)      │      │  (特性开关)     │
└─────────────────┘      └─────────────────┘      └─────────────────┘
         │                          │                          │
         ▼                          ▼                          ▼
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│ KernelValidator │      │SequentialDeliber│     │  ErrorHandler   │
│  (内核校验)     │      │  (顺序审议)      │      │  (异常处理)     │
└─────────────────┘      └─────────────────┘      └─────────────────┘
```

### 1.3 模块合并方案

#### 合并 1：数据验证 + 内核验证 → ContentAuditor

**原模块**:
- `utils.filter_trajectories()` - 轨迹质量过滤
- `ConclusionValidator` - 结论校验引擎

**合并后**: `ContentAuditor`

```python
@dataclass
class ContentAuditor:
    """内容审核器 - 统一验证逻辑
    
    职责:
    1. 数据验证：轨迹质量、长度、重复性检查
    2. 内核验证：结论准确性、严重性阈值、规则引擎
    3. 降级传播：自动降级、回退策略
    """
    
    config: AuditConfig
    
    def audit_trajectory(self, trajectory: str) -> AuditResult:
        """审核单条轨迹"""
        # Step 1: 数据验证（原有 utils.filter_trajectories）
        data_result = self._validate_data(trajectory)
        if not data_result.is_valid:
            return data_result
        
        # Step 2: 内核验证（原有 ConclusionValidator）
        kernel_result = self._validate_kernel(trajectory)
        
        # Step 3: 综合评估
        return self._combine_results(data_result, kernel_result)
    
    def audit_conclusion(self, issues: List[Issue], llm_verdict: str) -> AuditResult:
        """审核最终结论"""
        return self._run_rule_engine(issues, llm_verdict)
```

#### 合并 2：降级传播收拢 → ErrorHandler

**原问题**: 降级逻辑分散在各模块（shadow_mode、fallback_to_llm）

**合并后**: 统一异常处理框架

```python
@dataclass
class ErrorHandler:
    """统一异常处理器
    
    职责:
    1. 异常分类：可恢复 vs 致命
    2. 降级策略：自动降级、回退
    3. 传播控制：阻断传播、记录日志
    """
    
    config: ErrorConfig
    
    def handle(self, error: Exception, context: dict) -> ErrorResponse:
        """处理异常，返回降级结果或传播异常"""
        error_type = self.classify(error)
        
        if error_type == ErrorType.RECOVERABLE:
            return self._handle_recoverable(error, context)
        elif error_type == ErrorType.FATAL:
            return self._handle_fatal(error, context)
        else:
            raise error  # 未知异常，向上传播
```

---

## 2. 接口定义

### 2.1 ContentAuditor 接口

```python
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Dict, Any


class Severity(str, Enum):
    """问题严重性级别"""
    P0 = "P0"  # 致命 - 一票否决
    P1 = "P1"  # 重大 - 累计阈值
    P2 = "P2"  # 一般 - 加权评分
    P3 = "P3"  # 建议 - 仅记录
    
    @classmethod
    def from_str(cls, s: str) -> 'Severity':
        """安全转换，支持模糊匹配，默认 P2"""
        mapping = {
            "CRITICAL": cls.P0, "P0": cls.P0, "致命": cls.P0, "严重": cls.P0,
            "MAJOR": cls.P1, "P1": cls.P1, "重大": cls.P1,
            "MINOR": cls.P2, "P2": cls.P2, "一般": cls.P2,
            "INFO": cls.P3, "P3": cls.P3, "建议": cls.P3,
        }
        return mapping.get(s.upper(), cls.P2)


class Verdict(str, Enum):
    """审核结论"""
    PASS = "PASS"           # 通过
    CONDITIONAL = "CONDITIONAL"  # 附条件通过
    REJECT = "REJECT"       # 不通过


@dataclass
class Issue:
    """问题描述"""
    severity: Severity
    description: str
    domain: str              # 领域：安全/架构/性能/...
    confidence: float        # 置信度 0.0-1.0
    evidence: str = ""       # 证据
    suggestion: str = ""     # 建议


@dataclass
class AuditResult:
    """审核结果"""
    verdict: Verdict
    issues: List[Issue]
    score: float             # 加权得分
    rules_applied: List[str] # 应用的规则
    human_review_required: bool = False
    fallback_used: bool = False
    shadow_log: Optional[Dict[str, Any]] = None  # 影子模式日志
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "verdict": self.verdict.value,
            "issues": [
                {
                    "severity": i.severity.value,
                    "description": i.description,
                    "domain": i.domain,
                    "confidence": i.confidence,
                    "evidence": i.evidence,
                    "suggestion": i.suggestion,
                }
                for i in self.issues
            ],
            "score": self.score,
            "rules_applied": self.rules_applied,
            "human_review_required": self.human_review_required,
            "fallback_used": self.fallback_used,
            "shadow_log": self.shadow_log,
        }


@dataclass
class AuditConfig:
    """审核配置"""
    enabled: bool = True
    shadow_mode: bool = False          # 影子模式：只记录不覆盖
    fallback_to_llm: bool = True       # 异常时回退到 LLM 结论
    confidence_threshold: float = 0.8  # 置信度阈值
    
    # P0 一票否决规则
    p0_veto_enabled: bool = True
    p0_min_count: int = 1
    p0_min_confidence: float = 0.8
    
    # P1 累计阈值规则
    p1_threshold_enabled: bool = True
    p1_threshold: int = 3
    
    # 加权评分规则
    weighted_score_enabled: bool = True
    weights: Dict[str, int] = None  # {P0: 10, P1: 5, P2: 2, P3: 1}
    reject_threshold: float = 15.0
    warn_threshold: float = 8.0
    
    # 领域覆盖率规则
    domain_coverage_enabled: bool = True
    required_domains: List[str] = None  # ["安全", "架构", "性能"]
    min_coverage: float = 0.6
    
    def __post_init__(self):
        if self.weights is None:
            self.weights = {"P0": 10, "P1": 5, "P2": 2, "P3": 1}
        if self.required_domains is None:
            self.required_domains = ["安全", "架构", "性能"]


class ContentAuditor:
    """内容审核器"""
    
    def __init__(self, config: AuditConfig):
        self.config = config
    
    def audit_trajectory(self, trajectory: str) -> AuditResult:
        """审核单条轨迹
        
        Args:
            trajectory: 轨迹文本
        
        Returns:
            AuditResult 审核结果
        
        Raises:
            AuditConfigError: 配置错误
        """
        pass
    
    def audit_conclusion(
        self, 
        issues: List[Issue], 
        llm_verdict: str
    ) -> AuditResult:
        """审核最终结论
        
        Args:
            issues: 发现的问题列表
            llm_verdict: LLM 给出的结论 ("PASS"/"CONDITIONAL"/"REJECT")
        
        Returns:
            AuditResult 审核结果（可能覆盖 LLM 结论）
        
        Raises:
            RuleEngineError: 规则引擎执行异常（如果 fallback_to_llm=False）
        """
        pass
    
    def _validate_data(self, trajectory: str) -> AuditResult:
        """数据验证：长度、重复性、格式"""
        pass
    
    def _validate_kernel(self, trajectory: str) -> AuditResult:
        """内核验证：结论准确性、规则引擎"""
        pass
    
    def _run_rule_engine(
        self, 
        issues: List[Issue], 
        llm_verdict: str
    ) -> AuditResult:
        """执行规则引擎"""
        pass
    
    def _combine_results(
        self, 
        data_result: AuditResult, 
        kernel_result: AuditResult
    ) -> AuditResult:
        """合并数据验证和内核验证结果"""
        pass
```

### 2.2 ErrorHandler 接口

```python
from enum import Enum
from typing import Optional, Dict, Any, Callable


class ErrorType(str, Enum):
    """异常分类"""
    RECOVERABLE = "recoverable"  # 可恢复：降级后继续
    FATAL = "fatal"              # 致命：必须中断


class RecoveryStrategy(str, Enum):
    """恢复策略"""
    FALLBACK = "fallback"           # 回退到默认值
    RETRY = "retry"                 # 重试
    SKIP = "skip"                   # 跳过当前步骤
    DEGRADE = "degrade"             # 降级处理
    ABORT = "abort"                 # 中断执行


@dataclass
class ErrorResponse:
    """异常处理响应"""
    handled: bool                  # 是否已处理
    strategy: RecoveryStrategy     # 使用的策略
    fallback_value: Any = None     # 回退值
    error_message: str = ""        # 错误信息
    should_propagate: bool = False # 是否需要继续传播
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "handled": self.handled,
            "strategy": self.strategy.value,
            "fallback_value": self.fallback_value,
            "error_message": self.error_message,
            "should_propagate": self.should_propagate,
        }


@dataclass
class ErrorConfig:
    """错误处理配置"""
    max_retries: int = 3
    retry_base_delay: float = 1.0
    enable_fallback: bool = True
    log_errors: bool = True
    
    # 异常类型映射
    error_type_map: Dict[str, ErrorType] = None
    
    def __post_init__(self):
        if self.error_type_map is None:
            self.error_type_map = {
                # 可恢复异常
                "TimeoutError": ErrorType.RECOVERABLE,
                "ConnectionError": ErrorType.RECOVERABLE,
                "RateLimitError": ErrorType.RECOVERABLE,
                "JSONDecodeError": ErrorType.RECOVERABLE,
                "ValidationError": ErrorType.RECOVERABLE,
                
                # 致命异常
                "AuthenticationError": ErrorType.FATAL,
                "ConfigurationError": ErrorType.FATAL,
                "OutOfMemoryError": ErrorType.FATAL,
            }


class HeavySkillError(Exception):
    """HeavySkill 基础异常"""
    def __init__(self, message: str, error_type: ErrorType = ErrorType.FATAL):
        super().__init__(message)
        self.error_type = error_type


class RecoverableError(HeavySkillError):
    """可恢复异常"""
    def __init__(self, message: str, fallback_value: Any = None):
        super().__init__(message, ErrorType.RECOVERABLE)
        self.fallback_value = fallback_value


class FatalError(HeavySkillError):
    """致命异常"""
    def __init__(self, message: str):
        super().__init__(message, ErrorType.FATAL)


class ErrorHandler:
    """统一异常处理器"""
    
    def __init__(self, config: ErrorConfig):
        self.config = config
        self._handlers: Dict[str, Callable] = {}
    
    def register_handler(
        self, 
        error_type: str, 
        handler: Callable[[Exception, dict], ErrorResponse]
    ) -> None:
        """注册异常处理器
        
        Args:
            error_type: 异常类型名称
            handler: 处理函数 (error, context) -> ErrorResponse
        """
        pass
    
    def handle(self, error: Exception, context: dict = None) -> ErrorResponse:
        """处理异常
        
        Args:
            error: 捕获的异常
            context: 上下文信息
        
        Returns:
            ErrorResponse 处理结果
        
        Raises:
            FatalError: 致命异常且无法降级
        """
        pass
    
    def classify(self, error: Exception) -> ErrorType:
        """分类异常
        
        Args:
            error: 异常对象
        
        Returns:
            ErrorType 异常类型
        """
        pass
    
    def wrap_async(
        self, 
        func: Callable, 
        fallback_value: Any = None
    ) -> Callable:
        """装饰器：自动包装异步函数的异常处理
        
        Args:
            func: 异步函数
            fallback_value: 异常时的回退值
        
        Returns:
            包装后的函数
        """
        pass
```

### 2.3 HeavySkillFacade 接口

```python
from dataclasses import dataclass
from typing import Optional, Dict, Any, List


@dataclass
class FacadeConfig:
    """门面配置"""
    # Pipeline 配置
    api_base: str = "https://api.deepseek.com"
    api_key: str = ""
    model: str = "deepseek-v4-pro"
    reason_k: int = 8
    summary_k: int = 4
    max_iterations: int = 1
    
    # 审核配置
    audit_enabled: bool = True
    audit_shadow_mode: bool = False
    
    # 错误处理配置
    error_fallback_enabled: bool = True
    max_retries: int = 3
    
    # Feature Flags
    feature_flags: Dict[str, bool] = None
    
    def __post_init__(self):
        if self.feature_flags is None:
            self.feature_flags = {}


@dataclass
class PipelineResult:
    """管道执行结果"""
    query: str
    final_answer: Optional[str]
    audit_result: Optional[AuditResult]
    trajectories: List[str]
    total_tokens: int
    total_latency: float
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "final_answer": self.final_answer,
            "audit_result": self.audit_result.to_dict() if self.audit_result else None,
            "trajectories_count": len(self.trajectories),
            "total_tokens": self.total_tokens,
            "total_latency": self.total_latency,
            "error": self.error,
        }


class HeavySkillFacade:
    """HeavySkill 门面 - 单一集成点
    
    提供简化的对外接口，隐藏内部复杂性。
    所有外部调用都通过此门面进行。
    """
    
    def __init__(self, config: FacadeConfig):
        self.config = config
        self._auditor = ContentAuditor(AuditConfig(
            enabled=config.audit_enabled,
            shadow_mode=config.audit_shadow_mode,
        ))
        self._error_handler = ErrorHandler(ErrorConfig(
            enable_fallback=config.error_fallback_enabled,
            max_retries=config.max_retries,
        ))
        self._feature_flags = FeatureFlagManager(config.feature_flags)
    
    async def execute(self, query: str) -> PipelineResult:
        """执行完整的 HeavySkill 流程
        
        Args:
            query: 用户查询
        
        Returns:
            PipelineResult 完整结果
        
        Raises:
            FatalError: 致命异常且无法恢复
        """
        pass
    
    async def execute_with_progress(
        self, 
        query: str, 
        progress_callback: Optional[Callable] = None
    ) -> PipelineResult:
        """带进度回调的执行
        
        Args:
            query: 用户查询
            progress_callback: 进度回调函数 (stage, progress, total)
        
        Returns:
            PipelineResult 完整结果
        """
        pass
    
    def get_health_status(self) -> Dict[str, Any]:
        """获取系统健康状态
        
        Returns:
            健康状态字典
        """
        pass
```

---

## 3. 错误处理策略

### 3.1 异常分类树

```
HeavySkillError (基类)
├── RecoverableError (可恢复)
│   ├── TimeoutError (超时)
│   │   └── 处理: 重试 (最多3次，指数退避)
│   ├── ConnectionError (连接错误)
│   │   └── 处理: 重试 (最多3次)
│   ├── RateLimitError (限流)
│   │   └── 处理: 重试 (退避后重试)
│   ├── JSONDecodeError (JSON解析错误)
│   │   └── 处理: 回退到文本解析
│   ├── ValidationError (验证错误)
│   │   └── 处理: 降级处理 (跳过验证)
│   └── TrajectoryError (轨迹错误)
│       └── 处理: 跳过当前轨迹
│
└── FatalError (致命)
    ├── AuthenticationError (认证错误)
    │   └── 处理: 中断，提示用户
    ├── ConfigurationError (配置错误)
    │   └── 处理: 中断，提示修复配置
    ├── OutOfMemoryError (内存溢出)
    │   └── 处理: 中断，清理资源
    └── RuleEngineError (规则引擎错误)
        └── 处理: 回退到 LLM 结论 (如果 enable_fallback)
```

### 3.2 错误处理策略表

| 异常类型 | 分类 | 处理方式 | 传播规则 |
|----------|------|----------|----------|
| `TimeoutError` | 可恢复 | 重试最多3次，指数退避 (1s, 2s, 4s) | 不传播，重试成功后继续 |
| `ConnectionError` | 可恢复 | 重试最多3次 | 不传播，重试失败后回退 |
| `RateLimitError` | 可恢复 | 等待后重试 (60s, 120s, 240s) | 不传播 |
| `JSONDecodeError` | 可恢复 | 回退到正则表达式解析 | 不传播，使用降级结果 |
| `ValidationError` | 可恢复 | 记录警告，跳过验证 | 不传播，继续执行 |
| `TrajectoryError` | 可恢复 | 跳过当前轨迹，继续其他 | 不传播 |
| `RuleEngineError` | 可恢复/致命 | 如果 `fallback_to_llm=True` 则回退；否则致命 | 视配置而定 |
| `AuthenticationError` | 致命 | 中断执行，返回错误 | 向上传播 |
| `ConfigurationError` | 致命 | 中断执行，提示修复 | 向上传播 |
| `OutOfMemoryError` | 致命 | 清理资源，中断 | 向上传播 |

### 3.3 降级策略实现

```python
class DegradationManager:
    """降级管理器"""
    
    # 降级链定义
    DEGRADATION_CHAIN = {
        "deliberation": [
            "full_deliberation",      # 完整审议
            "quick_deliberation",     # 快速审议（减少轨迹数）
            "consensus_only",         # 仅使用共识答案
            "first_valid",            # 使用第一个有效轨迹
        ],
        "validation": [
            "full_validation",        # 完整验证
            "basic_validation",       # 基础验证（仅长度检查）
            "skip_validation",        # 跳过验证
        ],
        "reasoning": [
            "parallel_reasoning",     # 并行推理
            "sequential_reasoning",   # 顺序推理（降级）
            "single_shot",            # 单次调用
        ],
    }
    
    def degrade(self, component: str, current_level: str) -> str:
        """获取下一级降级策略
        
        Args:
            component: 组件名称
            current_level: 当前级别
        
        Returns:
            下一级降级策略，如果已经是最后一级则返回 None
        """
        chain = self.DEGRADATION_CHAIN.get(component, [])
        if current_level not in chain:
            return None
        
        current_idx = chain.index(current_level)
        if current_idx + 1 < len(chain):
            return chain[current_idx + 1]
        return None
```

### 3.4 JSON 解析脆弱性修复

**问题**: LLM 输出的 JSON 可能格式不正确，直接 `json.loads()` 会崩溃

**修复方案**:

```python
import json
import re
from typing import Any, Optional


class RobustJSONParser:
    """健壮的 JSON 解析器
    
    处理 LLM 输出的常见 JSON 问题：
    1. 尾随逗号
    2. 单引号
    3. 注释
    4. 缺少引号的键
    5. 不完整的 JSON
    """
    
    @staticmethod
    def parse(text: str) -> Optional[Any]:
        """解析 JSON，支持多种降级策略
        
        Args:
            text: 待解析的文本
        
        Returns:
            解析结果，失败返回 None
        """
        if not text:
            return None
        
        # 策略1: 直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # 策略2: 清理后解析
        cleaned = RobustJSONParser._clean_json(text)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        
        # 策略3: 提取 JSON 块
        json_block = RobustJSONParser._extract_json_block(text)
        if json_block:
            try:
                return json.loads(json_block)
            except json.JSONDecodeError:
                pass
        
        # 策略4: 正则提取关键字段
        return RobustJSONParser._extract_fields_regex(text)
    
    @staticmethod
    def _clean_json(text: str) -> str:
        """清理 JSON 文本"""
        # 移除注释
        text = re.sub(r'//.*?\n', '\n', text)
        text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
        
        # 移除尾随逗号
        text = re.sub(r',\s*([}\]])', r'\1', text)
        
        # 单引号替换为双引号（小心处理转义）
        text = text.replace("'", '"')
        
        return text
    
    @staticmethod
    def _extract_json_block(text: str) -> Optional[str]:
        """从文本中提取 JSON 块"""
        # 尝试提取 {...} 或 [...]
        patterns = [
            r'\{[^{}]*\}',  # 简单对象
            r'\[[^\[\]]*\]',  # 简单数组
            r'\{.*?\}',  # 嵌套对象（非贪婪）
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                return match.group(0)
        
        return None
    
    @staticmethod
    def _extract_fields_regex(text: str) -> Optional[dict]:
        """使用正则表达式提取关键字段"""
        result = {}
        
        # 提取 verdict
        verdict_match = re.search(
            r'"?verdict"?\s*[:=]\s*"?(\w+)"?', 
            text, 
            re.IGNORECASE
        )
        if verdict_match:
            result['verdict'] = verdict_match.group(1)
        
        # 提取 answer
        answer_match = re.search(
            r'"?answer"?\s*[:=]\s*"([^"]+)"', 
            text
        )
        if answer_match:
            result['answer'] = answer_match.group(1)
        
        return result if result else None
```

---

## 4. Feature Flag 设计

### 4.1 Feature Flag 管理器

```python
import os
from typing import Dict, Any, Optional


class FeatureFlagManager:
    """Feature Flag 管理器
    
    支持:
    1. 环境变量覆盖
    2. 配置文件默认值
    3. 运行时动态切换
    4. 回滚策略
    """
    
    # 所有 Feature Flags 定义
    FLAGS = {
        # 内容审核
        "CONTENT_AUDITOR_ENABLED": {
            "env_var": "HS_CONTENT_AUDITOR_ENABLED",
            "default": True,
            "description": "启用内容审核器",
            "rollback": "禁用后跳过所有验证，直接使用 LLM 输出",
        },
        "CONTENT_AUDITOR_SHADOW_MODE": {
            "env_var": "HS_AUDITOR_SHADOW_MODE",
            "default": False,
            "description": "影子模式：只记录不覆盖",
            "rollback": "关闭影子模式后，审核结果将覆盖 LLM 结论",
        },
        
        # 结论校验规则
        "P0_VETO_ENABLED": {
            "env_var": "HS_P0_VETO_ENABLED",
            "default": True,
            "description": "P0 一票否决规则",
            "rollback": "禁用后 P0 问题不会自动 REJECT",
        },
        "P1_THRESHOLD_ENABLED": {
            "env_var": "HS_P1_THRESHOLD_ENABLED",
            "default": True,
            "description": "P1 累计阈值规则",
            "rollback": "禁用后 P1 问题不会触发 REJECT",
        },
        "WEIGHTED_SCORE_ENABLED": {
            "env_var": "HS_WEIGHTED_SCORE_ENABLED",
            "default": True,
            "description": "加权评分规则",
            "rollback": "禁用后不会基于加权评分 REJECT",
        },
        "DOMAIN_COVERAGE_ENABLED": {
            "env_var": "HS_DOMAIN_COVERAGE_ENABLED",
            "default": True,
            "description": "领域覆盖率规则",
            "rollback": "禁用后不会检查领域覆盖率",
        },
        
        # 错误处理
        "ERROR_FALLBACK_ENABLED": {
            "env_var": "HS_ERROR_FALLBACK_ENABLED",
            "default": True,
            "description": "异常时回退到 LLM 结论",
            "rollback": "禁用后异常将直接抛出",
        },
        
        # 降级策略
        "DEGRADATION_ENABLED": {
            "env_var": "HS_DEGRADATION_ENABLED",
            "default": True,
            "description": "启用自动降级",
            "rollback": "禁用后异常将直接中断执行",
        },
        
        # 人工审核队列
        "HUMAN_REVIEW_QUEUE": {
            "env_var": "HS_HUMAN_REVIEW_QUEUE",
            "default": True,
            "description": "P0 否决时标记人工审核",
            "rollback": "禁用后 P0 否决不会标记人工审核",
        },
        
        # JSON 解析
        "ROBUST_JSON_PARSER": {
            "env_var": "HS_ROBUST_JSON_PARSER",
            "default": True,
            "description": "使用健壮的 JSON 解析器",
            "rollback": "禁用后回退到标准 json.loads()",
        },
        
        # 并行推理
        "PARALLEL_REASONING_ENABLED": {
            "env_var": "HS_PARALLEL_REASONING",
            "default": True,
            "description": "启用并行推理（Stage 1）",
            "rollback": "禁用后降级为顺序推理",
        },
        
        # 迭代审议
        "ITERATIVE_DELIBERATION": {
            "env_var": "HS_ITERATIVE_DELIBERATION",
            "default": True,
            "description": "启用迭代审议",
            "rollback": "禁用后只执行一次审议",
        },
    }
    
    def __init__(self, overrides: Dict[str, bool] = None):
        """初始化
        
        Args:
            overrides: 运行时覆盖值
        """
        self._overrides = overrides or {}
        self._cache: Dict[str, bool] = {}
    
    def is_enabled(self, flag_name: str) -> bool:
        """检查 Feature Flag 是否启用
        
        优先级: 运行时覆盖 > 环境变量 > 默认值
        
        Args:
            flag_name: Flag 名称
        
        Returns:
            是否启用
        """
        if flag_name in self._cache:
            return self._cache[flag_name]
        
        flag_def = self.FLAGS.get(flag_name)
        if not flag_def:
            return False
        
        # 1. 运行时覆盖
        if flag_name in self._overrides:
            value = self._overrides[flag_name]
            self._cache[flag_name] = value
            return value
        
        # 2. 环境变量
        env_value = os.getenv(flag_def["env_var"])
        if env_value is not None:
            value = env_value.lower() in ("true", "1", "yes")
            self._cache[flag_name] = value
            return value
        
        # 3. 默认值
        self._cache[flag_name] = flag_def["default"]
        return flag_def["default"]
    
    def get_rollback_strategy(self, flag_name: str) -> str:
        """获取回滚策略
        
        Args:
            flag_name: Flag 名称
        
        Returns:
            回滚策略描述
        """
        flag_def = self.FLAGS.get(flag_name)
        if not flag_def:
            return "Unknown flag"
        return flag_def.get("rollback", "No rollback strategy defined")
    
    def get_all_flags(self) -> Dict[str, Any]:
        """获取所有 Flag 的当前状态"""
        return {
            name: {
                "enabled": self.is_enabled(name),
                "env_var": self.FLAGS[name]["env_var"],
                "default": self.FLAGS[name]["default"],
                "rollback": self.FLAGS[name]["rollback"],
            }
            for name in self.FLAGS
        }
```

### 4.2 Feature Flag 总表

| 模块 | 环境变量 | 默认值 | 回滚策略 |
|------|----------|--------|----------|
| 内容审核器 | `HS_CONTENT_AUDITOR_ENABLED` | `true` | 禁用后跳过所有验证，直接使用 LLM 输出 |
| 影子模式 | `HS_AUDITOR_SHADOW_MODE` | `false` | 关闭后审核结果将覆盖 LLM 结论 |
| P0 一票否决 | `HS_P0_VETO_ENABLED` | `true` | 禁用后 P0 问题不会自动 REJECT |
| P1 累计阈值 | `HS_P1_THRESHOLD_ENABLED` | `true` | 禁用后 P1 问题不会触发 REJECT |
| 加权评分 | `HS_WEIGHTED_SCORE_ENABLED` | `true` | 禁用后不会基于加权评分 REJECT |
| 领域覆盖率 | `HS_DOMAIN_COVERAGE_ENABLED` | `true` | 禁用后不会检查领域覆盖率 |
| 异常回退 | `HS_ERROR_FALLBACK_ENABLED` | `true` | 禁用后异常将直接抛出 |
| 自动降级 | `HS_DEGRADATION_ENABLED` | `true` | 禁用后异常将直接中断执行 |
| 人工审核队列 | `HS_HUMAN_REVIEW_QUEUE` | `true` | 禁用后 P0 否决不会标记人工审核 |
| 健壮 JSON 解析 | `HS_ROBUST_JSON_PARSER` | `true` | 禁用后回退到标准 json.loads() |
| 并行推理 | `HS_PARALLEL_REASONING` | `true` | 禁用后降级为顺序推理 |
| 迭代审议 | `HS_ITERATIVE_DELIBERATION` | `true` | 禁用后只执行一次审议 |

---

## 5. 集成方案

### 5.1 workflow.py 修改方案

**目标**:
- 单一集成点：所有外部调用通过 `HeavySkillFacade`
- 向后兼容：保留原有接口，内部委托给门面
- 可回滚：通过 Feature Flag 控制新旧逻辑切换

**修改文件**:
- `workflow/pipeline.py` - 主要修改
- `workflow/parallel_reasoning.py` - 适配审核器
- `workflow/sequential_deliberation.py` - 适配审核器
- `workflow/utils.py` - 迁移到 ContentAuditor

### 5.2 新文件结构

```
workflow/
├── __init__.py
├── pipeline.py              # 修改：委托给门面
├── parallel_reasoning.py    # 修改：集成审核器
├── sequential_deliberation.py  # 修改：集成审核器
├── memory_cache.py          # 保持不变
├── utils.py                 # 保持不变（向后兼容）
│
├── auditor/                 # 新增：内容审核器
│   ├── __init__.py
│   ├── content_auditor.py   # ContentAuditor 实现
│   ├── data_validator.py    # 数据验证逻辑
│   ├── kernel_validator.py  # 内核验证逻辑
│   └── robust_json.py       # 健壮 JSON 解析
│
├── error_handling/          # 新增：错误处理框架
│   ├── __init__.py
│   ├── error_handler.py     # ErrorHandler 实现
│   ├── degradation.py       # 降级管理器
│   └── exceptions.py        # 异常定义
│
├── feature_flags/           # 新增：Feature Flag 管理
│   ├── __init__.py
│   └── flag_manager.py      # FeatureFlagManager
│
└── facade/                  # 新增：门面
    ├── __init__.py
    └── heavyskill_facade.py # HeavySkillFacade
```

### 5.3 集成代码

#### 5.3.1 pipeline.py 修改（向后兼容）

```python
"""
HeavySkill Pipeline - 向后兼容版本

保留原有接口，内部委托给 HeavySkillFacade。
通过 Feature Flag 控制新旧逻辑切换。
"""

from __future__ import annotations

import logging
from typing import Optional

# Feature Flag 控制
USE_NEW_ARCHITECTURE = os.getenv("HS_USE_NEW_ARCHITECTURE", "false").lower() == "true"

logger = logging.getLogger(__name__)


# 向后兼容：保留原有数据类
@dataclass
class HeavySkillResult:
    """保留原有数据类，增加审核结果字段"""
    query: str
    final_answer: Optional[str]
    consensus_answer: Optional[str]
    # ... 原有字段 ...
    
    # 新增字段（向后兼容）
    audit_result: Optional[Dict[str, Any]] = None
    error_handling: Optional[Dict[str, Any]] = None


@dataclass
class HeavySkillPipeline:
    """HeavySkill 管道 - 向后兼容版本
    
    如果 USE_NEW_ARCHITECTURE=true，内部使用 HeavySkillFacade
    否则使用原有逻辑
    """
    
    config: HeavySkillConfig
    
    async def run(self, query: Optional[str] = None) -> HeavySkillResult:
        """执行管道（向后兼容）"""
        if USE_NEW_ARCHITECTURE:
            return await self._run_with_facade(query)
        else:
            return await self._run_legacy(query)
    
    async def _run_with_facade(self, query: str) -> HeavySkillResult:
        """使用新架构执行"""
        from .facade import HeavySkillFacade, FacadeConfig
        
        facade_config = FacadeConfig(
            api_base=self.config.api_base,
            api_key=self.config.api_key,
            model=self.config.model,
            reason_k=self.config.reason_k,
            summary_k=self.config.summary_k,
            max_iterations=self.config.max_iterations,
        )
        
        facade = HeavySkillFacade(facade_config)
        result = await facade.execute(query)
        
        # 转换为原有格式
        return HeavySkillResult(
            query=result.query,
            final_answer=result.final_answer,
            consensus_answer=result.final_answer,  # 兼容
            # ... 其他字段 ...
            audit_result=result.audit_result.to_dict() if result.audit_result else None,
        )
    
    async def _run_legacy(self, query: str) -> HeavySkillResult:
        """原有逻辑（保持不变）"""
        # ... 原有代码 ...
        pass
```

#### 5.3.2 ContentAuditor 集成

```python
# workflow/auditor/content_auditor.py

from dataclasses import dataclass
from typing import List, Optional

from ..feature_flags import FeatureFlagManager
from ..error_handling import ErrorHandler, RecoverableError


@dataclass
class ContentAuditor:
    """内容审核器实现"""
    
    config: AuditConfig
    flags: FeatureFlagManager
    error_handler: ErrorHandler
    
    def audit_trajectory(self, trajectory: str) -> AuditResult:
        """审核轨迹"""
        # 检查 Feature Flag
        if not self.flags.is_enabled("CONTENT_AUDITOR_ENABLED"):
            return AuditResult(
                verdict=Verdict.PASS,
                issues=[],
                score=0,
                rules_applied=["disabled"],
            )
        
        try:
            # 数据验证
            data_result = self._validate_data(trajectory)
            
            # 内核验证
            kernel_result = self._validate_kernel(trajectory)
            
            # 合并结果
            return self._combine_results(data_result, kernel_result)
            
        except Exception as e:
            # 错误处理
            response = self.error_handler.handle(e, {"trajectory": trajectory[:100]})
            
            if response.handled and response.fallback_value:
                return response.fallback_value
            
            # 如果配置了回退，返回通过
            if self.flags.is_enabled("ERROR_FALLBACK_ENABLED"):
                return AuditResult(
                    verdict=Verdict.PASS,
                    issues=[],
                    score=0,
                    rules_applied=["error_fallback"],
                    fallback_used=True,
                )
            
            raise
    
    def audit_conclusion(
        self, 
        issues: List[Issue], 
        llm_verdict: str
    ) -> AuditResult:
        """审核结论"""
        # 检查 Feature Flag
        if not self.flags.is_enabled("CONTENT_AUDITOR_ENABLED"):
            return AuditResult(
                verdict=Verdict(llm_verdict),
                issues=issues,
                score=0,
                rules_applied=["disabled"],
            )
        
        # 影子模式
        shadow_mode = self.flags.is_enabled("CONTENT_AUDITOR_SHADOW_MODE")
        
        try:
            result = self._run_rule_engine(issues, llm_verdict)
            
            if shadow_mode:
                # 影子模式：记录但不覆盖
                return AuditResult(
                    verdict=Verdict(llm_verdict),  # 使用 LLM 结论
                    issues=issues,
                    score=result.score,
                    rules_applied=result.rules_applied,
                    shadow_log=result.to_dict(),
                )
            
            return result
            
        except Exception as e:
            # 规则引擎异常处理
            if self.flags.is_enabled("ERROR_FALLBACK_ENABLED"):
                return AuditResult(
                    verdict=Verdict(llm_verdict),
                    issues=issues,
                    score=0,
                    rules_applied=["rule_engine_fallback"],
                    fallback_used=True,
                )
            raise
    
    def _run_rule_engine(
        self, 
        issues: List[Issue], 
        llm_verdict: str
    ) -> AuditResult:
        """执行规则引擎"""
        rules_applied = []
        
        # Rule 1: P0 一票否决
        if self.flags.is_enabled("P0_VETO_ENABLED"):
            p0_issues = [
                i for i in issues 
                if i.severity == Severity.P0 
                and i.confidence >= self.config.p0_min_confidence
            ]
            if len(p0_issues) >= self.config.p0_min_count:
                rules_applied.append("p0_veto")
                return AuditResult(
                    verdict=Verdict.REJECT,
                    issues=issues,
                    score=999,
                    rules_applied=rules_applied,
                    human_review_required=self.flags.is_enabled("HUMAN_REVIEW_QUEUE"),
                )
        
        # Rule 2: P1 累计阈值
        if self.flags.is_enabled("P1_THRESHOLD_ENABLED"):
            p1_count = len([i for i in issues if i.severity == Severity.P1])
            if p1_count >= self.config.p1_threshold:
                rules_applied.append("p1_threshold")
                return AuditResult(
                    verdict=Verdict.REJECT,
                    issues=issues,
                    score=p1_count * 5,
                    rules_applied=rules_applied,
                )
        
        # Rule 3: 加权评分
        if self.flags.is_enabled("WEIGHTED_SCORE_ENABLED"):
            score = sum(
                self.config.weights.get(i.severity.value, 1) 
                for i in issues
            )
            if score >= self.config.reject_threshold:
                rules_applied.append("weighted_score_reject")
                return AuditResult(
                    verdict=Verdict.REJECT,
                    issues=issues,
                    score=score,
                    rules_applied=rules_applied,
                )
            elif score >= self.config.warn_threshold:
                rules_applied.append("weighted_score_warn")
                return AuditResult(
                    verdict=Verdict.CONDITIONAL,
                    issues=issues,
                    score=score,
                    rules_applied=rules_applied,
                )
        
        # Rule 4: 领域覆盖率
        if self.flags.is_enabled("DOMAIN_COVERAGE_ENABLED"):
            covered_domains = set(i.domain for i in issues)
            required = set(self.config.required_domains)
            coverage = len(covered_domains & required) / len(required)
            
            if coverage < self.config.min_coverage:
                rules_applied.append("domain_coverage_fail")
                return AuditResult(
                    verdict=Verdict.REJECT,
                    issues=issues,
                    score=0,
                    rules_applied=rules_applied,
                )
        
        # 默认：使用 LLM 结论
        rules_applied.append("default_pass")
        return AuditResult(
            verdict=Verdict(llm_verdict),
            issues=issues,
            score=0,
            rules_applied=rules_applied,
        )
```

#### 5.3.3 ErrorHandler 集成

```python
# workflow/error_handling/error_handler.py

import asyncio
import logging
from typing import Any, Callable, Dict, Optional

from .exceptions import (
    HeavySkillError,
    RecoverableError,
    FatalError,
    ErrorType,
    ErrorResponse,
    RecoveryStrategy,
)

logger = logging.getLogger(__name__)


class ErrorHandler:
    """统一异常处理器"""
    
    def __init__(self, config: ErrorConfig):
        self.config = config
        self._handlers: Dict[str, Callable] = {}
        
        # 注册默认处理器
        self._register_default_handlers()
    
    def _register_default_handlers(self):
        """注册默认异常处理器"""
        
        # 超时处理
        self.register_handler(
            "TimeoutError",
            lambda e, ctx: ErrorResponse(
                handled=True,
                strategy=RecoveryStrategy.RETRY,
                error_message=str(e),
            )
        )
        
        # 连接错误处理
        self.register_handler(
            "ConnectionError",
            lambda e, ctx: ErrorResponse(
                handled=True,
                strategy=RecoveryStrategy.RETRY,
                error_message=str(e),
            )
        )
        
        # JSON 解析错误处理
        self.register_handler(
            "JSONDecodeError",
            lambda e, ctx: ErrorResponse(
                handled=True,
                strategy=RecoveryStrategy.FALLBACK,
                fallback_value=ctx.get("fallback_value"),
                error_message=str(e),
            )
        )
    
    def handle(self, error: Exception, context: dict = None) -> ErrorResponse:
        """处理异常"""
        context = context or {}
        error_type = type(error).__name__
        
        # 查找处理器
        handler = self._handlers.get(error_type)
        if handler:
            try:
                return handler(error, context)
            except Exception as handler_error:
                logger.error(f"Handler error: {handler_error}")
        
        # 分类处理
        error_class = self.classify(error)
        
        if error_class == ErrorType.RECOVERABLE:
            return self._handle_recoverable(error, context)
        elif error_class == ErrorType.FATAL:
            return self._handle_fatal(error, context)
        
        # 未知异常
        return ErrorResponse(
            handled=False,
            strategy=RecoveryStrategy.ABORT,
            error_message=str(error),
            should_propagate=True,
        )
    
    def classify(self, error: Exception) -> ErrorType:
        """分类异常"""
        # 检查自定义类型映射
        error_type = type(error).__name__
        if error_type in self.config.error_type_map:
            return self.config.error_type_map[error_type]
        
        # 检查异常继承关系
        if isinstance(error, RecoverableError):
            return ErrorType.RECOVERABLE
        elif isinstance(error, FatalError):
            return ErrorType.FATAL
        
        # 默认：可恢复
        return ErrorType.RECOVERABLE
    
    def _handle_recoverable(
        self, 
        error: Exception, 
        context: dict
    ) -> ErrorResponse:
        """处理可恢复异常"""
        if self.config.enable_fallback:
            return ErrorResponse(
                handled=True,
                strategy=RecoveryStrategy.FALLBACK,
                fallback_value=context.get("fallback_value"),
                error_message=str(error),
            )
        
        return ErrorResponse(
            handled=False,
            strategy=RecoveryStrategy.ABORT,
            error_message=str(error),
            should_propagate=True,
        )
    
    def _handle_fatal(
        self, 
        error: Exception, 
        context: dict
    ) -> ErrorResponse:
        """处理致命异常"""
        return ErrorResponse(
            handled=False,
            strategy=RecoveryStrategy.ABORT,
            error_message=str(error),
            should_propagate=True,
        )
    
    def register_handler(
        self, 
        error_type: str, 
        handler: Callable
    ) -> None:
        """注册异常处理器"""
        self._handlers[error_type] = handler
    
    def wrap_async(
        self, 
        func: Callable, 
        fallback_value: Any = None
    ) -> Callable:
        """装饰器：包装异步函数"""
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                response = self.handle(e, {"fallback_value": fallback_value})
                if response.handled:
                    return response.fallback_value
                raise
        
        return wrapper
```

### 5.4 回滚方案

#### 方案 1：环境变量回滚

```bash
# 完全回滚到旧架构
export HS_USE_NEW_ARCHITECTURE=false

# 部分回滚：禁用内容审核
export HS_CONTENT_AUDITOR_ENABLED=false

# 部分回滚：启用影子模式（只记录不覆盖）
export HS_AUDITOR_SHADOW_MODE=true

# 部分回滚：禁用 P0 一票否决
export HS_P0_VETO_ENABLED=false
```

#### 方案 2：代码回滚

```python
# 快速回滚：在 pipeline.py 顶部添加
USE_NEW_ARCHITECTURE = False  # 强制使用旧架构
```

#### 方案 3：配置文件回滚

```yaml
# config.yaml
feature_flags:
  USE_NEW_ARCHITECTURE: false
  CONTENT_AUDITOR_ENABLED: false
```

### 5.5 集成检查清单

- [ ] **Phase 1: 基础设施**
  - [ ] 创建 `workflow/auditor/` 目录
  - [ ] 创建 `workflow/error_handling/` 目录
  - [ ] 创建 `workflow/feature_flags/` 目录
  - [ ] 创建 `workflow/facade/` 目录

- [ ] **Phase 2: 核心模块**
  - [ ] 实现 `ContentAuditor`
  - [ ] 实现 `ErrorHandler`
  - [ ] 实现 `FeatureFlagManager`
  - [ ] 实现 `RobustJSONParser`

- [ ] **Phase 3: 集成**
  - [ ] 修改 `pipeline.py` 支持新旧切换
  - [ ] 修改 `parallel_reasoning.py` 集成审核器
  - [ ] 修改 `sequential_deliberation.py` 集成审核器

- [ ] **Phase 4: 测试**
  - [ ] 单元测试：每个模块独立测试
  - [ ] 集成测试：完整流程测试
  - [ ] 回滚测试：验证回滚方案
  - [ ] 性能测试：确保无性能退化

- [ ] **Phase 5: 部署**
  - [ ] 灰度发布：影子模式运行
  - [ ] 监控告警：关键指标监控
  - [ ] 文档更新：API 文档、运维文档

---

## 附录

### A. 参考文件

- `references/conclusion-validator-optimization.md` - 结论校验引擎设计
- `references/conclusion-validator-pattern.md` - 结论校验设计模式
- `references/heavyskill-evaluation-findings.md` - 评估发现
- `workflow/pipeline.py` - 当前管道实现
- `workflow/utils.py` - 当前工具函数
- `workflow/parallel_reasoning.py` - 当前并行推理
- `workflow/sequential_deliberation.py` - 当前顺序审议
- `workflow/memory_cache.py` - 当前缓存实现
- `configuration.py` - 配置系统

### B. 变更日志

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| v1.0 | 2026-07-01 | 初始版本，基于 HeavySkill 审查发现 |

---

**文档完成**: 2026-07-01  
**下一步**: 按照集成检查清单逐步实施
