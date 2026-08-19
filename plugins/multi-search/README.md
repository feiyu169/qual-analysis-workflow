# multi-search —— DSH 多信息源聚合搜索插件

一次调用并行检索 **Tavily / AnySearch / 小红书 / 知乎** 四个信息源，按源分组返回结构化结果并跨源去重。

## 为什么是正式 bundle 而不是动态插件

DSH 的 `cordis_define` 动态插件跑在 vm 沙箱里，**禁用 `fetch` / `process` / `require`**（网络必须走 `ctx.web`，
而 `ctx.web.fetch` 只支持 GET、不能带请求头），所以无法直接调用 Tavily / AnySearch 的 REST API。
本插件作为 **host realm 正式 bundle** 安装（完整 Node 能力），这是能真正联网的方案。

## 信息源说明

| 源 | 方式 | 需要密钥 |
|----|------|----------|
| Tavily | 官方 REST `POST https://api.tavily.com/search` | `TAVILY_API_KEY` |
| AnySearch | 官方 MCP 端点 `POST https://api.anysearch.com/mcp`（JSON-RPC 2.0 `tools/call`，方法 `search`） | `ANYSEARCH_API_KEY` |
| 小红书 | 无公开 API → 经 Tavily/AnySearch 的 `site:xiaohongshu.com` 站点限定搜索，结果按域名过滤 | 复用上面任一 |
| 知乎 | 无公开 API（`x-zse-96` 签名反爬）→ 经 Tavily/AnySearch 的 `site:zhihu.com` 站点限定搜索 | 复用上面任一 |

> 想直连知乎/小红书正文，可另接社区 MCP 服务器（需登录 Cookie），再作为新 adapter 加进 `lib/index.js` 的 `runOne`。

## 安装

### 方式 A：直接放入 profile（无需 pnpm，推荐）

1. 把本包复制到 profile 的 node_modules：
   ```
   robocopy "<本目录>" "%USERPROFILE%\.dsh\profiles\web\node_modules\multi-search" /E
   ```
   （即确保 `%USERPROFILE%\.dsh\profiles\web\node_modules\multi-search\package.json` 与 `lib\index.js` 存在）
2. 在 `%USERPROFILE%\.dsh\profiles\web\cordis.patch.yml` 追加：
   ```yaml
   - insert:
       - id: multi-search
         name: 'multi-search'
         config: {}
   ```
3. **重启 DSH**（关掉 3080 端口的进程后重新运行 `start-dsh.cmd`）。重启后会话里会出现 `search_multi` 工具。

### 方式 B：pnpm（标准途径）

```bash
pnpm --version || corepack enable pnpm
dsh plugin --profile web add "<本目录绝对路径>"
# 重启 DSH
```

## 配置密钥（三选一，按优先级）

1. 插件配置：`cordis.patch.yml` 中给 `multi-search` 行加 `config: { tavilyApiKey: '...', anysearchApiKey: '...' }`
2. DSH 凭据服务：在 Web 的 Models/设置页写入同名条目 `TAVILY_API_KEY`、`ANYSEARCH_API_KEY`
3. 启动 DSH 的进程环境变量 `TAVILY_API_KEY`、`ANYSEARCH_API_KEY`

## 使用

模型直接调用（或让内置 web_search 走它）：

```
search_multi { query: "2025 大模型 Agent 综述", sources: ["tavily","anysearch","xiaohongshu","zhihu"], max_results: 5 }
```

可选：让内置 `web_search` 也走聚合源 —— 在 `cordis.patch.yml` 追加并重启：

```yaml
- id: web
  config:
    searchProvider: multi
```

## 卸载

删除 `cordis.patch.yml` 里的 `multi-search` insert 行与 `web` 行覆盖，删掉
`node_modules\multi-search` 目录，重启 DSH。
