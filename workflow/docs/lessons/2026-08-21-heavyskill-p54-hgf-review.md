# HGF 审查：heavyskill P54 截断修复（代码 + 架构）

> 档案：2026-08-21-heavyskill-p54-hgf-review.md | 关联 P54
> 审查方式：HGF 门禁真实执行（L2/CODE/low-risk）+ 基线对比 + 动态边界验证 +
> heavyskill 模式1 K=4 独立轨迹深度审查（内联 47KB diff，关键声称全部实证核验）
> 审查对象：提交 `4ecf9c5`（P54 截断治理，8 Python 文件 + config.yaml + 9 单测）
> 状态：**FAIL（待修复清单见下，复审后更新为已修复/带条件放行）**

---

## 一、门禁执行结果（真实运行）

| 门禁 | 级别 | 结果 | 证据 |
|---|---|---|---|
| static_analysis (ruff) | MUST_PASS | ❌ FAIL | 当前 182 项；**正确基线**：父提交 4602b31=176 → 4ecf9c5=182，**净增 6 项**（P54 新代码引入：SIM103×1/I001×1/UP006×2/UP045×2；其余 176 项为既有风格债） |
| unit_test (pytest) | MUST_PASS | ✅ PASS | heavyskill 自身测试 9/9；CLI 按配置跑 root tests/ 55 通过 |
| secret_scan (detect-secrets) | MUST_PASS | ✅ PASS | 0 密钥 |
| security_scan (semgrep) | MUST_PASS | ✅ PASS | 0 发现 |
| test_quality (AST) | MUST_PASS | ✅ PASS | 9 测试 23 断言，无空桩 |
| failure_log | MUST_PASS | ✅ PASS | 11 条记录完整 |
| dependency_scan (safety) | SHOULD_PASS | ⏭️ ERROR | 环境无网络（非代码） |
| format_check | OPTIONAL | ❌ FAIL | 338 处格式问题（ruff format 可修，既有债） |

> 修正记录：初审报告曾称 ruff"零新增"（HEAD=CURRENT=181），实为基线取错版本
> （`git show HEAD:` 的 HEAD 即 P54 提交本身）。正确基线对比为 176→182，净增 6。

## 二、深度审查：4 轨迹共识矩阵（裁决 3×PASS_WITH_WARNING + 1×FAIL）

| # | 发现 | 级别 | 共识 | 实证 |
|---|---|---|---|---|
| 1 | **CLI 标志名断裂**：argparse 定义下划线 `--max_tokens`/`--summary_max_tokens`，告警文案与 SKILL.md 用短横线 → 修复指引执行必报错 | P1 | #1 #2 #3 | ✅ `--summary-max-tokens` → SystemExit 2 |
| 2 | **冒号守卫误杀标准格式**：`(?:is\|:)`/`[为是：:]` 先吞动词，冒号进 group，新守卫 `startswith(":")` 拒绝 → `"The final answer is: 42"`、`"答案是：42"` 均 None。垃圾防护本应由 pipeline 层 content_fallback 承担，extract_answer 过度防御 | P1 | #3（#4 变体同根因） | ✅ 新版 None vs 旧版 `': 42'` |
| 3 | **审议截断无防垃圾保护**：Stage1 截断剔除，Stage2 审议截断时 `final_answer` 仍从残稿提取（`**最终答案：…但` 被采信），不重试不回退共识；`previous_deliberation` 会把残稿喂下一轮迭代 | P1 | #1 #2 #3 #4 | ✅ 截断残稿 → `'HGF 部分具备生产力，但'` |
| 4 | **config 预算打通不完整**：仅 2 键接入；`--temperature`(1.0)/`--summary_temperature`(0.7)/`--language`(en) 等 default 非 None 参数 `or` 短路 → config.yaml 值不生效 | P2 | #1 #2 | ✅ config 0.7 实际生效 1.0 |
| 5 | **"显式标记接受部分结果"空头支票**：无 `--accept-partial`；截断运行 exit 恒 0 | P2 | #1 #2 | ✅ 代码核对 |
| 6 | **has_truncation() 忽略 content_fallback**：8/8 思维链回退零告警 | P2 | #1 #2 | ✅ 代码核对 |
| 7 | **全截断两套有效性标准**：filter 用未过滤 answers vs cache 用 is_valid；successful_count 截断计成功 | P2 | #1 #4 | ✅ 动态验证 |
| 8 | **is_terminated 误杀无标点答案**：`"42"` → None；末行不 rstrip 尾标点 → 分票 | P2 | #1 #2 #3 #4 | ✅ 实测 |
| 9 | **多行答案行为变化**：`**最终答案：**\n方案A…\n方案B…` 只取首行；`answer is:\n42\nbecause` 新版 None | P2 | #1 | ✅ 实测（B 场景新版更优） |
| 10 | **DeliberationRecord 缺 truncated**：cache 序列化视图与 result 视图不一致 | P2 | #1 #4 | ✅ 代码核对 |
| 11 | **max_tokens=32768 未真实端点验证**：300s 读超时下长输出可能转 failed 不进截断摘要；端点上限未知 | P1/P2 | #3 | ⚠️ 需 K=2 真实冒烟 |
| 12 | discourse 模式（therefore/所以）加 `\n` 后抓推理步进 | P2 | #3 | 中等 |

## 三、验证评估

