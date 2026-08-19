# HGF Workflow（Hermes Gate Flow）— V3.2.0

门禁驱动开发工作流。核心哲学：**每个交付步骤都有准入条件、准出条件、以及
"真实执行"的验证方法**——"文件存在 ≠ 它工作"。

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
