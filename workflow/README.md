# HGF Workflow（Hermes Gate Flow）— V3.3.2

门禁驱动开发工作流。核心哲学：**每个交付步骤都有准入条件、准出条件、以及
"真实执行"的验证方法**——"文件存在 ≠ 它工作"。

## 架构概览（组件 / 数据流 / 信任边界 / 接口）

### 组件

| 组件 | 职责 |
|------|------|
| CLI（`workflow_cli.py`） | 入口：execute/history/lifecycle/canary/metrics |
| 门禁执行器（`gate_executor.py`） | 编排等级矩阵、验证契约、失败记录、基线/历史 |
| 门禁插件（`gate_plugins.py`） | 13 个工具插件（ruff/pytest/detect-secrets/semgrep/safety/checkov/纪律/生态） |
| 生命周期（`lifecycle*.py`） | Phase 0-5 DAG 状态机 + 26 个准出检查器 + 流程度量 |
| 状态存储（`state_io.py`/`baseline.py`/`failure_log.py`/`run_history.py`） | 原子写入 `.hgf/` 下的 JSON/JSONL 状态文件 |
| 桥接（`hgf_bridge.py` + `plugin/hgf-tools.js`） | DSH 动态插件 ↔ Python 引擎的 JSON 长驻桥 |

### 数据流

```
用户请求 → workflow_cli/bridge/mcp（入口层）
  → classify_task / assess_risk（分级+风评）
  → gate_executor（加载 mcp-gates.yaml 矩阵 → 逐 gate 执行工具）
  → 工具真跑（ruff/pytest/semgrep/detect-secrets/safety/checkov）
  → 结果标准化（GateResult）→ 报告 + failure_log（失败闭环）
  → lifecycle advance（gates.yaml DAG 准出检查器）→ 状态落盘 .hgf/
```

### 信任边界

- **进程边界**：CLI / bridge / MCP 各自独立进程，独占 `.hgf/` 状态目录
  （跨进程并发追加不保证原子，见 state_io 文档）；
- **文件边界**：`.hgf/` 状态文件为单写入者；`config/*.yaml` 为只读配置；
- **外部工具边界**：门禁工具输出经 `_safe_parse` fail-loud 解析，
  工具升级漂移由 `canary.py` 金丝雀拦截；
- **评审边界**：`review.py` 双签名 + kind 语义（独立评审 vs 自检），
  user_acceptance 拒绝 self-check。

### 接口

| 接口 | 端点 | 请求/响应 |
|------|------|-----------|
| CLI | `workflow_cli.py --execute/--history/--lifecycle/--canary/--failures` | 参数（--task/--files/--dir）+ JSON/文本报告 |
| 桥 | `hgf_bridge.py --serve`（stdio JSON-RPC） | 每行 `{id,command,args}` → `{id,ok,result\|error}` |
| MCP | `mcp_server.py`（stdio） | classify_task/assess_risk/execute_gates/verify_tdd 等工具 |
| Python API | `gate_executor.GateExecutor` / `lifecycle.*` / `failure_log.*` | 对象调用，返回 GateExecutionReport / dict |

**Schema 约定**：所有接口的请求/响应均为 JSON 对象（CLI 用 `--json` 输出，
桥/MCP 用 JSON 行协议）。数据 schema 定义见各模块 docstring 与
`hgf_state.py` 的 `hgf.v1` 信封（schema/kind/writer/timestamp/payload），
旧记录读取兼容（V3.2.5）。

## 模块地图

### 核心（可执行、有测试、覆盖率 ≥80%）

| 模块 | 职责 |
|------|------|
| `task_classifier.py` | 任务分级（L0-L3、热修复、混合类型、关键模块升级） |
| `risk_assessor.py` | 风险评级（关键词映射含中文、组合加成、P32 高风险护栏） |
| `gate_types.py` | 标准化输出（GateConfig/GateResult/GateExecutionReport） |
| `gate_plugin.py` | 插件基类（命令模板、_safe_parse fail-loud） |
| `gate_plugins.py` | 12 个门禁插件（6 工具 + 3 纪律 + 3 生态） |
| `gate_executor.py` | 门禁编排（等级矩阵、验证契约、重试/升级、基线、运行历史） |
| `failure_log.py` | 结构化失败记录 `.hgf/failures.jsonl`（failure-log 门禁数据层） |
| `failure_handler.py` | 失败分类/重试/升级（V3.2 接线进执行器） |
| `baseline.py` | 标准基线 `.hgf/baseline.json`（配置哈希+工具版本，漂移告警） |
| `run_history.py` | 运行历史 `.hgf/runs.jsonl`（趋势与回归可见） |
| `lifecycle.py` | 生命周期 DAG（gates.yaml 状态机：准入→准出检查器→done） |
| `false_positive_checker.py` | 已知误报/豁免 |

### 入口

| 模块 | 用途 |
|------|------|
| `workflow_cli.py` | 命令行：`--execute` 门禁、`--history` 历史、`--lifecycle status/advance`、`--version` |
| `mcp_server.py` | MCP 服务（hermes 兼容入口，DSH 侧推荐用 CLI） |
| `hgf_bridge.py` | **插件桥**（V3.2.6）：JSON-in/JSON-out，被 `plugin/hgf-tools.js` 动态插件 spawn 调用 |
| `plugin/hgf-tools.js` | **DSH 动态插件持久化源码**：注册 5 个原生工具（hgf_execute_gates 等） |

