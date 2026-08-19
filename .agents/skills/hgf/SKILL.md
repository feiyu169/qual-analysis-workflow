---
name: hgf
description: >-
  Hermes Gate Flow (HGF) 门禁驱动开发工作流（DSH 接入版）。当用户要求"代码审查 /
  质量检查 / 运行质量门禁 / 提交前检查 / 用 HGF / HAF流程" 时使用。每个 Gate 必须有
  准入/准出条件与真实执行验证（L1-L5），禁止"文件存在即通过"。配套代码在
  workspace/workflow/（gate_executor、risk_assessor、task_classifier、mcp_server 等）。
---

# Hermes Gate Flow (HGF) — 门禁驱动开发（DSH 接入）

HGF 是 hermes 沉淀的多组件项目质量门禁工作流：**每个交付步骤都有明确的准入条件、
准出条件、以及"真实执行"的验证方法**，防止"看起来做完了"冒充"真的能用"。

## 核心流程

```
用户需求 → Phase 0 需求分析 → 编写代码 → classify_task（分级 L0-L3）
  → assess_risk（风险评级）→ execute_gates（质量门禁，失败修复重跑）
  → 用户确认 → 提交（git hook 预检）
```

| 阶段 | 动作 | DSH 侧对应工具 |
|------|------|----------------|
| Phase 0 | 需求分析、任务分类 | todo_write 拆解 |
| 编写 | 按需求写代码 | write / edit |
| classify | 按文件数/行数/变更类型/关键模块分级 | 本技能规则（人工判定） |
| assess | 关键词风险映射（auth/payment/security…）+ 高风险护栏 | 本技能规则 |
| gates | ruff / pytest / semgrep / 安全检查 | pwsh 执行（无 MCP 时手动等价） |
| 确认 | 结果呈现、等待用户批准 | 汇报 + ask_user_question |
| 提交 | git hook 预检 | pwsh git |

## 验证分级（什么是"真验证"）

| 级别 | 方法 | 何时用 |
|------|------|--------|
| L1 | 单元测试（通过/失败计数） | 核心计算逻辑 |
| L2 | 真实数据端到端集成测试 | 数据→计算→输出链 |
| L3 | 真实外部数据验证 | 调用外部 API 的组件 |
| L4 | 手动触发 + 输出检查 | cron/定时任务 |
| L5 | 路由/分发测试 | 路由器/选择器组件 |

**不算验证（一律禁止）**：
- ✗ 文件存在且 >0 字节
- ✗ "SKILL.md 写好了"
- ✗ "API 返回 200"（没查实际数据）
- ✗ "cron 已创建"（没触发过）
- ✗ lint 通过（必要但不充分）

## 从 DSH 驱动（代码在 workspace/workflow/）

```powershell
# 本机实测环境（2026-08-17 接入，V3.1）：系统 Python 3.14，已装 pyyaml/
# structlog/pytest/pytest-cov/ruff/detect-secrets/safety/semgrep
#（safety/semgrep 依赖较重，首次安装用清华镜像）
$py = "C:\Users\79902\AppData\Local\Programs\Python\Python314\python.exe"
$env:PYTHONPATH = "D:\OneDrive\文档\deepseek harness workspace\workflow"
cd "D:\OneDrive\文档\deepseek harness workspace\workflow"

# 方式1：CLI（推荐，含分级+风评+门禁，--execute 时退出码=门禁结果）
& $py workflow_cli.py --task "任务描述" --files "a.py,b.py" --lines 100 --dir . --execute [--json]

# 方式1b：生命周期（config/gates.yaml 的 Phase 0-5 DAG 状态机）
& $py workflow_cli.py --lifecycle status --dir .
& $py workflow_cli.py --lifecycle advance gate_0_1 --file docs/requirements.md --dir .

# 方式1c：运行历史与基线
& $py workflow_cli.py --history --dir .
# .hgf/baseline.json（配置哈希+工具版本，漂移告警）、.hgf/runs.jsonl（趋势）

# 方式1d：金丝雀版本回归（V3.2.8）与评审工具链（V3.2.8）
& $py workflow_cli.py --canary --dir .            # 工具版本漂移时跑轻量回归
& $py workflow_cli.py --canary --force --dir .    # 强制跑
& $py workflow_cli.py --review-build review.py --dir .        # 生成审查包
& $py workflow_cli.py --review-record review_passed --verdict pass --verifier heavyskill

# 方式2：直接调用 gate 执行器（端到端 demo 见 workflow/demo_hgf/hgf_demo.py）
& $py demo_hgf\hgf_demo.py

# 方式3：MCP 服务方式（hermes 原用法，需 structlog 等依赖）
#   python mcp_server.py  → 注册为 stdio MCP 服务，工具：
#   classify_task / assess_risk / execute_gates / verify_tdd / check_security / get_workflow_status
```

