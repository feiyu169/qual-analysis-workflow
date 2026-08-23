# Qual v9 重构规划：对标 dayu-agent

> **版本**: v1.0 | **日期**: 2026-08-10 | **审查状态**: 待 HeavySkill K=8 审查

---

## 一、总体判断

### 1.1 qual 应该保留什么

| 组件 | 保留理由 | 改造程度 |
|------|----------|----------|
| **Gate 0-8 状态机引擎** | 核心差异化（dayu 没有买方研究门禁） | 轻度改造（线性→DAG） |
| **11 章 CFA 框架** | 核心价值（dayu 没有买方报告模板） | 不改 |
| **contracts 层（frozen dataclass）** | 已与 dayu 对齐 | 补充 Protocol |
| **v3 质量保障体系** | 15 个模块已通过 Gate 0-6 | 增量集成 |
| **MinerU 财报解析** | dayu 无此能力 | 不改 |
| **Wind MCP 数据源** | 定制化数据接入 | 不改 |

### 1.2 qual 应该借鉴 dayu 什么

| dayu 范式 | qual 现状 | 差距 | 借鉴方式 |
|-----------|-----------|------|----------|
| **仓储协议（6 Protocol）** | dict[str, Any] 传递 | 严重 | 新增 5 个窄 Protocol |
| **write_pipeline 状态机** | 单轮审计修复 | 严重 | 引入 PREPARE→GENERATE→VALIDATE→REPAIR→COMPLETE |
| **宿主强约束** | regex 事后拦截 | 致命 | 数据仓库协议接管 |
| **audit/confirm/repair 闭环** | 16 检查器→3 检查器 | 重要 | 引入三步闭环 |
| **四层分治** | workflow.py 107KB 单体 | 重要 | 拆分为 UI→Service→Host→Agent |

### 1.3 qual 应该舍弃什么

| dayu 组件 | 舍弃理由 |
|-----------|----------|
| 多租户隔离 | qual 是单次分析工具，无多租户需求 |
| 分布式消息队列 | 单进程内状态机足够 |
| PostgreSQL + 分区 | SQLite / 文件系统足够（嵌入式场景） |
| RBAC 权限矩阵 | 单用户场景，无权限需求 |
| 区块链存证 | 过度设计，哈希链足够 |

---

## 二、架构设计

### 2.1 目标架构（四层分治）

```
┌─────────────────────────────────────────────────────────────────┐
│  UI 层（DSH Skill 入口）                                        │
│  - 触发条件、参数校验、结果展示                                  │
│  - 不含业务逻辑                                                  │
├─────────────────────────────────────────────────────────────────┤
│  Service 层（业务编排）                                          │
│  - QualWorkflow: 状态机编排                                      │
│  - ChapterWriter: 章节生成服务                                   │
│  - AuditService: 审计修复服务                                    │
│  - ValuationService: 估值计算服务                                │
├─────────────────────────────────────────────────────────────────┤
│  Host 层（基础设施）                                             │
│  - DataRepository: 数据仓储协议实现                              │
│  - LLMCaller: LLM 调用抽象                                      │
│  - AuditLogger: 审计日志                                         │
│  - CheckpointManager: 断点恢复                                   │
├─────────────────────────────────────────────────────────────────┤
│  Agent 层（外部依赖）                                            │
│  - Wind MCP、MinerU、DeepSeek                                    │
│  - 不可变，仅通过 Protocol 交互                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 与现有代码的映射

| 目标层 | 现有代码 | 改造动作 |
|--------|----------|----------|
| UI 层 | `qual_v8/workflow.py` 入口 | 提取为薄入口 |
| Service 层 | `workflow.py` 的 `run_analysis()` | 拆分为 4 个 Service |
| Host 层 | `data_collector.py`、`llm_caller.py`、`checkpoint.py` | 封装为 Protocol 实现 |
| Agent 层 | Wind MCP、MinerU | 不改 |

---

## 三、数据控制范式重构（P0）

### 3.1 问题根因

**当前范式**：LLM 生成数字 → PGNB regex 事后拦截 → 替换为占位符 → 回填

```
LLM 输出: "营收 73.66 亿元"
  ↓ regex 匹配
PGNB 拦截: "营收 [PLACEHOLDER_REVENUE] 亿元"
  ↓ 回填
