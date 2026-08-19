# Finance Tool Suite Changelog

> 版本刻度说明（三刻度分离，详见 `docs/qual-version-architecture.md`）：
> - **包版本**（本文件）：`finance.__version__`，semver，对外接口变更时递增
> - **架构代次**：`qual_v8.ARCH_GEN`（当前 v8），仅架构级重写时递增
> - **组件代次**：`quality.COMPONENT_GEN`（当前 v3），质量组件层整体换代时递增

## [5.0.0] - 2026-08-16（基线）

### 已记录
- 导出并迁移自 Hermes/WSL：downloaders/parsers/processors/data_context/workflow/quality/qual_v8/memory 全链路
- Windows 侧依赖安装完成（requirements-windows.txt 15/15）
- MinerU 唯一解析接入（`filing_downloader._parse_pdf`），失败即中断并写 run-aborted.json

## [未发布] - 2026-08-18（本轮：架构代次 v8 可运行化 + 数据矛盾修复）

### 新增（架构代次 v8）
- **qual_v8 引擎可运行化**：9 个 Gate 灌入 v2-v7 真实组件，`QualWorkflow.execute()` 成为可用入口
  - 引擎机制：补全 flow_definition（gate_0~8）、真实重试、check_criteria 调用、enforce 模式阻断（关键 Gate 0/2/4/8）
  - DataAnchor 修复：死代码修复、canonical 键别名、财年维度（DataPoint.fiscal_year）、多财年锚点、财年感知校验
  - 新增 `qual_v8/adapters.py`：build_data_context / wind_coverage / industry_for（替代硬编码"新能源汽车"）
  - Gate8 双层校验：DataAnchor 数字校验器（1% 容忍）+ 红队审查（buy_side_report_review skill）
- **红队审查接入 Gate8**（`quality/review_integrator.py`）
  - 修复硬编码美团锚点 → `_build_wind_anchor_table()` 动态 canonical 表
  - 新增 `review_report_text()` 文本版审查入口
  - 解析器兼容 F-1/I-1 编号格式
  - `harness_llm.create_harness_caller` 支持 max_tokens/system 覆盖

### 修复（P0 数据矛盾，方案 A/B 落地）
- **方案 A 单源契约**：新增 `canonical.py` 唯一映射真源（canonical 键 + 别名表 + canonicalize 归一）；
  `data_context.safe_get/has_field/latest_value` 加 canonical 兜底；`fact_checker` wind_field 全部改 canonical 键 +
  get_series 别名兜底；`fact_extractor.cross_validate_with_wind` 改 get_series（修复键契约断裂——原先取 `年净利润` 等永远 None，校验静默失效）
- **方案 B1 事实提取财年锚定**：`extract_facts` 新增 `fiscal_year`/`report_type` 参数（入参优先 → Wind labels[-1] 回退）；
  新增 `_inject_fiscal_year_instruction`（批次文本注入当期/对比期财年指令）；`_merge_chunk_data` 后统一设置 facts.fiscal_year；
  workflow Step 1.6 从 filing metadata 或 Wind labels[-1] 推断财年传入
- **方案 B2 事实表↔Wind 仲裁**：新增 `workflow._reconcile_facts_with_wind`（同财年偏差≤1% 保留/超限以 Wind 覆盖/
  异财年财务字段降级为"历史参考，不得作为当期值引用"）；`_build_chapter_prompt` 注入仲裁说明
- **v8 Gate1/Gate3 仲裁接入（本次）**：Gate1 `_extract_facts` 返回**完整 ExtractedFacts 对象**（保留 fiscal_year/report_type），
  context 存 `facts`（对象）+ `facts_dict`（dict 视图）；`_facts_to_dict` 键对齐 required_fields
  （net_profit→net_income、operating_cashflow→operating_cash_flow）；`_check_required_fields`/`_check_value_deviation`/
  `check_criteria` 兼容对象；required_fields 移除 operating_income（非提取强制输出）；
  Gate3 复用对象 → `_reconcile_facts_with_wind` 在 v8 --full 生成路径生效
- **filing_downloader fiscal_year 修复**：不再用发布日期年份（FY2025 年报 2026-04 发布会错标 2026）；
  改为正文报告期推断（"截至2025年12月31日止年度"→2025）→ 发布日期-1 兜底 → 调用方与 Wind labels[-1] 对齐
- **数据源权威契约落地**（`data_context.py`）：新增 `SOURCE_AUTHORITY`（filing=content_primary / wind=numeric_primary /
  search=supplementary）+ `SOURCE_TRUTH_ORDER`（一手>二手>三手）；`_build_chapter_prompt` 注入"数据源权威契约"说明
  （财务数值以 Wind 锚点为准、运营定性以财报事实表为准、行业外部以搜索为准、冲突 Wind 优先）——v2-v7 与 v8 Gate3 自动生效
- **章节内容固化（防 LLM 随意生成）**（`docs/qual-chapter-fixation.md`）：
  - `CHAPTER_SKELETON`：每章固定子节清单（ch1-9）
  - `_build_chapter_prompt`：注入"章节骨架"（固定标题+子节+H1 铁律：禁止 `# 第N章`）
  - `_generate_chapter`：格式修正 prompt 增强（删除自造 H1 + 保持主题）
  - `_assemble_report`：内容内 H1 全部降级 H2（防重号/模板泄漏）
  - `structural_check`：新增 H1 唯一性检查（自造 `# 第N章` 判 critical）
  - v8 Gate8：加"正文自造 H1 检测"
