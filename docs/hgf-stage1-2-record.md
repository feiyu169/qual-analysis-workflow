# HGF 阶段化实施记录（2026-08-22）

## 阶段 0：快速诊断（HeavySkill K8 + 子代理诊断）
- **三方专家审查**：投资分析 / 架构 / 编程，8 轨迹审议
- **P5/P6/P12 同源诊断**：检查器提取层与 DataAnchor 语义分裂（口径/符号/财年三处）
- **P6 根因**：FactChecker 单财年假设（matches[0] vs Wind[-1]）→ 全量 fatal 假阳性
- **P5 根因**：cross_chapter_consistency 自建 regex 不排除子公司/符号翻转/跨财年误归因
- **P12 根因**：numeric guard 白名单缺小额科目 + FINANCIAL_CHAPTERS 含 ch5 过严
- **P11 根因**：workflow.py Step 4.7 与 gate4 重复调用 review_and_repair_loop

## 阶段 1：恢复管线可收敛（57bc12c）
1. **P6 退役 FactChecker** → DataAnchor validate_chapter_any_fy（多财年感知）
2. **P12 白名单补全**：小额科目（减值/补助/汇兑/回购等）+ FINANCIAL_NUMBERS_BY_CH={5:1,6:3}
3. **P5 统一提取层**：cross_chapter_consistency 改用 extract_data_spans（子公司排除+符号归一）
4. **删除重复审查循环**：workflow.py Step 4.7 改为独立终局 sweep

## 阶段 2：日期语义治理（407f3d8）
1. **bind_fuzzy_dates**：上下文感知（财务语境→FY替换，非财务豁免）
2. 接入 Gate3 / review_repair_loop / Gate8 三处
3. 修复：最长匹配优先（近年来→近年）+ 最近分隔符截断（防跨句污染）+ 从非财务词典移除"趋势"

## 阶段 3：全流程重跑验证
### 第一次重跑结果（无终局 sweep）
- Gate 0-3: ✅ 全通过
- Gate 4: ❌ 仅 2 issues（现金流占位符残留），事实核查/日期锚点/收敛早停全部消除
- Gate 5-8: 级联失败（Gate 4 未通过）
- **改善**：跨章一致性 77→9（↓88%），事实核查 19→0，日期锚点 35→0

### 修复：终局 sweep 独立运行（16821aa）
- Gate 4 失败后仍运行 ADVC + PGNB + bind_fuzzy_dates + bind_placeholders
- 确保占位符残留被回填

### 第二次重跑（pwsh-13，进行中）
- 预期：终局 sweep 回填现金流占位符 → Gate 4 的 2 issues 消除 → Gate 4 通过 → Gate 5-8 正常运行

## 代码变更汇总
| 文件 | 变更 |
|------|------|
| tools/finance/quality/review_repair_loop.py | 退役 FactChecker → DataAnchor; bind_fuzzy_dates 接入; bind_bare_numbers patch 兜底 |
| tools/finance/quality/numeric_guard.py | 白名单补全; FINANCIAL_NUMBERS_BY_CH 分级 |
| tools/finance/quality/cross_chapter_consistency.py | extract_data_spans 统一提取; unattributed_historical 保留 |
| tools/finance/workflow.py | 删除重复审查循环; 终局 sweep 独立运行; bind_fuzzy_dates 接入 |
| tools/finance/qual_v8/numeric_binder.py | bind_bare_numbers + bind_fuzzy_dates 新函数 |
| tools/finance/qual_v8/gates/gate8.py | bind_fuzzy_dates + bind_bare_numbers 终局接入 |
| tools/finance/test_pgnb.py | +5 fuzzy dates + 2 bare_numbers tests |
| tools/finance/test_stage_c.py | 更新 for DataAnchor 路径 |
| tools/finance/quality/test_pgnb_patch_backstop.py | 新文件：5 patch 兜底测试 |
