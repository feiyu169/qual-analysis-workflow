# HGF + HeavySkill 结合方案

> 版本：V1.0
> 日期：2026-06-21
> 作者：Hermes Agent

---

## 一、方案概述

### 1.1 目标

将 HGF（Hermes Gate Flow）的质量门禁机制与 HeavySkill 的多轨迹审查能力结合，形成一个**自动化、可量化、可追溯**的技术方案审查流程。

### 1.2 核心价值

| 维度 | HGF | HeavySkill | 结合后 |
|------|-----|------------|--------|
| **流程管理** | ✅ 标准化流程 | ❌ 无流程 | ✅ 完整流程 |
| **质量门禁** | ✅ 多级门禁 | ❌ 无门禁 | ✅ 自动化门禁 |
| **深度审查** | ⚠️ 依赖人工 | ✅ 6轨迹深度审查 | ✅ AI深度审查 |
| **问题发现** | ⚠️ 依赖经验 | ✅ 系统化发现 | ✅ 全面覆盖 |
| **结论校验** | ❌ 无校验 | ⚠️ LLM可能偏差 | ✅ 规则引擎校验 |
| **可追溯性** | ✅ 完整记录 | ⚠️ 部分记录 | ✅ 全链路追溯 |

---

## 二、架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    HGF + HeavySkill 审查流程                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Phase 0: 需求分析                                               │
│      ↓                                                           │
│  Phase 1: 任务分类（HGF Task Classifier）                        │
│      ↓                                                           │
│  Phase 2: 风险评估（HGF Risk Assessor）                          │
│      ↓                                                           │
│  Phase 3: HeavySkill 深度审查                                    │
│      ├── Stage 1: 自由探索（4条轨迹）                            │
│      ├── Stage 2: 检查清单验证                                   │
│      └── Stage 3: 结论校验引擎                                   │
│      ↓                                                           │
│  Phase 4: 专家审查（可选）                                       │
│      ↓                                                           │
│  Phase 5: 门禁执行（HGF Gate Executor）                          │
│      ↓                                                           │
│  Phase 6: 报告生成                                               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 组件说明

| 组件 | 职责 | 来源 |
|------|------|------|
| **Task Classifier** | 任务分类、风险评估 | HGF |
| **Risk Assessor** | 风险等级判定 | HGF |
| **HeavySkill** | 多轨迹深度审查 | HeavySkill |
| **Query Enhancer** | 检查清单注入 | 自研 |
| **Conclusion Validator** | 结论校验 | 自研 |
| **Gate Executor** | 门禁执行 | HGF |
| **Report Generator** | 报告生成 | 自研 |

---

## 三、详细流程

### 3.1 Phase 0: 需求分析

**输入**：用户提交的技术方案

**处理**：
1. 读取方案文档
2. 识别方案类型（架构设计/API设计/数据库设计/部署方案等）
3. 提取关键信息（技术栈、功能模块、约束条件）

**输出**：方案元数据

### 3.2 Phase 1: 任务分类

**使用 HGF Task Classifier**

```python
# 任务分类
task = TaskClassifier.classify(
    description="审查技术方案",
    files=["proposal.md"],
    lines=count_lines("proposal.md")
)

# 输出
{
    "level": "L2",  # 中等复杂度
    "type": "review",  # 审查类任务
    "risk": "medium",  # 中等风险
    "estimated_time": "30min"
}
```

### 3.3 Phase 2: 风险评估

**使用 HGF Risk Assessor**

```python
# 风险评估
risk = RiskAssessor.assess(
    affected_areas=["architecture", "security", "performance"],
    description="审查技术方案"
)

# 输出
{
    "risk_score": 15,
    "risk_level": "high",
    "risk_factors": {
        "security": 3,
        "architecture": 2,
        "performance": 1
    }
}
```

### 3.4 Phase 3: HeavySkill 深度审查（核心）

#### Stage 1: 自由探索

**输入**：原始 query（不含检查清单）

**处理**：
```bash
cd ~/.hermes/skills/heavyskill
python3 scripts/run_heavyskill.py \
  -q "请从技术可行性、架构设计、安全性、风险遗漏 4 个维度审查这个方案" \
  -f /tmp/proposal.md \
  --reason_k 4 --summary_k 2 --language cn \
  -o /tmp/heavyskill-stage1-output.json
```

**输出**：4条自由探索轨迹

#### Stage 2: 检查清单验证

**输入**：Stage 1 输出 + 领域检查清单

**处理**：
1. 识别方案领域（安全/架构/性能/API/数据库/部署）
2. 加载对应检查清单
3. 验证 Stage 1 结果的完整性
4. 标记遗漏项

**输出**：清单覆盖报告

#### Stage 3: 结论校验

**输入**：Stage 1 输出 + Stage 2 报告