- **深度审查规范化（防审查引入新矛盾）**（`docs/qual-review-discipline.md`）：
  - 五条铁律：①修复最小侵入（Patch 模式，不整章重写）②修复带锚点（Wind 锚点表注入）③修复后全量校验（失败回滚）
    ④修复预算（≤5 patch）+ 单调性 ⑤修复审计日志
  - 新增 `quality/patch_applier.py`：patch JSON 解析 + 唯一匹配 + 预算 + 校验闭环（structural/consistency/numeric）
  - `review_repair_loop._repair_chapters` 改 patch 模式（原整章重写 + 前 3000 字截断 → patch + 锚点 + 校验回滚）
  - 单测：T1 唯一匹配 / T2 非唯一拒绝 / T3 预算超限 / T4 校验回滚 / T5 代码块解析 全部通过
  - 待改：review_integrator.fix_report 与 repairer.repair_chapter 的 patch 化（P1）
- **P1 完成：三条修复路径全部 patch 化**（2026-08-18）：
  - `review_integrator.fix_report`：整报告重写 → patch JSON（≤15 patch）+ 结构/数字锚点校验 + 失败回滚/强制修正兜底
  - `repairer._call_llm_repair`：完整章节 → patch JSON（≤5 patch）+ structural 校验 + 失败降级
  - `repairer._BUILTIN_REPAIR_PROMPT`：输出格式改为 patch JSON
  - 验证：repairer patch 应用（80亿→73.66亿，校验通过）✅；未点名内容保留 ✅；quick 回归 Gate0-7 PASS ✅
  - 深度审查架构确认文档：`docs/qual-deep-review-architecture.md`（三层防线 + 五条纪律 + 数据流 + 能力边界）
- **实质审查与红队审查改进（2026-08-18，对照 docs/qual-substantive-vs-redteam.md）**：
  - ① 实质审查专用 caller：`_run_substantive_review` 构造审查 system caller（max_tokens=8000/temp=0.3/审查 system）替代报告撰写 system
  - ② 锚点注入：`depth_reviewer`/`conclusion_validator` 加 wind_data 参数 + prompt 注入 Wind canonical 锚点表；截断 3000→8000
  - ③ 红队分批：Gate8 `_run_redteam_review` 报告 >12000 字符时按 `# 第N章` 逐章红队补审（每章 ≤12000），批次致命/重要汇总
  - 验证：全文件编译 ✅；quick 回归 Gate0-7 PASS、Gate8 正确拒绝 R5 ✅
  - **多角色辩论审查可行性评估**（docs/qual-debate-review-feasibility.md）：基础设施（debate_coordinator 三角色+超时保护）已存在，
    可行；需 ①锚点注入 ②输出转审查 issues ③限定 3 章+1 轮+超时降级；建议先小步验证 ch10
- **辩论机制统一落地（2026-08-18，docs/qual-debate-unified.md + qual-debate-timeout-redesign.md）**：
  - 单一引擎 + 双消费：新增 `quality/debate_service.py`（DebateService：锚点表构建唯一化 + timeout 可配 +
    enhance/review 双消费 + retries）；质量增强（9 章→关键 5 章）与实质审查（新增第 5 项对抗辩论，3 关键章）共用
  - 超时修订：角色线程 60→240s（推理模型，原过严）；部分成功降级——Bull 可独立增强、Bear 缺失标记 partial、
    PM 超时 `_auto_pm_synthesis` 自动裁决（不退回 Bull 草稿）；DebateResult 加 stages/partial
  - 验证：编译 ✅；单测（review 提取 Bear 问题/enhance append/partial 保留 Bull）✅；quick 回归 ✅
- **字符数超中断防治（P0+P1 落地，docs/qual-review-char-limit.md）**：
  - **P0-① harness_llm max-tokens 保留**：截断但有内容 → 保留 + 标注"⚠️ 输出被截断"（不 raise 丢稿）；无内容仍报错
  - **P0-② 新增 `quality/review_chunker.py`**：按章→小节→句子边界分批（不切断数字/表格）+ merge_batch_issues（单批失败不丢整份）；Gate8 红队接入（替换手写 split + 修 errors 二次清空 bug）
  - **P1-③ depth_reviewer 自适应**：≤20000 全文，超限按小节分批多段取最低分；辩论 Bull 输入 3000→20000
  - **P1-④ Gate8 红队 checkpoint**：每批落盘 redteam_checkpoints/seg{N}.json，中断可续审 + 未审标注
  - 验证：编译 ✅；单测（chunker 39 段≤5000 / merge 未审 / max-tokens 保留+不重试）✅；quick 回归 ✅

### 修复（其他）
- Gate3/4 形式问题（占位符/币种/模板泄漏/章节重号）降级 warning 交 Gate8 收口，不阻断检查链
- Gate2 FCF 负值放行（亏损/投资期为真实状态，只要求非零）
- Gate1 quick 模式 SKIPPED 不阻断（无 LLM 且已有章节时跳过事实提取）
- Gate6 无第0章时 quick 预填放行
- Gate7 记忆存储兼容无 data_ctx；warnings 防御 int/None
- fact_checker f-string 正则转义 SyntaxWarning 修复

### 版本治理（三刻度落地）
- `qual_v8/__init__.py` 声明 `ARCH_GEN="v8"`；`quality/__init__.py` 声明 `COMPONENT_GEN="v3"`
- `workflow.py` 头注释更新为 legacy 单体定位（v2，被 v8 Gate3/4/5/6 调用）
- 新建本 CHANGELOG.md（包版本刻度）

### 已知遗留
- 事实表↔Wind 仲裁在 v2-v7 单体生效；v8 Gate3 的生成路径（--full）需同步接入
- `data_repair._build_correct_values` 的 `年毛利率/年毛利` 等别名未完全 canonical 化（低优先）
- wind_field_mapper.FIELD_MAPPINGS（英文→Wind代码）仍独立存在（TTM 字段，供估值用，与 canonical 财务年字段不同域）

---
