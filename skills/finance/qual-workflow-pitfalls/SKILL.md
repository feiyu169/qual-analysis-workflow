---
name: qual-workflow-pitfalls
description: >-
  Qual工作流系统性缺陷清单与长效修复模式。覆盖流程执行、估值模块、数据一致性、
  方法论四大类17个已验证缺陷，附HeavySkill K=8审查通过的工程修复模式。
  当qual分析报告出现估值异常、数据矛盾、流程跳过等问题时加载此skill。
version: 2.4
author: Hermes Agent
triggers:
  - "qual流程问题"
  - "估值异常"
  - "数据矛盾"
  - "qual工作流修复"
  - "断点恢复placeholder"
  - "洞察审计假信号"
  - "DCF与情景分析不一致"
  - "qual v3实施"
  - "HeavySkill审查qual"
  - "qual整合"
  - "workflow集成"
  - "Gate-Driven架构"
  - "审查修复循环"
  - "非侵入式挂载"
---

# Qual工作流系统性缺陷与修复模式

> 本skill记录qual工作流在阅文集团（00772.HK）、美团（3690.HK）、顺丰（002352.SZ）
> 三份报告中反复出现的系统性缺陷，以及经HeavySkill K=8审查通过的工程修复模式。

---

## 一、缺陷清单（已验证，三份报告交叉确认）

### 1.1 流程执行缺陷

| 编号 | 缺陷 | 根因 | 验证报告 |
|------|------|------|----------|
| **Q0-1** | Gate Checks未执行 | 模块路径不正确，动态加载失败 | 阅文/美团 |
| **Q0-2** | 审查集成被跳过 | success=False时直接返回 | 阅文 |
| **Q0-3** | 断点恢复恢复placeholder | 未检查内容质量 | 阅文 |
| **Q0-4** | 参数传递不完整 | WACC/g/EBIT使用默认值 | 阅文 |
| **Q0-5** | 异常处理跳过而非阻断 | 关键步骤异常被静默吞没 | 阅文/美团 |

### 1.2 估值模块缺陷

| 编号 | 缺陷 | 根因 | 验证报告 |
|------|------|------|----------|
| **Q1-1** | DCF与情景分析结果相差3倍+ | 两套方法使用不同假设 | 阅文(3.3x)/美团(五套互斥) |
| **Q1-2** | 当前股价三处互不兼容 | 辩论模块各自硬编码 | 阅文(20.22/25-28/33.3) |
| **Q1-3** | 翻转阈值方向标反+量级荒诞 | 计算逻辑错误+文字描述有误 | 阅文/美团 |
| **Q1-4** | 洞察审计100/100假信号 | 自动满分占位 | 顺丰/美团/阅文（三份全中） |

### 1.3 数据一致性缺陷

| 编号 | 缺陷 | 根因 | 验证报告 |
|------|------|------|----------|
| **Q2-1** | 营收双口径未调和 | 财报原文 vs Wind结构化口径 | 阅文(73.66 vs 80.07) |
| **Q2-2** | 净亏损双值 | 归母 vs 含少数股东混用 | 阅文(-7.76 vs -8.44) |
| **Q2-3** | 定性描述前后矛盾 | 辩论模块与最终分析脱节 | 阅文(付费用户"创新高"vs"下降") |
| **Q2-4** | XX占位符未清除 | LLM生成截断/未完成 | 阅文/美团 |

### 1.4 方法论缺陷

| 编号 | 缺陷 | 根因 | 验证报告 |
|------|------|------|----------|
| **Q3-1** | 可比公司混入非同业 | 硬编码错误可比 | 阅文(B站/爱奇艺/迪士尼) / 美团(用自己) |
| **Q3-2** | 局部→全局聚合不透明 | 元裁决规则未编码 | 阅文(第6章看多 vs 终稿中性) |
| **Q3-3** | ROIC<WACC未回应 | 价值毁灭信号被忽视 | 阅文(ROIC -3.8% < WACC 8.1%) |
| **Q3-4** | 币值混用 | RMB/HKD未统一 | 阅文/美团 |

---

## 二、修复模式（HeavySkill K=8审查通过，综合评分85/100）

### 模式A：断点恢复质量检查（解决Q0-3）

**铁律**：checkpoint恢复时必须检查内容质量，placeholder不应被标记为"已完成"。

```python
class ContentValidator:
    """断点恢复内容验证器"""
    
    INVALID_PATTERNS = [
        "[Placeholder]", "XX亿元", "XX港元",
        "具体数据待核实", "数据不足", "需要配置 LLM API",
    ]
    MIN_CONTENT_LENGTH = 100
    REQUIRED_SECTIONS = ["## ", "### "]
    
    @classmethod
    def is_valid(cls, content: str, chapter_id: str) -> bool:
        if not content:
            return False
        for pattern in cls.INVALID_PATTERNS:
            if pattern in content:
                return False
        if len(content) < cls.MIN_CONTENT_LENGTH:
            return False
        if not any(s in content for s in cls.REQUIRED_SECTIONS):
            return False
        return True
```

**workflow.py修复点**：
```python
# 修复前（错误）
if checkpoint.is_chapter_completed(ticker, chapter_id):
    cached = checkpoint.get_chapter(chapter_id)
    if cached:  # 只检查是否存在
        return cached

# 修复后（正确）
if checkpoint.is_chapter_completed(ticker, chapter_id):
    cached = checkpoint.get_chapter(chapter_id)
    if cached and "[Placeholder]" not in cached:  # 检查内容质量
        return cached
    elif cached and "[Placeholder]" in cached:
        logger.info(f"第{chapter_id}章为placeholder，重新生成")
```

---

### 模式B：参数传递强制检查（解决Q0-4）

**铁律**：关键参数（WACC、永续增长率、EBIT利润率）不允许使用默认值。

```python
from functools import wraps
import inspect

def require_params(*param_names):
    """装饰器：强制检查参数是否传递"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            sig = inspect.signature(func)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            for name in param_names:
                if name not in bound.arguments:
                    raise ValueError(f"参数'{name}'未传递，不允许使用默认值")
                param = sig.parameters.get(name)
                if param and param.default is not inspect.Parameter.empty:
                    if bound.arguments[name] == param.default:
                        raise ValueError(f"参数'{name}'使用了默认值，必须显式传递")
            return func(*args, **kwargs)
        return wrapper
    return decorator

# 使用示例
@require_params('base_wacc', 'base_terminal_growth')
def run_depth_enhancement(chapters, financials, base_wacc, base_terminal_growth):
    ...
```

---

### 模式C：异常分级处理（解决Q0-5）

**铁律**：致命异常必须阻断流程，警告异常记录但继续，可恢复异常自动重试。

```python
from enum import Enum

class ExceptionLevel(Enum):
    FATAL = "fatal"        # 阻断流程
    WARNING = "warning"    # 记录+继续
    RECOVERABLE = "recoverable"  # 重试

class ExceptionHandler:
    EXCEPTION_CONFIG = {
        # 致命异常：阻断流程
        "GateChecksFailed": ExceptionConfig(level=ExceptionLevel.FATAL),
        "ValuationFailed": ExceptionConfig(level=ExceptionLevel.FATAL),
        "ReviewFailed": ExceptionConfig(level=ExceptionLevel.FATAL),
        # 警告异常：记录+继续
        "DepthEnhancementFailed": ExceptionConfig(level=ExceptionLevel.WARNING),
        # 可恢复异常：重试
        "LLMTimeout": ExceptionConfig(level=ExceptionLevel.RECOVERABLE, max_retries=3),
    }
```

---

### 模式D：统一估值假设层（解决Q1-1）

**铁律**：DCF和情景分析必须使用相同的FCF计算公式和参数。

```python
@dataclass
class ValuationAssumptions:
    """估值假设（DCF和情景分析共用）"""
    base_revenue: float
    revenue_growth_rates: List[float]  # 5年增速
    ebit_margins: List[float]  # 5年利润率
    wacc: float
    terminal_growth: float
    tax_rate: float = 0.25
    da_ratio: float = 0.03
    capex_ratio: float = 0.04

class UnifiedValuation:
    """统一估值计算"""
    
    def calc_fcf(self, revenue, ebit_margin, growth):
        """统一FCF公式（DCF和情景分析共用）"""
        ebit = revenue * ebit_margin
        nopat = ebit * (1 - self.assumptions.tax_rate)
        da = revenue * self.assumptions.da_ratio
        capex = revenue * self.assumptions.capex_ratio
        wc_change = revenue * growth * 0.02
        return nopat + da - capex - wc_change
    
    def validate_consistency(self, scenarios, tolerance=0.2):
        """验证DCF与情景分析一致性（差异<20%）"""
        dcf_value = self.calc_dcf()
        scenario_value = self.calc_scenario_weighted_average(scenarios)
        ratio = dcf_value / scenario_value if scenario_value > 0 else 0
        if abs(ratio - 1) > tolerance:
            raise ValueError(f"DCF与情景分析不一致：差异{abs(ratio-1)*100:.1f}%")
```

---

### 模式E：洞察审计禁用自动满分（解决Q1-4）

**铁律**：洞察审计100/100在三份报告中全部为假信号，必须禁用自动满分。

```python
class InsightAuditor:
    """洞察审计器（扣分制，非自动满分）"""
    
    def audit(self, chapters, review_result):
        audits = []
        for ch_num, content in chapters.items():
            audit = InsightAuditResult(chapter_num=ch_num, score=100)
            
            # 从审查结果中提取该章问题
            for issue in review_result.fatal_issues:
                if f"第{ch_num}章" in issue.location:
                    audit.issues.append(issue)
                    audit.score -= 30  # 致命问题扣30分
            
            for issue in review_result.important_issues:
                if f"第{ch_num}章" in issue.location:
                    audit.issues.append(issue)
                    audit.score -= 15  # 重要问题扣15分
            
            audit.score = max(0, audit.score)
            audits.append(audit)
        
        return audits
```

---

### 模式F：翻转阈值二分法+方向验证（解决Q1-3）

**铁律**：翻转阈值必须使用数值方法计算，禁止人工硬编码。

