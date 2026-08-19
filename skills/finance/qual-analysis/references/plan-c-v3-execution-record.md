# 方案 C v3 执行记录 — 快手 1024.HK

**日期**: 2026-07-01
**状态**: 成功（3个bug修复后）

## 执行流程

```
Phase 1: 解析 3 份年报 (2023/2024/2025)
  FY2023: 566 章节 (7.5MB)
  FY2024: 674 章节 (11.4MB) ← 修复: 原下载为小米年报(4.9MB)
  FY2025: 725 章节 (9.9MB)

Phase 2: 逐份提取事实 (三层面防护)
  FY2023: DAU=3.799亿, GMV=4039亿, ARPU=None
  FY2024: DAU=None, GMV=None, ARPU=None (提取失败，已重试2次)
  FY2025: DAU=4.1亿, GMV=15980.71亿, ARPU=198.6元

Phase 3: 合并 3 年趋势
  FY2023: DAU=3.799 GMV=4039
  FY2024: (缺失)
  FY2025: DAU=4.1 GMV=15980.71 ARPU=198.6

Phase 4: run_analysis()
  success=True, quality=high, 11/11章, errors=0
```

## 修复的 3 个 Bug

### Bug 1: FY2024 下载了小米的年报
- 症状: 事实提取全部返回 None
- 根因: `dl._download_pdf(candidate)` 的候选对象错误
- 修复: `_verify_company_identity()` 检查前20章节是否包含公司名/代码
- 文件: `fact_extractor.py`

### Bug 2: LLM 提取单位偏差 100 倍
- 症状: DAU=410.2(应4.1), GMV=1598070.7(应15980.71)
- 根因: LLM 对中文单位(亿/万)理解不稳定
- 修复: `normalize_units()` 按合理范围自动修正
- 文件: `fact_extractor.py`

### Bug 3: _merge_chunk_data NoneType
- 症状: `TypeError: 'NoneType' object is not iterable`
- 根因: LLM 返回 `business.segments: null`，`for seg in None` 崩溃
- 修复: 所有列表字段合并前检查 `and biz['segments']`
- 文件: `fact_extractor.py`

## 报告验证 (ch05)

```
DAU: "DAU 4.1亿" ✅
GMV: "GMV（1.598万亿元）" ✅
ARPU: "ARPU（198.6元）" ✅
年份: "2025财年" ✅
```

## 已知遗留问题

1. **FY2024 事实提取失败**: 即使下载了正确的年报，LLM 仍返回全 None。可能原因:
   - 2024 年报结构与 2023/2025 不同
   - 高价值章节排序未命中运营数据章节
   - 需要单独调试 FY2024 的提取 prompt

2. **FY2023 ARPU 缺失**: 2023 年报可能未披露 ARPU 数据

## 性能数据

| 阶段 | 耗时 |
|------|------|
| Phase 1 (解析 3 PDF) | ~5 min |
| Phase 2 (30 次 LLM 调用) | ~3 min |
| Phase 3 (合并) | <1 sec |
| Phase 4 (run_analysis) | ~15 min |
| **总计** | **~25 min** |
