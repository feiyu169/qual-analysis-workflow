# HGF 项目记录（会话持久化存档）

> 本文件是 HGF（Hermes Gate Flow）在 DSH 中全部工作的持久化记录，供下次会话恢复上下文。
> 最后更新：2026-08-21（HGF V3.3.3 记忆长效机制落地——P53 元门禁自律 + 四层记忆架构，已推送 hermes-gate-flow）

---

## 一、项目全貌

HGF 是门禁驱动开发工作流，部署于 DSH（Cordis 插件宿主）。代码在：
`D:\OneDrive\文档\deepseek harness workspace\workflow\`

**版本**：`workflow/__init__.py` = **3.3.2**（V3.3.1 + 自审查收敛修复 S1/S2/S3 + M1/M2/M4 + L1/L2/L3）

**git 仓库**：`workflow/` **无独立 .git**，是工作区根仓库
`D:\OneDrive\文档\deepseek harness workspace`（remote: `git@github.com:feiyu169/qual-analysis-workflow.git`）的子目录。
`git log -- workflow/` 仅 4 个提交（c616aaf 基线导入/fcbf7ca/2498634/99a2445，早期历史被压扁）。
**HGF 专属远程仓库**：`git@github.com:feiyu169/hermes-gate-flow.git`（master = a89ae74，V3.3.2 完整内容 90 文件，2026-08-21 快进追加推送，6 提交含 TDD 顺序）。

---

## 二、版本演进史（按时间顺序）

| 版本 | 内容 | commit |
|------|------|--------|
| V3.2 基线 | 门禁引擎/纪律门禁/生命周期/插件桥（106 测试） | `6ef38be` |
| V3.2.8 收尾 | 金丝雀(canary.py) | `6e8e999` |
| V3.2.8 收尾 | CI 演练(ci_simulate.sh) + pre-push hook | `b26671b` |
| V3.2.8 收尾 | tdd_evidence 真检查器（git 历史） | `07006b9` |
| V3.2.8 收尾 | 评审工具链(review.py 审查包+双签名) | `782d1d0` |
| V3.2.8-A | 失败记录"已解决"口径（re_run_result 非空=已解决，CLI --failures） | `8c3fbd0` |
| V3.2.9 | 架构评审修复：安全准出真跑(A/J)+verify_tdd强实现(B)+误报接线(C)+路径/argv/hook卫生(D/F/G)+版本观测收敛(E/H/I) | `ed7766e` |
| V3.2.10 | 插件效能：hgf_bridge --serve 长驻桥（11-32× 提速）+命令级超时+排队+结构化错误+env fail-fast | `c0716b7` |
| V3.2.11 P1 | 诚实化：文档语义校验器+integration真验L2+DAG接电(auto_advance)+reopen回路 | `d2f4e86` |
| V3.2.11 P2-4 | 权威化+规模化+持续：评审kind语义+流程度量+健康探针+门禁健康报告 | `e1a2730` |
| V3.2.11 待办 | 版本号 3.2.11 + 集成测试套件 + 狗粮化修复(shell参数数组/零依赖直通) + user_acceptance 人工通道 | `db2a548`/`024d1f5`/`72d361f` |
| **V3.3.0** | **架构重构（架构专家评审 6.8/10 的 R1-R4）**：原子写入(state_io) + 统一检查器(tool_runner) + lifecycle 拆分(dag/checkers/metrics) + 矩阵-生命周期解耦(注入回调) | `3dc9c3c` |
| **V3.3.1** | **架构复审修复（复审共识 7.6/10 的建议 1-4）**：_run_command 委托 tool_runner + mcp_server.check_security 改走 tool_runner + 删 gate_results 死表 + atomic_append_jsonl 诚实化(fsync) + re-export 收敛(__all__) + reopen 异常改 warning | `00faa14` |
| **V3.3.1 狗粮化** | **3 项待办完成 + 16/16 gate 全流程端到端跑通**：heavyskill 模式2 恢复（.env 已有 key + K=1 冒烟通过）+ .github 已同步 + checkov 无 IaC 直通增强 | `99a2445`（hermes-gate-flow master） |
| **V3.3.2** | **HGF 自审查收敛修复**（报告 output/hgf-self-audit-report.md）：S1 failure_log 失败雪崩自锁（自身失败不入日志 + `--failures --archive` 归档 201 条历史脏数据）+ S2 baseline.json 损坏容错（load 返回 None + canary 自动重建）+ S3 requirements-hgf.txt 改真 pip 文件 + M1 README 补语义条目 + M2 版本收敛 3.3.2 + M4 dependency_scan 注释诚实化 + L1/L2/L3 状态补全（STATE.md/lifecycle.json/reviews.jsonl） | `a89ae74`（hermes-gate-flow master，2026-08-21 推送） |
| **V3.3.3** | **记忆长效机制（V2 方案，P53 元门禁自律）**：heavyskill K=8 审议后实施——L0 `_check_self_audit` 检查器 4 项验证 + gate_5_3 独立门禁 + 8 防回归测试 + pre-push/CI self-audit job；L1 AGENTS.md 记忆继承协议（dsh-agent-instructions 自动加载）；L2 docs/lessons/ 档案库 + 索引校验 + pitfalls-summary.json；L3 scripts/self_check.py 三问自检。**203 测试全绿 + L2 门禁 success=True** | `d62b875`（hermes-gate-flow master，2026-08-21 推送） |

### V3.3.0 架构重构明细（2026-08-18，架构专家 8 轨迹评审后实施）

| 项 | 内容 | 效果 |
|----|------|------|
| R1 原子写入 | state_io.py（write-temp+os.replace）；hgf_state/baseline/lifecycle/review/record_matrix_evidence 全接入；update_failure 消除"先删后写" | 崩溃不丢数据 |
| R2 统一检查器 | tool_runner.py（safe_run argv+shell=False/split_command）；_check_tool_scan/_check_static/_check_health 改走它 | 消除 shell=True 遗留 + 双重执行路径 |
| R3 拆分 lifecycle | lifecycle_dag(176行)+lifecycle_checkers(634行)+lifecycle_metrics(189行)+lifecycle re-export 壳 | 970 行上帝模块 → 单一职责 |
| R4 矩阵解耦 | gate_executor 加 matrix_evidence_callback 注入（默认 None）；CLI/bridge/mcp 注入回调 | 消除执行层↔生命周期双向耦合 |

**验证**：188 tests / 86% cov / ruff 全绿 / 净减 786 行 / 狗粮化状态完好（gate_3_1 done）

---

## 二·五、GitHub 远程仓库状态（2026-08-21）

| 仓库 | remote | 状态 |
|------|--------|------|
| **hermes-gate-flow**（HGF 专属） | `git@github.com:feiyu169/hermes-gate-flow.git` | master=`a89ae74`（V3.3.2 完整内容，90 文件）；2026-08-21 快进追加推送（99a2445→a89ae74，非 force）；浅克隆验证 __version__="3.3.2"、requirements 真 pip 文件、关键模块齐全 |
| qual-analysis-workflow（工作区根） | `git@github.com:feiyu169/qual-analysis-workflow.git` | 根仓库 remote，workflow/ 无独立 .git |

**SSH 配置**（2026-08-21 完成，免 -i 直接可用）：
- `~/.ssh/id_ed25519`（复制自工作区根 `id_ed25519`，411B）+ `~/.ssh/id_ed25519.pub`（生成）
- `~/.ssh/config`：`Host github.com` → `IdentityFile ~/.ssh/id_ed25519` + `IdentitiesOnly yes`
- 验证：`ssh -T git@github.com` → "Hi feiyu169! You've successfully authenticated"；`git ls-remote` 免 -i 成功

**推送命令备忘**（本地 hgf-export 分支 = workflow/ 的 subtree split，当前 6 提交）：
```powershell
# 导出最新 workflow/ 到 hgf-export（续接历史）
git subtree split --prefix=workflow --branch=hgf-export
# 推送（V3.3.1 首次用 --force 替换旧存档；V3.3.2 起为快进追加，无需 --force）
git push git@github.com:feiyu169/hermes-gate-flow.git hgf-export:master
```

---

## 三、当前运行状态（会话级，DSH 重启即失）

**动态插件**（重启后需从 `workflow/plugin/` 源码重建，idPrefix 会变）：

| 插件 | 源码 | 平台 | 用途 | 重建 |
|------|------|------|------|------|
| hgf-tools | `workflow/plugin/hgf-tools.js` | Host | 5 个 HGF 原生工具（长驻 stdio 桥 V3.2.10） | define(kind new, idPrefix hgf) + run |
| codex-sidebar | `workflow/plugin/codex-sidebar.js` | Client | 仿 Codex 左侧边栏 | define(kind new, idPrefix cdx) + run（需浏览器批准） |
| ~~codex-workspace~~ | `workflow/plugin/codex-workspace*.js` | Host+Client | 右侧工作台（**已按用户要求删除**，源码保留备查） | — |

**重建要点**：
- hgf-tools.js 有 `inject: ['timer']`（沙箱无 setTimeout，超时用 ctx.timeout）
- BRIDGE 路径硬编码回退：`D:\OneDrive\文档\deepseek harness workspace\workflow\hgf_bridge.py`（env HGF_BRIDGE/HGF_PYTHON 优先）
- Client 插件 cordis_run 返回 awaiting-approval 是正常流程

**可用工具注意**：heavyskill 原生工具在最近一次 DSH 重启后**不可用**（工具集变化），但 `heavyskill` 技能仍在（模式1=DSH 子代理 K 路并行审议，模式2=Python 流水线需 DEEPSEEK_API_KEY + venv，当前两者均不可用——模式1 子代理是可用路径）。

---

## 四、关键架构事实（下次会话免重复梳理）

### 门禁矩阵（config/mcp-gates.yaml）
- MUST_PASS：static_analysis(ruff)/unit_test(pytest ≥80%)/secret_scan(detect-secrets)/test_quality(AST拒空桩)/failure_log
- SHOULD_PASS：security_scan(semgrep)/dependency_scan(safety，环境限制降级)/integration_probe
- OPTIONAL：performance_test/iac_scan(checkov)/format_check/docs_check/pin_check
- 等级：L0-L3/L3_LITE/IAC/CONFIG/DOCS

### 生命周期（config/gates.yaml，16 gate Phase 0-5）
- V3.2.11 后：文档类 gate 用 `_check_document_semantic`（9 类结构模板，长度不作通过依据）
- integration_test_passed → `_check_integration_tests`（需 tests/integration/ 或 @pytest.mark.integration）
- 安全类真跑：sast→semgrep、dependency→safety、iac→checkov、dast→需外部报告
- 健康/监控 → `_check_health`（probe_command/scripts/probes/<type>.py/--file；**裸 --confirm 已禁止**）
- 评审类 → `_check_review`（双签名 + kind 语义，user_acceptance 拒绝 self-check）
- DAG 接电：`record_matrix_evidence` + `auto_advance`（矩阵全绿自动推进纯矩阵 gate）
- 迭代回路：`--lifecycle reopen <gate>`（级联下游 + 返工计数 + 写 failure_log）

### 其他机制
- 失败纪律：failures.jsonl 必须 root_cause/fix，否则 failure_log 门禁 FAIL；re_run_result 非空=已解决
- 金丝雀：canary.py（工具版本漂移→轻量回归集）；CI：ci_simulate.sh + .github/workflows/hgf-gates.yml
- 度量：`--metrics`（phase_time/rework_count/escape_rate）、`--history` 门禁健康报告（always_failed 逃逸舱口）
- 评审工具链：`--review-build`/`--review-record --kind`/`--review-fresh`

### 环境（Windows，系统 Python 3.14）
- Python：`C:\Users\79902\AppData\Local\Programs\Python\Python314\python.exe`
- PYTHONPATH=workflow；测试：`python -m pytest tests\ -q --cov=. --cov-config=.coveragerc`
- 工具：ruff 0.16.3/pytest 9.1.1/pytest-cov 7.1.0/detect-secrets 1.5.0/safety 3.8.1(SAFETY_API_KEY)/semgrep 1.173.0/checkov 3.3.11/PyYAML 6.0.3/structlog 26.1.0
- pip 镜像：https://pypi.tuna.tsinghua.edu.cn/simple
- Git Bash：`C:\Program Files\Git\bin\bash.exe`（bash 脚本用）
- 会话权限：danger-full-access（不请求沙箱升级）
- 测试基线：**195 passed / 覆盖率 87% / ruff+format 全绿**（2026-08-21 V3.3.2 自审查修复后）

---

## 五、用户决策记录（不可违背）

1. **不修补**系统 Python 的 51 个已知漏洞（output/security-remediation.md，待决策）
2. 跳过 HGF 意见 #5（fast/deep 模式）
3. 保留左侧 Codex 侧边栏；**删除**右侧工作台（wkp-4）
4. heavyskill 作为评审引擎（内容必须内联，子代理读不了本地文件）
5. 评审后修复方案选择：架构评审→全修(A)；插件评审→按 ROI 全修；全流程评审→四阶段全实施(A)
6. 之前"6 项待处理"误报→采用方案 A（re_run_result 非空=已解决）

---

## 六、已完成的评审记录

1. **架构评审**（heavyskill，6.5/10）→ V3.2.9 修复（安全准出名不副实等 A-J）
2. **插件效能评审**（heavyskill，6/10）→ V3.2.10 修复（长驻桥等）
3. **全流程评审**（heavyskill 模式1 K=8 子代理，共识 3.5/10）→ V3.2.11 四阶段
   - 核心诊断：真实工具箱(7/10) + 纸面生命周期(0-1/10)
   - 8 条轨迹独立发现：准入无检查器/max_retries 未实现/confirm 死代码/集成探针空转/safety 从未判定/覆盖率未接线/--no-verify 绕过

---

## 七、待办/下次会话候选任务（2026-08-21 更新：全部完成）

原 7 项待办核查后状态：
1. ✅ 补真实集成测试套件（tests/integration/ 两处已建，_check_integration_tests 真实通过）
2. ✅ 版本号同步（当前 3.3.1）
3. ✅ **.github workflow 同步**（2026-08-21 确认：工作区根已是 git 仓库，HEAD 已含"空变更跳过"——无需处理）
4. ✅ 语义模板真实文档验证（狗粮化 gate_1_1 STRIDE 文档实证）
5. ✅ user_acceptance 人工通道（_check_review 含人工验收证据，狗粮化 gate_3_3 实际通过）
6. ✅ **heavyskill 模式2 恢复**（2026-08-21：httpx 0.28.1 已装于系统 Python；DEEPSEEK_API_KEY 在 config/.env 长度 35；K=1 冒烟 20.5s/1047 tokens 通过。**用法**：从 .env 读 key → `python skills/heavyskill/scripts/run_heavyskill.py --query "..." --reason_k 8 --summary_k 4 --api_key $key`）
7. ✅ **HGF 狗粮化验收**（2026-08-21：**16/16 gate 全部 done，Phase 0-5 端到端真实跑通**）
8. ✅ **HGF 推送 GitHub + SSH 配置**（2026-08-21：SSH 私钥配置到 ~/.ssh 免 -i 验证通过；workflow V3.3.1 以 hgf-export 子树 force push 至 hermes-gate-flow master=`99a2445`；**V3.3.2 修复后 2026-08-21 再推送 master=`a89ae74`（快进追加，TDD 顺序 test→feat→docs 三提交 17a7c42/499b9cd/8c16d28）**，浅克隆验证 90 文件完整）

### 狗粮化 16 gate 全流程里程碑（2026-08-21）
- `.hgf-dogfood/`（gitignore）demo 项目从 gate_0_1 推进至 gate_5_2 **全部 done**
- Phase 3-5 实测：gate_3_2(DAST外部报告) → gate_3_3(user_acceptance 人工通道) →
  gate_4_1(部署+密钥轮换语义+checkov无IaC直通) → gate_4_2(健康探针真跑) →
  gate_4_3(监控语义) → gate_5_1(监控探针真跑，曾拦截38.5%错误率→清理测试残留后通过) →
  gate_5_2(反馈评审)
- metrics 实测：Phase 3 跨度 71.36h（真实时间）、返工 0、逃逸 0
- **本轮引擎增强**：`_check_checkov` 无 IaC 资产直通（同 dependency 零依赖逻辑）+ 2 测试

### 剩余可选（非待办）
- 用 heavyskill 模式2 跑一次完整 K=8 评审（验证流水线全规模可用）
- 把狗粮化推进过程沉淀为 hgf 技能的教学示例

---

## 八、常见操作速查

```powershell
# 全量测试
$env:PYTHONPATH = "D:\OneDrive\文档\deepseek harness workspace\workflow"
cd "D:\OneDrive\文档\deepseek harness workspace\workflow"
& "C:\Users\79902\AppData\Local\Programs\Python\Python314\python.exe" -m pytest tests\ -q --cov=. --cov-config=.coveragerc

