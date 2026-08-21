# Changelog

## 2026-08-21 — heavyskill 审查质量四路径增强（双模型 deepseek+mimo，按技术方案实施）

### 背景
P54 复审结论"能保证不残缺，不能保证结论必然正确"。按
`skills/heavyskill/references/enhancement-plan-dual-model.md` 实施四条增强路径补齐质量缺口。
实测 mimo-v2.5-pro（token-plan-cn.xiaomimimo.com）key 有效、OpenAI 兼容、与 deepseek-v4-pro
同为推理模型（截断治理机制对双模型通用）。

### 路径3：quality_score 落地 + 动态 K
- `utils.score_trajectory`（0-100 确定性规则：完整性 40 + 有效性 40 + 退化惩罚，truncated 归零）
- `memory_cache` 赋值 quality_score（替换恒 1.0 死字段）；`_select_max_answer_frequency`/
  `_select_max_diversity` 组内按质量分降序择优
- `utils.auto_k_for_query`（short/medium/long 分档）+ `ParallelReasoner.reason(k=)` 覆盖 +
  pipeline 首轮质量不足自动补跑（`k_extended` 输出）

### 路径4：审查包分批（split_pack + 元审议）
- `workflow/splitter.py`：章节边界（markdown 标题/def|class/分隔线）切分 + 500 字符重叠 +
  max_chunks 上限
- `workflow/chunked_review.py`：ChunkedReviewer——分块独立 pipeline → 分块结论聚合 →
  元审议（复用 SequentialDeliberator）

### 路径1：结论验证器（mimo 规则+LLM 混合）
- `workflow/validator.py`：规则校验（verdict_format/p0_consistency/coverage_complete）+
  mimo LLM 校验（逻辑矛盾/遗漏维度/过度自信，JSON 输出宽松解析）；fail-open 降级

### 路径2：异质模型独立二审（mimo）
- `workflow/second_review.py`：mimo 独立二审（不注入一审结论）→ 确定性仲裁（任一 FAIL
  取 FAIL/一致提升置信度/分歧标记人工复核）；fail-open

### 集成与配置
- HeavySkillConfig 新增 quality/validator/second_review 配置组；CLI `--auto-k`/
  `--enable-validator`/`--enable-second-review`/`--validator-api-key`；输出 JSON 新增
  `k_extended`/`validation`/`second_review` 字段；config.yaml 增配置段（密钥占位符）

### 验证
- 单测 18 → 33（质量分×3/auto_k×2/选择排序/splitter×4/规则验证×3/JSON 解析/二审仲裁×3）
- ruff 全绿（新代码零新增债）；HGF CLI 9 门禁全部 MUST_PASS（exit=0）
- **真实双模型端到端（105s）**：deepseek-chat 主链路 truncation 全 0；
  mimo validator 抓到 2 个真实 P1 issue（"测试用例指数增长判断缺乏严谨性"/
  "首因效应分析遗漏自我修正维度"）+ 维度覆盖 warning；mimo 独立二审给出更严格裁决、
  仲裁安全优先生效——异质校验价值实证

## 2026-08-21 — heavyskill P54 复审修复（R1-R7，HGF 裁决 FAIL → PASS_WITH_WARNING）

### 背景
对 P54 截断修复做 HGF 审查（门禁 + heavyskill 模式1 K=4 深度审查），裁决 FAIL：
三条 P1（CLI 标志名断裂/冒号守卫误杀标准格式/审议截断无防垃圾保护）+ 九项 P2 共识。
审查档案：`docs/lessons/2026-08-21-heavyskill-p54-hgf-review.md`。

### 修复（skills/heavyskill）
- R1：argparse 双拼写注册短横线别名（`--max-tokens`/`--summary-max-tokens` + 兼容下划线），
  统一告警文案/SKILL.md/文档
- R2：extract_answer 冒号守卫改**净化而非拒绝**（`"答案是：42"` → `"42"`）；垃圾防护
  收敛到 pipeline 层 content_fallback
