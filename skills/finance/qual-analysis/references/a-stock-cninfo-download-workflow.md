# A股财报获取 + MinerU解析工作流

## 概述

A股财报通过CNInfo（巨潮资讯网）下载器获取。与港股/美股不同，A股下载器速度快（~5秒/份），但MinerU解析大PDF需要2-3分钟。

## 完整工作流

### Step 1: 下载年报

```python
from finance.downloaders.cninfo_downloader import CNInfoDownloader
from finance.downloaders.http_client import HttpClient
from finance.downloaders.models import ReportQuery

http = HttpClient()
dl = CNInfoDownloader(http_client=http)

query = ReportQuery(
    market='CN',
    ticker='002352.SZ',  # A股代码
    start_date='2023-01-01',
    end_date='2026-12-31',
    target_periods=('FY',)  # 只取年报
)

profile = dl.resolve_company(query)
candidates = dl.list_candidates(query, profile)

# 下载所有年份
for c in candidates:
    asset = dl._download_and_save(c)
    print(f'{c.fiscal_year}: {asset.pdf_path} ({asset.content_length} bytes)')
```

**保存路径**: `~/.hermes/workspace/filings/cninfo/{year}/{date}_FY_{year}年年度报告.pdf`

### Step 2: MinerU解析

```python
from finance.filing_downloader import _parse_pdf
from pathlib import Path

pdf_path = Path('~/.hermes/workspace/filings/cninfo/2025/2026-03-30_FY_2025年年度报告.pdf')
result = _parse_pdf(pdf_path)
# result: {text, sections, tables, page_count, parse_log}
```

**⚠️ 关键**: 必须用 `_parse_pdf()` 而非直接调用 `FallbackParser`。MinerU的章节识别能力是FallbackParser的数百倍。

### Step 3: 构建filing_data并调用run_analysis

```python
import json
from finance.llm_caller import create_deepseek_caller
from finance.workflow import run_analysis

filing_data = {
    "sections": result["sections"],
    "tables": result["tables"],
    "metadata": {
        "ticker": "002352.SZ",
        "market": "cn",
        "fiscal_year": 2025,
        "fiscal_period": "FY",
        "page_count": result["page_count"],
    },
    "source": "filing",
    "text": result["text"],
}

llm_caller = create_deepseek_caller()
result = run_analysis(
    ticker='002352.SZ',
    company_name='顺丰控股',
    market='cn',
    wind_data=wind_data,
    filing_data=filing_data,
    llm_caller=llm_caller,
    shares=52.65,
    output_dir='/tmp/sf-output',
)
```

## 实测数据

### 顺丰控股 (002352.SZ)

| 年份 | 文件大小 | 下载耗时 | MinerU解析耗时 | sections | text chars |
|------|----------|----------|---------------|----------|------------|
| 2023 | 58MB | ~5s | ~180s | ~700 | ~400K |
| 2024 | 34MB | ~5s | ~150s | ~600 | ~350K |
| 2025 | 24MB | ~5s | ~170s | 546 | 286K |

### FallbackParser vs MinerU (2025年报, 283页)

| 指标 | FallbackParser | MinerU精准API |
|------|---------------|---------------|
| sections | 1 | 546 |
| text chars | 247K | 286K |
| 解析耗时 | 0.3s | 169s |
| 章节识别 | 无 | AI模型识别 |

## 已知问题

### CNInfo公司名解析

CNInfo下载器通过股票代码前缀识别市场（000/002=深市, 600/601=沪市），但公司名可能解析为借壳上市前的名称（如002352解析为"鼎泰新材"而非"顺丰控股"）。**下载的PDF内容是正确的**，不影响分析。

### Dayu MCP不支持多数A股

`mcp_dayu_list_documents(ticker='002352.SZ')` 返回 `"Financial Document Tools do not have this company"`。Dayu数据库仅覆盖部分热门A股。**必须使用CNInfo下载器**。

### MinerU 200页分段

MinerU精准API限制200页/段。`_parse_pdf()`内部自动处理分段：
- ≤200页: 单段解析
- \>200页: 自动分2+段，合并结果

### 全工作流耗时

run_analysis()完整执行（11章+审计+辩论）约15-30分钟。**必须后台运行**：
```python
# 使用 terminal(background=True, notify_on_complete=True)
```

## Wind数据准备

A股Wind数据字段名与港股不同，注意现金流字段带"_TTM"后缀：

```python
wind_data = {
    "income": {
        "年营业总收入": [2584.09, 2844.20, 3082.27],
        "年归属母公司股东的净利润": [82.34, 101.70, 111.17],
        "年EBITDA": [290.47, 324.48, 316.39],
    },
    "balance": {
        "年资产总计": [2214.91, 2138.24, 2164.69],
        "年所有者权益合计": [1032.84, 1023.35, 1103.25],
    },
    "cashflow": {
        "经营活动现金净流量_TTM": [293.02, 281.46, 290.49],  # 注意_TTM后缀
    },
    "_year_labels": {
        "说明": "索引0=FY2023, 索引1=FY2024, 索引2=FY2025",
        "财年": [2023, 2024, 2025]
    }
}
```

总股本需从其他来源获取（Wind不提供），可用雪球/同花顺查询。