- 无 MCP 时用手动等价：静态分析 `ruff check`、单测 `pytest`、安全 `grep` 常见模式，
  输出格式仍按 HGF（Gate 结果表 + 准出判定）。
- 门禁配置：`workflow/config/gates.yaml`、`mcp-gates.yaml`、`risk_mapping.yaml`、
  `exceptions.yaml`（已知误报豁免）。

## V3.1 改进（2026-08-17 实施，全部经过狗粮化验证）

- **三个纪律门禁**（mcp-gates.yaml 已挂入 L1-L3）：
  - `test_quality`（test-quality）：AST 解析检测空桩测试（无断言的 `test_*` 函数）→ FAIL；
  - `integration_probe`（integration-probe）：配置驱动的调用点探针，"文件存在≠已接入"自动化；
  - `failure_log`（failure-log）：门禁失败自动写入 `.hgf/failures.jsonl`，
    复跑前必须补 root_cause/fix（`failure_log.update_failure`），否则该门禁 FAIL。
- **配置单一事实来源**：门禁命令一律从 `mcp-gates.yaml` 读模板（`{files}`/`{coverage_min}`），
  插件不再硬编码；`DEFAULT_CONFIG` 已删除，配置缺失即抛错（fail-closed）；
  启动时校验门禁名可解析、工具已注册。
- **验证级别契约**：每个门禁声明 `verification: L1-L5`，执行器检查插件能力
  （`verification_levels`）必须覆盖声明级别，否则 ERROR。
- **CLI 修复**：`workflow_cli.py` 去掉 hermes 硬编码路径，支持 `--dir`/`--execute`/`--json`，
  退出码=门禁结果（0=通过，1=失败）。
- **risk_assessor 修复**：`KEYWORD_MAPPING`（中文关键词）此前定义后从未使用（P31），
  已接线到 affected_areas 与 description。
- **ruff 规则集固定**：`workflow/pyproject.toml` 的 `[tool.ruff.lint]` 固定 select/ignore
  并逐条注明理由（DTZ005 与 P17 冲突等），门禁标准可复现。
- **测试套件**：`workflow/tests/` 96 个测试、85% 覆盖率（`.coveragerc` 排除入口脚手架）；
  HGF 对自身 L3 狗粮化：全部 MUST_PASS 通过（exit=0）。

## V3.2 演进（2026-08-17，路线图全量实施）

- **假通过防线（fail-loud）**：`GateResult.parse_error` + `GatePlugin._safe_parse`；
  detect-secrets/semgrep/safety/checkov 解析失败 → **ERROR 拒绝判定**（checkov
  假通过教训普适化）；**MUST_PASS 的 ERROR 同样阻断流水线**（V3.2 修复假绿灯）。
- **重试/升级**：failure_handler 接线（超时/网络/限流指数退避，仅 MUST_PASS 重试；
  连续失败 2 次→通知、3 次→冻结流程，写入 result.suggestions）。
- **生命周期**：`lifecycle.py` 让 gates.yaml（16 gate，Phase 0-5）变成可执行 DAG：
  `--lifecycle status/advance`；准出检查器真实执行（文档内容≥100 字符拒空壳、
  pytest/ruff 真跑、评审记录）；无检查器条件需 `--confirm`。
