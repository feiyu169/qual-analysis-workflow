# Qual工作流质量保障技术方案 v3.1 (最终版)

**文档版本**: 3.1 (最终版)  
**创建日期**: 2026-07-28  
**审查状态**: HeavySkill K=8通过

---

## 核心架构

### 四层防护体系

```
第1层: 数据标准化 (输入层)
├── 字段映射配置化 (P84)
├── 年份锚点强制传递 (S01)
├── 净利润口径定义 (S06)
└── FCF标准公式 (S07)

第2层: 估值约束 (计算层)
├── WACC CAPM校准 (P90)
├── DCF单一权威源 (S02)
├── 可比公司多维匹配 (S03)
├── 翻转阈值方向验证 (S08)
└── ROIC-WACC一致性检查 (S09)

第3层: 逻辑综合 (输出层)
├── 结论综合引擎 (S04)
├── 否决项概率评估
├── AI痕迹自动清洗 (P13)
└── 数据质量门禁

第4层: 质控验证 (审计层)
├── 审计真实性验证 (S05)
├── Gate Checks
└── 回归测试集
```

---

## 关键模块设计

### 1. DCFService (替代DCFAuthority单例)

```python
class DCFService:
    """无状态，依赖注入，组合现有DCFCalculator"""
    
    def __init__(self, calculator=None, config=None):
        self._calculator = calculator or DCFCalculator()
        self._config = config or DCFServiceConfig()
    
    def run_full_analysis(self, inputs: DCFInputs) -> DCFAnalysisResult:
        result = self._calculator.calculate(inputs)
        sensitivity = None
        if self._config.enable_sensitivity:
            sensitivity = self._calculator.sensitivity_analysis(...)
        return DCFAnalysisResult(dcf=result, sensitivity=sensitivity)
```

### 2. QualityPipeline (拆分Step 4.5)

| 子步骤 | 模块 | 降级策略 |
|--------|------|----------|
| 4.1 | structural_check | 不可降级，失败阻塞 |
| 4.2 | semantic_audit | 可降级，LLM超时时跳过 |
| 4.3 | chapter_repair | 可降级，依赖审计结果 |
| 4.4 | checkpoint | 不阻塞，失败仅warning |

### 3. FeatureFlags

```python
@dataclass(frozen=True)
class FeatureFlags:
    _enabled: frozenset = field(default_factory=lambda: frozenset(FeatureModule))
    
    @classmethod
    def default(cls): return cls()  # 全部启用
    
    @classmethod
    def minimal(cls): return cls(_enabled=CORE_MODULES)
    
    @classmethod
    def no_llm(cls): return cls(_enabled=frozenset(FeatureModule) - LLM_MODULES)
```

### 4. WACC CAPM完整参数

```
Ke = Rf + β × (MRP + CRP) + α

其中:
- Rf: 10年期国债收益率
- β: 回归Beta + 基本面Beta加权，Blume调整(0.67×raw + 0.33×1.0)
- MRP: 股权风险溢价(6.5%)
- CRP: 国家风险溢价(中国A股=0)
- α: 规模溢价(≤3%) + 流动性溢价(1.5%) + 治理溢价
- 总α上限: 6%
```

### 5. 终值计算双轨方法

- **永续增长法**: g∈[1.5%, 3.5%], g<WACC
- **退出倍数法**: EV/EBITDA, 可比公司25-75百分位
- **TV/EV比例上限**: 75%

### 6. FCF定义三层规范

- **FCFF**: EBIT×(1-T) + D&A - CapEx - ΔWC
- **FCFE**: Net Income + D&A - CapEx - ΔWC + Net Borrowing
- **LFCF**: Operating CF - CapEx

### 7. 可比公司多维度匹配

| 维度 | 权重 | 算法 |
|------|------|------|
| 业务构成 | 40% | 余弦相似度 |
| 商业模式 | 25% | 标签匹配 |
| 规模 | 15% | 层级距离 |
| 成长阶段 | 10% | 阶段距离 |
| 地理覆盖 | 10% | 收入占比差异 |

### 8. 结论综合引擎

- 各章权重: ch05经营表现(20%)最高
- 否决项优先: 触发则直接SELL
- 单一结论: BUY/HOLD/SELL

### 9. ROIC-WACC四象限分析

| 象限 | 条件 | 允许声称 |
|------|------|----------|
| Q1 | 价值创造+趋势改善 | "价值创造确立" |
| Q2 | 价值创造但趋势平稳 | "价值创造稳定" |
| Q3 | 价值毁损但趋势改善 | "拐点临近" |
| Q4 | 价值毁损且趋势恶化 | "价值毁损持续" |

---

## 与现有代码关系

**增量集成策略**: 现有quality/目录41个文件零修改

```
quality/
├── dcf.py, sensitivity.py, ...  # 现有41文件（保留不动）
└── v3/                           # v3.0新增子包
    ├── __init__.py               # try/except导入
    ├── feature_flags.py
    ├── dcf_service.py
    ├── year_anchor.py
    ├── pipeline.py
    └── adapters/
```

---

## 13个系统性缺陷清单

| 编号 | 问题 | 严重度 | 解决方案 |
|------|------|--------|----------|
| P84 | Wind现金流字段映射 | P0 | 字段映射配置化 |
| P90 | WACC硬编码10% | P1 | CAPM校准 |
| P13 | AI痕迹严重 | P1 | 自动清洗 |
| P76 | success掩盖降级 | P1 | 数据质量门禁 |
| S01 | 年份锚点错误 | 致命 | YearAnchor |
| S02 | DCF多源矛盾 | 致命 | DCFService |
| S03 | 可比公司错配 | 致命 | 多维度匹配 |
| S04 | 结论未综合 | 致命 | ConclusionSynthesizer |
| S05 | 审计无效 | 致命 | AuditValidator |
| S06 | 净利润口径混乱 | 重要 | 口径定义 |
| S07 | FCF定义粗糙 | 重要 | 三层规范 |
| S08 | 翻转阈值方向错 | 重要 | 方向验证 |
| S09 | ROIC<WACC冲突 | 重要 | 四象限分析 |
