# 实质性内容审查框架 — 小鹏汽车实测 (2026-08-08)

## 背景

qual工作流的审查环节（structural_check、InsightAuditor等）只检查"形式"（是否有必需小节），不检查"实质"（内容是否正确）。人工批判性审阅发现4个致命问题(F1-F4)和7个重要问题(I1-I7)，全部未被自动化审查捕获。

## 问题根因

| 根因 | 表现 |
|------|------|
| 审查只检查"是否包含" | 第6章包含所有小节，但内容错误（现金流误称转正） |
| 洞察审计只检查"是否有洞察" | 第6章有"造血能力初步形成"洞察，但基于错误事实 |
| 翻转阈值使用模板数据 | 营收1427.8亿比实际高3-4倍，多份报告共用同一bug模板 |
| 语义审计只检查单章节内部 | 第6章说转正，第5/9章说为负，无人检测冲突 |

## 解决方案：两层审查架构 + 修复循环

### Step 4.7: 形式审查（5个模块）

检查跨章节一致性、逻辑自洽性、数据合理性。

| 模块 | 文件 | 捕获的问题 |
|------|------|------------|
| CrossChapterConsistency | `cross_chapter_consistency.py` | F1: 现金流正负打架、I1: 总资产口径 |
| LogicConsistency | `logic_consistency_check.py` | F2: 估值与叙述矛盾 |
| DataReasonableness | `data_reasonableness_check.py` | F3: 营收基数1427.8亿 |
| ValuationArbitrator | `valuation_arbitrator.py` | F4: 三套估值不收敛 |
| DateAnchor | `date_anchor_check.py` | I5: 2024 vs 2025时点混乱 |

### Step 4.8: 实质性审查（4个模块）

与Wind数据比对、LLM语义审查、结论合理性验证。

| 模块 | 文件 | 捕获的问题 |
|------|------|------------|
| FactChecker | `fact_checker.py` | 营收/净利润与Wind偏差>5% |
| DepthReviewer | `depth_reviewer.py` | 第5章/第10章深度不足 |
| ConclusionValidator | `conclusion_validator.py` | "中性"评级但上行空间100% |
| AssumptionChecker | `assumption_checker.py` | WACC=6.4%缺少数据支撑 |

### 审查修复循环（review_repair_loop.py）

审查不是终点，修复才是目的。Step 4.7和4.8合并为一个审查修复循环：

```python
def review_and_repair_loop(chapters, ctx, llm_caller, wind_data, max_rounds=3):
    for round_num in range(1, max_rounds + 1):
        # 1. 执行审查
        round_issues = _run_deep_review(chapters, wind_data)
        round_issues.extend(_run_substantive_review(chapters, llm_caller, wind_data, industry))
        
        # 2. 检查是否通过
        if not round_issues:
            return ReviewRepairResult(passed=True, ...)
        
        # 3. 使用LLM修复问题
        fixed_count = _repair_chapters(chapters, round_issues, llm_caller)
    
    return ReviewRepairResult(passed=False, remaining_issues=round_issues)
```

## 实测结果（小鹏汽车9868.HK）

| 审查技能 | 结果 | 检测到的问题 |
|----------|------|--------------|
| 跨章节一致性 | ❌ score=0 | 16个问题，经营现金流冲突 |
| 逻辑一致性 | ❌ score=60 | 情景基准30.6元隐含-32.5%上行 |
| 数据合理性 | ❌ score=60 | 营收基数1970亿是实际的2.6倍 |
| 估值仲裁 | ✅ score=100 | 无明显问题 |
| 日期锚点 | ❌ score=0 | 47个问题，不同章节不同年份 |
| 事实核查 | ❌ score=0 | 29个数据偏差 |
| 分析深度 | ✅ score=62 | 第5/10章深度不足 |
| 结论合理性 | ✅ score=85 | 中性但上行100% |
| 假设合理性 | ✅ score=90 | WACC缺数据支撑 |

**总计**：形式审查96个问题 + 实质性审查70个问题 = 166个问题

## 关键教训

1. **事实核查是最高价值审查**：与Wind数据比对能直接发现F1/F3类致命问题
2. **分析深度需要LLM**：纯关键词评估准确率低（~60%），LLM语义审查更可靠
3. **结论合理性检查简单有效**：提取评级+上行空间+估值判断，检查一致性
4. **假设合理性需要行业基准**：WACC/永续增长率需要与行业平均值对比
5. **人工批判性审阅不可替代**：自动化审查只能捕获数据层面问题，投资逻辑、估值合理性等仍需人工判断
6. **审查必须带修复循环**：审查发现问题后应自动修复→再审查，不是只报告问题（review_repair_loop.py）

## HeavySkill审查结论

HeavySkill K=8审查确认：
- 形式审查（Step 4.7）能有效捕获跨章节数据矛盾
- 实质性审查（Step 4.8）需要Wind数据和LLM支持
- 审查修复循环是必要的（用户指出"qual流程应该是审查后自动修复，再审查"）
- 人工批判性审阅（buy_side_report_review）仍是不可替代的最后一道防线