- **L2-L5 证据机制**：门禁配置 `evidence`（glob），声明 L2+ 必须有非空证据文件。
- **生态门禁**：format-check（ruff format）、pin-check（依赖固定 ==）、
  docs-check（README 章节，probes 配置必需章节）。
- **基线/历史**：`.hgf/baseline.json`（配置哈希+工具版本漂移告警）、
  `.hgf/runs.jsonl` + `--history`（通过率、反复失败门禁）。
- **CI**：`.github/workflows/hgf-gates.yml`（PR/推送对变更文件跑完整 HGF）。
- **环境限制记录**：safety 3.x 需 API key/网络才能产出 JSON，本机无 key →
  L3 的 dependency_scan 降为 SHOULD_PASS（注释说明，具备 SAFETY_API_KEY 时应移回
  must_pass）；`safety check --offline` 需已有缓存库。
- **死代码归档**：9 个未接线模块移入 `_legacy/`（复活条件见其 README）。

## V3.2.5 补充意见实施（2026-08-17）

- **工具版本契约**：插件声明 `min_version/max_version`（如 safety >=2,<4），
  版本越界 → ERROR"工具升级可能改变输出契约，请升级 HGF 解析器"（防
  ruff/safety/checkov 结构漂移类事故）。
- **报告环境维度**：`tool_health`（SKIPPED/ERROR 门禁一览）——环境问题与
  代码质量分离，避免把网络/工具故障当成代码信号。
- **评审双签名**：reviews.jsonl 记录必须 `reviewer ≠ verifier` 且均非空，
  防 agent 自签评审冒充独立审查（lifecycle review_passed 检查器强制）。
- **.hgf 状态目录 schema**：`hgf_state.py` 统一 `hgf.v1` 信封
  （schema/kind/writer/timestamp/payload），旧记录读取兼容；`.hgf/STATE.md`
  注册表；baseline/lifecycle 单文档也带 schema_version。
- **分级人工覆盖**：CLI `--level`（机器建议、人确认，覆盖原因输出到 stderr）。
- **P 库状态注册表**：`workflow/docs/pitfalls-registry.md`（已门禁化/文档纪律/
  编号重复标记）。
- **工具链自身依赖**：`workflow/requirements-hgf.txt` 固定 9 个门禁工具版本，
  可用 `safety check -r requirements-hgf.txt` 深度狗粮化。
- **safety API key**：已配置（SAFETY_API_KEY）；在线扫描在受限网络下慢/被限流，
  dependency_scan 维持 SHOULD_PASS 作低频深度检查；系统 Python 有 51 个已知
  漏洞（清单见 `output/security-remediation.md`，修复待决策）。

## V3.2.6 插件模式（HGF as DSH Plugin，2026-08-18 实测通过）

HGF 已能以**原生工具**暴露给模型（不再经 pwsh 文本解析）：
- 架构：模型调用工具 → 动态插件 spawn `python hgf_bridge.py <cmd> <json>` → JSON 返回
- **5 个工具**：`hgf_execute_gates`（等级门禁）/ `hgf_classify_task`（分级）/
  `hgf_assess_risk`（风评）/ `hgf_lifecycle`（status/advance）/ `hgf_history`（历史）
- **持久化源码**：`workflow/plugin/hgf-tools.js`（动态插件是会话级、重启失效；
  重建 = 读该文件 → cordis_define（kind new/existing）→ cordis_run，共 2 次调用）
- **桥接脚本**：`workflow/hgf_bridge.py`（JSON-in/JSON-out，屏蔽 structlog 防污染；
  lifecycle 用 gates.yaml 而非 mcp-gates.yaml）
- **实测结论**：链路 5/5 工具通过；沙箱需 danger-full-access（同 pwsh 约束）；
  每次调用 spawn 一次 Python（约 0.5-1s）；双维护约定：**插件为主入口、CLI 为
  脚本化兜底**。
- 升级注意：插件内 BRIDGE 路径硬编码（含中文工作区路径），移动工作区需同步修改。
  HGF 对自身 L2 狗粮化 8/8 门禁全绿。