最终输出: "营收 80.07 亿元"（Wind 数据）
```

**问题**：
1. regex 匹配不可靠（漏网率 ~15%）
2. 回填破坏语义（"增长 20%" 回填后可能变成 "增长 -5%"）
3. LLM 生成的定性描述与回填的定量数据矛盾

### 3.2 dayu 范式：仓储协议事前约束

**核心思想**：LLM 不能直接生成数字，只能从仓储中"选择"数字。

```
数据流:
  Wind MCP → FinancialDataRepository（结构化存储）
                ↓
            ChapterWriter（只读访问）
                ↓
            报告（数字来自仓储，LLM 只写定性分析）
```

### 3.3 qual 的实现方案

#### Phase 1: FinancialDataRepository Protocol

```python
@runtime_checkable
class FinancialDataRepository(Protocol):
    """财务数据仓储协议——LLM 只能通过此接口读数据"""
    
    def get_revenue(self, year: int) -> float: ...
    def get_net_income(self, year: int, basis: str = "gaap") -> float: ...
    def get_cashflow(self, year: int, type: str = "operating") -> float: ...
    def get_balance_sheet(self, year: int) -> BalanceSheetData: ...
    def get_market_data(self) -> MarketData: ...
    def get_valuation_params(self) -> ValuationParams: ...
    
    def validate(self) -> List[str]: ...
    """返回空列表=数据完整，否则=缺失字段列表"""
```

#### Phase 2: Prompt 注入数据表

```python
def build_chapter_prompt(chapter_id: int, repo: FinancialDataRepository) -> str:
    """构建章节 prompt——数据表作为上下文注入"""
    
    data_table = f"""
## 财务数据表（来自 Wind MCP，不可修改）

| 指标 | FY2023 | FY2024 | FY2025 |
|------|--------|--------|--------|
| 营业收入（亿元） | {repo.get_revenue(2023):.2f} | {repo.get_revenue(2024):.2f} | {repo.get_revenue(2025):.2f} |
| 净利润（亿元） | {repo.get_net_income(2023):.2f} | {repo.get_net_income(2024):.2f} | {repo.get_net_income(2025):.2f} |
| ... | ... | ... | ... |

⚠️ 重要约束：
1. 数字必须从上表引用，禁止自行计算或估算
2. 如需计算增速，请使用表中数据，公式：(当期-基期)/|基期|×100%
3. 如表中无数据，标记为"数据缺失"而非估算
"""
    
    return data_table + chapter_template
```

#### Phase 3: 输出验证（保留 PGNB 作为最后防线）

```python
class OutputValidator:
    """输出验证器——验证报告中的数字是否来自仓储"""
    
    def validate_chapter(self, content: str, repo: FinancialDataRepository) -> ValidationResult:
        extracted_numbers = self._extract_numbers(content)
        repo_numbers = self._get_repo_numbers(repo)
        
        mismatches = []
        for num in extracted_numbers:
            if not self._matches_repo(num, repo_numbers, tolerance=0.01):
                mismatches.append(num)
        
        return ValidationResult(
            passed=len(mismatches) == 0,
            mismatches=mismatches,
            action="repair" if mismatches else "accept"
        )
```

### 3.4 迁移策略

| 阶段 | 动作 | 风险 |
|------|------|------|
| Phase 1 | 新增 `FinancialDataRepository` Protocol + 实现 | 低：增量添加 |
| Phase 2 | 改造 `build_chapter_prompt()` 注入数据表 | 中：需回归测试 |
| Phase 3 | 保留 PGNB 作为最后防线，但标记为 deprecated | 低：向后兼容 |

---

## 四、质量保障闭环（P0）

### 4.1 问题根因

**当前**：16 检查器 → 3 检查器 + 单轮确定性修复

**缺失**：
1. 无 audit（审计发现问题）→ confirm（确认问题）→ repair（修复问题）闭环
2. 修复后无回归验证
3. Gate4 失败 → Gate5-8 级联跳过

### 4.2 dayu 范式：write_pipeline 状态机

```
ChapterState:
  PREPARE → GENERATE → VALIDATE → REPAIR → COMPLETE
                  ↓          ↓         ↓
              audit_log   confirm   repair_log
```

### 4.3 qual 的实现方案

#### 4.3.1 ChapterState 状态机

```python
class ChapterState(Enum):
    PREPARE = "prepare"      # 准备 prompt + 数据
    GENERATE = "generate"    # LLM 生成
    VALIDATE = "validate"    # 结构化 + 语义验证
    REPAIR = "repair"        # 修复（最多 3 轮）
    COMPLETE = "complete"    # 完成
    FAILED = "failed"        # 失败（超过重试上限）

