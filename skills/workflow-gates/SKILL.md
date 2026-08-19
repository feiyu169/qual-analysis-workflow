---
name: workflow-gates
description: 代码质量门禁，自动分级+风险评估+门禁执行
category: development
version: "1.0"
---

# Workflow Gates Skill

代码质量门禁技能，自动完成任务分级、风险评估和门禁执行。

## 触发条件

当用户表达以下意图时触发：

- "代码审查"
- "质量检查"
- "提交前检查"
- "PR 检查"
- "帮我检查代码"
- "运行质量门禁"
- "检查代码质量"
- "分析任务风险"

## HGF 定义澄清

**HGF (Hermes Gate Flow)** 是 Gate-Driven 工作流框架，不是测试提升流程。

HGF = 阶段化门禁流程（Phase 0-5，含 Grill Session、架构设计、TDD、集成测试、部署等 Gate）

测试提升流程（变异测试、属性测试等）是 HGF 中 Gate T（测试门禁）的实现手段，不是 HGF 本身。

**关键区分**：
- HGF 工作流 = `config/gates.yaml` + `gate_manager.py` + `state_machine.py`
- 测试质量提升 = `mutmut` + `hypothesis` + 测试金字塔
- 两者是包含关系：测试质量提升服务于 HGF 的 Gate T

## 工作流程

### 1. 任务分级

调用 `classify_task` 工具，获取任务等级和风险评估。

```
输入：
- description: 任务描述
- files: 变更文件列表
- lines: 变更行数

输出：
- level: 任务等级 (L0/L1/L2/L3/L3_LITE/IAC/CONFIG/DOCS)
- type: 变更类型 (CODE/IAC/CONFIG/DOCS/MIXED)
- risk: 风险等级 (low/medium/high)
```

### 2. 执行门禁

调用 `execute_gates` 工具，执行对应等级的质量门禁。

```
输入：
- level: 任务等级
- files: 变更文件列表

输出：
- success: 是否成功
- passed: 通过门禁数
- failed: 失败门禁数
- results: 门禁详情
```

### 3. 安全检查

调用 `check_security` 工具，执行安全扫描。

```
输入：
- files: 变更文件列表

输出：
- all_passed: 是否全部通过
- results: 检查结果
```

### 4. 生成报告

根据门禁执行结果，生成质量报告。

## MCP 工具

### classify_task

任务分级工具。

**参数**：
- description (string, required): 任务描述
- files (array, required): 文件列表
- lines (integer, optional): 变更行数
- affected_areas (array, optional): 影响区域
- labels (array, optional): 标签

### execute_gates

执行质量门禁工具。

**参数**：
- level (string, required): 任务等级
- files (array, required): 文件列表
- working_dir (string, optional): 工作目录

### check_security

安全检查工具。

**参数**：
- files (array, required): 文件列表
- working_dir (string, optional): 工作目录

### analyze_requirements

需求分析工具。

**参数**：
- description (string, required): 需求描述
- context (object, optional): 上下文信息

### review_design

设计评审工具。

**参数**：
- design_doc (string, required): 设计文档
- requirements (object, optional): 需求分析结果

### check_deployment

部署检查工具。

**参数**：
- config (object, required): 部署配置
- environment (string, required): 环境

## 使用示例

### 示例 1：代码审查

用户：帮我检查这段代码

响应：
1. 识别变更文件
2. 调用 classify_task 获取等级
3. 调用 execute_gates 执行门禁
4. 生成质量报告

### 示例 2：提交前检查

用户：我要提交代码，先检查一下

响应：
1. 获取 git diff 信息
2. 调用 classify_task 获取等级
3. 调用 execute_gates 执行门禁
4. 调用 check_security 安全检查
5. 生成检查报告

### 示例 3：需求分析

用户：帮我分析这个需求

响应：
1. 调用 analyze_requirements 分析需求
2. 生成需求完整性报告
3. 提供改进建议

## 错误处理

### 门禁失败