- 门禁工具齐全：ruff/pytest/pytest-cov/detect-secrets/safety/semgrep/checkov 已装
  （checkov 3.3.11；其 JSON 顶层为数组，解析器已兼容新旧格式并有回归测试）。

## V3.2.8 收尾补齐（2026-08-18：CI 真跑 / 提交钩子 / TDD 证据 / 金丝雀 / 评审工具链）

针对 HGF 流程架构审计的 4 项收尾 + 第 5 项评审工具链（按推荐顺序实施）：

1. **CI 真跑**：`workflow/scripts/ci_simulate.sh`（Git Bash 运行）——对
   `git diff --name-only BASE_REF`（默认 HEAD~1）的变更文件真实执行
   `workflow_cli.py --execute --json`，grep 汇总 `gate exit code`，脚本退出码=门禁结果；
   实测对 HEAD~1..HEAD 变更跑通（CI_EXIT=0）。CI 流水线只需 `bash workflow/scripts/ci_simulate.sh`。
2. **提交前钩子**：`workflow/git_hooks/pre-push` + `workflow/scripts/install_git_hooks.ps1`
   （`git config core.hooksPath workflow/git_hooks`）。pre-push 对暂存文件
   （`--cached`）与 HEAD~1 变更分别跑门禁，任一级别 MUST_PASS 失败 → exit 1 拒绝推送；
   已用临时 bare remote 实测：门禁失败阻止推送、通过后推送成功。
3. **TDD 证据检查器**：`lifecycle._check_tdd_evidence`——用
   `git log --diff-filter=A` 对比测试文件与实现文件的首个提交时间，
   test 先于 impl（或同提交）→ pass，否则 FAIL"测试后于实现"；
   已接线到 lifecycle 检查器表并配 11 个生命周期测试。
4. **金丝雀版本回归**：`workflow/canary.py`——`current_tool_versions()` 对比
   `.hgf/baseline.json` 工具版本，漂移时跑轻量金丝雀集（ruff 固定文件 +
   快速 pytest），防"工具升级悄悄改契约"。CLI：`--canary`（有漂移才跑）/
   `--canary --force`（强制跑）；`--json` 输出。4 个测试覆盖。
5. **评审工具链（heavyskill 接入）**：`workflow/review.py`——
   - `build_pack(working_dir, file)`：把被审文件内联成审查包（满足 heavyskill
     子代理读不了本地文件的约束），超 20000 字符截断并标记；
   - `record_review(...)`：双签名结论写 `.hgf/reviews.jsonl`
     （reviewer=agent / verifier=heavyskill），lifecycle review_passed 检查器强制
     reviewer ≠ verifier；
   - CLI：`--review-build <file> [--review-out]`（输出默认
     `.hgf/review-packs/<file>.md`）、`--review-record <gate> --verdict pass|fail
     [--verifier] [--reviewer] [--notes]`；
   - 流程：`--review-build` 生成包 → 把包内容内联进 heavyskill query 审查 →
     `--review-record` 落盘 → `--lifecycle advance <review_gate> --file <包>` 验证。
   4 个测试覆盖（内联/截断/双签名/自签拒绝）。

## V3.2.8-A 失败记录"已解决"口径（2026-08-18）

审计发现 `.hgf/failures.jsonl` 6 条历史失败全部已修复（root_cause/fix/re_run_result
齐全），但记录 schema 无 `resolved` 状态位 → 按"未标记 resolved"统计会误报 6 项待处理。
采用**约定式判定（方案 A，零 schema 变更）**：

- **已解决 = `re_run_result` 非空**（`failure_log.is_resolved(entry)`）；
  复跑通过即补 `re_run_result`，无需维护独立状态位。
- **gate_executor 自动闭环**：execute_gates 结束后，对本次**通过**的 MUST_PASS 门禁，
  若有历史失败记录自动回填 `re_run_result="复跑通过（passed）"` ——
  "失败要记录 → 复跑闭环"成为系统行为，不再依赖手工维护。
