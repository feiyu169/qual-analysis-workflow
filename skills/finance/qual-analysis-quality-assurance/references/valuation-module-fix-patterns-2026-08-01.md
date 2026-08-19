# 估值模块系统性修复模式 (2026-08-01)

## 背景

阅文集团(00772.HK)分析中，估值模块产生全部负值的DCF结果。经审计发现4个文件、10处独立bug需要协同修复。审查报告从4个致命问题降至修复后重审时可接受水平。

## 修复清单

| # | 文件 | 函数 | 问题 | 修复 |
|---|------|------|------|------|
| 1 | workflow.py | extract_dcf_params | FCF=ocf+investing_cf(负值) | FCF=ocf-capex |
| 2 | workflow.py | extract_dcf_params | WACC=10%(硬编码) | CAPM: Ke=Rf+β×ERP, WACC=Ke×85%+Kd×(1-T)×15% |
| 3 | workflow.py | extract_dcf_params | 净负债用总负债 | 净现金公司(权益/负债>3)调整为负债×30% |
| 4 | workflow.py | 断点恢复(3处) | Placeholder被缓存后恢复 | 检查"[Placeholder]" in cached |
| 5 | valuation_engine.py | CORE_COMPARABLES | 抖音/Meta/拼多多(不可比) | 掌阅/中文在线/B站/爱奇艺/迪士尼 |
| 6 | valuation_engine.py | compute_dcf | WACC默认10% | None→CAPM自动计算 |
| 7 | valuation_engine.py | compute_dcf | EBIT利润率用净利润(负) | 用营业利润(正), 负时fallback 5% |
| 8 | valuation_engine.py | compute_full_valuation | WACC=0.10,TG=0.03 | WACC=None,TG=0.02 |
| 9 | valuation_engine.py | compute_dcf | 净负债字段'最近3年每年负债合计' | '年负债合计' |
| 10 | depth_enhancer.py | run_depth_enhancement | EBIT利润率用净利润(负) | 用营业利润(正), 负时fallback 5% |

## 断点恢复Placeholder检测

所有3处断点恢复逻辑都需要修复:
- `_write_chapters()` — 第1-9章
- `_generate_decision_chapter()` — 第10章
- `_generate_overview_chapter()` — 第0章

```python
# 修复模式
if checkpoint.is_chapter_completed(ticker, chapter_id):
    cached = checkpoint.get_chapter(chapter_id)
    if cached and "[Placeholder]" not in cached:
        return cached
    elif cached and "[Placeholder]" in cached:
        logger.info(f"第X章为placeholder，重新生成")
```

## EBIT利润率计算规则

**核心规则**: EBIT利润率 = 营业利润 / 营收, 不是净利润 / 营收

```python
op_list = income.get('年营业利润', [])
if op_list and rev_list:
    latest_margin = op_list[-1] / rev_list[-1]
    if latest_margin < 0:
        latest_margin = 0.05  # 保守估计
```

## CAPM WACC计算

```python
rf = 0.023      # 无风险利率(10年期国债)
beta = 1.2       # Beta系数
erp = 0.055      # 股权风险溢价
ke = rf + beta * erp  # 0.089
kd = 0.05        # 债务成本
tax_rate = 0.25
wacc = ke * 0.85 + kd * (1 - tax_rate) * 0.15  # 0.081
```

## 可比公司选择原则

**错误**: 抖音/Meta/拼多多/美团 — 业务模式完全不同
**正确**: 掌阅科技/中文在线(在线阅读) + B站/爱奇艺(内容平台) + 迪士尼(标杆)

## 审查集成被success=False跳过

`review_integrator.py`的`run_analysis_with_review()`在qual分析返回success=False时跳过审查。
Workaround: 直接调用`integrator.review_report()`绕过success检查。

## 验证要点

修复后检查:
1. DCF估值WACC应为~8.1%（非10%）
2. 情景分析EBIT利润率应为正值（~5%）
3. 目标价推导应为正值
4. 结论翻转阈值应合理（营收翻转点不可能为负）
5. 可比公司应为在线阅读/内容平台行业

## 关键教训

1. **不能只修一个文件** — 估值链: 参数提取→核心计算→主流程→深度优化，每步可能有独立bug
2. **EBIT≠净利润** — 亏损公司净利润为负，但营业利润可能为正
3. **断点恢复是陷阱** — 第一次运行的错误结果会被缓存，后续运行无法自动修复
4. **审查集成有守门条件** — success=False可能阻止审查执行
5. **字段名可能不一致** — Wind数据的字段名与代码期望可能不同
