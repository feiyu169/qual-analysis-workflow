# 下载器架构对比：Dayu-Agent vs Hermes (Verified 2026-06-24)

## 参考实现位置

- **Dayu港股**: `/home/lff7767162/repos/dayu-agent/dayu/fins/downloaders/hkexnews_downloader.py` (~1252行)
- **Dayu美股**: `/home/lff7767162/repos/dayu-agent/dayu/fins/downloaders/sec_downloader.py` (~2232行)
- **Dayu A股**: `/home/lff7767162/repos/dayu-agent/dayu/fins/downloaders/cninfo_downloader.py` (~1078行)
- **Dayu数据模型**: `/home/lff7767162/repos/dayu-agent/dayu/fins/pipelines/cn_download_models.py` (~194行)

## 关键差异

### 1. HTTP客户端

| 维度 | Hermes当前 | Dayu | 影响 |
|------|-----------|------|------|
| 客户端 | `urllib.request` | `httpx.Client` | 无连接池/重试 |
| 重试 | 无 | 指数退避3次 | 瞬时失败即崩 |
| 超时 | 固定30s | 可配置 | 灵活性差 |
| 限流 | RateLimiter类 | `_throttle_before_request` | 粗粒度 |

### 2. 数据映射获取

| 映射 | Hermes当前 | Dayu | 影响 |
|------|-----------|------|------|
| **HK stockId** | 动态获取(active only) | active + inactive双列表 | 部分股票找不到 |
| **US CIK** | 硬编码20只 | 动态获取10000+ | 绝大多数股票不可用 |
| **CN orgId** | 硬编码5只 | 从API动态获取 | 绝大多数股票不可用 |
| **CN市场识别** | 硬编码column=szse | ticker前缀自动识别 | 上交所股票失败 |

### 3. API参数格式

**港股 (HKEXNews)**:
- Hermes: 只查年报 (t2code=40100)
- Dayu: 按财期分别查询 (FY/H1/Q1-Q4各有独立分类代码)

**美股 (SEC)**:
- Hermes: 本地硬编码CIK映射表
- Dayu: 从 `https://www.sec.gov/files/company_tickers.json` 动态获取

**A股 (巨潮)**:
- Hermes: 硬编码column=szse，只有5只股票的orgId
- Dayu: 根据ticker前缀自动识别szse/sse，从 `http://www.cninfo.com.cn/new/data/szse_stock.json` 获取全量映射

### 4. 错误处理

| 场景 | Hermes当前 | Dayu |
|------|-----------|------|
| 公司未找到 | 返回空列表 | 抛出ValueError |
| API失败 | 返回空列表 | 抛出RuntimeError |
| PDF验证失败 | 静默跳过 | 抛出RuntimeError |

### 5. 类型系统

| 维度 | Hermes当前 | Dayu |
|------|-----------|------|
| 数据模型 | 简单dataclass | frozen dataclass + 强类型 |
| 财期类型 | str | Literal["FY","H1","Q1","Q2","Q3","Q4"] |
| 市场类型 | str | Literal["CN","HK","US"] |
| 版本管理 | 无 | CN_PIPELINE_DOWNLOAD_VERSION常量 |

## Dayu关键设计模式

### 模式1: 按财期分类查询 (港股)

```python
_PERIOD_TO_CATEGORY_SPEC = {
    "FY": _HkCategorySpec(t1code="40000", t2_group_code="-2", t2code="40100"),
    "H1": _HkCategorySpec(t1code="40000", t2_group_code="-2", t2code="40200"),
    "Q1": _HkCategorySpec(t1code="10000", t2_group_code="3", t2code="13600"),
    # ...
}
```

每个财期单独查询，避免混淆。

### 模式2: 双stock list (港股)

```python
for url in (HKEXNEWS_ACTIVE_STOCK_ZH_URL, HKEXNEWS_INACTIVE_STOCK_ZH_URL):
    payload = self._http_get_json(url)
    # ...
```

Active + Inactive确保覆盖已退市股票。

### 模式3: 动态CIK映射 (美股)

```python
SEC_TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"

def _fetch_ticker_map(self):
    payload = self._http_get_json(SEC_TICKER_MAP_URL)
    return {entry["ticker"]: str(entry["cik_str"]).zfill(10) for entry in payload.values()}
```

### 模式4: 市场自动识别 (A股)

```python
_TICKER_PREFIX_TO_MARKET_PARAMS = {
    "000": ("szse", "sz"),  # 深市主板
    "002": ("szse", "sz"),  # 中小板
    "300": ("szse", "sz"),  # 创业板
    "600": ("sse", "sh"),   # 沪市主板
    "688": ("sse", "sh"),   # 科创板
    # ...
}
```

### 模式5: 标题黑名单过滤 (A股)

```python
_TITLE_BLOCKLIST = (
    "摘要", "英文版", "ESG", "审计报告", "已取消", "募集说明书",
    "可持续发展", "财务报表", "英文)", "英文）",
)
```

### 模式6: HEAD预检 (港股/A股)

```python
def _http_head_meta(self, url: str) -> _HeadMeta:
    """HEAD拉取content-length/etag/last-modified"""
    response = self._client.head(url, follow_redirects=True)
    return _HeadMeta(
        content_length=int(response.headers.get("Content-Length", 0)),
        etag=response.headers.get("ETag"),
        last_modified=response.headers.get("Last-Modified"),
    )
```

用于fingerprint比对，避免重复下载。

## 重构方案 (2026-06-24)

技术文档: `/home/lff7767162/projects/hermes-downloader-refactor-spec.md`

核心模块:
1. `models.py` - frozen dataclass + 强类型 + 异常类
2. `http_client.py` - httpx + 重试 + 限流
3. `base.py` - 缓存 + SHA256 + 统一流程
4. `hkexnews_downloader.py` - 双stock list + 按财期查询
5. `sec_downloader.py` - 动态CIK + Submissions API
6. `cninfo_downloader.py` - 动态orgId + 市场识别
