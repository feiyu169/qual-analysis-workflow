# Granger因果检验 — scipy实现

> 创建日期: 2026-07-01
> 替代方案: statsmodels (有依赖冲突)

## 为什么不用statsmodels

statsmodels在Python 3.11环境下与pandas/numpy有循环导入问题：
```
ImportError: numpy._core.multiarray failed to import
```

## scipy实现方案

使用scipy.stats.f.cdf实现F检验，核心逻辑：

```python
import numpy as np
from scipy import stats

def granger_test(cause_arr, effect_arr, max_lag=2, significance_level=0.05):
    """Granger因果检验 — scipy F-test实现"""
    best_pvalue = 1.0
    best_lag = 1
    n = len(effect_arr)
    
    for lag in range(1, max_lag + 1):
        if n - lag < lag + 2:
            continue
        
        y = effect_arr[lag:]
        
        # 受限模型: effect[t] = a + b*effect[t-1:t-lag]
        X_r = np.column_stack(
            [np.ones(len(y))] + 
            [effect_arr[lag-i-1:n-i-1] for i in range(lag)]
        )
        
        # 非受限模型: + c*cause[t-1:t-lag]
        X_u = np.column_stack(
            [X_r] + 
            [cause_arr[lag-i-1:n-i-1] for i in range(lag)]
        )
        
        # OLS
        beta_r = np.linalg.lstsq(X_r, y, rcond=None)[0]
        beta_u = np.linalg.lstsq(X_u, y, rcond=None)[0]
        
        rss_r = np.sum((y - X_r @ beta_r) ** 2)
        rss_u = np.sum((y - X_u @ beta_u) ** 2)
        
        # F检验
        df1 = lag
        df2 = len(y) - X_u.shape[1]
        if df2 <= 0 or rss_u == 0:
            continue
        
        f_stat = ((rss_r - rss_u) / df1) / (rss_u / df2)
        p_value = 1 - stats.f.cdf(f_stat, df1, df2)
        
        if p_value < best_pvalue:
            best_pvalue = p_value
            best_lag = lag
    
    return best_pvalue, best_lag
```

## 使用注意事项

1. **数据预处理**: 使用增长率而非原始值，消除量纲影响
2. **最小观测值**: 至少需要4个增长率数据点
3. **滞后阶数**: max_lag不能超过数据量的1/3
4. **双向检验**: 必须同时检验A→B和B→A
5. **p值解读**: p < 0.05表示存在Granger因果关系

## 实测结果

快手财务数据（2023-2025）：
- 收入增长 → 利润增长: p=0.8896, 显著=False
- 利润增长 → 收入增长: p=0.5363, 显著=False

解读：3年数据量不足，无法得出显著的因果关系。需要5年以上数据。
