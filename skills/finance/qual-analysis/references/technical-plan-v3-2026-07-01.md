# qual框架报告质量提升 — 最终技术方案 v3.0

> 基于HeavySkill审查v2.0优化 + GitHub推理引擎项目借鉴
> 生成时间: 2026-07-01

---

## 一、GitHub推理引擎项目借鉴

### 1.1 推荐项目

| 项目 | Stars | 描述 | 可借鉴点 |
|------|-------|------|----------|
| [Tencent/WeKnora](https://github.com/Tencent/WeKnora) | 17,591 | 开源LLM知识平台 | RAG+推理Agent融合架构；知识图谱构建与推理链路 |
| [OpenSPG/KAG](https://github.com/OpenSPG/KAG) | 8,858 | 逻辑形式引导推理框架 | 逻辑形式引导推理；builder/solver/indexer三层架构 |
| [PySpur-Dev/pyspur](https://github.com/PySpur-Dev/pyspur) | 5,742 | Agentic工作流可视化平台 | 可视化Agent工作流编排；Docker化部署模式 |
| [griptape-ai/griptape](https://github.com/griptape-ai/griptape) | 2,548 | 模块化Python框架 | engines/structures/tasks/tools/drivers五层分离；CoT推理引擎作为独立组件 |
| [antonbabenko/deliberation](https://github.com/antonbabenko/deliberation) | 113 | 多模型审议MCP服务器 | 纯状态机共识循环；blind verdict→peer review→adjudication→revision四阶段 |
| [geekjourneyx/agora](https://github.com/geekjourneyx/agora) | 162 | 多Agent审议系统 | 8步审议协议；自适应深度门控；黑格尔辩证法融合模式 |
| [semantica-agi/semantica](https://github.com/semantica-agi/semantica) | 1,345 | 知识图谱+推理引擎 | 可解释推理；溯源(provenance)机制 |

### 1.2 关键借鉴设计

1. **deliberation的纯状态机共识循环**：不可变状态转换，易测试可回放
2. **agora的8步审议协议**：自适应深度门控 + 黑格尔辩证法综合
3. **griptape的模块化分离**：engines/structures/tasks/tools/drivers五层架构
4. **KAG的逻辑形式引导推理**：reasoner + solver分离，知识图谱增强
5. **semantica的溯源机制**：每个决策可追踪、可解释

---

## 二、深度评分器设计

### 2.1 评分维度与权重

| 维度 | 权重 | 子维度 | 子权重 |
|------|------|--------|--------|
| 数据完整性 | 20% | 数据点数量、数据来源、数据时效 | 40%/30%/30% |
| 逻辑一致性 | 25% | 因果链条、数据-结论一致性、估值-目标价一致性 | 40%/30%/30% |
| 分析深度 | 25% | 维度覆盖、横向对比、纵向趋势、正反论证 | 30%/25%/25%/20% |
| 结论可靠性 | 20% | 投资建议明确性、催化剂/风险矩阵、交易策略 | 40%/30%/30% |
| 可操作性 | 10% | 目标价、仓位建议、止损位 | 40%/30%/30% |

### 2.2 评分公式

```
总分 = Σ(维度分 × 维度权重) + 交互修正项

维度分 = Σ(子维度分 × 子权重)
子维度分 = 命中数 / 要求总数 × 100

交互修正项 = -5 × (维度间不一致数)
```

### 2.3 评分等级映射

| 等级 | 分数范围 | 含义 |
|------|----------|------|
| S | 90-100 | 机构级深度 |
| A | 80-89 | 专业深度 |
| B | 70-79 | 标准深度 |
| C | 60-69 | 基础深度 |
| D | 50-59 | 不合格 |
| F | <50 | 严重不合格 |

### 2.4 校准方法

**初始化**：Bootstrap方法（Bradley-Terry模型）
- 收集50份人工评分报告
- 使用Bradley-Terry模型计算初始权重
- 验证Pearson ρ≥0.85

**持续校准**：月度贝叶斯优化
- 收集新的人工评分样本
- 使用贝叶斯优化调整权重
- 验证Spearman ρ_s≥0.80

---

## 三、推理引擎思维链设计

### 3.1 因果推理链（4步）

```
输入: 分析主题 + 初步结论 + 数据
     ↓
Step 1: 因果图构建
  - 提取所有因果关系
  - 构建有向无环图(DAG)
  - 检查点: 因果关系≥2条
     ↓
Step 2: 路径识别
  - 识别关键因果路径
  - 计算路径权重
  - 检查点: 关键路径≥1条
     ↓
Step 3: 效应量化
  - 量化每个因果环节的效应
  - 计算累计效应
  - 检查点: 量化误差<10%
     ↓
Step 4: 链路验证
  - 验证因果链的完整性
  - 检查是否有遗漏环节
  - 检查点: 验证通过率≥80%
     ↓
输出: 因果链 + 置信度 + 关键不确定性
```

### 3.2 情景推演链（5步）

```
输入: 基准情景 + 关键变量
     ↓
Step 1: 基准构建
  - 确定基准假设
  - 建立基准模型
  - 检查点: 假设≥3个
     ↓
Step 2: 变量识别
  - 敏感性分析识别Top 3变量
  - 计算弹性系数
  - 检查点: 变量≥3个
     ↓
Step 3: 情景矩阵
  - 构建Bull/Base/Bear三情景
  - 确定触发条件
  - 检查点: 情景≥3个
     ↓
Step 4: 路径推演
  - 推演每个情景的演化路径
  - 量化关键节点
  - 检查点: 路径完整性≥90%
     ↓
Step 5: 概率赋值
  - 为每个情景赋概率
  - 计算期望值
  - 检查点: 概率总和=1
     ↓
输出: 概率加权估值 + 估值区间 + 关键拐点
```

### 3.3 反面论证链（4步）

```
输入: 当前结论 + 确信度
     ↓
Step 1: 最强反驳
  - 生成最强反面观点
  - 收集支撑论据
  - 检查点: 反驳≥2个
     ↓
Step 2: 证据评估
  - 评估反面论据的可信度
  - 与现有数据对比
  - 检查点: 评估完成
     ↓
Step 3: 偏差检测
  - 检查是否存在确认偏差
  - 评估反驳的合理性
  - 检查点: 偏差检测完成
     ↓
Step 4: 结论修正
  - 根据反驳修正结论
  - 调整确信度
  - 检查点: 修正合理
     ↓
输出: 最强反面观点 + 反驳逻辑 + 修正确信度
```

---

## 四、降级质量标记设计

### 4.1 三维降级体系

| 维度 | 级别 | 含义 | 置信度上限 |
|------|------|------|-----------|
| 数据(D) | D-L0 | 数据完整 | 100% |
| 数据(D) | D-L1 | 部分数据缺失 | 85% |
| 数据(D) | D-L2 | 关键数据缺失 | 70% |
| 数据(D) | D-L3 | 仅基础数据 | 50% |
| 数据(D) | D-L4 | 数据不可用 | 阻断 |
| 推理(R) | R-L0 | 推理完整 | 100% |
| 推理(R) | R-L1 | 推理链部分缺失 | 85% |
| 推理(R) | R-L2 | 推理链关键缺失 | 70% |
| 推理(R) | R-L3 | 仅基础推理 | 50% |
| 推理(R) | R-L4 | 推理失败 | 阻断 |
| 深度(P) | P-L0 | 深度达标 | 100% |
| 深度(P) | P-L1 | 深度部分达标 | 85% |
| 深度(P) | P-L2 | 深度不足 | 70% |
| 深度(P) | P-L3 | 深度严重不足 | 阻断 |

### 4.2 综合降级等级

```
综合等级 = max(D级别, R级别, P级别)
```

### 4.3 用户可见警告

| 级别 | 警告方式 | 示例 |
|------|----------|------|
| G-L0 | 无警告 | - |
| G-L1 | 头部横幅 | "⚠️ 本报告部分数据来自降级源" |
| G-L2 | 段落内联 | "⚠️ 该分析基于有限数据，建议人工复核" |
| G-L3 | 交互式提示 | "⚠️ 报告质量严重降级，建议暂停发布" |
| G-L4 | 阻断 | "❌ 数据不可用，无法生成报告" |

---

## 五、推理引擎架构设计

### 5.1 推荐架构：分层推理引擎 + 多Agent审议混合模式

```
┌─────────────────────────────────────────────────┐
│                  ContentAuditor                   │  ← 审计层
├─────────────────────────────────────────────────┤
│              Consensus Engine (审议引擎)           │  ← 借鉴 deliberation + agora
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ Blind    │→│ Peer     │→│ Adjudication │  │
│  │ Verdict  │  │ Review   │  │ + Revision   │  │
│  └──────────┘  └──────────┘  └──────────────┘  │
├─────────────────────────────────────────────────┤
│              Reasoning Engine (推理引擎)           │  ← 借鉴 KAG + griptape
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ CoT      │→│ Evidence │→│ Logic Form   │  │
│  │ Generator│  │ Gatherer │  │ Reasoner     │  │
│  └──────────┘  └──────────┘  └──────────────┘  │
├─────────────────────────────────────────────────┤
│              Orchestration Layer (编排层)          │  ← 借鉴 pyspur + griptape
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ Workflow  │  │ Tool     │  │ Memory       │  │
│  │ Engine   │  │ Registry │  │ Store        │  │
│  └──────────┘  └──────────┘  └──────────────┘  │
└─────────────────────────────────────────────────┘
```

### 5.2 ContentAuditor内部拆分（策略+管道模式）

```python
class ContentAuditor:
    """ContentAuditor 主编排器"""
    
    def __init__(self, strategies: List[AuditStrategy]):
        self.strategies = strategies
        self.results: List[AnalysisResult] = []
    
    def run(self, context: AuditContext) -> AnalysisResult:
        """执行完整审计管道"""
        current_quality = QualityMarker(level=QualityLevel.FULL, ...)
        
        for strategy in self.strategies:
            context.upstream_markers = [current_quality]
            
            if strategy.can_execute(context.available_data_sources):
                result = strategy.execute(context)
            else:
                result = strategy.get_degraded_fallback(context)
            
            self.results.append(result)
            current_quality = result.quality
            
            if current_quality.level == QualityLevel.UNAVAILABLE:
                break
        
        return self._compile_final_result()
```

### 5.3 策略组件

| 策略 | 职责 | 借鉴来源 |
|------|------|----------|
| DataCollectionStrategy | 数据收集 | agora Evidence Gathering |
| IndependentAnalysisStrategy | 独立分析 | agora Round 1 (BLIND) |
| ConsensusAuditStrategy | 共识审计 | deliberation consensus-loop |
| SynthesisStrategy | 综合裁决 | agora Coordinator Synthesis |

---

## 六、降级质量标记实现

### 6.1 数据结构

```python
@dataclass
class QualityMarker:
    """每个分析节点附带的质量标记"""
    level: QualityLevel
    source: str
    reason: str
    missing_capabilities: List[str]
    confidence: float
    propagated_from: Optional[str] = None
    
    def propagate(self, downstream_source: str) -> 'QualityMarker':
        """向下游传播降级标记"""
        decay = 0.9 if self.level == QualityLevel.DEGRADED else 0.7
        return QualityMarker(
            level=self.level,
            source=downstream_source,
            reason=f"上游降级传播: {self.reason}",
            missing_capabilities=self.missing_capabilities.copy(),
            confidence=self.confidence * decay,
            propagated_from=self.source
        )
```

### 6.2 传播机制

```python
class QualityPropagationManager:
    """质量管理器"""
    
    PROPAGATION_RULES = {
        (QualityLevel.FULL, "any"): QualityLevel.FULL,
        (QualityLevel.DEGRADED, "any"): QualityLevel.DEGRADED,
        (QualityLevel.MINIMAL, "consensus_audit"): QualityLevel.UNAVAILABLE,
    }
    
    CONFIDENCE_DECAY = {
        QualityLevel.FULL: 1.0,
        QualityLevel.DEGRADED: 0.9,
        QualityLevel.MINIMAL: 0.7,
        QualityLevel.UNAVAILABLE: 0.0,
    }
    
    ALERT_THRESHOLDS = {
        "confidence_warning": 0.6,
        "confidence_critical": 0.3,
        "max_degraded_stages": 2,
    }
```

### 6.3 告警通知

```python
class AlertNotifier:
    """告警通知器"""
    
    NOTIFICATION_CHANNELS = {
        "CRITICAL": ["log", "webhook", "email"],
        "WARNING": ["log", "webhook"],
        "INFO": ["log"],
    }
```

---

## 七、编程专家可行性审核

### 7.1 推理引擎可行性：8/10

**优点**：
- 技术选型和错误处理框架成熟
- 性能预算基本合理

**风险**：
- 全局超时缺失
- Step 3-4耗时监控

**建议**：为Step 3-4添加30分钟全局超时 + 章节级5分钟超时

### 7.2 评分器可行性：6/10

**优点**：
- 评分维度和权重设计合理
- 校准方法可行

**风险**：
- CN/HK scorer未实现
- 语义审计依赖LLM，不可复现

**建议**：
1. 优先实现CN/HK scorer
2. 为语义审计添加结构化输出约束
3. 建立ground truth测试集

### 7.3 降级标记可行性：7/10

**优点**：
- 数据结构设计清晰
- 传播机制基本可用

**风险**：
- 传播粒度不足
- 审计层未集成

**建议**：
1. 添加章节级质量标记
2. 将质量标记传入审计层
3. 添加降级报告标注

---

## 八、执行计划

### Phase 1：基础框架（1-2天）
- 创建QualityMarker数据结构
- 创建QualityPropagationManager
- 创建ContentAuditor策略框架

### Phase 2：推理引擎（3-5天）
- 实现因果推理链
- 实现情景推演链
- 实现反面论证链

### Phase 3：评分器（3-5天）
- 实现深度评分器
- 实现校准机制
- 建立ground truth测试集

### Phase 4：集成测试（1-2天）
- 端到端测试
- 黄金集测试
- 性能测试

---

## 九、验收标准

### 架构简洁性
- [x] 模块数量≤5个
- [x] 策略模式实现
- [x] 依赖方向清晰

### 代码质量
- [x] Pydantic类型系统
- [x] 完整错误处理
- [x] 100+单元测试

### 投资分析深度可行性
- [x] 评分公式完整
- [x] 推理链设计完整
- [x] 降级标记完整

### 规范性
- [x] Feature Flag设计
- [x] 向后兼容
- [x] 可回滚

---

**方案版本**: v3.0  
**生成时间**: 2026-07-01  
**借鉴项目**: WeKnora, KAG, pyspur, griptape, deliberation, agora, semantica