如果门禁失败，提供：
1. 失败原因
2. 修复建议
3. 相关文档链接

### 工具不可用

如果 MCP 工具不可用：
1. 提示用户工具不可用
2. 建议检查 MCP Server 状态
3. 提供手动检查步骤

## 配置

### 门禁配置

配置文件：`.mcp-gates.yaml`

```yaml
gates:
  must_pass:
    - name: "static_analysis"
      tool: "ruff"
  should_pass:
    - name: "security_scan"
      tool: "semgrep"
  optional:
    - name: "performance_test"
      tool: "pytest"
```

### 误报配置

配置文件：`.mcp-gates-exceptions.yaml`

```yaml
known_false_positives:
  - id: "fp-001"
    rule: "semgrep/rule-name"
    file: "path/to/file"
    reason: "误报原因"
```

### Gate T: 测试门禁体系（HGF集成）

在HGF工作流中，测试门禁（Gate T）是确保交付质量的关键环节。

### Gate T 四级门禁（V3修订版，HeavySkill审查通过）

| 门禁 | 触发时机 | 执行测试 | 通过标准 | 阻塞策略 | SLA |
|------|----------|----------|----------|----------|-----|
| **Gate T0** | 代码提交/PR | L1冒烟测试 | 100%通过 | 阻断构建 | 4h内修复 |
| **Gate T1** | PR合并 | L2功能+L3边界 | 100%通过, 无P0缺陷 | 阻断合并 | 24h内修复 |
| **Gate T2** | 预发布/发版 | L4状态+L5并发+L6安全 | L4/L6=100%, L5=98%, 无高危漏洞 | 阻断发布 | 24h内修复 |
| **Gate T3** | 每日凌晨 | L1-L4全量回归 | 99%通过, 无新增缺陷 | 通知告警 | 48h内修复 |

**V3关键修订**（HeavySkill 6轨迹审查发现）：
- Gate T0 移除单元测试覆盖率要求（方案不含单元测试，需开发团队配合）
- Gate T2 安全测试改为100%（原95%容错可能掩盖P0漏洞，环境依赖用例标记skip/xfail）
- Gate T2 并发测试改为98%（受时序影响，引入pytest-rerunfailures自动重试）
- 所有Schema必须设置 `class Meta: unknown = EXCLUDE`（防止API变更导致门禁误报）
- CI/CD配置必须在第2天完成（不能拖到第8天）

**高危漏洞定义**：
- OWASP Top 10 漏洞
- CVSS评分 >= 7.0
- 敏感信息泄露（密码、Token、堆栈、数据库结构）

### 测试分级体系

- **Level 1 (冒烟)**: 核心功能可用性, <2分钟
- **Level 2 (功能)**: 正向流程全覆盖, <10分钟
- **Level 3 (边界)**: 边界条件和异常输入, <20分钟
- **Level 4 (状态流转)**: 所有状态转换路径, <30分钟
- **Level 5 (并发)**: 并发场景数据一致性, <30分钟
- **Level 6 (安全)**: XSS/SQL注入/权限/越权, <30分钟
- **Level 7 (性能)**: 响应时间/吞吐量/资源消耗, <60分钟

### HeavySkill审查测试方案

使用HeavySkill对测试方案进行多轨迹审查（6条轨迹 + 综合分析）：

```bash
cd ~/.hermes/skills/heavyskill && python3 scripts/run_heavyskill.py \
  -q "$(cat /tmp/review-query.txt)" \
  -f /tmp/test-plan.md \
  --reason_k 6 --summary_k 3 --language cn \
  -o /tmp/review.json --quiet
```

审查维度：覆盖完整性、深度充分性、HGF集成度、自动化可行性、风险识别、改进建议

**实战验证（2026-06-17）**：
- 测试方案V1审查：6/6轨迹，52,231 tokens → 发现5个P0 + 5个P1问题
- 测试方案V2审查：6/6轨迹，57,759 tokens → 发现5个P0 + 8个P1问题
- 关键发现：Schema必须设unknown=EXCLUDE、CI/CD不能拖到第8天、安全测试不能95%容错