class ChapterStateMachine:
    MAX_REPAIR_ROUNDS = 3
    
    def execute(self, chapter_id: int, ctx: AnalysisContext) -> ChapterResult:
        state = ChapterState.PREPARE
        repair_round = 0
        
        while state != ChapterState.COMPLETE and state != ChapterState.FAILED:
            if state == ChapterState.PREPARE:
                prompt = self._prepare(chapter_id, ctx)
                state = ChapterState.GENERATE
                
            elif state == ChapterState.GENERATE:
                content = self._generate(prompt, ctx.llm_caller)
                state = ChapterState.VALIDATE
                
            elif state == ChapterState.VALIDATE:
                validation = self._validate(content, chapter_id, ctx)
                if validation.passed:
                    state = ChapterState.COMPLETE
                else:
                    self._log_audit(chapter_id, validation.issues)
                    state = ChapterState.REPAIR
                    
            elif state == ChapterState.REPAIR:
                if repair_round >= self.MAX_REPAIR_ROUNDS:
                    state = ChapterState.FAILED
                else:
                    content = self._repair(content, validation.issues, ctx.llm_caller)
                    repair_round += 1
                    state = ChapterState.VALIDATE  # 回到验证
        
        return ChapterResult(
            chapter_id=chapter_id,
            content=content,
            state=state,
            repair_rounds=repair_round,
            audit_log=self._get_audit_log(chapter_id)
        )
```

#### 4.3.2 三步闭环（audit → confirm → repair）

```python
class AuditConfirmRepairLoop:
    """审计-确认-修复闭环"""
    
    def audit(self, content: str, contract: ChapterContract) -> AuditResult:
        """Step 1: 审计——发现问题"""
        issues = []
        
        # 结构化检查
        structural = self.structural_checker.check(content, contract)
        issues.extend(structural.issues)
        
        # 语义检查
        semantic = self.semantic_checker.check(content, contract)
        issues.extend(semantic.issues)
        
        # 逻辑矛盾检查
        contradiction = self.contradiction_detector.detect(content)
        issues.extend(contradiction)
        
        return AuditResult(issues=issues, passed=len(issues) == 0)
    
    def confirm(self, audit_result: AuditResult, content: str) -> ConfirmResult:
        """Step 2: 确认——验证问题是否真实（排除误报）"""
        confirmed = []
        false_positives = []
        
        for issue in audit_result.issues:
            if self._is_confirmed(issue, content):
                confirmed.append(issue)
            else:
                false_positives.append(issue)
        
        return ConfirmResult(
            confirmed=confirmed,
            false_positives=false_positives,
            needs_repair=len(confirmed) > 0
        )
    
    def repair(self, content: str, confirmed_issues: List[Issue], 
               llm_caller: Callable) -> str:
        """Step 3: 修复——生成修复 prompt"""
        repair_prompt = self._build_repair_prompt(content, confirmed_issues)
        repaired = llm_caller("repair", repair_prompt)
        
        # 验证修复是否解决了问题
        remaining = self._verify_repair(repaired, confirmed_issues)
        if remaining:
            logger.warning(f"修复后仍有 {len(remaining)} 个问题未解决")
        
        return repaired
```

### 4.4 Gate 依赖重构：线性链 → DAG

#### 当前问题

```
Gate0 → Gate1 → Gate2 → Gate3 → Gate4 → Gate5 → Gate6 → Gate7 → Gate8
                                    ↓
                              Gate4 失败 → Gate5-8 全部跳过
```

#### 目标架构：DAG + 发布门禁

```
                    ┌─── Gate1 ───┐
Gate0 ──── Gate2 ──┤             ├─── Gate6 ──── Gate8 (发布门禁)
                    └─── Gate3 ───┘
                         ↓
                    Gate4 (审计修复，独立重试)
                         ↓
                    Gate5 (质量增强，独立重试)
                         ↓
                    Gate7 (问题转化)