```python
def calc_revenue_flip(self, target_equity_value):
    """计算营收翻转点（二分法）"""
    low, high = self.base_revenue * 0.3, self.base_revenue * 3.0
    for _ in range(50):
        mid = (low + high) / 2
        equity = self.calc_equity_value(mid, ...)
        if equity > target_equity_value:
            high = mid
        else:
            low = mid
    
    flip_value = (low + high) / 2
    
    # 方向验证（关键！）
    if flip_value > self.base_revenue:
        direction = "up"
        impact = f"当营收升至{flip_value:.0f}亿元时，估值等于当前股价"
    else:
        direction = "down"
        impact = f"当营收降至{flip_value:.0f}亿元时，估值等于当前股价"
```

---

### 模式G：MarketData单一数据源+新鲜度检查（解决Q1-2）

**铁律**：全文股价必须来自单一数据源，禁止各模块自行硬编码。

```python
class MarketData:
    """市场数据（单一数据源+新鲜度检查）"""
    
    FRESHNESS_THRESHOLDS = {
        "stock_price": 24,      # 股价：24小时
        "financial_data": 720,  # 财务数据：30天
    }
    
    def __init__(self, ticker: str, market: str):
        self.ticker = ticker
        self.market = market
        self._snapshots: Dict[str, PriceSnapshot] = {}
    
    @property
    def currency(self) -> str:
        if self.market == "hk": return "HKD"
        elif self.market == "cn": return "RMB"
        elif self.market == "us": return "USD"
        return "USD"
    
    def check_freshness(self, data_type: str = "stock_price") -> bool:
        """检查数据新鲜度"""
        snapshot = self._get_snapshot("latest")
        timestamp = datetime.fromisoformat(snapshot.timestamp)
        age_hours = (datetime.now() - timestamp).total_seconds() / 3600
        threshold = self.FRESHNESS_THRESHOLDS.get(data_type, 24)
        if age_hours > threshold:
            logger.warning(f"数据过期: {age_hours:.1f}小时 > {threshold}小时")
            return False
        return True
    
    def set_snapshot(self, key: str, price: float, currency: str = None):
        """设置快照（统一入口）"""
        self._snapshots[key] = PriceSnapshot(
            price=price, currency=currency or self.currency,
            timestamp=datetime.now().isoformat(), source="manual",
        )
```

**workflow.py修复点**：
```python
# 修复前（错误）：各模块自行获取股价
# L2338: 当前股价20.22港元
# L407: 当前股价约25-28港元
# L3094: 当前股价33.3元

# 修复后（正确）：单一数据源
md = MarketData(ticker="00772.HK", market="hk")
md.set_snapshot("latest", price=20.22, currency="HKD")
current_price = md.get_price()  # 所有模块引用同一值
```

---

### 模式H：FlipThresholdCalculator二分法+收敛兜底（解决Q1-3，v3增强）

**铁律**：翻转阈值必须使用二分法计算，禁止人工硬编码，并有收敛失败兜底。

```python
@dataclass
class ConvergenceResult:
    """收敛结果"""
    converged: bool
    iterations: int
    final_value: float
    error_message: Optional[str] = None

class FlipThresholdCalculator:
    """翻转阈值计算器（二分法+方向验证+输入边界+收敛兜底）"""
    
    INPUT_BOUNDS = {
        "revenue": {"min": 0.1, "max": 10000},
        "ebit_margin": {"min": -0.5, "max": 0.5},
        "wacc": {"min": 0.03, "max": 0.25},
    }
    
    def _binary_search(self, target_value, variable, low, high, 
                       max_iterations=50, tolerance=0.001) -> ConvergenceResult:
        """二分法搜索（含收敛兜底）"""
        for iteration in range(max_iterations):
            mid = (low + high) / 2
            equity = self.calc_equity_value(mid, ...)
            if abs(equity - target_value) < tolerance:
                return ConvergenceResult(converged=True, iterations=iteration+1, final_value=mid)
            if equity > target_value: high = mid
            else: low = mid
        
        # 收敛失败兜底
        return ConvergenceResult(
            converged=False, iterations=max_iterations,
            final_value=(low + high) / 2,
            error_message=f"二分法在{max_iterations}次迭代后未收敛",
        )
```

**实测结果**（阅文集团）：
- 营收翻转点: 185.1亿元（up）✅ 收敛
- EBIT利润率翻转点: 9.7%（up）✅ 收敛
- WACC翻转点: 25.0%（up）⚠️ 未收敛但使用兜底值

---

### 模式I：InsightAuditor动态扣分+定期校准（解决Q1-4，v3增强）

**铁律**：洞察审计禁用自动满分，使用扣分制+动态规则。

```python
class InsightAuditor:
    """洞察审计器（扣分制+动态规则+定期校准）"""
    
    DEDUCTION_RULES = [
        DeductionRule(pattern="placeholder", deduction=30, description="包含占位符", category="完整性"),
        DeductionRule(pattern="xx", deduction=25, description="包含XX占位", category="完整性"),
        DeductionRule(pattern="数据不足", deduction=20, description="数据不足声明", category="数据质量"),
        DeductionRule(pattern="需要配置", deduction=25, description="需要配置提示", category="完整性"),
    ]
    
    FATAL_DEDUCTION = 30
    IMPORTANT_DEDUCTION = 15
    
    def audit(self, chapters, review_result=None):
        audits = []
        for ch_num, content in chapters.items():
            audit = InsightAuditResult(chapter_num=ch_num, score=100)
            
            # 应用动态扣分规则
            for rule in self.DEDUCTION_RULES:
                if rule.pattern in content.lower():
                    audit.score -= rule.deduction
                    audit.deduction_details.append({...})
            
            # 从审查结果中扣分
            if review_result:
                for issue in review_result.fatal_issues:
                    if f"第{ch_num}章" in issue.location:
                        audit.score -= self.FATAL_DEDUCTION
            
            audit.score = max(0, audit.score)
            audits.append(audit)
        return audits
```

**实测结果**（阅文集团）：
- 第1章（正常内容）: 100分
- 第2章（包含placeholder）: 45分
- 第3章（包含XX占位）: 75分

---

### 模式J：ROICChecker强制回应（解决Q3-3）

**铁律**：ROIC<WACC时，看多结论必须强制回应价值毁灭信号。

```python
class ROICChecker:
    """ROIC检查器"""
    
    @staticmethod
    def generate_prompt_injection(roic: float, wacc: float) -> str:
        """生成prompt注入"""
        if roic >= wacc:
            return ""
        return f"""
⚠️ 重要提示：ROIC({roic:.1%}) < WACC({wacc:.1%})，存在价值毁灭信号。
在给出看多结论时，必须明确回应：
1. 为什么ROIC<WACC的情况下仍看多？
2. 什么条件下ROIC会超过WACC？
3. 如果ROIC持续<WACC，投资结论如何调整？
如果无法合理回应上述问题，应给出中性或看空结论。
"""
```

---

## 三、HeavySkill审查结论（K=8, 51319 tokens）

### ⚠️ 铁律：HeavySkill审查先行（Verified 2026-08-08）

**当用户要求"按要求修改方案"或"立即实施"时，必须先用HeavySkill K=8审查方案，再实施。**

**小鹏汽车实测案例**：
- 初始方案（未经审查）：放宽结构化预检阈值≥60→≥40、使用营业支出×0.7估算毛利率、使用signal.SIGALRM超时
- HeavySkill审查发现：这些方案会**降低**买方报告专业性
- 修正后方案：保持≥60阈值、仅营业成本计算、使用threading.Timer

**审查→修正→实施流程**：
```
1. 提出解决方案
2. HeavySkill K=8审查（不降低专业性原则）
3. 根据审查结论修正方案
4. 按HGF流程实施
5. 端到端测试验证
```

**Pitfall: 跳过HeavySkill审查直接实施**
- **症状**: 方案实施后发现会降低报告质量
- **根因**: 未经过独立审查，方案中的风险未被识别
- **修复**: 任何qual工作流修改方案，必须先经HeavySkill K=8审查

### 综合判定

**在落实补充措施的前提下，该方案可以长效解决流程执行问题，保证报告真实、严谨、务实。**

### 评估统计

| 评估结果 | 数量 | 占比 |
|----------|------|------|
| 有效 | 14个 | 67% |
| 部分有效 | 7个 | 33% |
| 无效 | 0个 | 0% |

### 仍需补充的高优先级改进

1. **F1假设合理性审计**：增加中间变量比对和差异归因机制
2. **I6权重透明化**：公开权重依据、定期回测敏感性
3. **P0-5降级防护**：通过继承体系、CI规则禁止裸异常

---

## 五、v3架构组件（HGF Gate 1-5实施通过，2026-08-02）

### 5.1 已实施组件清单

| Gate | 组件 | 文件路径 | 测试状态 |
|------|------|----------|----------|
| Gate 1 | ModuleLoader | `finance/quality/v3/module_loader.py` | ✅ |
| Gate 1 | ContentValidator | `finance/quality/v3/content_validator.py` | ✅ |
| Gate 1 | require_params | `finance/quality/v3/params_checker.py` | ✅ |
| Gate 1 | ExceptionHandler | `finance/quality/v3/exception_handler.py` | ✅ |
| Gate 2 | ValuationAssumptions | `finance/valuation/assumptions.py` | ✅ |
| Gate 2 | UnifiedValuation | `finance/valuation/unified.py` | ✅ |
| Gate 3 | DataMappingRegistry | `finance/data/mapping.py` | ✅ |
| Gate 3 | DataContext | `finance/data/context.py` | ✅ |
| Gate 4 | DecisionAggregator | `finance/decision/aggregator.py` | ✅ |
| Gate 2 | MarketData | `finance/market_data.py` | ✅ |
| Gate 2 | FlipThresholdCalculator | `finance/valuation/flip_threshold.py` | ✅ |
| Gate 2 | InsightAuditor | `finance/quality/v3/insight_audit.py` | ✅ |
| Gate 2 | ROICChecker | `finance/quality/v3/roic_checker.py` | ✅ |

### 5.2 ValuationAssumptions+UnifiedValuation（解决Q1-1，v3增强）

**铁律**：DCF和情景分析必须使用相同的FCF公式、假设层、差异归因。