# 生命周期状态/推进/重开
& $py workflow_cli.py --lifecycle status --dir .
& $py workflow_cli.py --lifecycle advance --gate gate_0_1 --file docs/gate_0_1.md --dir .
& $py workflow_cli.py --lifecycle reopen --gate gate_0_1 --notes "原因" --dir .

# 度量/历史/门禁健康
& $py workflow_cli.py --metrics --dir .
& $py workflow_cli.py --history --dir .

# 重建插件（DSH 重启后）
# 1. cordis_define: kind new, idPrefix hgf/cdx, code.host/client = plugin/*.js 的 return {...} 体
# 2. cordis_run: mode run
```

---

## 九、V3.2.11 待办完成记录（2026-08-18，commit db2a548 / 024d1f5 / +）

### 待办 1：真实集成测试套件 ✅
- `workflow/tests/integration/test_hgf_chain.py`：4 个快速跨模块链路
  （classify/assess 协作、矩阵证据接电、失败纪律全循环、套件可收集）
- `demo_hgf/tests/integration/test_cart_flow.py`：3 个业务集成测试
  （购物车结算流、业务不变量、非法输入）标记 @pytest.mark.integration
- 效果：`_check_integration_tests` 在 workflow 目录真实通过（L2 准出有证据）

### 待办 2：版本号同步 ✅
- `__init__.py` / `config/workflow.yaml`：3.2.9 → 3.2.11

### 待办 3：狗粮化验收 ✅（Phase 0→3.1 真实跑通 9/16 gate）
- 在 `workflow/.hgf-dogfood/`（已 gitignore）建 demo 项目（日志模块）
- 全流程实测：gate_0_1(需求)→0_2(安全需求)→0_3(需求评审)→1_1(架构+STRIDE)
  →1_2(接口)→1_3(详细设计)→2_1(代码实现 TDD，tdd_evidence git 历史验证通过)
  →2_2(代码审查)→3_1(集成测试+脱敏) 全部 done
- **验收发现并修复 3 个引擎 bug**：
  1. `_check_unit_tests`/`_check_integration_tests` 的 shell=True 命令引号被拆
     → 参数数组 + shell=False（"no tests ran" 问题）
  2. `_check_dependency`：零第三方依赖项目直接通过（无扫描目标客观事实），
     有依赖才跑 safety；safety 超时 300→120s
  3. 语义校验器正确拦截缺 STRIDE 的架构文档（gate_1_1 首次被拒，补 STRIDE 后过）
- metrics 实测：Phase 0 跨度 0.0h、Phase 1 跨度 0.01h、返工 0、逃逸率 0.0

### 待办 4：user_acceptance 人工通道 ✅
- `_check_review`：user_acceptance 需独立评审记录 **+ 人工验收证据文件**
  （docs/user_acceptance.md 含"验收"≥100 字符或 --file）——agent 不得仅凭
  双签名记录通过验收
- 测试：无证据拒绝 / 有证据通过

### 遗留（下次会话可选）
- ~~dogfood 继续推进 Phase 3.2-5~~ ✅ 已完成（16/16 gate，见第七节）
- ~~把狗粮化推进过程沉淀为 hgf 技能的教学示例~~ ✅ 已完成（SKILL.md「教学实例」段，commit f757802）


---

## 2026-08-21 qual 三阶段收官（FiscalSemantics 架构方案）

- **阶段 A/B/C 全部完成**（三阶段路线图 v2.1 实施落地）
- 最终验收重跑：Gate0-3 全过，耗时 -35%（6449→4197s，无墙钟耗尽）
- **FiscalSemantics**（docs/qual-fiscal-semantics.md）：财年语义单源化——DataAnchor 归因（L1）/ 跨章归因分桶（L2）/ 生成时校验（L3）
- 最小测试案例：合并重复 + 端到端 Gate4 场景 0.09s 验证（test_fiscal_semantics.py）
- 测试 63 passed；HGF 各批终检 exit=0；推送 0fc2d81 + 9feb499

---

## 2026-08-22 qual ADVC + HGF 深检修复 + 双专家/HeavySkill 评审（本会话，master=2026-08-22 b5596cd）

> 本会话完成四大块：ADVC P1/P2 → HGF 全面深检（P0-P2 修复）→ 遗留项处理 → 双专家+HeavySkill 评审。下会话恢复从此段开始。

### 一、ADVC（锚点驱动数值修复）——数值错位根治（commit 9174e3f, 02510dd, d950fa0）

**问题**：LLM 把总资产 1031.63 亿写成 31.63 亿（33 倍错位），Gate4 拦截但修复循环 LLM 反复产错。

**方案**（docs/qual-numeric-repair-blueprint.md 双专家蓝图 + docs/qual-anchor-repair-architecture.md）：
- 层0 `normalize_values.anchor_deviation`：×10ⁿ/÷10ⁿ/prefix_drop/digit_typo 签名检测（2 位小数口径）
- 层1 `qual_v8/anchor_repair.py`：T1 高置信自动替换（**自证=替换后整章 validate_chapter_any_fy 必须通过，否则全量回滚**）/ T2 低置信开关（enable_t2 默认关）/ T3 只标注不喂 LLM + hints 通道（digit_typo 弱提示）
- 层2 三处接线：`_generate_chapter` 清洗层（T3→omit 指令"省略该数值"）+ `_repair_chapters` 轮首 sweep（值类问题不进 LLM prompt）+ Gate8 组装闸门救援 sweep
- 测试：test_anchor_deviation(8) / test_anchor_repair(8) / test_advc_wiring(2) / test_advc_golden(15 黄金回归集)
- 另修：test_v31_p0a 裸模块属性赋值跨文件泄漏（monkeypatch 化）——污染根因

### 二、HGF 全面深度检查 + P0-P2 修复（commit 538d462, 8ab3f27；报告 docs/qual-hgf-deep-check-2026-08-22.md）

**检查发现（均经运行时探针实锤）**：
- **P0-① 27 个测试文件 collection 错误**：测试用 `finance.quality.v3.X` 导入，模块已平铺到 quality/ 根，v3/__init__.py 空 shim
- **P0-② ModuleLoader 2/4 必需模块加载失败**：MODULE_CONFIG 引用幽灵模块（gate_checks 无实现、review_integrator 路径缺失）→ 主流程启动自检报错
- P1：WorkflowIntegration 空转（17 个 v3 导入全失败）；6 个真空桩测试
- P2：ruff 默认规则集噪声；21 文件 hermes 路径硬编码

**修复**：
- 20 个 v3 shim（`quality/v3/*.py` re-export）+ quality/__init__.py 顶层 27 符号 re-export（DegradationLevel 从 types 导出，修复两枚举冲突）+ 7 个模块 17 处相对导入修复（`..X`→`.X`）+ 测试路径契约对齐（hermes_tools.finance→finance、quality→finance.quality）
- 契约判定三态：一致→接入聚合；本地真实缺陷→修复（capm 补 CAPMConfig/calculate_ke/beta/alpha/formula/mrp）；hermes 版 API 未随迁→显式 skip 标注（downloaders 3 类、config_validator 整文件等）
- ModuleLoader 候选路径指向平铺真实模块，gate_checks 降级非必需
- **结果**：`pytest tools/finance` 从 27 不可收集 → **406 passed + 32 skipped，0 失败**；HGF 聚合入口 `pytest tests/` 88 → **248 passed + 17 skipped**（654 为含 tests/ 合并跑口径，实测单跑 tools/finance=438）。**2026-08-22 P0/P1 修复后**：单跑 **416 passed + 32 skipped（448）**，聚合 `pytest tests/` 同步增加

**遗留项处理**（8ab3f27）：
- filing_service 断裂修复：filing_downloader 补模块级 list_filings；移除 get_downloader 死导入；download_with_cache 改走真实 downloader
- 6 个纯死代码归档 quality/_legacy/（data_mapping/gate0_reviewer/gate_dependency/gate_regression/management_incentive/params_checker）+ README（复活条件）；peer_comparison 等 3 个误判修正保留
- lint 清理：ruff --fix 4192 处 + W293 全清 + pyproject.toml（规则集对齐 HGF，忽略 RUF001-003 中文标点/S101 assert/E402/S310）→ **4993 → 435**（剩余 E501/PERF/B007/FBT/F841 历史债务）

### 三、双专家全面检查 + HeavySkill K=8 评审（commit b5596cd）

**评审链路**：代码专家（6.5/10）→ 投资专家（6.0/10）→ HeavySkill K=8 多轨迹审议（**5.5/10**，交叉验证并纠错）

**产物**（全部已推送）：
- docs/qual-expert-review-code-2026-08-22.md（代码专家完整报告）
- docs/qual-expert-review-investment-2026-08-22.md（投资专家完整报告）
- docs/qual-expert-heavyskill-review-2026-08-22.md（三方综合 + 最终修复清单）
- heavyskill-qual-review.json（K=8 原始轨迹 + 审议，无截断）

**最终修复清单（三方合并，下会话实施起点）**：
- **P0 必须修 7 项**：
  1. 估值链口径系列：毛利率=营业利润率（wind_field_disposition.py:26-35，亏损公司报负毛利率）；净负债=总负债+×0.3（workflow.py:2253-2265，净现金股目标价低 20-40%）；β=1.2 硬编码（workflow.py:2235-2239）；可比公司写死含迪士尼（valuation_engine.py:100-112）
  2. **review_incomplete 静默通过**：review_repair_loop.py:213-221 passed 分支不检查 review_incomplete，Gate4 只取 passed（gate4.py:296）→ 审查不完整却绿灯。修复：passed 分支加 `not review_incomplete`
  3. **T9-T14 硬编码阅文值覆写 facts**：workflow.py:2883-2948（非阅文公司算错值）。修复：删除或从 ctx.wind 取真实值
- **P1 应当修 6 项**：ADVC 误改子公司数据（data_anchor.py:249-269 语境排除表加限定词）；fact_extractor 财务填充不感知 fiscal_year（fact_extractor.py:778-786 R1）；评级一致性检查空转（gate5 无 dcf_value→gate6 静默跳过）；legacy 路径 review loop 无 budget/deadline（workflow.py:3050-3057）；pct/运营字段无锚点（R4/R5）；流程防护弱化（默认 shadow 只审不修 qual_v8/workflow.py:253 / 人工确认默认 True gate8.py:297 / 质量标注 HTML 注释不可见 workflow.py:447-452 / 红队 fail-open gate8.py:511）
- **P2 可选 6 项**：架构收敛（三路径→v8 + 拆 3282 行 + 清死代码）；32 SKIP 测试迁移；"Wind 验 Wind"退化（gate1.py:275-303）；汇率 0.92 配置化（base_valuation.py:107）；SOTP 接入；财年校验异常被吞（data_anchor.py:468-469）

**多轮测试根治评估**（HeavySkill 修正）：
- ✅ 根治：数值错位（ADVC）、841.63 财年误报（FiscalSemantics）、ModuleLoader、测试污染、外部抖动
- ⚠️ 部分根治：死循环（legacy 路径无预算/墙钟保护）；测试断裂（32 SKIP 未迁移）

### 四、下会话恢复要点（快速上手）

1. **当前状态**：master = b5596cd（2026-08-22）；工作区干净；测试 406+32（tools/finance 单跑）/ 248+17（tests/ 聚合）
2. **优先任务**：按最终修复清单 P0 7 项实施（估值链口径 → review_incomplete → T9-T14）
3. **关键文件地图**：workflow.py（3282 行 legacy 生成服务，被 v8 下沉复用）/ qual_v8/（编排层 Gate0-8）/ quality/（69 平铺 + 27 shim + 6 _legacy）/ docs/qual-*（44 篇）
4. **测试入口**：`pytest tests/`（HGF 聚合 248+17）/ `pytest tools/finance --ignore=tools/finance/.venv`（全量 406+32）
5. **lint**：`python -m ruff check tools/finance --exclude .venv --exclude _legacy`（435 处历史债务）
6. **heavyskill 模式2**：key 在 config/.env（DEEPSEEK_API_KEY）；`python skills/heavyskill/scripts/run_heavyskill.py --query "..." --reason_k 8 --summary_k 4 --api_key $key --accept-partial`
7. **推送**：SSH 用 `$env:GIT_SSH_COMMAND = "ssh -i '...id_ed25519' -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile='...ssh_known_hosts'"`

### 五、会话教训（沉淀）

- **"文件存在≠已接入"在测试体系同样成立**：27 个测试文件长期不可收集却被当作"测试全绿"——HGF 门禁 `pytest tests/` 只覆盖聚合文件，必须定期全目录收集验证
- **ruff --fix 全库会掩盖断裂代码**：filing_service 引用不存在的 get_downloader 被 F401 静默删除而非修复——自动清理前先确认引用完整性
- **子代理读不到本地文件**：双专家评审必须把架构事实/证据行号内联进 prompt，否则只能泛泛而谈（本次双专家产出高质报告依赖内联材料）
- **heavyskill 模式2 需 --accept-partial**：8 条轨迹有 3 条输出短答案（"TP 未接入"）污染共识投票，但 deliberation_response 是真实综合结论——读 JSON 的 deliberation 而非 consensus_answer