```

**关键改造**：
1. Gate4/5 解耦为独立重试节点，失败不阻塞 Gate6
2. Gate8 改为发布门禁（必须全部通过才能输出报告）
3. 增加并行分支（Gate1/2/3 可并行执行）

```python
class GateDAG:
    """Gate 有向无环图"""
    
    def __init__(self):
        self.nodes = {
            "gate_0": GateNode("gate_0", deps=[]),
            "gate_1": GateNode("gate_1", deps=["gate_0"]),
            "gate_2": GateNode("gate_2", deps=["gate_0"]),
            "gate_3": GateNode("gate_3", deps=["gate_0"]),
            "gate_4": GateNode("gate_4", deps=["gate_1", "gate_2", "gate_3"]),
            "gate_5": GateNode("gate_5", deps=["gate_4"]),
            "gate_6": GateNode("gate_6", deps=["gate_1", "gate_2", "gate_3"]),
            "gate_7": GateNode("gate_7", deps=["gate_5", "gate_6"]),
            "gate_8": GateNode("gate_8", deps=["gate_7"], is_publish_gate=True),
        }
    
    def get_ready_gates(self, completed: Set[str]) -> List[str]:
        """获取所有依赖已满足的 Gate"""
        return [
            name for name, node in self.nodes.items()
            if name not in completed and all(dep in completed for dep in node.deps)
        ]
```

---

## 五、contracts 层完善

### 5.1 现有 contracts

已实现：
- `frozen dataclass`：AnalysisContext、WindData、ChapterResult 等
- 缺失：`Protocol` 定义

### 5.2 需要新增的 Protocol

| Protocol | 职责 | dayu 对应 |
|----------|------|-----------|
| `FinancialDataRepository` | 财务数据读取 | CompanyMeta / SourceDocument |
| `ChapterWriter` | 章节生成 | ProcessedDocument |
| `AuditChecker` | 审计检查 | （qual 独有） |
| `ValuationCalculator` | 估值计算 | （qual 独有） |
| `LLMProvider` | LLM 调用抽象 | （qual 独有） |
| `CheckpointStore` | 断点存储 | （qual 独有） |

```python
# contracts/protocols.py

@runtime_checkable
class FinancialDataRepository(Protocol):
    """财务数据仓储"""
    def get_revenue(self, year: int) -> float: ...
    def get_net_income(self, year: int, basis: str) -> float: ...
    def get_cashflow(self, year: int, type: str) -> float: ...
    def get_balance_sheet(self, year: int) -> BalanceSheetData: ...
    def get_market_data(self) -> MarketData: ...
    def validate(self) -> List[str]: ...

@runtime_checkable
class ChapterWriter(Protocol):
    """章节生成器"""
    def write(self, chapter_id: int, prompt: str, context: AnalysisContext) -> str: ...
    def validate_output(self, content: str, contract: ChapterContract) -> bool: ...

@runtime_checkable
class AuditChecker(Protocol):
    """审计检查器"""
    def check(self, content: str, contract: ChapterContract) -> AuditResult: ...
    def get_name(self) -> str: ...

@runtime_checkable
class ValuationCalculator(Protocol):
    """估值计算器"""
    def calculate_dcf(self, inputs: DCFInputs) -> DCFResult: ...
    def calculate_comparable(self, inputs: CompInputs) -> CompResult: ...
    def validate_consistency(self, dcf: DCFResult, comp: CompResult) -> bool: ...

@runtime_checkable
class LLMProvider(Protocol):
    """LLM 提供者"""
    def call(self, system: str, user: str, temperature: float = 0.2) -> str: ...
    def get_model_name(self) -> str: ...

@runtime_checkable
class CheckpointStore(Protocol):
    """断点存储"""
    def save_chapter(self, ticker: str, chapter_id: int, content: str) -> None: ...
    def load_chapter(self, ticker: str, chapter_id: int) -> Optional[str]: ...
    def is_valid(self, content: str) -> bool: ...
