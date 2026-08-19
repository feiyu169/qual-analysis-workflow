# 披露易 API 实现细节 (Verified 2026-06-23)

## 正确的 API 端点

### 1. 股票列表 (获取 stockId)

```
GET https://www1.hkexnews.hk/ncms/script/eds/activestock_sehk_c.json
GET https://www1.hkexnews.hk/ncms/script/eds/inactivestock_sehk_c.json
```

**响应格式**: JSON 数组
```json
[
  {"i": 1, "c": "00001", "n": "長和", "s": 7111},
  {"i": 2, "c": "00002", "n": "中電控股", "s": 3533}
]
```

**字段映射**：
- `c` → stock_code (股票代码)
- `i` → stock_id (内部ID，用于搜索)
- `n` → company_name (公司名称)
- `s` → 某种排序值

**⚠️ 关键**：字段名是 `c` 和 `i`，不是 `sc` 和 `si`！

### 2. 搜索财报 (titleSearchServlet)

```
GET https://www1.hkexnews.hk/search/titleSearchServlet.do
```

**参数**：
```
lang=ZH
category=0
market=SEHK
stockId={stockId}  # 从股票列表获取
searchType=1
documentType=-1
t1code=40000       # 财务报表
t2Gcode=-2
t2code=40100       # 年报 (40200=中期, 13600=季度)
fromDate=20200101
toDate=20261231
MB-Daterange=0
rowRange=100
sortByOptions=DateTime
sortDir=0
```

**响应格式**:
```json
{
  "result": "[{\"FILE_INFO\":\"9MB\",\"NEWS_ID\":\"12115449\",\"TITLE\":\"2025年報\",...}]",
  "hasNextRow": false,
  "recordCnt": 3
}
```

**⚠️ 关键**：`result` 是一个 JSON **字符串**，需要二次解析：
```python
result_str = result.get("result", "[]")
rows = json.loads(result_str) if isinstance(result_str, str) else result_str
```

### 3. 每条记录的字段

```json
{
  "FILE_INFO": "9MB",
  "NEWS_ID": "12115449",
  "SHORT_TEXT": "財務報表...",
  "TOTAL_COUNT": "3",
  "STOCK_NAME": "美圖公司",
  "TITLE": "2025年報",
  "FILE_TYPE": "PDF",
  "DATE_TIME": "22/04/2026 16:55",
  "LONG_TEXT": "財務報表...",
  "STOCK_CODE": "01357",
  "FILE_LINK": "/listedco/listconews/sehk/2026/0422/2026042200741_c.pdf"
}
```

**下载 URL 构造**：
```python
filing_url = f"https://www1.hkexnews.hk{FILE_LINK}"
```

## 错误的 API 端点 (不要使用)

| URL | 问题 |
|-----|------|
| `search/titlesearch.xhtml` | 返回 HTML，不是 JSON |
| `ncms/json/eds/search_result.json` | 404 Not Found |

## 分类代码 (t1code / t2code)

| 类型 | t1code | t2code | 说明 |
|------|--------|--------|------|
| 年报 | 40000 | 40100 | Annual Report |
| 中期报告 | 40000 | 40200 | Interim Report |
| 季度报告 | 10000 | 13600 | Quarterly Results |