- 已覆盖：9/9（拒残稿/拒思维链/合法答案/cache 剔除+不投票/config 字段/client 双标记/摘要）。
  核心数据流"标记→剔除→摘要"闭环正确，全截断优雅降级，无 P0。
- 缺口：CLI config 加载零测试（机制 1 本体）；审议截断路径零测试；冒号标准格式用例缺失
  （恰是 P1 回归点）；pipeline 接线映射未测；truncated∩fallback 组合未测；真实 API 冒烟（无 key）。

## 四、最终裁决：FAIL（需修复后复审）

4 轨迹 3×WARNING + 1×FAIL；三条 P1 均已实证：① CLI 标志断裂 ② 冒号守卫误杀 ③ 审议截断无保护。
按 HGF 纪律（P1 未解决不得合入）裁决 FAIL。

## 五、修复清单（复审前必须完成）

- **R1（P1）**：argparse 双拼写注册短横线别名（`--max-tokens`/`--summary-max-tokens` + dest），
  统一 SKILL.md/告警文案/lesson 文档
- **R2（P1）**：extract_answer 冒号守卫改净化（`lstrip(":：").strip()`）而非拒绝；垃圾防护收敛到
  pipeline 层 content_fallback；补 `"答案是：42"` → `"42"` 标准格式单测
- **R3（P1）**：审议 `response.truncated` 时强制回退 `cache.get_consensus_answer()`（或置 None+
  告警升级"结论不可信"）；`previous_deliberation` 不回填截断残稿
- **R4（P2）**：config 加载抽 `build_config()` 纯函数，全键 `args.X if args.X is not None else
  defaults.get(...)`（修 temperature/language 短路）+ 四象限单测
- **R5（P2）**：新增 `--accept-partial`（截断且无答案 → exit 2）；has_truncation 纳入
  content_fallback；filter 早退统一 cache 有效集；successful_count 排除截断；
  DeliberationRecord 补 truncated
- **R6（P2）**：清 6 项新 ruff 债（SIM103/I001/UP006×2/UP045×2）；skills/heavyskill 加 scoped
  ruff 配置并基线化既有债，让门禁恢复度量增量
- **R7**：补单测（冒号格式/审议回退/build_config/全截断端到端）→ 目标 ≥15 项；
  有 key 后 K=2 真实冒烟

## 六、复审闭环（实施后更新）

- [x] R1-R7 全部完成（2026-08-21）：
  - R1 argparse 双拼写（`--max-tokens`/`--summary_max_tokens` + 短横线别名）+ 文档/告警统一
  - R2 extract_answer 冒号净化（`"答案是：42"` → `"42"`，垃圾防护收敛 pipeline 层 content_fallback）
  - R3 审议截断回退共识 + previous_deliberation 不回填残稿
  - R4 build_config() 纯函数三级解析（CLI > config > 默认，修 temperature/language 短路）+ 4 单测
  - R5 `--accept-partial`（截断且无答案 exit 2）+ has_truncation 纳入 fallback + filter 统一 cache 有效集 + successful_count 排除截断 + DeliberationRecord 补 truncated
  - R6 清 6 项新 ruff 债 + skills/heavyskill scoped ruff 配置（tests/ 不豁免，存量基线化）
  - R7 单测 9 → 18（新增冒号格式/审议回退/build_config×4/全截断端到端/truncated∩fallback）
- [x] 门禁复审：ruff 全绿 / pytest 18 passed（覆盖 64%）/ semgrep 0 / detect-secrets 0
- [x] **HGF CLI --execute 复审：9 门禁 8 通过 + 1 环境跳过（safety SHOULD_PASS），
  全部 MUST_PASS 通过（exit=0）**——static_analysis/failure_log/format 从 FAIL 转绿
- [x] 复审裁决更新：FAIL → **PASS_WITH_WARNING**（见下）

## 七、复审裁决（2026-08-21，R1-R7 实施后）

**PASS_WITH_WARNING**：
- 三条 P1 全部修复并实证：① CLI 双拼写（短横线可用）② 冒号标准格式恢复提取 ③ 审议截断回退共识
- P2 共识 9 项全部落地（config 全键打通、--accept-partial、fallback 告警、filter 统一、
  successful_count 语义、DeliberationRecord 序列化一致、ruff 增量可度量）
- 残余警告（不阻断，待环境允许）：
  1. ~~`max_tokens=32768` 未经真实端点验证~~ **已验证（2026-08-21，真实 API）**：
     - v4-pro 接受 max_tokens=32768（HTTP 200，finish=stop 完整输出）
     - deepseek-chat K=2 端到端：truncation 全 0/False、2/2 轨迹含最终答案标记、
       共识为完整句子、审议完整收尾（10.58s）
     - v4-pro K=1 端到端：truncation 全 0、轨迹/审议完整（136s，推理模型预期耗时）
     - 小预算(512)对比：截断被检测（truncated=1+content_fallback=1）、轨迹剔除、
       successful_count=0、final_answer=None（不采信残稿）、⚠️ 告警 + 早退统一判定——全部生效
  2. is_terminated 对无标点收尾答案仍偏保守（"宁漏勿错"取舍，已文档化）
  3. 存量 format 债（ruff format 29 文件）为 OPTIONAL 门禁，未纳入本次修复
- 结论：**可合入，真实 API 冒烟已验证通过**（原"待有 key 后跑"跟进项已闭环）