### 参考文档

- `references/hgf-core-defects.md` — HGF 全部 13 个缺陷清单（4 轮 HeavySkill K=8 审查，含修复代码和关键坑）
- `references/hgf-implementation-review.md` — HGF 实现审查
- `references/deployment-pitfalls.md` — 部署常见陷阱和解决方案
- `references/hgf-async-architecture.md` — HGF 异步架构改造模式（aiosqlite、细粒度锁、超时取消）
- `references/hgf-async-defects.md` — HGF 异步架构缺陷清单（13 个架构级缺陷）
- `references/expert-gated-testing.md` — 专家门禁测试经验
- `references/test-automation-framework.md` — 测试自动化框架设计（V3.0，含Schema/Fixtures/Gate T/GitHub Actions）

## 相关技能

- hermes-gate-flow: 完整工作流设计、HeavySkill审查方法论、GBrain配置
- test-driven-development: TDD 开发流程
- requesting-code-review: 代码审查流程
- systematic-debugging: 系统调试流程
- gate-driven-development: Gate-driven 完整工作流模式
- heavyskill: 多轨迹推理引擎，用于方案审查

## GitHub 仓库

https://github.com/feiyu169/hermes-gate-flow

## 实现位置

本地: ~/.hermes/workflow/
MCP 注册: ~/.hermes/mcp_servers.yaml
测试: 108/108 通过

## HeavySkill 迭代审查模式（2026-07-11 验证）

当使用 HeavySkill 审查技术文档时，**必须进行多轮审查**：
- 第 1 轮：识别主要缺陷（通常发现 3-5 个）
- 第 2 轮：修复后重新审查，发现遗漏缺陷（通常再发现 2-3 个）
- 第 3-4 轮：继续修复和审查，直到无新缺陷

**实战数据**：
- HGF 架构修复：3 轮审查（v1→v2→v3），每轮发现新问题直到通过
- Qual 工作流改进：2 轮审查（v1.0→v1.1），v1.0 有 4 项阻断性问题
- Qual 工作流缺陷修复：3 轮审查（v1→v2→v3），v1 有 4 项遗漏

**审查原则**：
1. 每轮修复后必须重新提交审查
2. 修复代码必须同步更新测试
3. 全量测试通过后才能提交下一轮审查
4. K=8 用于技术文档审查（提供足够多样性）
5. 子代理无法读取本地文件 → 必须将关键内容内联到 query 中

**Query 模板**：
```bash
cd ~/.hermes/skills/heavyskill
python3 scripts/run_heavyskill.py \
  --query "请审查这份技术文档 v{N}（已修复 v{N-1} 审查发现的全部问题）。评估维度：1) ... 2) ... 3) ... 4) ..." \
  --include-file /path/to/document.md \
  --reason_k 8 \
  --summary_k 4 \
  --language cn \
  --output /tmp/heavyskill-review-v{N}.json \
  --quiet
```

**读取审查结果**：
```python
import json
with open('/tmp/heavyskill-review-v{N}.json') as f:
    data = json.load(f)
final = data.get('deliberation', [{}])[0].get('deliberation_response', '')
print(final)
```

**详细模式**：`references/iterative-review-pattern.md`（heavyskill skill）

## HGF 三大核心缺陷（2026-07-11 修复）

HeavySkill K=8 审查发现的三大架构级缺陷，已修复：

### 缺陷 1：准出条件验证绕过
- **问题**：`_verify_criteria` 对 `document_types`、`deploy_types` 入口条件直接返回 True
- **影响**：10+ 个 Gate 入口条件未实际验证
- **修复**：入口条件检查前驱 Gate 状态，出口条件优先调用验证引擎

### 缺陷 2：Gate 间无依赖关系
- **问题**：`GateConfig` 无 `depends_on` 字段，流程可乱序执行
- **影响**：可跳过需求评审直接写代码
- **修复**：添加 `depends_on` 字段，`execute_gate` 强制检查依赖