```python
@dataclass
class ValuationAssumptions:
    """估值假设（共用参数层+假设审计）"""
    base_revenue: float
    revenue_growth_rates: List[float]
    ebit_margins: List[float]
    wacc: float
    terminal_growth: float
    tax_rate: float = 0.25
    da_ratio: float = 0.03
    capex_ratio: float = 0.04
    audits: Dict[str, AssumptionAudit] = field(default_factory=dict)

    def validate_values(self) -> List[str]:
        """验证假设值合理性"""
        errors = []
        if self.wacc < 0.03 or self.wacc > 0.25:
            errors.append(f"WACC {self.wacc} 超出合理范围")
        if self.wacc <= self.terminal_growth:
            errors.append(f"WACC ({self.wacc}) 必须大于永续增长率 ({self.terminal_growth})")
        return errors

class UnifiedValuation:
    """统一估值+差异归因"""

    def validate_consistency(self, scenarios, tolerance=0.2):
        """验证DCF与情景分析一致性"""
        dcf_value = self.calc_dcf()
        scenario_value = self.calc_scenario_weighted_average(scenarios)
        ratio = dcf_value / scenario_value if scenario_value > 0 else 0
        attribution = self._attribute_difference(dcf_value, scenario_value, scenarios)
        if abs(ratio - 1) > tolerance:
            logger.warning(f"差异超过阈值: {abs(ratio-1)*100:.1f}%")
            return {"passed": False, "attribution": attribution, "action_required": "人工复核"}
        return {"passed": True, "attribution": attribution}

    def _attribute_difference(self, dcf_value, scenario_value, scenarios):
        """差异归因（中间变量比对）"""
        dcf_tv = self.dcf_intermediates.get("pv_terminal", 0)
        scenario_tv = sum(
            self.scenario_intermediates.get(name, {}).get("pv_terminal", 0) * weight
            for name, weight in self.assumptions.scenario_weights.items()
        )
        attributions = [IntermediateVariable(
            name="终值", dcf_value=dcf_tv, scenario_value=scenario_tv,
            difference=dcf_tv - scenario_tv, explanation="终值差异",
        )]
        max_attr = max(attributions, key=lambda x: abs(x.difference))
        return DifferenceAttribution(
            total_difference=dcf_value - scenario_value,
            attributions=attributions,
            conclusion=f"主要差异来源: {max_attr.name}（差异{max_attr.difference:.1f}元）",
        )
```

**实测结果**（阅文集团 00772.HK，2026-08-02）：
- 修复前: DCF=-7.3元, 情景基准=3.5元（3.3倍矛盾）
- 修复后: DCF=18.24元, 情景加权=17.12元（差异7%，通过）

**估值参数**：
- WACC: 8.1%（CAPM: Rf=2.3%, Beta=1.2, ERP=5.5%）
- 永续增长率: 2.0%
- 基础营收: 80.07亿元
- 净负债: -127.81亿元（净现金公司）
- 总股本: 10.12亿股

**翻转阈值实测**：
- 营收翻转点: 185.1亿元（up，当前80.07亿的2.3倍）
- EBIT利润率翻转点: 9.7%（up，当前5.0%）
- WACC翻转点: 25.0%（up，当前8.1%）

**端到端测试结果**（2026-08-02）：
| 测试项 | 结果 | 关键数据 |
|--------|------|----------|
| 完整估值流程 | ✅ 通过 | DCF=18.24元 |
| 一致性验证 | ✅ 通过 | 差异7% |
| 翻转阈值 | ✅ 通过 | 方向正确 |
| 市场数据 | ✅ 通过 | 20.22 HKD |
| 洞察审计 | ✅ 通过 | 扣分制 |
| ROIC检查 | ✅ 通过 | -3.8%<8.1% |
| 决策聚合 | ✅ 通过 | 中性 |
| 内容验证 | ✅ 通过 | 语义规则 |
| 异常处理 | ✅ 通过 | 分级处理 |

### 5.3 ModuleLoader+启动自检（解决Q0-1，v3增强）

```python
class ModuleLoader:
    """模块加载器（动态路径+启动自检+最小必备白名单）"""
    MINIMAL_REQUIRED_CHECKS = ["gate_checks", "review_integrator",
                                "content_validator", "exception_handler"]

    @classmethod
    def startup_self_check(cls):
        """启动自检：验证所有必需模块"""
        path_errors = cls.validate_paths()
        check_errors = cls.validate_minimal_checks()
        if path_errors or check_errors:
            raise RuntimeError(f"模块自检失败: {path_errors + check_errors}")
```

### 5.4 ContentValidator+语义验证（解决Q0-3/Q2-3，v3增强）

```python
class ContentValidator:
    """内容验证器（模式匹配+长度+语义一致性）"""
    SEMANTIC_RULES = [
        {"name": "营收增长与描述一致",
         "pattern": r'营收.*?增长.*?(-?\d+\.?\d*)%',
         "check": lambda m: float(m.group(1)) > 0,
         "error": "描述'增长'但百分比为负"},
        {"name": "净利润为正时不应描述亏损",
         "pattern": r'净利润.*?(-?\d+\.?\d*)\s*亿.*?亏损',
         "check": lambda m: float(m.group(1)) < 0,
         "error": "净利润为正但描述为亏损"},
    ]
```

### 5.5 QualException继承体系（解决Q0-5，v3增强）

```python
class QualException(Exception):
    """Qual流程异常基类"""
    def __init__(self, message, level=ExceptionLevel.FATAL, context=None):
        super().__init__(message)
        self.level = level
        self.context = context or {}

class FatalException(QualException): pass
class WarningException(QualException): pass
class RecoverableException(QualException): pass

class ModuleLoadException(FatalException): pass
class ValidationException(FatalException): pass
class ValuationException(FatalException): pass
class GateCheckException(FatalException): pass
```

---

## 六、HeavySkill审查迭代方法论

### 6.1 三轮审查收敛模式

本次qual v3方案经3轮HeavySkill K=8审查迭代：

| 轮次 | 版本 | 综合评分 | 关键改进 |
|------|------|----------|----------|
| 1 | v1 | 80/100 | 基础方案，F1/I6/P0-5粒度不足 |
| 2 | v2 | 85/100 | 细化F1假设审计、I6裁决算法、P0-5异常分级 |
| 3 | v3 | 88/100 | 增加差异归因、权重回测、QualException继承体系 |

### 6.2 审查驱动的改进模式

**关键发现**：HeavySkill每轮审查发现的问题直接转化为下一轮改进输入。

```
审查报告问题清单 → 分类（致命/重要/建议）→ 转化为技术方案 → 实施 → 重新审查
```

**v3新增的审查驱动改进**：
1. F1假设合理性审计 → AssumptionAudit + DifferenceAttribution
2. I6权重透明化 → WeightJustification + BacktestResult + 专家覆写
3. P0-5降级防护 → QualException继承体系 + CI规则
4. 度量指标审计 → MetricAudit（目的性+关联性校准）
5. P0-3语义验证 → _validate_semantic_consistency

---

## 七、第三方审查Skill增强模式

### 7.1 问题→检查项转化

审查报告发现的问题应系统性转化为skill检查项：

```python
class IssueTransformer:
    ISSUE_PHASE_MAPPING = {
        "F1": "phase_2",  # 估值双方法矛盾
        "F2": "phase_2",  # 当前股价不一致
        "F3": "phase_2",  # 翻转阈值错误
        "F4": "phase_5_5",  # 洞察审计假信号
    }
    ISSUE_CHECK_MAPPING = {
        "F1": "DCF vs 情景期望值一致性",
        "F2": "当前股价一致性",
        "F3": "翻转阈值方向验证",
        "F4": "洞察审计反向举证",
    }
```

### 7.2 持续改进闭环

```
审查报告 → 问题提取 → 转化为skill检查项 → 更新skill → 下次审查自动检查
```

---

## 八、v3组件集成模式（2026-08-02验证）

### 8.0 集成检查清单（HGF Gate 1 执行模式）

当需要将多个v3组件集成到workflow.py/quality_enhancer.py时，严格按以下步骤执行：

**Step 1: 修复语法错误**
- 检查所有try-except块是否正确闭合
- 常见错误：多个连续try块缺少except，导致IndentationError

**Step 2: 添加HAS_*导入标志**
```python
# 标准模式（必须遵循）
try:
    from .module.path import ClassName
    HAS_CLASS_NAME = True
except ImportError:
    HAS_CLASS_NAME = False
```

**Step 3: 在关键代码点集成**
- 启动自检：`run_analysis()`开头
- 断点恢复：`_write_chapters()`中checkpoint检查后
- 异常处理：`except Exception as e:`块中
- 质量增强：`Step 4.5`中调用quality_enhancer后

**Step 4: 验证（Gate 2-4）**
- Gate 2: 端到端测试（组件导入+功能调用）
- Gate 3: 功能完整性（语法检查+集成点统计）
- Gate 4: 代码质量门禁（语法+导入+集成完整性）

### 8.1 Pitfall: 多try块语法错误（Verified 2026-08-02）

**症状**：workflow.py导入部分出现SyntaxError/IndentationError

**根因**：多个连续的try块缺少except闭合：
```python
# ❌ 错误：3个连续try块没有except
try:
    from .module_a import A
try:
    from .module_b import B
try:
    from .module_c import C
    HAS_C = True
except ImportError:
    HAS_C = False
```

**修复**：每个try必须有对应的except：
```python
# ✅ 正确：每个try块独立闭合
try:
    from .module_a import A
    HAS_A = True
except ImportError:
    HAS_A = False

try:
    from .module_b import B
    HAS_B = True
except ImportError:
    HAS_B = False
```

**验证方法**：`python3 -m py_compile finance/workflow.py`

### 8.2 Pitfall: ContentValidator断点恢复位置（Verified 2026-08-02）

**集成位置**：`_write_chapters()`函数中，在checkpoint恢复检查之后