**处理**：
```python
# 结论校验
validator = ConclusionValidator()
result = validator.validate(
    issues=extracted_issues,
    llm_verdict=infer_verdict(final_answer)
)

# 输出
{
    "verdict": "REJECT",  # 规则引擎结论
    "original_verdict": "PASS",  # LLM原始结论
    "verdict_changed": True,
    "rules_applied": [
        {"rule": "p0_veto", "triggered": True},
        {"rule": "domain_coverage", "triggered": True}
    ]
}
```

### 3.5 Phase 4: 专家审查（可选）

**触发条件**：
- 风险等级为"high"
- HeavySkill 结论为"REJECT"
- 用户要求专家审查

**处理**：
```python
# 分派专家
delegate_task(tasks=[
    {"goal": "编程专家审查", "role": "leaf"},
    {"goal": "架构专家审查", "role": "leaf"}
])
```

### 3.6 Phase 5: 门禁执行

**使用 HGF Gate Executor**

```yaml
# 门禁配置
gates:
  must_pass:
    - name: "heavyskill_review"
      tool: "heavyskill"
      level: "MUST_PASS"
      criteria: "结论不为REJECT"
    
    - name: "checklist_coverage"
      tool: "checklist_validator"
      level: "MUST_PASS"
      criteria: "清单覆盖率>=60%"
  
  should_pass:
    - name: "expert_review"
      tool: "delegate_task"
      level: "SHOULD_PASS"
      criteria: "专家评分>=3.5"
```

**执行结果**：
```python
{
    "gate_results": [
        {"name": "heavyskill_review", "status": "PASSED"},
        {"name": "checklist_coverage", "status": "PASSED"},
        {"name": "expert_review", "status": "CONDITIONAL_PASS"}
    ],
    "final_verdict": "CONDITIONAL_PASS"
}
```

### 3.7 Phase 6: 报告生成

**输出**：完整的审查报告

```markdown
# 技术方案审查报告

## 一、审查概览
- 方案名称：XXX
- 审查时间：2026-06-21
- 审查结论：附意见通过

## 二、HeavySkill 审查结果
- 轨迹数：4
- 问题发现率：86%
- 结论：REJECT（规则引擎覆盖）

## 三、检查清单验证
- 清单项数：30
- 已覆盖：25
- 遗漏：5

## 四、问题清单
| 级别 | 问题 | 位置 | 建议 |
|------|------|------|------|
| P0 | SQL注入风险 | 用户登录 | 使用参数化查询 |
| P1 | 缺少分页设计 | API接口 | 添加分页参数 |

## 五、门禁结果
| 门禁 | 状态 | 说明 |
|------|------|------|
| heavyskill_review | ✅ 通过 | - |
| checklist_coverage | ✅ 通过 | 覆盖率83% |
| expert_review | ⚠️ 附意见 | 需修复P0问题 |

## 六、改进建议
1. 修复SQL注入风险
2. 添加分页设计
3. 完善错误处理
```

---

## 四、集成方式

### 4.1 脚本集成

```python
# hgf_heavyskill_review.py

class HGFHeavySkillReviewer:
    """HGF + HeavySkill 集成审查器"""
    
    def __init__(self):
        self.task_classifier = TaskClassifier()
        self.risk_assessor = RiskAssessor()
        self.heavyskill = HeavySkillRunner()
        self.query_enhancer = QueryEnhancer()
        self.conclusion_validator = ConclusionValidator()
        self.gate_executor = GateExecutor()
    
    def review(self, proposal_path: str) -> ReviewResult:
        """执行完整审查流程"""
        
        # Phase 1: 任务分类
        task = self.task_classifier.classify(proposal_path)
        
        # Phase 2: 风险评估
        risk = self.risk_assessor.assess(task)
        
        # Phase 3: HeavySkill 深度审查
        heavyskill_result = self.heavyskill.run(proposal_path)
        enhanced_result = self.query_enhancer.enhance(heavyskill_result)
        validated_result = self.conclusion_validator.validate(enhanced_result)
        
        # Phase 4: 专家审查（可选）
        if risk.level == "high":
            expert_result = self.run_expert_review(proposal_path)
        else:
            expert_result = None
        
        # Phase 5: 门禁执行
        gate_result = self.gate_executor.execute(
            heavyskill=validated_result,
            expert=expert_result,
            risk=risk
        )
        
        # Phase 6: 报告生成
        report = self.generate_report(
            task=task,
            risk=risk,
            heavyskill=validated_result,
            expert=expert_result,
            gate=gate_result
        )
        
        return ReviewResult(
            verdict=gate_result.final_verdict,
            report=report
        )
```

### 4.2 MCP Server 集成