- **CLI 视图**：`workflow_cli.py --failures [--dir .] [--json]` 输出
  总条数 / 未解决条数（re_run_result 为空）/ 未解决明细。
- **测试**：`is_resolved` 约定（含空串/None/缺字段）、`unresolved_failures` 过滤、
  复跑通过自动回填（gate_executor），共 3 个新断言场景。
- **实测**：对现存 6 条记录 → `--failures` 显示"未解决 0 条，✅ 全部已解决"。

**回归基线**：全量测试 113 passed（含 review 4 个、tdd_evidence、canary 4 个，
canary 测试较慢约 70s）；ruff 全绿；`review.py`/`workflow_cli.py` 均过 ruff 检查。

## V3.2.9 架构评审修复（2026-08-18：heavyskill 独立审议 6.5/10 → 5 组修复）

对 HGF 全面架构评审（heavyskill 8 轨迹审议）后实施的全部建议：

1. **A/J 安全准出真跑（消除"名不副实"）**：`lifecycle._CHECKERS` 中
   `sast_scan` → 真跑 semgrep、`dependency_scan` → 真跑 safety、
   `iac_security_audit` → 真跑 checkov（此前全部映射 ruff/pytest 兜底）；
   `dast_scan` → 需外部 DAST 报告（--file）或 --confirm，显式标注不静默通过。
   新检查器 `_check_tool_scan`：工具缺失/超时/执行失败 → FAIL（fail-loud）。
2. **B 弱入口修复**：`mcp_server.verify_tdd` 委托 `lifecycle._check_tdd_evidence`
   （git 历史真验证），废弃"commit 消息含 test 字样即通过"的弱判定。
3. **C 豁免机制接线**：`false_positive_checker` 接入 gate_executor——
   FAILED 结果的 issues 全部命中已知误报（rule+file 精确、未过期）→ PASSED
   并注明豁免；部分命中 → 保留 FAILED 并提示。此前定义了单例却从未调用。
4. **D/F/G 工程卫生**：
   - D：hgf-tools.js 路径环境变量化（`HGF_BRIDGE`/`HGF_PYTHON`，移动工作区免改码）；
   - F：`gate_plugin._run_command` 改 argv 数组 + `shell=False`（新增 `_build_argv`，
     {files} 展开为独立参数，路径含空格安全，不再 shell 字符串拼接）；
   - G：pre-push hook / ci_simulate.sh 无 Python 变更时跳过门禁（不再传 `__no_change__`）。
5. **E/H/I 一致性与观测收敛**：`__version__` 同步 3.2.9；`failure_handler.record_failure`
   docstring 澄清内存态 vs failure_log 持久化边界；mcp_server 不再双写 sqlite
   gate_results（门禁历史统一 .hgf/runs.jsonl，`get_workflow_status` 读取 .hgf 趋势）。

**回归基线**：129 passed（+10 新测试：安全准出映射/工具缺失 fail-loud/误报豁免
全豁免-部分豁免-无匹配/argv 展开含空格路径/run_command shell=False），覆盖率 85%，
ruff 全绿；bash hook 语法校验通过；mcp_server 冒烟（verify_tdd 委托、status 收敛）通过。

## V3.2.10 插件效能改进（2026-08-18：heavyskill 插件评审 6/10 → 长驻桥）

对 hgf-tools 动态插件按评审 ROI 实施：

1. **长驻 stdio 桥**（最高 ROI）：`hgf_bridge.py --serve` 模式——stdio JSON-RPC
   循环（stdin 每行 `{id,command,args}` 请求，stdout 每行 `{id,ok,result|error}` 响应，
   单命令失败不退出进程）；插件懒启动一次、后续请求复用进程。
   **实测**：classify 418→37ms（11×）、assess_risk 1275→39ms（32×）、
   lifecycle 439→49ms（9×）。
2. **命令级超时**：`COMMAND_TIMEOUT` 表（execute_gates 30min，其余 15-30s），
   超时 `proc.terminate()` 进程树 + 下次请求自动重建。