```python
# 正确集成位置
if checkpoint and checkpoint.is_chapter_completed(ctx.ticker, chapter_id):
    cached = checkpoint.get_chapter(chapter_id)
    if cached and "[Placeholder]" not in cached:
        # v3: ContentValidator验证（在这里集成）
        if HAS_CONTENT_VALIDATOR:
            try:
                validation = ContentValidator.validate(cached, str(chapter_num))
                if not validation.passed:
                    logger.warning(f"内容验证失败: {validation.errors}，重新生成")
                    continue
            except Exception as e:
                logger.warning(f"ContentValidator验证失败: {e}，使用原内容")
        chapters[chapter_num] = cached
        continue
```

**注意**：ContentValidator的MIN_CONTENT_LENGTH=100，测试内容需超过此阈值

### 8.3 Pitfall: ExceptionHandler集成模式（Verified 2026-08-02）

**集成位置**：章节写作的`except Exception as e:`块中

```python
except Exception as e:
    if HAS_EXCEPTION_HANDLER:
        try:
            ExceptionHandler.handle(e, context={"chapter_num": chapter_num, "ticker": ctx.ticker})
        except FatalException:
            logger.error(f"致命错误: {e}")
            raise  # 致命异常必须抛出
        except WarningException as we:
            logger.warning(f"警告: {we}")  # 警告记录但继续
    else:
        logger.error(f"失败: {e}")
    error_content = _build_insufficient_data_response(chapter_num, ctx, str(e))
    chapters[chapter_num] = error_content
```

### 8.4 DecisionAggregator第10章集成（Verified 2026-08-02）

**集成位置**：`_generate_decision_chapter()`函数末尾，在保存断点之后

```python
# 保存断点后集成DecisionAggregator
if checkpoint:
    checkpoint.save_chapter(ctx.ticker, chapter_id, content)

if HAS_DECISION_AGGREGATOR:
    try:
        from .decision.aggregator import DecisionAggregator, ChapterJudgment
        judgments = []
        for num, ch_content in chapters.items():
            if num < 10:
                # 简单关键词判断
                if "看多" in ch_content or "买入" in ch_content:
                    judgment = "看多"
                elif "看空" in ch_content or "卖出" in ch_content:
                    judgment = "看空"
                else:
                    judgment = "中性"
                judgments.append(ChapterJudgment(chapter_num=num, judgment=judgment, confidence=50))
        if judgments:
            aggregation = DecisionAggregator.aggregate(judgments)
    except Exception as e:
        logger.warning(f"DecisionAggregator聚合失败: {e}")
```

### 8.5 集成完整性检查清单

完成所有组件集成后，运行以下验证：

```python
# 1. 语法检查
python3 -m py_compile finance/workflow.py
python3 -m py_compile finance/quality_enhancer.py

# 2. 组件导入验证
python3 -c "from finance.workflow import HAS_MODULE_LOADER, HAS_CONTENT_VALIDATOR, ...; assert all([HAS_MODULE_LOADER, ...])"

# 3. 集成点统计
# 每个组件应在workflow.py中有4-7处引用
```

### 8.6 DataMappingRegistry数据获取流程集成（Verified 2026-08-02）

**集成位置**：`_collect_data()`函数开头，在Wind数据处理之前

```python
if HAS_DATA_MAPPING:
    try:
        from .data.mapping import DataMappingRegistry
        registry = DataMappingRegistry()
        if wind_data:
            mapping_result = registry.validate_mappings(wind_data)
            if mapping_result.get("warnings"):
                logger.warning(f"字段映射警告: {mapping_result['warnings']}")
    except Exception as e:
        logger.warning(f"DataMappingRegistry校验失败: {e}")
```

### 8.7 FactTable/ComparableConfig/MarketData/FlipThreshold/InsightAuditor批量集成（Verified 2026-08-02）

**集成位置**：Step 4.5b，在quality_enhancer调用之后。5个组件各自独立try-except，降级只warning不阻断。

### 8.8 Step 7问题转化流程（Verified 2026-08-02）

**集成位置**：Step 6之后、返回结果之前

自动检测placeholder（P0）和币种混用（P1），输出`result["review_issues"]`

### 8.9 QualMetricsTracker 10个核心指标（Verified 2026-08-02）

| 指标 | 目标值 | 关联性 |
|------|--------|--------|
| gate_checks_execution_rate | 100% | 0.90 |
| placeholder_rate | 0% | 0.95 |
| dcf_scenario_difference | <20% | 0.75 |
| flip_threshold_direction_accuracy | 100% | 0.85 |
| insight_audit_score | 非100/100 | 0.70 |

完整10个指标详见 `references/v3-integration-patterns-2026-08-02.md`

### 8.10 Pitfall: 文件存在≠已接入（"90%陷阱"）（Verified 2026-08-02）

**症状**：所有HAS_*标志为True，v3目录下文件齐全，但某些组件在workflow.py中零调用。

**根因**：创建文件+添加HAS_*导入标志后，未在workflow.py的实际业务逻辑中添加调用点。HAS_*只验证"能不能导入"，不验证"有没有用到"。

**案例**：`review_integrator.py` 存在于 `quality/v3/`，但 `grep "review_integrator\|ReviewIntegrator" workflow.py` 返回空——文件存在但从未接入。

**验证方法（必须在声称"集成完成"前执行）**：
```bash
# 对每个v3组件，检查workflow.py中是否有调用点（不只是导入）
for comp in review_integrator content_validator exception_handler insight_audit roic_checker; do
    count=$(grep -c "$comp\|$(echo $comp | sed 's/_/ /g' | sed 's/\b\(.\)/\u\1/g' | sed 's/ //g')" ~/.hermes/tools/finance/workflow.py 2>/dev/null)
    if [ "$count" -eq 0 ]; then
        echo "❌ $comp: 文件存在但workflow.py中零调用"
    else
        echo "✅ $comp: $count 处引用"
    fi
done
```

**区分三个层次**：
| 层次 | 验证方法 | 含义 |
|------|----------|------|
| 文件存在 | `ls quality/v3/xxx.py` | 代码已写 |
| 可导入 | `HAS_XXX = True` | 依赖链通 |
| 已接入 | `grep -c "xxx" workflow.py > 0` | 业务逻辑中真正调用 |

**修复**：找到正确的集成点（参考8.2-8.8各组件的集成位置），添加调用代码。

---

### 8.11 16组件完整集成地图（Verified 2026-08-02）

| 阶段 | 组件数 | workflow.py行数 |
|------|--------|-----------------|
| Phase 1 核心集成 | 5个 | 3762行 |
| Phase 2 数据一致性 | 9个 | +697行 |
| Phase 3 Skill增强 | 2个+度量 | 2662行总计 |

完整集成地图详见 `references/v3-integration-patterns-2026-08-02.md`

---

### 8.12 Step 4.5 质量增强死循环 — 三连环卡死 (Verified 2026-08-05)

**症状**: `run_analysis()` 在 Step 4.5 质量增强阶段卡死，运行28分钟无新输出。所有章节结构化预检失败（score=40-55），LLM修复返回"LLM 返回内容异常，保留原内容"，数据修复模块输出"无法修复 营业收入：缺少正确值"/"无法修复 毛利率：缺少正确值"后进入死循环。

**根因（三连环，代码级定位）**:

**环1: LLM修复内容长度检查过严** (`quality/repairer.py` L216)
```python
# 当前代码：修复内容必须 > 原始内容的50%
if repaired and len(repaired.strip()) > len(current_content) * 0.5:
    current_content = repaired
else:
    logger.warning(f"修复 {chapter_id} 第 {round_num} 轮: LLM 返回内容异常")
```
- **问题**: LLM返回精简修复（如只修复关键段落）时长度不足50%，被判定为"异常"
- **修复**: 改为 `len(repaired.strip()) > 100` 或增加"如果修复了问题则接受"的逻辑

**环2: Wind数据字段名不匹配** (`data_repair.py` L575-592)
```python
# _build_correct_values() 期望的字段名：
if '年营业总收入' in income:      # ← 代码期望
    correct_values['营业收入'] = vals[-1]

# 但调用方传入的字段名：
wind_data = {"income": {"年营业收入": [...]}}  # ← 实际传入
```
- **问题**: 字段名`年营业收入`≠`年营业总收入`，导致`correct_values`为空字典
- **影响**: 所有一致性问题都无法修复，日志刷屏"无法修复 XXX：缺少正确值"
- **修复**: 统一字段名，或在`_build_correct_values`中兼容两种写法

**环3: 辩论机制无超时保护** (`quality_enhancer.py` L132-156)
```python
for ch_num in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
    debate = run_debate(...)  # 每章3次LLM调用，无超时
```
- **问题**: 9章×3次=27次LLM调用，任一次超时都会导致整体卡死
- **修复**: 增加 `try/except TimeoutError` 或设置 `enable_debate=False` 作为降级

**连锁效应**:
```
Step 4 结构化预检失败 → LLM修复失败(长度检查) → 保留原始内容
  → Step 4.5 数据修复失败(字段名不匹配) → 日志刷屏
  → Step 4.5 辩论机制启动 → 27次LLM调用 → 卡死
```

**已实施修复（4个，2026-08-05验证）**:

| # | 文件 | 修复 | 效果 |
|---|------|------|------|
| 1 | `quality/repairer.py` L216 | 长度检查从 `> len(current_content)*0.5` 改为 `> 200` | LLM修复不再被误判为"异常" |
| 2 | `data_repair.py` L575 | `_build_correct_values` 增加fallback链：`['年营业总收入', '年营业收入', '营业收入', '总收入']` | 营业收入正确映射；毛利率优先直接获取，否则从毛利计算 |
| 3 | `quality_enhancer.py` L128 | 辩论机制增加 `concurrent.futures.ThreadPoolExecutor` 120s超时 | 单章辩论超时后跳过，不阻塞后续章节 |
| 4 | `llm_caller.py` L73 | `openai.OpenAI(timeout=60.0)` | API调用60秒超时，配合修复3真正释放线程 |

**修复效果**:

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| "LLM 返回内容异常" | 所有章节×3轮 | 0次 |
| "无法修复 营业收入" | 8次 | 0次 |
| "无法修复 毛利率" | 8次 | 1次（Wind无此字段，预期行为） |
| 进程卡死 | 28分钟无输出 | 正常推进 |

