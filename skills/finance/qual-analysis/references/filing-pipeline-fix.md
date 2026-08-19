# 财报获取管道修复记录 — 2026-06-30

## 问题

filing_downloader.py 有 3 个阻断性 bug，导致整个财报获取链路断裂。

## 修复

### Bug 1: FilingInfo 不存在
- **原代码**: `from .downloaders.base import FilingInfo`
- **修复**: 改用 `ReportQuery` / `DownloadedAsset` (从 models.py 导入)

### Bug 2: HKEXNewsDownloader() 缺 http_client
- **原代码**: `HKEXNewsDownloader()` (无参)
- **修复**: `HKEXNewsDownloader(http_client=HttpClient())`

### Bug 3: list_filings() 不存在
- **原代码**: `downloader.list_filings(ticker, limit=limit)`
- **修复**: `downloader.download(query=ReportQuery(...), limit=limit)`

### Bug 4: 解析器无 parse() 方法
- **原代码**: `parser.parse(pdf_path)`
- **修复**: 改用 DocumentStore 接口:
  ```python
  parser = MinerUParser(pdf_path, config=config)
  text = parser.get_full_text()
  sections = parser.list_sections()  # list[SectionSummary]
  content = parser.read_section(ref)  # SectionContent, 有 .text 属性
  tables = parser.list_tables()
  ```

### Bug 5: MinerU 200 页限制
- **修复**: 分段解析再合并
  ```python
  for i in range(0, total_pages, 200):
      config = MinerUConfig(api_mode="precise", page_range=f"{i+1}-{min(i+200, total_pages)}")
      parser = MinerUParser(pdf_path, config=config)
  ```

### Bug 6: FallbackParser 章节检测差
- **修复**: 降序优先 MinerU → Docling → Fallback; Fallback 按页标记切分

## 正确调用链

```python
from finance.filing_downloader import fetch_filing

filing_data = fetch_filing(ticker="1024.HK", market="hk", limit=1)
# 返回: {sections: {title: content}, tables: [...], text: str, metadata: dict, source: "filing"}
```

## 验证结果

快手 2025 年报 (374页, 9.9MB):
- MinerU 分段解析 (1-200, 201-374)
- 产出: 725 章节, 2,114,003 字符
- 耗时: ~3 分钟
