# Qual流程v8.2 Gate-Driven架构 (2026-08-08)

## 背景

经HeavySkill K=8三轮迭代审查（v8.0→v8.1→v8.2），用户多次纠正后确定的架构设计。

## 核心用户纠正

### 纠正1: 第三方监督不是HeavySkill (Verified 2026-08-08)

**用户原话**: "第三方监督使用heavyskill过于重了，第三方监督是评估有没有严格按照流程要求一一执行"

**正确理解**:
- 第三方监督 = 轻量级流程合规性检查（规则驱动，秒级，无Token消耗）
- HeavySkill = 深度推理评估（用于技术方案审查，不是流程监督）

**实现**:
```python
class FlowComplianceChecker:
    """轻量级流程合规性检查器"""
    def check_gate(self, gate_num, execution_log):
        checks = []
        checks.extend(self._check_preconditions(gate_spec, execution_log))
        checks.extend(self._check_execution_content(gate_spec, execution_log))
        checks.extend(self._check_pass_criteria(gate_spec, execution_log))
        checks.extend(self._check_failure_handling(gate_spec, execution_log))
        checks.extend(self._check_human_intervention(gate_spec, execution_log))
        return ComplianceResult(passed=all(c.passed for c in checks), checks=checks)
```

### 纠正2: 数据源不可用判定必须严苛 (Verified 2026-08-08)

**用户原话**: "数据弹性，wind和财报数据不可用，需要转换时，必须先取得人工同意才能进行，且不可用的条件判定要严苛"

**5个必须同时满足的条件**:
1. 连续3次获取失败，每次间隔≥30秒
2. 错误类型为永久性错误（403、404、格式严重损坏）
3. 尝试≥2个备用数据源均失败
4. 用户明确拒绝手动上传
5. 等待时间≥10分钟

**人工同意流程**: 系统检测→重试→诊断→备用源验证→人工确认→执行决策

### 纠正3: 审查必须有修复循环 (Verified 2026-08-08)

**用户原话**: "qual流程应该是审查后自动修复，再审查，为什么不执行"

**正确流程**: 审查→修复→再审查，直到通过或达到最大轮数（3次）

### 纠正4: 财报是必须使用的数据 (Verified 2026-08-08)

**用户原话**: "财报是必须使用的数据，不允许跳过"

## 9个Gate定义

| Gate | 名称 | 前置条件 | 通过标准（确定性规则） |
|------|------|----------|------------------------|
| 0 | 数据源验证 | 无 | 财报文件存在且可解析，Wind字段覆盖率≥95% |
| 1 | 类型推断+数据提取 | Gate 0通过 | 市场类型在预定义列表中，必填字段全部存在，数值偏差≤2% |
| 2 | 数据收集+参数提取 | Gate 1通过 | FCF≠0，WACC∈[5%,15%]，永续增长率∈[1%,5%] |
| 3 | 逐章写作 | Gate 2通过 | 11章完整，每章≥500字，关键数据点跨章一致 |
| 4 | 审计修复+深度审查 | Gate 3通过 | 格式错误数=0，估值参数与Gate 2一致，逻辑矛盾≤2 |
| 5 | 质量增强+组件集成 | Gate 4通过 | 估值计算正确，组件集成100% |
| 6 | 综合结论+决策章 | Gate 5通过 | 投资评级在预定义列表中，目标价与估值偏差≤20% |
| 7 | 问题转化+记忆存储 | Gate 6通过 | 问题转化成功率≥90% |
| 8 | 最终验证 | Gate 7通过 | 质量评分≥70%，人工确认通过 |

## 与v8.1的关键差异

| 项目 | v8.1 | v8.2 |
|------|------|------|
| 通过标准 | 模糊评分（≥95%、≥80%） | 确定性规则集合 |
| 第三方监督 | HeavySkill（重） | 规则驱动检查（轻） |
| 异常处理 | 基本重试 | 超时+熔断+回滚 |
| 人工介入 | 无SLA | 定义SLA和超时降级 |
| 状态管理 | 无 | 状态机+持久化 |
| 数据源 | 基本备用源 | 具体备用源列表+数据质量评分 |

## 详细技术文档

`~/.hermes/docs/qual-workflow-v8.2.md`

## HeavySkill审查结论摘要

> 方案以Gate-Driven架构和轻量级第三方监督为核心，构建了一套严格的质量闭环，整体方向正确、结构完整。当前形态下可在理想数据环境中实现原型，但要在生产环境中稳定运行，必须补齐异常处理、确定计算验证、循环终止条件和人工协同机制。