**关键教训**:
1. **HTTP timeout必须在客户端设置**: `concurrent.futures` 超时只能控制主流程，底层HTTP请求仍在等待。必须在 `openai.OpenAI(timeout=...)` 设置才能真正释放线程。
2. **毛利率不能用营业支出计算**: `年营业支出` 包含经营开支，不等于营业成本。需要直接获取毛利率字段，或从毛利计算。
3. **Wind数据字段名必须有fallback链**: 不同API返回不同字段名，不能硬编码单一字段名。

**验证方法**:
```bash
cd ~/.hermes/tools/finance
python3 -c "
from data_repair import _build_correct_values
wind = {'income': {'年营业收入': [306.76, 408.66, 767.20]}}
print(_build_correct_values(wind))
# 期望: {'营业收入': 767.2}
"
```

**⚠️ 关键更新（2026-08-06验证）**: 修复#3（`concurrent.futures`超时）**实际无效**。即使4个修复全部应用，进程仍卡死24+分钟。原因：`future.result(timeout=120)`只控制主线程等待，底层线程继续运行。`openai.OpenAI(timeout=60.0)`应能释放线程，但辩论机制仍卡死（可能是streaming响应或连接池问题）。

**唯一可靠修复**: 在workflow.py中禁用辩论：
```python
chapters, quality_result = enhance_report_quality(
    ...
    enable_debate=False,  # 辩论机制已禁用（会导致进程卡死）
    ...
)
```

**辩论机制卡死的架构缺陷**:
1. `debate_coordinator.py`中3次LLM调用（Bull/Bear/PM）无独立超时
2. `concurrent.futures`超时无法kill底层线程
3. 9章×3调用=27次LLM调用，任何一次卡住都会阻塞整个流程
4. 即使OpenAI客户端设了timeout，streaming响应或连接池问题仍可能导致卡死

**临时绕过**: 如果工作流卡在 Step 4.5 超过5分钟，手动终止并基于已生成的章节内容手动组装报告。小鹏汽车（9868.HK）分析实测：手动终止后基于Wind数据+年报直接生成10+1章报告，耗时约10分钟。

### 8.13 run_analysis() 参数签名 — 无 wind_valuation 参数 (Verified 2026-08-05)

**症状**: `run_analysis(ticker="9868.HK", wind_valuation={...})` 报错 `TypeError: run_analysis() got an unexpected keyword argument 'wind_valuation'`

**根因**: `run_analysis()` 的签名是 `(ticker, company_name, market, wind_data, filing_data, search_results, llm_caller, output_dir, shares)`，不包含 `wind_valuation` 参数。

**正确做法**:
```python
result = run_analysis(
    ticker="9868.HK",
    company_name="小鹏汽车",
    market="hk",
    wind_data=wind_data,  # 估值数据通过 wind_data 传递
    llm_caller=llm_caller,
    shares=19.56,
    output_dir="/path/to/output",
)
```

**教训**: 调用 `run_analysis()` 前必须用 `inspect.signature()` 确认参数签名。

### 8.14 qual-analysis-workflow 独立项目 vs 主工作流 (Verified 2026-08-05)

**区别**: `~/projects/qual-analysis-workflow/` 是从 qual-analysis skill 质量层提取的独立项目，**不是**主工作流 `~/.hermes/tools/finance/workflow.py`。

| 项目 | 路径 | 功能 |
|------|------|------|
| 主工作流 | `~/.hermes/tools/finance/workflow.py` | 完整11章报告生成+审计修复+质量增强 |
| 独立项目 | `~/projects/qual-analysis-workflow/` | 质量保证框架（formulas/validators/DCF/SOTP/审查集成） |

**关键区别**:
- 独立项目的 `QualWorkflow` 类是简化版（使用硬编码示例数据）
- 主工作流的 `run_analysis()` 使用真实 Wind MCP + 财报数据
- 两者的 `_quality_review` 实现不同：独立项目用规则匹配，主工作流用 LLM-as-Judge

**何时用哪个**:
- 分析个股 → 用主工作流 `run_analysis()`
- 测试质量模块 → 用独立项目的 pytest
- 改进估值公式 → 修改独立项目的 `quality/formulas.py`，验证后移植到主工作流

### 8.15 辩论机制(debate_coordinator)架构性卡死 — 必须禁用 (Verified 2026-08-06)

**症状**: Step 4.5质量增强阶段卡死，进程运行24+分钟无新输出。即使应用了8.12中的4个修复（repairer长度检查、data_repair字段映射、concurrent.futures超时、OpenAI timeout），问题依然存在。

**根因**: `debate_coordinator.py`的架构设计有根本缺陷，无法通过简单超时修复。

**架构分析**:
```
quality_enhancer.py Stage 3:
  for ch_num in [1..9]:           # 9个章节串行
    run_debate(ch_num, ...)       # 每章3次LLM调用
      ├─ llm_caller("bull", ...)  # 调用1: 看多论点
      ├─ llm_caller("bear", ...)  # 调用2: 看空质疑
      └─ llm_caller("pm", ...)    # 调用3: PM综合判断
```

**为什么concurrent.futures超时无效**:
1. `future.result(timeout=120)` 只控制主线程的等待时间
2. 底层线程中的LLM调用继续运行，不受超时影响
3. Python的GIL使得线程无法被强制终止
4. 即使OpenAI客户端设了`timeout=60.0`，streaming响应或连接池问题仍可能导致卡死

**Verified Fix (2026-08-08)**: 使用 `threading.Timer` + daemon threads 替代 `signal.SIGALRM` 和 `concurrent.futures`

```python
# debate_coordinator.py
import threading

class LLMTimeoutError(Exception):
    """LLM调用超时异常"""
    pass

def llm_caller_with_timeout(
    llm_caller: Callable[[str, str], str],
    chapter_name: str,
    prompt: str,
    timeout_seconds: int = 60,
) -> str:
    """带超时保护的LLM调用（跨平台安全）"""
    result = [None]
    exception = [None]
    
    def target():
        try:
            result[0] = llm_caller(chapter_name, prompt)
        except Exception as e:
            exception[0] = e
    
    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout=timeout_seconds)
    
    if thread.is_alive():
        raise LLMTimeoutError(f"LLM调用超时({timeout_seconds}s): {chapter_name}")
    
    if exception[0]:
        raise exception[0]
    
    return result[0]

# run_debate 中使用 llm_caller_with_timeout
def run_debate(..., llm_timeout_seconds=60):
    try:
        result.bull_argument = llm_caller_with_timeout(
            llm_caller, f"bull_ch{chapter_num}", bull_prompt, llm_timeout_seconds
        )
    except LLMTimeoutError as e:
        result.degraded = True
        result.warnings.append(f"Bull超时: {e}")
        result.pm_synthesis = chapter_content
        return result
```

**quality_enhancer.py 修改**:
```python
# 移除 concurrent.futures，直接调用 run_debate
from .debate_coordinator import run_debate

LLM_TIMEOUT = 60

debate = run_debate(
    chapter_num=ch_num,
    chapter_title=title,
    chapter_content=chapters[ch_num],
    base_valuation_summary=valuation_summary,
    llm_caller=llm_caller,
    llm_timeout_seconds=LLM_TIMEOUT,  # 超时保护在内部实现
)
```

**⚠️ 关键**: `signal.SIGALRM` 不能用于多线程环境（只在主线程有效，Windows不支持）。必须使用 `threading.Thread` + `join(timeout)` 模式。

**为什么不能简单修复**:
1. `signal.SIGALRM`只在主线程有效，`run_debate`在子线程中运行
2. `threading.Thread`没有强制终止机制（Python设计限制）
3. `multiprocessing`可以强制终止，但需要重构整个调用链
4. 辩论机制的3次LLM调用之间有依赖关系（Bear需要Bull的输出），无法并行

**唯一可靠修复**: 禁用辩论机制
```python
# workflow.py L2350
chapters, quality_result = enhance_report_quality(
    chapters=chapters,
    financials=ctx.wind.__dict__ if hasattr(ctx.wind, '__dict__') else {},
    wind_valuation=wind_valuation_data,
    company_name=company_name,
    ticker=ticker,
    shares=shares,
    fiscal_year=2025,
    llm_caller=llm_caller,
    enable_debate=False,  # 辩论机制已禁用（会导致进程卡死）
    enable_valuation=True,
    enable_depth=True,
)
```

**辩论机制的实际价值**: 辩论机制（Bull→Bear→PM）是报告质量增强功能，不是核心功能。禁用后：
- 报告仍能正常生成（11章完整）
- 估值仍能正常计算（DCF+SOTP）
- 数据修复仍能正常执行
- 唯一损失是"预期差分析"和"确信度评分"

**未来修复方向**: 如果需要恢复辩论机制，需要重构为：
1. 使用`multiprocessing.Process`代替`threading.Thread`，支持`process.terminate()`
2. 或者将辩论机制改为异步任务，通过消息队列控制超时
3. 或者在`debate_coordinator.py`的每次LLM调用前设置`signal.SIGALRM`（仅限主线程）

**验证方法**:
```bash
# 验证辩论已禁用
grep "enable_debate" ~/.hermes/tools/finance/workflow.py
# 期望: enable_debate=False

# 验证进程不再卡死
cd ~/.hermes && python3 -c "
from tools.finance.workflow import run_analysis
from tools.finance.llm_caller import create_deepseek_caller
import time
start = time.time()
# ... 运行分析
print(f'耗时: {time.time()-start:.0f}秒')
# 期望: <300秒（不含辩论）
"
```

---

## 八B、LLM输出格式合规保障模式（Verified 2026-08-08）

当qual工作流要求LLM按特定格式生成内容，但LLM经常使用变体格式时，使用4层保障机制：
1. **降低temperature**（0.7→0.2，实测0.2比0.3更好）
2. **System Prompt格式约束**（明确禁止###，列出禁止变体列表）
3. **User Prompt格式示例**（完整示例+⚠️警告"绝对禁止使用###"）
4. **后处理验证+重试**（structural_check+格式修正提示，最多3次重试）