3. **并发排队**：请求队列串行（单进程 stdin 天然串行）。
4. **结构化错误**：桥返回非法 JSON / 进程退出 / 超时 → 带命令名的可读错误。
5. **env fail-fast**：`HGF_BRIDGE`/`HGF_PYTHON` 缺失回退硬编码；spawn 失败抛错
   提示设置 env。

**沙箱教训（run-9）**：动态包沙箱**无 Node 定时器全局**（setTimeout 不可用），
必须 `inject: ['timer']` + `ctx.timeout(fn, ms)`（返回 disposer）。
subprocess 服务 spawn spec：`stdin:'pipe'` → `handle.stdin`（Writable）、
`stdout:'pipe'` → `handle.stdout`（Readable，`.on('data')` 流式读行）、
`terminate()` 树级终止（Windows taskkill /T）、`graceMs` 是终止宽限不是超时。

**回归基线**：+5 新测试（serve 协议：返回/未知命令存活/多命令复用/非法 JSON
不崩溃/中文往返）；全量 134+ tests、覆盖率≥85%、ruff 全绿。
重建插件后实测：hgf_assess_risk/hgf_history 经长驻桥正常返回。

## V3.2.11 全流程可信化四阶段（2026-08-18：heavyskill 全流程评审 3.5/10 → 四阶段）

对 HGF 从"项目全流程编程开发"角度评审（8 路独立子代理，共识 3.5/10）后的
四阶段改造。核心诊断：真实工具箱(7/10) + 纸面生命周期(0-1/10) 的缝合体。

**Phase 1 诚实化**（已实施）：
- 12 个文档 gate 换**语义校验器** `_check_document_semantic`：按准出类型强制
  结构条目组（架构=组件/数据流/信任边界/接口；威胁模型=STRIDE；接口=端点/请求/
  响应/schema；设计/安全需求/脱敏/部署/密钥轮换/监控各有模板），组内中英任一
  命中、组间全命中；长度≥300 仅拒空壳、**不作通过依据**。
- 测试分层：`_check_integration_tests` 真验 L2——需 `tests/integration/` 或
  `@pytest.mark.integration`，无集成测试即 FAIL（不再用单测冒充集成）。
- **DAG 接电**：`record_matrix_evidence` + `auto_advance`——矩阵 MUST_PASS 全绿
  → 通过的门禁映射为准出证据（static_analysis→static_analysis、unit_test→
  unit_test_passed 等）→ 纯矩阵 gate 自动推进（含评审/文档类不推进，保持诚实）；
  gate_executor 运行后自动调用。
- **迭代回路**：`--lifecycle reopen <gate>`（done→runnable + 级联下游 blocked +
  rework_count 计数 + 返工写 failure_log 根因）。
- pre-push hook 门禁后输出生命周期接电状态。

**Phase 2 权威化**（已实施）：
- 评审诚实化：review 记录带 `kind`（independent/self-check）；user_acceptance/
  review_checklist **拒绝 self-check**（被审对象不得自证通过）；`verify_fresh`
  生成无会话种子的独立二验请求（要求行级 findings 文件:行号 + VERDICT）。
- CI 合并阻断：`.github/workflows/hgf-gates.yml` 空变更跳过门禁（不再传
  `__no_change__`）；作为 PR required check 即阻断合并。
- 流程度量：`lifecycle.metrics()`——phase_time（各 Phase 完成跨度）、
  rework_count（累计返工）、escape_rate（Phase3+ 失败/全部失败）；
  CLI `--metrics`。

**Phase 3 规模化**（已实施）：
- 健康/监控准出真实探针：`_check_health` 支持 gate 配置 `probe_command`
  真跑、`scripts/probes/<type>.py` 探针脚本、--file 证据——**不再接受裸
  --confirm**；`check_exit_criteria` 的 confirm 必须附存在的证据文件。

**Phase 4 持续**（已实施）：
- 门禁健康报告 `run_history.gate_health()`：逐门禁 runs/failed/fail_rate/
  always_failed（从未通过=逃逸舱口，若被降级即"门禁损坏被降级而非修复"）；
  `--history` 显示警告，供人工校准。