- R3：审议截断强制回退共识（残稿结论不采信）；previous_deliberation 不回填截断残稿
- R4：config 加载抽 `build_config()` 纯函数，全键 `CLI > config.yaml > 默认` 三级解析
  （修 temperature/language 等 `or` 短路不生效）
- R5：新增 `--accept-partial`（截断且无答案 exit 2）；has_truncation 纳入思维链回退；
  早退判定统一 cache 有效集；successful_count 排除截断；DeliberationRecord 补 truncated
- R6：清 6 项新 ruff 债（SIM103/I001/UP006×2/UP045×2）+ skills/heavyskill scoped ruff
  配置（存量基线化，tests/ 不豁免）——static_analysis 门禁从 182 项 FAIL 转绿
- R7：单测 9 → 18（冒号格式/审议回退/build_config×4/全截断端到端/truncated∩fallback/
  has_truncation 含 fallback）

### 门禁复审（HGF CLI --execute）
- 9 门禁：8 通过 + 1 环境跳过（safety SHOULD_PASS），**全部 MUST_PASS 通过**（exit=0）；
  ruff 全绿 / pytest 18 passed（覆盖 64%）/ semgrep 0 / detect-secrets 0 / format 通过
- 附带修复：`.hgf/failures.jsonl` 1 条历史不完整记录按 V3.3.2 S1 归档
  （`--failures --archive`），解除 failure_log 门禁自锁

### 文档
- 新审查档案 `docs/lessons/2026-08-21-heavyskill-p54-hgf-review.md` + README 索引
  + pitfalls-summary.json lessons 登记
- `.agents/skills/heavyskill/SKILL.md`：`--accept-partial`/审议回退/exit 2 行为说明

## 2026-08-21 — heavyskill 模式2 截断治理（P54，技能代码修复，非 HGF 版本变更）

### 背景
HGF 工作流会话多次出现"heavyskill 模式2 读取审查结果被截断"。实测
`output/hgf-productivity-review-result.json`：deliberation 停在"主要分歧 - Attempt 2"、
traj[3]/traj[4] 断在句中、consensus_answer 为思维链垃圾碎片。根因：
`max_tokens` 默认 4096 且 config.yaml 预算从未被 CLI 加载（配置断裂）→ 推理模型
思维链占满预算硬截断；`finish_reason` 从不检查 → 截断静默流入审议/共识；
content 空回退思维链 + extract_answer 抓碎片 → 共识失真。

### 修复（skills/heavyskill）
- 预算配置打通：`run_heavyskill.py` 从 config.yaml 加载 `max_tokens`(32768)/
  `summary_max_tokens`(16384，新增字段与 `--summary-max-tokens` CLI)；审议用独立预算
- finish_reason 显性化：LLMResponse/ReasoningResult/DeliberationResult 带 `truncated`/
  `content_fallback` 标记；截断轨迹自动剔除出审议与共识；思维链不投票
- 输出 JSON 新增 `truncation` 摘要字段；控制台截断 ⚠️ 告警
- `extract_answer` 加固：截断残稿（无终止符）不走末行回退、答案标记大小写不敏感、
  正则停止符补 `\n`（修"答案行后无句号即整段吞入"）
- 单测 `skills/heavyskill/tests/test_truncation.py`：9 项防回归

### 文档
- 新增 P54（pitfalls-registry.md + pitfalls-summary.json gated 列表）
- 新档案 `docs/lessons/2026-08-21-heavyskill-mode2-truncation.md` + README 索引
- `.agents/skills/heavyskill/SKILL.md` 模式2 章节：截断治理说明 + 读取审查结果标准姿势
- `skills/heavyskill/SKILL.md`、references/heavyskill-review-workflow.md、
  gate-driven-development/references/heavyskill-integration.md 同步更新

## 3.3.3 (2026-08-21) — 记忆长效机制（V2 方案，P53 元门禁自律）

### 背景
HGF 自审查发现 3 个 P0（failure_log 自锁 / baseline 损坏 / requirements 伪文件），
修复后经 heavyskill K=8 深度审议（151.95s，8/8 轨迹），按共识实施 V2 记忆长效机制。

