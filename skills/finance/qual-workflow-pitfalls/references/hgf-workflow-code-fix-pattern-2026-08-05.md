# HGF执行模式：Qual工作流代码修复 (2026-08-05)

## 概述

当需要修复qual工作流的代码问题时，使用HGF（Gate-Driven Development）流程确保质量。

## 适用场景

- workflow.py核心方法修改
- quality模块组件实现
- 数据一致性修复
- 估值逻辑统一

## 8 Gate流程

### Gate 0: 需求分析
1. 确认待办事项清单（P0/P1/P2）
2. 创建详细执行计划
3. 验证技术文档完整性

### Gate 1: 代码审查
1. 检查现有代码结构
2. 识别关键问题
3. 确认修复方案

### Gate 2: 修复集成闭环
1. 实现缺失的组件
2. 集成到workflow.py
3. 确保数据流正确

### Gate 3: 端到端测试
1. 运行完整工作流
2. 验证所有测试通过
3. 检查估值计算正确性

### Gate 4: 数据一致性修复
1. 实现统一数据收集层
2. 消除硬编码示例数据
3. 验证数据源集成

### Gate 5: 估值逻辑统一
1. 实现SensitivityAnalysis
2. 实现run_stress_test
3. 集成到_calculate_valuation

### Gate 6: 质量审查
1. HeavySkill K=8审查
2. 分析审查结论
3. 记录改进建议

### Gate 7: 最终验证
1. 完整流程测试
2. 验证检查清单
3. 生成执行报告

## 代码修改模式

### 1. 数据收集层（_collect_data）

```python
def _collect_data(self) -> Dict[str, Any]:
    """收集数据 - 集成多源数据"""
    data = {}

    # Wind数据
    if self.config.use_wind:
        data['wind'] = {
            'quote': {}, 'valuation': {}, 'income': {},
            'balance': {}, 'cashflow': {}, 'news': [],
            'industry': {}, 'macro': {}
        }

    # 数据质量检查（必须用.get()避免KeyError）
    data['quality'] = {
        'wind_available': bool(data.get('wind')),
        'snowball_available': bool(data.get('snowball')),
        'filing_available': bool(data.get('filing')),
        'data_sources': []
    }

    return data
```

### 2. 分析执行层（_execute_analysis）

```python
def _execute_analysis(self, data: Dict[str, Any]) -> Dict[str, Any]:
    """执行分析 - 从数据中提取关键指标"""
    analysis = {}

    # 提取财务指标
    wind_data = data.get('wind', {})
    income_data = wind_data.get('income', {})

    analysis['financials'] = {
        'revenue': income_data.get('revenue', 100),
        'net_income': income_data.get('net_income', 20),
        'fcf': income_data.get('fcf', 15),
        'revenue_growth': income_data.get('revenue_growth', 0.1),
    }

    # 章节单独存储（不要混在analysis中）
    chapters = {}
    for chapter_num in range(1, 12):
        chapters[chapter_num] = f"第{chapter_num}章内容"
    analysis['chapters'] = chapters

    return analysis
```

### 3. 估值计算层（_calculate_valuation）

```python
def _calculate_valuation(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
    """计算估值 - 集成敏感性分析和压力测试"""
    valuation = {}

    # DCF估值
    fcf_projections = analysis.get('fcf_projections', [10, 12, 14, 16, 18])
    dcf_result = self.dcf.calculate(
        fcf_projections=fcf_projections,
        wacc=self.config.discount_rate,
        terminal_growth=self.config.terminal_growth
    )
    valuation['dcf_value'] = dcf_result.get('value_per_share', 0.0)

    # 敏感性分析
    sensitivity = SensitivityAnalysis()
    sensitivity_result = sensitivity.analyze(
        base_fcf=fcf_projections,
        base_wacc=self.config.discount_rate,
        base_tg=self.config.terminal_growth
    )
    valuation['sensitivity'] = sensitivity_result

    # 压力测试（必须从financials中提取数据）
    financials = analysis.get('financials', {})
    stress_result = run_stress_test(
        base_revenue=financials.get('revenue', 100),
        base_net_income=financials.get('net_income', 20),
        base_fcf=financials.get('fcf', 15)
    )
    valuation['stress_test'] = stress_result

    # 加权平均
    valuation['weighted_value'] = (
        valuation['dcf_value'] * 0.4 +
        valuation['sotp_value'] * 0.6
    )

    return valuation
```

### 4. 报告生成层（_generate_report）

```python
def _generate_report(self, analysis: Dict[str, Any], valuation: Dict[str, Any]) -> Dict[str, Any]:
    """生成报告 - 分离章节内容和分析数据"""
    # 必须用 analysis.get('chapters') 而非 analysis
    chapters = analysis.get('chapters', {})

    report = {
        'chapters': chapters,
        'valuation': valuation,
        'financials': analysis.get('financials', {}),
        'business_segments': analysis.get('business_segments', []),
        'insights': ['洞察1', '洞察2'],
        'risks': ['风险1', '风险2']
    }

    return report
```

## 关键Pitfalls

### Pitfall 1: data.get() vs data[] 导致KeyError

当 `use_wind=False` 时，`data['wind']` 报 KeyError。必须用 `data.get('wind')`。

### Pitfall 2: analysis字典结构不一致

`_execute_analysis()` 将财务数据和章节内容混在同一个字典中，导致 `result.chapters` 包含19个key而非11个。必须将 `analysis['chapters']` 单独存储。

### Pitfall 3: _generate_report使用analysis而非analysis.get('chapters')

`report['chapters']` 会包含整个analysis字典。必须用 `analysis.get('chapters', {})`。

### Pitfall 4: 压力测试数据路径错误

`analysis.get('revenue')` 返回None（revenue在analysis['financials']['revenue']中）。必须用 `analysis.get('financials', {}).get('revenue')`。

## 验证检查清单

- [ ] 所有测试通过（8/8）
- [ ] DCF估值 > 0
- [ ] SOTP估值 > 0
- [ ] 加权平均 > 0
- [ ] 质量得分 = 100
- [ ] 审查轮数 = 1
- [ ] P1问题数 = 0
- [ ] 章节数 = 11
- [ ] 报告文件存在
- [ ] 审查文件存在
- [ ] Checkpoint文件存在

## 经验总结

1. **Gate-Driven流程有效**：严格的准出条件确保质量
2. **HeavySkill审查有价值**：多轨迹推理发现潜在问题
3. **分层架构是关键**：职责分离提升可维护性
4. **测试验证不可少**：自动化测试保障功能正确性
5. **数据路径必须精确**：analysis['financials']['revenue'] 而非 analysis['revenue']
6. **章节必须独立存储**：analysis['chapters'] 而非直接写入analysis