```

---

## 六、分阶段路线图

### Phase 0：准备工作（1-2 天）

**目标**：建立重构基础设施

| 任务 | 交付物 | 验证标准 |
|------|--------|----------|
| 创建 `qual_v9/` 目录结构 | 目录 + `__init__.py` | 可导入 |
| 定义所有 Protocol | `contracts/protocols.py` | `mypy` 通过 |
| 定义 frozen dataclass | `contracts/models.py` | 单元测试通过 |
| 建立回归测试框架 | `tests/regression/` | 可运行 |

**风险**：低

---

### Phase 1：数据控制范式重构（3-5 天）

**目标**：从"PGNB 事后拦截"转为"仓储协议事前约束"

| 任务 | 交付物 | 验证标准 |
|------|--------|----------|
| 实现 `FinancialDataRepository` | `repository/wind_repository.py` | 单元测试通过 |
| 改造 `build_chapter_prompt()` | `prompting/chapter_prompt.py` | 回归测试通过 |
| 实现 `OutputValidator` | `validation/output_validator.py` | 阅文报告测试通过 |
| PGNB 标记为 deprecated | 代码注释 + warning | 向后兼容 |

**验收标准**：
- 阅文集团报告中数字 100% 来自仓储
- PGNB 拦截率从 ~85% 提升到 100%（双重保障）

**风险**：
- 中：prompt 改造可能导致报告质量波动
- 缓解：A/B 测试（新旧 prompt 对比）

---

### Phase 2：质量保障闭环（3-5 天）

**目标**：引入 audit/confirm/repair 状态机

| 任务 | 交付物 | 验证标准 |
|------|--------|----------|
| 实现 `ChapterStateMachine` | `state_machine/chapter_sm.py` | 单元测试通过 |
| 实现 `AuditConfirmRepairLoop` | `audit/acr_loop.py` | 阅文报告测试通过 |
| 实现 `ContradictionDetector` | `audit/contradiction.py` | 16 个模式测试通过 |
| 集成到 Gate4 | `gates/gate_4.py` | 回归测试通过 |

**验收标准**：
- Gate4 通过率 ≥ 90%
- 审计日志完整记录每个修复轮次

**风险**：
- 中：LLM 修复可能导致内容退化
- 缓解：修复后回归验证（验证修复是否引入新问题）

---

### Phase 3：Gate DAG 重构（2-3 天）

**目标**：从线性链转为 DAG + 发布门禁

| 任务 | 交付物 | 验证标准 |
|------|--------|----------|
| 实现 `GateDAG` | `gates/dag.py` | 单元测试通过 |
| 改造 Gate 执行器 | `gates/executor.py` | 阅文报告测试通过 |
| 实现发布门禁 Gate8 | `gates/gate_8_publish.py` | 全部检查通过 |
| 实现并行执行 | `gates/parallel.py` | 性能测试通过 |

**验收标准**：
- Gate4 失败不再阻塞 Gate6
- Gate8 发布门禁 100% 拦截不合格报告
- 全流程耗时 < 15 分钟

**风险**：
- 低：DAG 执行逻辑相对简单

---

### Phase 4：四层分治重构（5-7 天）

**目标**：拆分 workflow.py 107KB 单体

| 任务 | 交付物 | 验证标准 |
|------|--------|----------|
| 提取 UI 层 | `ui/skill_entry.py` | 可触发分析 |
| 提取 Service 层 | `services/workflow_service.py` | 可执行完整流程 |
| 提取 Host 层 | `host/data_host.py` | Protocol 实现正确 |
| 集成测试 | `tests/integration/` | 端到端通过 |

**验收标准**：
- 单文件 < 500 行
- 职责边界清晰
- 端到端测试通过

**风险**：
- 高：大规模重构，可能引入回归
- 缓解：每步都有回归测试，失败可回滚

---

### Phase 5：集成验证 + HeavySkill 审查（2-3 天）

**目标**：端到端验证 + 独立审查

| 任务 | 交付物 | 验证标准 |
|------|--------|----------|
| 阅文集团端到端测试 | 测试报告 | Gate0-8 全部通过 |
| 美团端到端测试 | 测试报告 | Gate0-8 全部通过 |
| 顺丰端到端测试 | 测试报告 | Gate0-8 全部通过 |
| HeavySkill K=8 审查 | 审查报告 | 综合评分 ≥ 85 |

**验收标准**：
- 三份报告全部通过 Gate0-8
- HeavySkill 审查结论："通过"
- 全流程耗时 < 15 分钟

---

## 七、风险评估

### 7.1 总体风险矩阵

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| prompt 改造导致质量波动 | 中 | 高 | A/B 测试 + 渐进式迁移 |
| DAG 执行引入并发 bug | 低 | 中 | 单元测试 + 集成测试 |
| 四层分治引入回归 | 高 | 高 | 每步回归测试 + 可回滚 |
| LLM 修复内容退化 | 中 | 中 | 修复后回归验证 |
| 全流程超时 | 低 | 高 | 性能测试 + 熔断机制 |

### 7.2 关键风险详解

#### 风险 1：prompt 改造导致质量波动

**场景**：注入数据表后，LLM 可能过度依赖数据表，忽略定性分析

**缓解**：
1. A/B 测试：对同一公司，分别用新旧 prompt 生成，对比质量
2. 渐进式迁移：先在 ch05（经营表现）试点，再推广到全部章节
3. prompt 模板保留"定性分析"指令，避免 LLM 只做数据罗列

#### 风险 2：四层分治引入回归

**场景**：拆分 workflow.py 时，可能遗漏隐式依赖

**缓解**：
1. 先写端到端测试，再拆分代码（测试驱动重构）
2. 每拆一个模块，立即运行回归测试
3. 保留旧代码 30 天，确认无问题后删除

#### 风险 3：LLM 修复内容退化

**场景**：audit/confirm/repair 闭环中，LLM 修复可能引入新问题

**缓解**：
1. 修复后运行完整验证（不只验证修复的问题）
2. 设置最大修复轮次（3 轮），超过则升级人工
3. 记录修复历史，支持回滚到修复前版本

---

## 八、实施优先级

```
P0（必须）: Phase 0 + Phase 1 + Phase 2
  ↓ 验收: Gate4 通过率 ≥ 90%
  