### 新增（L0 代码门禁）
- `_check_self_audit` 检查器（lifecycle_checkers.py）：4 项机械验证——
  failures.jsonl 无 failure_log 自锁记录（S1 防回归，source 隔离自身记录）、
  baseline.json 可解析（S2）、requirements 用 packaging.Requirement 解析（S3，
  允许 -r/注释/环境标记）、lessons 索引完整性（L2 配套）
- `gate_5_3`「元门禁自律（P53）」：**独立门禁**（depends_on: []，不依赖被查对象）
- `tests/test_self_audit.py`：8 个防回归测试（含 self_audit 失败不写日志、索引校验）
- pre-push hook 追加 gate_5_3 检查 + `.github/workflows/hgf-gates.yml` 新增 self-audit job

### 新增（L1 自动加载）
- `AGENTS.md`（工作区根）：HGF 记忆继承协议，dsh-agent-instructions 自动注入每会话
- `docs/pitfalls-summary.json`：机器可读经验索引（省 token）

### 新增（L2 档案库）
- `docs/lessons/`：经验档案库 + README 索引（self_audit 第 4 项强制索引完整性）
- `docs/lessons/2026-08-21-self-audit.md`：本次 3 个 P0 根因完整记录

### 新增（L3 自检）
- `scripts/self_check.py`：三问自检（Q1 未提交改动 / Q2 gate_5_3 done / Q3 记录同步，
  git 内容对比防 touch 伪造），四触发点（pre-push/CI/会话收尾/schedule 可选）

### 文档
- P 库注册 P53「元门禁自律」
- README P 库对照表 + 工具链依赖说明更新

## 3.2.0 (2026-08-17) — HGF 演进路线图全量实施

### 阶段 0：止血与可复现
- 死代码归档：9 个未接线模块移入 `_legacy/`（含复活条件说明）；`__init__.py` 不再 re-export
- 版本号归一：`__version__ = "3.2.0"`，CLI `--version`，YAML 头部同步
- 补齐文档引用的缺失产物：`templates/gate-plugin-template.py`、`scripts/test_quality_metrics.py`
- 门禁基线 `.hgf/baseline.json`：配置哈希 + 工具版本，每次执行检测漂移并告警
- 离线提速注释：safety/semgrep 首次下载说明

### 阶段 1：让门禁可信
- **假通过防线（fail-loud）**：`GateResult.parse_error` + `GatePlugin._safe_parse`；
  detect-secrets/semgrep/safety/checkov 解析失败 → ERROR 拒绝判定（checkov 假通过普适化修复）
- **重试/升级接线**：failure_handler 接入 GateExecutor（超时/网络/限流指数退避重试、
  连续失败升级"通知负责人/冻结流程"）
- **运行历史**：`.hgf/runs.jsonl` + CLI `--history`（通过率、反复失败门禁）

### 阶段 2：生命周期真接线
- `lifecycle.py`：gates.yaml（16 gate Phase 0-5）变成可执行 DAG 状态机
  （准入=依赖完成，准出=检查器真实执行，状态存 `.hgf/lifecycle.json`）
- 准出条件检查器：文档（内容≥100 字符，拒空壳）、评审记录、pytest/ruff 真实执行、
  健康检查、`--confirm` 人工兜底
- L2-L5 证据机制：`GateConfig.evidence`，声明高级别验证必须有证据文件

### 阶段 3：生态与工程化
- CI：`.github/workflows/hgf-gates.yml`（PR/推送对变更文件跑完整 HGF，退出码即结果）
- 生态门禁：format-check（ruff format）、pin-check（依赖固定）、docs-check（README 章节）
- 文档治理：`workflow/README.md`（模块地图 + 12 YAML 职责表 + P 库门禁化对照）

### 工程修复
- ruff 规则集固定（pyproject [tool.ruff.lint]），消除随版本漂移
- 全库迁移残留扫描：3 处硬编码路径修复

### 测试
- 测试套件 90+ 个，核心覆盖率 ≥84%
- L2 狗粮化（HGF 检查 HGF）：8/8 门禁全绿