### 归档（`_legacy/`）

未接线的旧模块（state_machine/gate_manager/async_*/tdd_verifier 等），
复活条件见 `_legacy/README.md`。

## 12 个 YAML 配置职责

| 配置 | 谁用 | 职责 |
|------|------|------|
| `config/mcp-gates.yaml` | gate_executor | **工具矩阵**：门禁定义（命令模板/验证级别/证据）+ 等级矩阵（L0-L3/L3_LITE/IAC/CONFIG/DOCS） |
| `config/gates.yaml` | lifecycle | **生命周期 DAG**：Phase 0-5 的 16 个 gate（准入/准出条件） |
| `config/workflow.yaml` | failure_handler 等 | 阈值/超时/升级/豁免/关键模块/热修复关键词 |
| `config/risk_mapping.yaml` | risk_assessor | 风险因子权重/映射（英+中）/组合加成/降级规则 |
| `config/exceptions.yaml` | false_positive_checker | 已知误报/豁免 |
| `config/iac_governance.yaml` | 文档 | 分支保护与审计（模板） |
| `config/security_checklist.yaml` / `code_review_checklist.yaml` / `architecture_review_checklist.yaml` | 人工评审 | 检查清单 |
| `config/ci_cd_template.yaml` / `monitoring_template.yaml` | 部署 | CI/监控模板 |
| `config/critical_paths.yaml` | 文档 | 关键路径说明 |

## 端到端流程

```
用户需求 → classify_task（分级）→ assess_risk（风评）
  → execute_gates（等级门禁，真实执行）→ 报告 + 失败记录
  → lifecycle advance（DAG 推进，准出检查器）→ 基线/历史存档
```

## P 库纪律 → 门禁化对照

| 纪律（P#） | 现在由谁强制 |
|------------|--------------|
| P0 文件存在≠能用 | fail-loud 解析器（V3.2）+ lifecycle 检查器（内容校验） |
| P4 失败要记录 | failure-log 门禁（自动落盘 + 根因必填） |
| P16 CONDITIONAL PASS | lifecycle 的 --confirm 兜底 |
| P20 空桩测试 | test-quality 门禁（AST） |
| P28 不发明流程名 | hgf 技能约定 |
| P31 映射语言不一致 | risk_assessor 中文映射已接线 + 测试 |
| P32 高风险降级护栏 | risk_assessor 护栏 + 测试 |
| P33 增量覆盖率 | unit_test 的 incremental_coverage_min |
| P53 元门禁自律（V3.3.3） | self_audit 检查器 + gate_5_3（4 项机械验证）+ 7 测试 + pre-push/CI |

## 开发命令

```powershell
# 测试（含覆盖率门槛 80%）
python -m pytest tests/ --cov=. --cov-fail-under=80

# 静态检查（规则集见 pyproject.toml [tool.ruff.lint]，固定可复现）
ruff check .

# 对项目跑完整门禁
python workflow_cli.py --task "..." --files "a.py" --dir . --execute

# 生命周期
python workflow_cli.py --lifecycle status
python workflow_cli.py --lifecycle advance gate_0_1 --file docs/xxx.md
```

## TDD 纪律（V3.3.2 M3 澄清）

HGF 的 `_check_tdd_evidence` 检查器要求：`tests/` 首次提交 ≤ 实现首次提交
（测试先于实现，或同提交）。HGF 自身的仓库历史为基线导入（tests/ 与实现
同提交 c616aaf）→ **满足"测试不晚于实现"，门禁通过**。后续演进约定：
新增功能时先提交测试、再提交实现（`git add tests/ && commit` →
`git add 实现 && commit`），保持 TDD 证据可验证。

## 工具链依赖（V3.3.2：requirements-hgf.txt 为真 pip 文件）

`requirements-hgf.txt` 是 **pip 可解析的依赖锁定文件**（每行 `包==版本`），
与 `gate_plugins` 的 `min_version/max_version` 契约对应：

```powershell
# 安装（对齐 workflow 门禁所需版本）
python -m pip install -r requirements-hgf.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 用 dependency_scan 门禁扫描本文件自身
safety check -r requirements-hgf.txt --json
```

版本区间契约（插件解析器兼容范围）：ruff>=0.16、pytest>=7.0、
detect-secrets>=1.0、safety>=2.0,<4.0、semgrep>=1.0、checkov>=1.0,<4.0。
工具升级越界 → 门禁 ERROR"工具升级可能改变输出契约，请升级 HGF 解析器"。

## 部署与环境

| 项 | 说明 |
|----|------|
| 部署 | 纯 Python 包（无编译依赖），复制 `workflow/` 目录即可；DSH 侧经动态插件 + bridge 接入 |
| 环境 | Windows 10+ / Linux（CI），Python 3.12-3.14；系统 Python 3.14 实测 |
| 回滚 | 版本由 `__init__.py` + `config/workflow.yaml` 双写；升级前跑 `--canary` 金丝雀，失败即回退工具版本 |
| 配置 | `config/` 下 12 个 YAML（矩阵/DAG/风评/豁免/模板），缺失即 fail-closed 抛错 |