**实测数据（小鹏汽车9868.HK, 2026-08-08）**：
| 措施 | 格式遵从度(##) | 结构化预检通过率 |
|------|----------------|-----------------|
| 无措施 | ~30% | ~20% |
| 仅降低temperature(0.3) | ~50% | ~40% |
| 4层叠加(0.2+禁止###+示例+重试3次) | 75% | ~75% |

**关键教训**：
- 单一措施不够，必须4层叠加
- 不应放松预检阈值（≥60→≥40），而应扩展格式变体patterns
- temperature=0.2比0.3效果更好（格式遵从度+25%）
- 必须在prompt中明确写"绝对禁止使用###"，仅写"必须使用##"不够
- 重试时在prompt中追加上次失败的具体问题（哪些小节缺失）

详细实现和实测数据见 `references/llm-format-compliance-pattern-2026-08-08.md`。

---

## 八C、审查环节只检查"形式"不检查"实质"（Verified 2026-08-08，小鹏汽车实测）

> **核心发现**：qual工作流的审查环节只检查"是否有必需小节"，不检查"小节内容是否正确"。
> 这导致错误内容可以通过所有审查，直到人工批判性审阅才发现致命问题。

### 问题对照表

| 问题类型 | 审查环节 | 是否能捕获 | 根因 |
|----------|----------|------------|------|
| F1: 经营现金流正负打架 | 结构化预检/洞察审计 | ❌ 不能 | 只检查格式，不跨章节比对 |
| F2: 估值模型与叙述矛盾 | 情景分析/洞察审计 | ❌ 不能 | 模板生成，不验证逻辑一致性 |
| F3: 翻转阈值虚构数 | 翻转阈值计算 | ❌ 不能 | 使用硬编码模板数据(1427.8亿) |
| F4: 三套估值不收敛 | 估值模块 | ❌ 不能 | 独立计算，不比对 |
| I1: 总资产口径打架 | 数据一致性检查 | ❌ 不能 | 没有跨章节比对 |
| I3: None%占位符 | 占位符检查 | ⚠️ 有但未捕获 | 检查逻辑不完整 |
| I5: 日期锚点混乱 | 日期锚点检查 | ❌ 不能 | 没有此环节 |
| I6: 审计分项打分反向 | 洞察深度审计 | ❌ 不能 | 只检查是否有洞察，不检查正确性 |

### 缺失的5个审查技能（P0，必须新增）

| 缺失技能 | 功能 | 应捕获的问题 |
|----------|------|--------------|
| **cross_chapter_consistency** | 跨章节一致性检查 | F1: 经营现金流正负打架 |
| **logic_consistency_check** | 逻辑一致性检查 | F2: 估值模型与叙述矛盾 |
| **data_reasonableness_check** | 数据合理性验证 | F3: 翻转阈值虚构数(1427.8亿比实际高3-4倍) |
| **valuation_arbitrator** | 估值仲裁 | F4: 三套估值方法互不收敛 |
| **date_anchor_check** | 日期锚点检查 | I5: 日期锚点混乱(2024 vs 2025) |

### 根因分析

1. **structural_check**：只检查"是否包含必需小节"，不检查"小节内容是否正确"
2. **InsightAuditor**：只检查"是否有洞察"，不检查"洞察是否基于正确事实"
3. **FlipThresholdCalculator**：使用硬编码数据(1427.8亿)，不使用实际财务数据
4. **semantic_audit**：只检查单章节内部，不跨章节比对
5. **review_integrator.py**：文件存在但从未被workflow.py调用（"90%陷阱"，见8.10）

### 关键教训

**人工批判性审阅（buy_side_report_review skill）是不可替代的最后一道防线。**

qual工作流的自动化审查只能捕获格式问题和占位符问题，无法捕获：
- 跨章节数据矛盾（第6章说现金流转正，第5/9章说为负）
- 估值模型与叙述结论矛盾（情景表基准30.6元，叙述说"50-100%上行"）
- 模板垃圾数（翻转阈值营收1427.8亿比实际高3-4倍）
- 洞察审计评分反向（写错事实的章节得90分，写对事实的章节得30分）

**流程设计原则**：qual工作流生成报告后，**必须**运行buy_side_report_review进行批判性审阅，然后根据审阅结果修正报告。自动化审查不能替代人工审查。

### 模板垃圾数检测模式

**症状**：翻转阈值营收为1427.8亿（比实际营收高3-4倍）

**根因**：多份报告共用同一套带bug的估值模板，垃圾数被原样复制。

**检测方法**：
```python
def detect_template_garbage(flip_thresholds, actual_financials):
    """检测翻转阈值是否使用了模板垃圾数"""
    for threshold in flip_thresholds:
        if threshold.variable == "营收":
            actual_rev = actual_financials.get("revenue", 0)
            if threshold.current_value > actual_rev * 3:
                return True, f"翻转阈值营收{threshold.current_value}亿比实际{actual_rev}亿高{threshold.current_value/actual_rev:.1f}倍"
    return False, ""
```

**修复**：翻转阈值必须使用实际财务数据，禁止使用模板默认值。

### 9.0 v3修复验证清单（Verified 2026-08-08）

| # | 修复项 | 文件 | 验证方法 |
|---|--------|------|----------|
| 1 | create_default_assumptions()参数 | quality_enhancer.py | 检查是否传入不支持的base_ebit_margin |
| 2 | 辩论超时 | debate_coordinator.py | 使用threading.Timer，非signal.SIGALRM |
| 3 | 并发机制 | quality_enhancer.py | 直接调用run_debate，超时在内部实现 |
| 4 | 毛利率fallback | data_repair.py | 仅营业成本计算，无magic number |
| 5 | 翻转点收敛 | depth_enhancer.py | 100次迭代+收敛检查+区间估值 |
| 6 | 结构化预检 | structural_check.py | ≥60阈值不变，扩展格式变体 |
| 7 | ROIC回应 | roic_checker.py | 含定量分析+改善路径+行业对比 |

### 9.1 新增Pitfalls（Verified 2026-08-08）

**Pitfall: create_default_assumptions()参数不匹配**
- **症状**: `TypeError: create_default_assumptions() got an unexpected keyword argument 'base_ebit_margin'`
- **根因**: `create_default_assumptions()`只接受`base_revenue`, `base_wacc`, `base_terminal_growth`，不接受`base_ebit_margin`
- **修复**: 直接创建`ValuationAssumptions`对象，自定义`ebit_margins`列表
```python
assumptions = ValuationAssumptions(
    base_revenue=revenue,
    revenue_growth_rates=[0.05, 0.04, 0.03, 0.02, 0.02],
    ebit_margins=[ebit_margin * 0.8, ebit_margin, ebit_margin * 1.1, ...],
    wacc=0.081,
    terminal_growth=0.02,
)
```

**Pitfall: 翻转点计算未收敛**
- **症状**: `营收翻转点计算未收敛: 二分法在50次迭代后未收敛`
- **根因**: 50次迭代不足，边界条件导致不收敛
- **修复**: 增加到100次迭代，添加收敛容差检查，未收敛时返回区间估值
```python
MAX_ITERATIONS = 100  # 从50增加
CONVERGENCE_TOLERANCE = 1e-6

for i in range(MAX_ITERATIONS):
    if abs(high - low) < CONVERGENCE_TOLERANCE * base_value:
        converged = True
        break
    # ...

if not converged:
    return FlipThreshold(
        variable="变量名（未收敛）",
        direction="区间",
        impact=f"区间=[{low:.1f}, {high:.1f}]，仅供参考",
    )
```

**Pitfall: 毛利率使用magic number估算**
- **症状**: 毛利率使用`营业支出×0.7`或`行业均值18%`计算
- **根因**: 这些数字无财务理论依据，会引入系统性偏差
- **修复**: 仅允许从营业成本直接计算，缺失时标记为None
```python
# 禁止: estimated_cost = operating_expenses * 0.7
# 禁止: default_margin = 0.18  # 行业平均
# 允许: gross_margin = (revenue - cost_of_goods) / revenue
# 允许: gross_margin = None  # 数据缺失
```

**Pitfall: 结构化预检阈值放松**
- **症状**: 将≥60阈值降至≥40以通过更多报告
- **根因**: 这会破坏质量底线，允许低质量报告通过
- **修复**: 保持≥60阈值，扩展`_REQUIRED_SECTIONS`的格式变体模式
```python
# 错误: passed = critical_count == 0 and score >= 40.0
# 正确: passed = critical_count == 0 and score >= 60.0
# 正确: 增加更多patterns识别合法格式变体
```

### 八D-1B、HeavySkill工作流执行审查（Verified 2026-08-08，小鹏汽车实测）

当qual工作流执行完成后，使用HeavySkill K=8审查是否按流程执行。详见 `references/heavyskill-workflow-execution-review.md`。

**审查维度**：流程完整性、流程正确性、问题处理、最终质量

**实测结论（小鹏9868.HK v7.0）**：8/8轨迹一致判定"不合格"
- Step 4.6 Gate Checks跳过（模块未找到）
- Step 4.7审查修复循环失败（170+问题修复失败）
- Step 7问题转化流程代码错误
- 结论："报告不可作为直接交付物，需经人工深度复核修正"

### 八D-2、审查修复循环模式（Verified 2026-08-08，小鹏汽车实测）

> **核心发现**：审查环节发现问题后不应只是报告，而应自动修复→再审查，直到通过或达到最大轮数。
> 用户指出"qual流程应该是审查后自动修复，再审查"，这是workflow设计的基本原则。

### 八E、Gate-Driven架构设计模式（Verified 2026-08-08，HeavySkill K=8三轮审查）

> **核心发现**：qual工作流应采用Gate-Driven架构，每步有明确前置条件和预期结果，
> 第三方监督是轻量级规则驱动检查（不是HeavySkill），数据源不可用判定必须严苛且需人工同意。

**Pitfall: 第三方监督混淆HeavySkill与规则驱动检查（Verified 2026-08-08）**

- **症状**: 使用HeavySkill做每步的流程监督，导致分钟级延迟和高Token消耗
- **根因**: 混淆了"深度推理评估"和"流程合规性检查"的用途
- **规则**:
  - 第三方监督 = 轻量级规则驱动检查（秒级，无Token，检查"是否按流程执行"）
  - HeavySkill = 深度推理评估（用于技术方案审查，不是流程监督）
- **实现**: `FlowComplianceChecker` 检查前置条件、执行内容、通过标准、失败处理、人工介入

**Pitfall: 数据源不可用判定不严苛（Verified 2026-08-08）**

- **症状**: Wind API一次失败就判定为不可用，直接跳过或降级
- **根因**: 不可用判定条件过于宽松
- **规则**: 必须同时满足5个条件才判定为不可用：
  1. 连续3次获取失败，每次间隔≥30秒
  2. 错误类型为永久性错误（403、404、格式严重损坏）
  3. 尝试≥2个备用数据源均失败
  4. 用户明确拒绝手动上传
  5. 等待时间≥10分钟
- **人工同意**: 数据源降级必须人工同意，不能自动降级

**Pitfall: 模糊评分替代确定性规则（Verified 2026-08-08）**

- **症状**: "正确率≥95%"、"一致性评分≥80%"等模糊评分无法自动验证
- **根因**: 缺少标注真值，LLM自评不可信
- **规则**: 将模糊评分替换为确定性规则集合：
  - Gate 1: "必填关键字段存在性校验、数值与财报偏差≤2%"
  - Gate 3: "关键数据点在各章中引用一致、章节结构完整"
  - Gate 4: "格式错误数=0、估值参数与Gate 2一致、逻辑矛盾数≤2"

**Pitfall: 审查只报告不修复（Verified 2026-08-08）**

- **症状**: 审查发现166个问题，但报告仍然直接输出，未尝试修复
- **根因**: 审查和修复是分离的，审查结果未传入修复模块
- **规则**: 使用review_repair_loop.py实现审查→修复→再审查循环（最多3轮）

**Pitfall: 财报数据允许跳过（Verified 2026-08-08）**

- **症状**: "Step 1.5 自动获取财报"被跳过，使用Wind数据替代
- **根因**: 流程允许降级使用二手数据
- **规则**: 财报是必须使用的数据，不允许跳过。财报获取失败应阻断流程，不应静默降级。

详细架构设计见 `references/qual-v82-gate-driven-architecture-2026-08-08.md`。

**review_repair_loop.py** 实现了审查→修复→再审查的循环：

```python
def review_and_repair_loop(chapters, ctx, llm_caller, wind_data, max_rounds=3, industry="新能源汽车"):
    """审查修复循环：检查→修复→再检查，直到通过或达到最大轮数"""
    for round_num in range(1, max_rounds + 1):
        # 1. 执行审查（深度审查 + 实质性审查）
        round_issues = _run_deep_review(chapters, wind_data)
        round_issues.extend(_run_substantive_review(chapters, llm_caller, wind_data, industry))
        
        # 2. 检查是否通过
        if not round_issues:
            return ReviewRepairResult(passed=True, rounds=round_num, ...)
        
        # 3. 使用LLM修复问题
        fixed_count = _repair_chapters(chapters, round_issues, llm_caller)
    
    # 达到最大轮数
    return ReviewRepairResult(passed=False, rounds=max_rounds, ...)
```

**workflow.py集成**：Step 4.7和Step 4.8合并为一个审查修复循环：

```python
# Step 4.7: 深度审查 + 实质性审查（审查修复循环）
review_result = review_and_repair_loop(
    chapters=chapters,
    ctx=ctx,
    llm_caller=llm_caller,
    wind_data=wind_data_for_check,
    max_rounds=3,
    industry=industry,
)
```

**关键教训**：
1. 审查不是终点，修复才是目的
2. 每轮修复后必须再次审查，验证修复是否有效
3. 达到最大轮数后，报告剩余问题，不阻断流程
4. 修复使用LLM，需要传入问题列表和当前内容

**Pitfall: 审查只报告不修复**
- **症状**: 审查发现166个问题，但报告仍然直接输出，未尝试修复
- **根因**: 审查和修复是分离的，审查结果未传入修复模块
- **修复**: 使用review_repair_loop.py实现审查→修复→再审查循环

---

### 八D、实质性内容审查框架（Verified 2026-08-08，小鹏汽车实测）

**核心发现**：形式审查只能捕获跨章节数据矛盾，无法验证"内容是否正确"。需要Step 4.8实质性审查。

**两层审查架构**：
- Step 4.7（形式审查）：跨章节一致性、逻辑一致性、数据合理性、估值仲裁、日期锚点
- Step 4.8（实质审查）：事实核查(Wind比对)、分析深度(LLM)、结论合理性、假设合理性

**9个审查模块**（`quality/v3/`目录）：cross_chapter_consistency, logic_consistency_check, data_reasonableness_check, valuation_arbitrator, date_anchor_check, fact_checker, depth_reviewer, conclusion_validator, assumption_checker

**实测（小鹏9868.HK）**：事实核查发现29个数据偏差（score=0），结论合理性发现"中性"但上行100%。

**关键教训**：
1. 事实核查是最高价值审查（与Wind数据比对直接发现致命问题）
2. 人工批判性审阅不可替代（自动化审查无法捕获投资逻辑问题）

详细实现和实测数据见 `references/substantive-review-framework-2026-08-08.md`。

### 八D-3、非侵入式整合模式（Verified 2026-08-08，小鹏汽车实测，Updated 2026-08-08）

**用户纠正**：qual_v8不应是独立系统，必须整合到现有workflow.py中。

**核心规则**：新组件必须作为现有workflow的内部依赖，不能创建独立系统。

**Pitfall: 创建平行系统（Verified 2026-08-08）**
- **症状**: 新增的qual_v8模块独立于现有workflow运行，有自己的入口和配置
- **根因**: 未理解"整合"的含义，把新组件当作独立系统设计
- **修复**:
  1. 删除所有独立入口（CLI、__main__、API路由）
  2. 所有调用统一指向workflow.py的入口函数
  3. 使用WorkflowContext非侵入式挂载（shadow/soft/enforce模式）
  4. 目录下沉为 `workflow/_qual_v8/`

**整合四阶段（HeavySkill审查通过）**：
1. 非侵入式挂载：WorkflowContext注入，默认shadow模式
2. 功能对标：Step/Gate映射表（workflow.py的Step → qual_v8的Gate 0-8）
3. 渐进式激活：环境变量QUAL_MODE控制（shadow→soft→enforce）
4. 清理与唯一入口：移除qual_v8独立运行能力

**Pitfall: WorkflowContext钩子未被调用（Verified 2026-08-08）**
- **症状**: Gate状态全部为pending，qual_summary中workflow_state=initialized
- **根因**: WorkflowContext的on_step_start/on_step_end钩子未在workflow.py的实际Step中调用
- **影响**: 第三方监督、状态机、审计日志全部失效（只初始化不更新）
- **修复**: 必须在workflow.py的每个Step前后显式调用钩子
- **验证**: 运行后检查qual_summary.gate_states，不应全部为pending

**Pitfall: 影子模式≠自动检测（Verified 2026-08-08）**
- **症状**: shadow模式运行后，所有Gate仍为pending
- **根因**: shadow模式只记录不阻断，但钩子仍需被调用才能记录
- **规则**: shadow模式不等于自动检测Step执行，必须显式调用钩子

**Pitfall: ComplianceCheck缺少必需参数（Verified 2026-08-08）**
- **症状**: TypeError: ComplianceCheck.__init__() missing 2 required positional arguments: passed and message
- **根因**: ComplianceCheck使用@dataclass但passed和message没有默认值，创建时必须显式传入
- **修复**: 先计算passed和message，再创建ComplianceCheck对象；或给passed=False和message=""设默认值

**整合验证清单**：
1. WorkflowContext初始化成功（日志中有[Qual] WorkflowContext已初始化）
2. 每个Step前后是否调用钩子（grep on_step_start workflow.py）
3. Gate状态是否更新（检查qual_summary.gate_states不全为pending）
4. 审计日志是否记录（检查audit_log条目数>0）
5. 第三方监督是否执行（检查compliance_result日志）

详细整合模式见 `references/qual-v84-non-invasive-integration-2026-08-08.md`。

### 八D-4、Gate-Driven架构v8.4（Verified 2026-08-08，HeavySkill K=8五轮审查）

**核心架构**：9个Gate，每个有前置条件、通过标准、执行内容、第三方监督

| Gate | 名称 | 前置条件 |
|------|------|----------|
| 0 | 数据源验证 | 无 |
| 1 | 类型推断+数据提取 | Gate 0 |
| 2 | 数据收集+参数提取 | Gate 1 |
| 3 | 逐章写作 | Gate 2 |
| 4 | 审计修复+深度审查 | Gate 3 |
| 5 | 质量增强+组件集成 | Gate 4 |
| 6 | 综合结论+决策章 | Gate 5 |
| 7 | 问题转化+记忆存储 | Gate 6 |
| 8 | 最终验证 | Gate 7 |

**关键组件**：
- 状态机（7种Gate状态+6种工作流状态）
- 审计日志（哈希链防篡改）
- 熔断器（闭合/打开/半开+冷却期+人工重置）
- 错误分类器（临时/永久/业务，含错误码映射）
- 第三方监督（规则驱动，秒级响应，非HeavySkill）

详细架构见 `references/qual-v82-gate-driven-architecture-2026-08-08.md`。（Verified 2026-08-08，小鹏汽车v7.0实测）

**Pitfall: Gate Checks模块未找到导致跳过**
- **症状**: `Gate Checks模块未找到，跳过Step 4.6`
- **根因**: `gate_checks_integration.py`路径不正确或依赖缺失
- **影响**: 最终质量门禁完全缺失，未校验内容可能包含事实错误
- **修复**: Gate Checks应设为不可跳过的硬闸门，模块缺失时应阻断流程而非跳过

**Pitfall: 问题转化流程代码错误**
- **症状**: `问题转化流程失败: cannot access local variable 'result' where it is not associated with a value`
- **根因**: 变量作用域问题，`result`在某些代码路径下未初始化
- **影响**: 流程末端阻断，问题无法归档，知识闭环断裂
- **修复**: 确保`result`在使用前初始化，添加try-except降级处理

**Pitfall: 审查修复循环修复失败但仍继续**
- **症状**: Step 4.7审查修复循环3轮后仍有170+问题未修复，但流程继续生成报告
- **根因**: 修复模块能力不足（如修复后内容过短被拒绝），无升级机制
- **影响**: 大量问题遗留到最终报告
- **修复**: 引入修复失败升级机制，当修复率低于阈值时触发人工介入或中止

**Pitfall: 跨章节数据不一致无法修复（Verified 2026-08-08）**
- **症状**: 审查修复循环3轮后仍有191个跨章节一致性问题
- **根因**: 各章节独立生成，LLM每次使用不同数据值，修复模块无法确定"正确值"
- **影响**: 经营现金流在不同章节值不同（35.0亿/35.2亿/12.0亿/365.0亿）
- **修复**: 使用数据锚点机制（DataAnchor），在Gate 2从Wind数据提取唯一数据源，在Gate 4检查并替换不一致数据
- **详细实现**: 见 `references/data-anchor-mechanism-2026-08-08.md`

**Pitfall: FCF=0未触发硬阻断**
- **症状**: `DCF 警告: 经营活动现金流量净额为 0，FCF 可能不准确`，但流程继续
- **根因**: DCF参数异常仅作警告处理，未设硬阻断
- **影响**: 估值模型完全失效，DCF结论无意义
- **修复**: FCF=0或负值时应触发硬停止或强制人工确认

**Pitfall: 审计修复循环导致质量恶化（"打地鼠"效应）（Verified 2026-08-08, Re-verified 2026-08-09 XPeng 9868.HK）**

- **症状**: 审计修复循环运行后，问题数不减反增。小鹏汽车9868.HK实测：跨章节一致性从17问题增加到42问题（第2轮）
- **根因**: 修复模块修改某章数据后，与其它章节的旧引用产生新的不一致。修复A章→B章引用变错→修复B章→C章引用变错→...
- **影响**: 进程卡死35+分钟，最终只能手动终止
- **修复**: 
  1. `max_repair_rounds` 必须设为1（默认3会导致质量恶化）
  2. 修复后的章节标记为"已修复"，后续轮次不再修改
  3. 如果修复后问题数增加，立即终止循环并降级（不阻断主流程）
- **与8D-4的区别**: 8D-4记录的是"修复失败"（问题数不变），本pitfall记录的是"修复恶化"（问题数增加）

**Pitfall: v3模块接口不完整导致质量监控失效（Verified 2026-08-09, Re-verified 2026-08-09）**

- **症状**: 多个v3模块在运行时报属性缺失：
  - `ModuleLoader`: `'check_all_modules'` 方法不存在
  - `DataMappingRegistry`: `'validate_mappings'` 方法不存在
  - `QualMetricsTracker`: `cannot access local variable 'result'`
  - Gate Checks: `'str' object is not a mapping`
- **根因**: v3模块的接口在HeavySkill审查时定义了，但实现不完整。方法声明但未实现，或变量作用域错误
- **影响**: 质量层所有v3模块的自检/校验/跟踪功能均不工作（non-blocking，不阻断主流程，但质量监控完全失效）
- **修复优先级**: P1（不阻断报告生成，但无法提供质量保证）
- **验证**: 运行`run_analysis()`，检查日志中是否有`自检失败`/`校验失败`/`跟踪失败`

**5个具体Bug定位（Verified 2026-08-09 XPeng 9868.HK）**:

| Bug | 文件:行 | 错误 | 修复 |
|-----|---------|------|------|
| 1 | workflow.py L2145 | `loader.check_all_modules()` 不存在 | 改为`ModuleLoader.validate_paths()`或添加该方法 |
| 2 | workflow.py L589 | `registry.validate_mappings(wind_data)` 不存在 | 改为`registry.validate_consistency(wind_data)`或添加该方法 |
| 3 | workflow.py L2577 vs L2820 | `result["metrics_summary"]`在result定义前使用 | 将L2563-2579移到L2820之后 |
| 4 | gate_checks_integration.py L127 | `**chapter`对字符串解包 | 添加isinstance检查，str时包装为dict |
| 5 | Wind现金流字段 | `"经营活动之现金流量"` ≠ `"经营活动现金流量净额"` | 使用Wind原始字段名或添加映射 |
- **影响**: 质量层所有v3模块的自检/校验/跟踪功能均不工作（non-blocking，不阻断主流程，但质量监控完全失效）
- **修复优先级**: P1（不阻断报告生成，但无法提供质量保证）
- **验证**: 运行`run_analysis()`，检查日志中是否有`自检失败`/`校验失败`/`跟踪失败`

**Pitfall: Session Search上下文不完整导致误判（Verified 2026-08-09）**

- **症状**: 用户问"复盘qual流程上个会话的优化结果"，agent基于session_search结果报告"待修复"，但用户指出"不是已经修复了吗"
- **根因**: session_search返回的是匹配的会话片段，不是完整会话记录。同一问题可能在后续会话中已修复，但搜索结果只显示发现问题的会话
- **规则**:
  1. session_search 结果是**线索**，不是**结论**
  2. 当用户说"已经修复了"时，直接信任并询问详情，不要基于搜索结果反驳
  3. 复盘时应搜索多个关键词（问题+修复+完成）确认完整状态
  4. 对用户的断言保持信任优先，验证其次

**Pitfall: Session Search上下文不完整导致误判（Verified 2026-08-09）**

- **症状**: 用户问"复盘qual流程上个会话的优化结果"，agent基于session_search结果报告"待修复"，但用户指出"不是已经修复了吗"
- **根因**: session_search返回的是匹配的会话片段，不是完整会话记录。同一问题可能在后续会话中已修复，但搜索结果只显示发现问题的会话
- **规则**:
  1. session_search 结果是**线索**，不是**结论**
  2. 当用户说"已经修复了"时，直接信任并询问详情，不要基于搜索结果反驳
  3. 复盘时应搜索多个关键词（问题+修复+完成）确认完整状态
  4. 对用户的断言保持信任优先，验证其次

详细实现和实测数据见 `references/xpeng-analysis-failure-patterns-2026-08-09.md`。

### 8. 流程执行检查

1. ☐ ModuleLoader启动自检通过？（v3组件）
2. ☐ 断点恢复是否检查placeholder+语义验证？（模式A+v3语义）
3. ☐ 关键参数是否显式传递+值域校验？（模式B+v3值域）
4. ☐ 异常是否QualException分级处理？（模式C+v3继承体系）
5. ☐ 审查是否独立于分析结果执行？

### 8.2 估值模块检查

6. ☐ DCF和情景分析是否使用UnifiedValuation？（模式D+v3差异归因）
7. ☐ 假设审计是否完整（AssumptionAudit）？（v3新增）
8. ☐ 洞察审计是否为扣分制？（模式E/模式I）
9. ☐ 翻转阈值是否二分法+方向验证+收敛兜底？（模式F/模式H）
10. ☐ 当前股价是否MarketData单一数据源+新鲜度检查？（模式G）
11. ☐ ROIC<WACC是否被强制回应？（模式J/ROICChecker）

### 8.3 数据一致性检查

11. ☐ DataMappingRegistry是否统一口径？
12. ☐ DataContext是否口径校验？
13. ☐ 可比公司是否ComparableConfig白名单+行业分类？
14. ☐ 币种是否统一？

### 8.4 方法论检查

15. ☐ DecisionAggregator是否权重透明化+回测？
16. ☐ ROIC<WACC是否被回应？
17. ☐ 局部→全局聚合是否透明？

---

## 十、HGF执行模式

当需要修复qual工作流的代码问题时，使用HGF（Gate-Driven Development）流程确保质量。详见 `references/hgf-workflow-code-fix-pattern-2026-08-05.md`。

**适用场景**：
- workflow.py核心方法修改
- quality模块组件实现
- 数据一致性修复
- 估值逻辑统一

**8 Gate流程**：
1. Gate 0: 需求分析
2. Gate 1: 代码审查
3. Gate 2: 修复集成闭环
4. Gate 3: 端到端测试
5. Gate 4: 数据一致性修复
6. Gate 5: 估值逻辑统一
7. Gate 6: 质量审查（HeavySkill K=8）
8. Gate 7: 最终验证

---

## 十一、参考文档

| 文件 | 说明 |
|------|------|
| `references/v3-implementation-summary.md` | v3组件实施总结（HGF Gate 1-5） |
| `references/heavyskill-review-cycle.md` | HeavySkill三轮审查迭代记录 |
| `references/v3-integration-patterns-2026-08-02.md` | v3组件集成模式（16组件完整地图，HGF Phase 1+2+3，2026-08-02更新） |
| `references/yuewen-personal-review-2026-08-02.md` | 阅文集团个人审查记录 |
| `references/hgf-workflow-code-fix-pattern-2026-08-05.md` | HGF执行模式：Qual工作流代码修复（8 Gate完整流程） |
| `references/step45-hang-debugging-2026-08-05.md` | Step 4.5卡死调试记录（4个修复+验证方法） |
| `references/debate-mechanism-architecture-defect-2026-08-06.md` | 辩论机制架构性缺陷调试记录（concurrent.futures超时无效，必须禁用） |
| `references/heavyskill-workflow-execution-review.md` | HeavySkill工作流执行审查模式（查询模板、9维度审查、执行级pitfalls） |
| `references/review-repair-loop-pattern-2026-08-08.md` | **审查修复循环模式** — review_repair_loop.py、Gate Checks模块路径、Step 7变量作用域、FCF=0校验、保守修复策略、第三方监督模式 (2026-08-08) |
| `references/qual-v82-gate-driven-architecture-2026-08-08.md` | **Qual流程v8.2 Gate-Driven架构** — 轻量级第三方监督(非HeavySkill)、确定性规则集合、数据源严苛验证+人工同意、审查修复循环、超时/熔断/回滚机制 (2026-08-08) |
| `references/qual-v84-non-invasive-integration-2026-08-08.md` | **Qual v8.4非侵入式整合模式** — WorkflowContext注入、shadow/soft/enforce模式、Step/Gate映射、避免平行系统 (2026-08-08) |
| `references/data-anchor-mechanism-2026-08-08.md` | **数据锚点机制** — 跨章节数据同步，Wind数据作为唯一数据源，修复跨章节一致性问题 (2026-08-08) |