P1（重要）: Phase 3
  ↓ 验收: Gate4 失败不再阻塞 Gate6
  
P2（优化）: Phase 4
  ↓ 验收: 单文件 < 500 行
  
P3（验证）: Phase 5
  ↓ 验收: HeavySkill 审查通过
```

**关键约束**：
- Phase 0-2 必须在 Phase 3-4 之前完成（数据控制和质量闭环是基础）
- Phase 5 是验证阶段，必须在所有 Phase 完成后执行
- 每个 Phase 都有独立的验收标准，可独立交付

---

## 九、与 HeavySkill 审查结论的对应

| HeavySkill 审查结论 | 对应 Phase | 预期改善 |
|---------------------|------------|----------|
| 数据控制范式：不通过 | Phase 1 | 从 regex 事后拦截 → 仓储协议事前约束 |
| 质量保障：不通过 | Phase 2 | 从单轮修复 → audit/confirm/repair 闭环 |
| 可维护性：有条件通过 | Phase 4 | 从 107KB 单体 → 四层分治 |
| 遗漏风险：不通过 | Phase 2 + Phase 5 | 增加回归测试 + 审计日志 |

---

## 十、总结

### 核心改造点

1. **数据控制**：从"LLM 写数字 + PGNB 拦截" → "仓储协议 + 数据表注入"
2. **质量闭环**：从"单轮修复" → "audit/confirm/repair 三步闭环"
3. **Gate 依赖**：从"线性链" → "DAG + 发布门禁"
4. **代码结构**：从"107KB 单体" → "四层分治"

### 保留的核心价值

1. **11 章 CFA 框架**（dayu 没有）
2. **Gate 0-8 状态机**（dayu 没有买方研究门禁）
3. **MinerU 财报解析**（dayu 没有）
4. **Wind MCP 数据源**（定制化）

### 预期收益

| 指标 | 当前 | 目标 |
|------|------|------|
| Gate4 通过率 | ~70% | ≥ 90% |
| 全流程耗时 | 15 分钟 | < 15 分钟 |
| 数字准确率 | ~85% | 100% |
| 代码可维护性 | 107KB 单体 | < 500 行/文件 |

---

## 附录 A：HeavySkill 审查 Checklist

在实施 Phase 2 完成后，使用 HeavySkill K=8 审查：

```bash
cd ~/.hermes/skills/heavyskill && python3 scripts/run_heavyskill.py \
  --query "审查 qual v9 重构方案是否解决了 HeavySkill K8 审查的 4 个不通过项：
  1. 数据控制范式（regex 事后拦截 → 仓储协议事前约束）
  2. 质量保障（缺 audit/confirm/repair 闭环）
  3. 可维护性（缺 Protocol）
  4. 遗漏风险（缺回归测试、审计日志）
  
  请逐项检查解决方案的完整性和可行性" \
  --reason_k 8 --summary_k 4 --language cn
```

## 附录 B：回归测试清单

| 测试类型 | 测试用例 | 验证标准 |
|----------|----------|----------|
| 单元测试 | Protocol 实现 | 100% 通过 |
| 集成测试 | 端到端流程 | 3 份报告通过 |
| 回归测试 | 已知缺陷 | 不再复现 |
| 性能测试 | 全流程耗时 | < 15 分钟 |
| A/B 测试 | 新旧 prompt | 质量不退化 |