```python
# mcp_server.py

from mcp import Server, Tool

server = Server("hgf-heavyskill")

@server.tool("review_proposal")
async def review_proposal(proposal_path: str) -> dict:
    """审查技术方案"""
    reviewer = HGFHeavySkillReviewer()
    result = reviewer.review(proposal_path)
    return {
        "verdict": result.verdict,
        "report": result.report
    }

@server.tool("run_heavyskill_with_checklist")
async def run_heavyskill_with_checklist(
    query: str, 
    file_path: str,
    domains: list
) -> dict:
    """运行带检查清单的HeavySkill审查"""
    enhancer = QueryEnhancer()
    enhanced_query = enhancer.enhance(query, file_path, domains)
    result = run_heavyskill(enhanced_query, file_path)
    return enhance_output(result)
```

### 4.3 命令行集成

```bash
# 使用 HGF + HeavySkill 审查
python3 hgf_heavyskill_review.py \
  --proposal /tmp/proposal.md \
  --domains security,architecture \
  --output /tmp/review-report.md

# 或使用 MCP Server
hermes mcp run hgf-heavyskill review_proposal \
  --proposal_path /tmp/proposal.md
```

---

## 五、配置文件

### 5.1 HGF 门禁配置

```yaml
# hgf_heavyskill_gates.yaml

gates:
  # HeavySkill 审查门禁
  heavyskill_review:
    tool: "heavyskill"
    level: "MUST_PASS"
    criteria:
      - "结论不为REJECT"
      - "问题发现率>=60%"
      - "P0问题数=0"
    timeout: 300
  
  # 检查清单覆盖门禁
  checklist_coverage:
    tool: "checklist_validator"
    level: "MUST_PASS"
    criteria:
      - "清单覆盖率>=60%"
      - "P0清单项全部覆盖"
  
  # 专家审查门禁
  expert_review:
    tool: "delegate_task"
    level: "SHOULD_PASS"
    criteria:
      - "专家评分>=3.5"
      - "无P0级专家问题"
    trigger_conditions:
      - "risk_level=high"
      - "heavyskill_verdict=REJECT"
```

### 5.2 检查清单配置

```yaml
# checklists.yaml

domains:
  security:
    checklist_file: "security.yaml"
    weight: 1.5  # 安全权重更高
  
  architecture:
    checklist_file: "architecture.yaml"
    weight: 1.0
  
  performance:
    checklist_file: "performance.yaml"
    weight: 1.0
  
  api:
    checklist_file: "api.yaml"
    weight: 1.0
  
  database:
    checklist_file: "database.yaml"
    weight: 1.0
  
  deployment:
    checklist_file: "deployment.yaml"
    weight: 1.0
```

---

## 六、预期效果

### 6.1 效率提升

| 指标 | 人工审查 | HGF+HeavySkill | 提升 |
|------|----------|----------------|------|
| 审查时间 | 2-4小时 | 10-15分钟 | **90%↓** |
| 问题发现率 | 60-70% | 85-90% | **25%↑** |
| 结论准确性 | 80% | 95% | **15%↑** |
| 可追溯性 | 部分 | 完整 | **100%** |

### 6.2 质量提升

- **系统化**：检查清单确保全面覆盖
- **可量化**：评分体系提供客观指标
- **可重复**：标准化流程确保一致性
- **可改进**：数据驱动持续优化

---

## 七、实施计划

### 7.1 Phase 1: 基础集成（1周）

- [ ] 创建 HGF + HeavySkill 集成脚本
- [ ] 实现检查清单注入
- [ ] 实现结论校验引擎
- [ ] 创建命令行工具

### 7.2 Phase 2: 门禁集成（1周）

- [ ] 配置 HGF 门禁规则
- [ ] 实现自动化门禁执行
- [ ] 创建报告生成器

### 7.3 Phase 3: 测试优化（1周）

- [ ] 运行 7 个评测用例
- [ ] 对比优化效果
- [ ] 调整检查清单和门禁规则

### 7.4 Phase 4: 文档部署（3天）

- [ ] 编写使用文档
- [ ] 创建示例配置
- [ ] 部署 MCP Server

---

## 八、风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| HeavySkill 误判 | 审查结论错误 | 结论校验引擎兜底 |
| 检查清单不全 | 遗漏重要问题 | 定期更新清单 |
| 性能问题 | 审查时间过长 | 异步执行、缓存 |
| 集成复杂度 | 维护成本高 | 模块化设计 |

---

## 九、总结

### 9.1 核心价值

1. **流程标准化**：HGF 提供完整的审查流程
2. **深度审查**：HeavySkill 提供 6 轨迹深度审查
3. **质量保障**：结论校验引擎确保准确性
4. **可追溯性**：全链路记录，便于审计和改进

### 9.2 适用场景

- 技术方案评审
- 架构设计审查
- API 设计审查
- 数据库设计审查
- 部署方案审查
- 安全漏洞审查

### 9.3 预期收益

- 审查效率提升 90%
- 问题发现率提升 25%
- 结论准确性提升 15%
- 实现完全可追溯

---

**方案状态**：待确认
**下一步**：用户确认后开始实施