**回归基线**：全量 160+ tests、覆盖率≥85%、ruff 全绿；DAG 冒烟
（advance→reopen 级联→返工记录）验证通过。

## DSH 接入实测要点（Windows，2026-08-17 验证）

- **沙箱不是"禁执行"，是"禁管道"**：workspace-write 模式下受限令牌只拦写入，
  但受限进程无法通过管道捕获孙进程输出（python/git 直接管道调用报 Access denied）。
  改用**文件重定向**（`cmd *> out.txt` 再读文件）即可执行外部程序；切换到
  danger-full-access 后管道恢复正常。
- **编码迁移 bug 已修复**（8 处）：
  ① 6 处 `open()` 缺 `encoding='utf-8'`（gate_executor / false_positive_checker /
  verification_engine / post_deploy_tools / scripts/measure_contract_coverage.py）；
  ② `gate_plugin._run_command` 的 `subprocess.run(text=True)` 走 GBK 解码工具输出
  （含中文路径的 JSON 会崩）→ 已改 `encoding="utf-8", errors="replace"`；
  ③ `workflow_cli.py`/`mcp_server.py` 硬编码 `/home/lff7767162/.hermes/workflow` 路径
  → 已改为相对本文件的路径。
- **扁平布局测试收集**：门禁插件用裸 `pytest` 命令（非 `python -m pytest`），
  测试目录需配 `pyproject.toml` 的 `[tool.pytest.ini_options] pythonpath = ["."]`，
  否则 `from calc import ...` 报 ModuleNotFoundError（见 workflow/demo_hgf/pyproject.toml）。
- **覆盖率统计**：驱动脚本（如 hgf_demo.py）不被测试导入会拉低总数，用
  `.coveragerc` 的 `[run] omit` 排除脚手架，勿调低 `--cov-fail-under` 门槛。
- **端到端 demo**：`workflow/demo_hgf/`（calc.py + tests/ + hgf_demo.py），
  跑 `python demo_hgf/hgf_demo.py`（需 PYTHONPATH=workflow）即可看到
  classify_task → assess_risk → execute_gates 三段真实输出与门禁报告。

## 关键纪律（hermes 实测沉淀）

- **不发明新流程名**：用户说 "HAF" 指的就是 HGF，禁止自创缩写/变体（P28）。
- **"文件存在 ≠ 它工作"**：每个 Gate 都要跑真实计算/流水线（P0，最常见失败）。
- **失败要记录**：首次运行失败 → 记录失败原因 → 分析根因 → 修复 → 同一标准复跑，
  禁止悄悄调参掩盖（如 DCF 偏差 160% 直接改增速假装没失败）。
- **多人评审**：用户要求评审时组 3 人组（执行者 + 第三方代码专家 + 架构专家），
  双专家同意才推进；评审是迭代的（2-4 轮），每条意见都是必改项。
- **HeavySkill 子代理读不了文件**：需要深度审查时把关键代码/接口内联进 query
  （见 `heavyskill` 技能）。
- **集成验证三层次**：文件存在 → 可导入 → 业务逻辑中真正调用（"90% 陷阱"：
  HAS_* 标志=True 只证明能导入，不证明已接入；用 `grep -c` 验证调用点）。

## 参考文档（工作区）

- 主技能：`skills/software-development/gate-driven-development/SKILL.md`
- 封装技能：`skills/workflow-gates/SKILL.md`（async 架构与缺陷）
- 代码：`workflow/`（gate_types / gate_executor / gate_plugins / risk_assessor /
  task_classifier / failure_handler / false_positive_checker / mcp_server /
  async_gate_manager / state_machine 等）+ `workflow/config/` 12 个 YAML 门禁配置
- 测试质量脚本：`skills/software-development/gate-driven-development/scripts/test_quality_metrics.py`
- Gate 插件模板：`skills/software-development/gate-driven-development/templates/gate-plugin-template.py`