### 缺陷 3：失败处理重复计数
- **问题**：`execute_gate` 转移 FAILED 后，`handle_failure` 又做一次转移
- **影响**：`failure_count` 每次多 1
- **修复**：`handle_failure` 不再重复转移，只检查重试次数

### 额外发现（HeavySkill 持续审查）
- **超时 Off-by-one**：检查在转移前，实际允许次数比配置多 1 → 先转移再检查
- **非法状态转移**：`TIMEOUT → FAILED` 不合法 → 改为 `TIMEOUT → ESCALATED`
- **时区混淆**：`datetime.now(timezone.utc)` 与 naive datetime 相减 → 统一 aware 对象
- **数据库迁移**：旧数据库无 `timeout_count` 列 → 添加 `ALTER TABLE` 迁移逻辑

## HGF 异步架构实现（2026-07-11 完成）

### 核心组件
- `async_state_machine.py` — 异步状态机（aiosqlite + WAL 模式）
- `async_gate_manager.py` — 异步 Gate Manager（细粒度锁 + 超时取消）

### 关键设计模式
1. **细粒度锁**：Gate 级别锁，支持无依赖 Gate 并行
2. **超时取消**：`asyncio.wait_for` + `task.cancel()`，正确处理 CancelledError
3. **原子写入**：先数据库后内存，失败不更新内存
4. **状态恢复**：重启后自动处理超时 Gate
5. **私有方法**：`_handle_failure`、`_escalate_to_owner` 为私有，防止绕过锁

### 测试结果
329/329 通过（含 30 个异步测试：9 状态机 + 11 Manager + 10 集成）

### GitHub 仓库
https://github.com/feiyu169/hermes-gate-flow

## GitHub 上传脱敏流程（2026-07-11 验证）

上传代码到 GitHub 前必须脱敏：

1. **删除敏感文件**：`*.db`、`*.sqlite`、`__pycache__/`
2. **检查本地路径**：`grep -rn "/home/" *.py`
3. **检查密钥**：`grep -rn "api_key\|password\|secret\|token" *.py`
4. **添加 .gitignore**：确保 `*.db`、`__pycache__/`、`.venv/` 被忽略
5. **验证**：`git status` 确认无敏感文件跟踪

## HGF 异步架构（2026-07-11 实施）

HGF 工作流已改造为完全异步架构，解决事件循环阻塞、并发安全等问题。

**核心组件**：
- `async_state_machine.py` — 异步状态机（aiosqlite + WAL 模式）
- `async_gate_manager.py` — 异步 Gate Manager（细粒度锁 + 超时取消）

**关键模式**：
- 细粒度锁：Gate 级别锁，支持无依赖 Gate 并行
- 超时取消：`asyncio.wait_for` + `task.cancel()`
- 原子写入：先数据库后内存，失败不更新内存
- 状态恢复：重启后自动处理超时 Gate

**详细文档**：`references/hgf-async-architecture.md`
**架构缺陷清单**：`references/hgf-async-defects.md`（13 个架构级缺陷）

**测试结果**：329/329 通过（含 30 个异步测试）

## 注意事项

1. 门禁配置需要根据项目特点调整
2. 误报需要定期复查和清理
3. 安全检查可能需要网络访问
4. 首次运行可能需要安装依赖工具
5. **代码质量审查**: 当对 HGF 工作流代码本身进行审查时，参考 `gate-driven-development` 技能的 `references/hgf-code-pitfalls.md`，包含从实际评审中发现的 10+ 个 P0/P1 级问题（空壳实现、变量遮蔽、类型错误等）
5. **依赖安装**: structlog等依赖必须安装到正确Python版本的site-packages，使用 `pip3 install --target=<path>` 而非 `--user`
6. **MCP工具不可用时**: 直接用subprocess调用ruff/pytest作为fallback，详见gate-driven-development技能的 `references/hgf-execution-recipe.md`
