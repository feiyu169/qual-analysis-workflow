# 小鹏汽车 (9868.HK) Qual分析失败模式汇总 — 2026-08-09

## 概述

三次qual流程运行均失败，失败模式一致。本文档记录系统性根因和修复方案。

## 运行记录

| 运行 | 日期 | 耗时 | 报告 | 核心问题 |
|------|------|------|------|----------|
| xpeng-analysis-v4 | 08-05 | - | 1365行 | 辩论机制禁用，结构化预检不通过 |
| xpeng-analysis-qual-v2 | 08-08 | 1033秒 | 1188行 | 审计修复3轮无法收敛，Gate状态全部pending |
| xpeng-analysis-qual-v3 | 08-09 | 35+分钟 | 无(终止) | 审计修复循环卡死，修复恶化问题(17→42) |

## 系统性根因

### 1. MinerU 401 认证失败 (P0)

```
MinerU解析失败: HTTP 401: {"traceId":"c02dcfebb7fd","msgCode":"A0202","msg":"user authenticate failed"}
```

MinerU API token过期或无效。FallbackParser降级后只识别出18个章节（MinerU能识别数百个）。

### 2. 审计修复循环"打地鼠"效应 (P0)

Step 4审计修复循环的问题数不减反增：
```
第1轮: 跨章节一致性=0分/17问题, 事实核查=0分/56问题
第2轮: 跨章节一致性=0分/42问题, 事实核查=0分/60问题
```

修复A章的数据后，B章引用的旧数据变成错误，形成"打地鼠"效应。

### 3. Wind现金流字段映射不完整 (P0)

Wind A股返回的字段名含TTM后缀（`最近3年经营活动现金净流量_TTM`），代码期望不含后缀。导致FCF=0，DCF估值无意义。

### 4. 质量层v3模块接口不完整 (P1)

| 模块 | 错误 |
|------|------|
| ModuleLoader | `'check_all_modules'` 方法不存在 |
| DataMappingRegistry | `'validate_mappings'` 方法不存在 |
| QualMetricsTracker | `cannot access local variable 'result'` |
| Gate Checks | `'str' object is not a mapping` |

## 小鹏汽车基本面数据 (Wind, FY2023/2024/2025)

| 指标 | FY2023 | FY2024 | FY2025 |
|------|--------|--------|--------|
| 营业收入(亿元) | 306.76 | 408.66 | 767.20 |
| 净利润(亿元) | -103.76 | -57.90 | -11.39 |
| 营业利润(亿元) | -113.84 | -74.82 | -44.16 |
| 资产总计(亿元) | 841.63 | 827.06 | 1031.63 |
| 归母净资产(亿元) | 363.29 | 312.75 | 303.69 |
| 经营现金流(亿元) | 9.56 | -20.12 | 82.59 |
| 当前股价(港元) | - | - | 46.64 |

## 修复优先级

| 优先级 | 问题 | 修复方案 |
|--------|------|----------|
| P0 | MinerU 401 | 刷新API token |
| P0 | 审计修复循环 | max_repair_rounds=1，问题增加时终止 |
| P0 | Wind现金流映射 | 更新字段映射(含TTM后缀) |
| P1 | v3模块接口 | 补全缺失方法 |

---

## 已实施修复（2026-08-09验证通过）

### 修复1: 审计修复循环卡死

**修改文件**: `workflow.py`

```python
# 修改前
def _audit_and_fix(..., max_rounds: int = 3,):

# 修改后
def _audit_and_fix(..., max_rounds: int = 1, timeout_seconds: int = 300,):
```

循环中添加超时检查:
```python
for chapter_num in _CHAPTER_WRITE_ORDER:
    elapsed = time.time() - start_time
    if elapsed > timeout_seconds:
        logger.warning(f"审计超时 ({elapsed:.0f}s > {timeout_seconds}s)")
        for remaining_ch in _CHAPTER_WRITE_ORDER:
            if remaining_ch not in fixed:
                fixed[remaining_ch] = chapters.get(remaining_ch, "")
        break
```

### 修复2: ModuleLoader缺少check_all_modules方法

**修改文件**: `quality/v3/module_loader.py`

```python
# 添加方法
@classmethod
def check_all_modules(cls) -> Dict[str, Any]:
    warnings = []
    warnings.extend(cls.validate_paths())
    warnings.extend(cls.validate_minimal_checks())
    return {"success": len(warnings) == 0, "warnings": warnings, "loaded": list(cls._loaded_modules.keys())}

# 添加导入
from typing import Any, Dict, List, Optional  # 原来缺少Any
```

### 修复3: DataMappingRegistry缺少validate_mappings方法

**修改文件**: `data/mapping.py`

```python
# 添加方法
@classmethod
def validate_mappings(cls, data: dict) -> Dict[str, Any]:
    warnings = []
    warnings.extend(cls.validate_consistency(data))
    warnings.extend(cls.validate_schema(data))
    return {"success": len(warnings) == 0, "warnings": warnings}

# 添加导入
from typing import Any, Dict, List, Optional  # 原来缺少Any
```

### 修复4: Gate Checks类型错误

**修改文件**: `gate_checks_integration.py`

```python
# 修改前
def _convert_chapters_to_list(chapters: Dict[int, Dict[str, Any]]) -> List[Dict[str, Any]]:
    # **chapter 对字符串解包报错

# 修改后
def _convert_chapters_to_list(chapters) -> List[Dict[str, Any]]:
    for i in range(11):
        if i in chapters:
            chapter = chapters[i]
            if isinstance(chapter, str):
                chapter_with_id = {"chapter_id": f"ch{i:02d}", "content": chapter}
            elif isinstance(chapter, dict):
                chapter_with_id = {"chapter_id": f"ch{i:02d}", **chapter}
            else:
                continue
```

### 修复5: QualMetricsTracker变量作用域

**修改文件**: `workflow.py`

将第2597-2613行（QualMetricsTracker代码）移到第2876行之后（result定义之后）。

### 修复6: Wind现金流字段名不匹配

**修改文件**: `workflow.py`

```python
# 添加多别名回退函数
def _latest_with_aliases(data: dict, *aliases):
    for alias in aliases:
        val = _latest(data, alias)
        if val is not None and val != 0:
            return val
    return 0

# 使用多别名
ocf = _latest_with_aliases(cashflow,
    "经营活动现金净流量_TTM",           # A股Wind
    "过去三年每年经营活动之现金流量",     # 港股Wind
    "经营活动现金流量净额",
    "年经营活动现金流量净额",
)
```

### 验证结果

```
✅ workflow.py 导入成功 (max_rounds=1, timeout_seconds=True)
✅ ModuleLoader.check_all_modules 可调用
✅ DataMappingRegistry.validate_mappings 可调用
✅ _convert_chapters_to_list (str) 成功: 11章节
✅ FCF字段映射 成功: OCF=82.59
```
