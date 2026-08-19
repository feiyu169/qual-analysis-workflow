// multi-search —— DSH 多信息源聚合搜索插件（host realm 正式插件）
//
// 作用：
//   1) 注册模型工具 `search_multi`：一次调用并行检索四个信息源
//      - Tavily    （官方 REST API，POST https://api.tavily.com/search）
//      - AnySearch （官方 MCP 端点，JSON-RPC 2.0 tools/call，POST https://api.anysearch.com/mcp）
//      - 小红书 / 知乎：无公开 API（知乎带 x-zse-96 签名反爬；小红书无开放接口），
//        因此通过 Tavily / AnySearch 的 site: 站点限定搜索实现，并在结果上按域名过滤。
//   2) 向 ctx.web 注册搜索 provider `multi`：把内置 web_search 指到它
//      （可选：profile 的 cordis.patch.yml 中 `- id: web / config: { searchProvider: multi }`）。
//
// 密钥（按优先级）：插件 config.tavilyApiKey / config.anysearchApiKey
//   → DSH 凭据服务（Web Models 页写入的 TAVILY_API_KEY / ANYSEARCH_API_KEY）
//   → 启动环境变量 / process.env。
//
// 注意：这个插件必须在 host realm 运行（作为 profile bundle 安装），
//   不能做成 cordis_define 动态插件 —— 动态插件的 vm 沙箱禁用 fetch / process / require，
//   无法直接调用 REST API。本包通过 dsh.bundle.patch 声明，作为正式 bundle 加载。

import { defineTool } from '@deepseek-ai/dsh-tools'
import { credentialRef } from '@deepseek-ai/dsh-credentials'
import { launchEnvironmentOf } from '@deepseek-ai/dsh-launch-environment'
import { WebError } from '@deepseek-ai/dsh-web'

export const name = 'multi-search'
export const inject = ['web']

const DEFAULT_MAX_RESULTS = 5
const MAX_RESULTS_CAP = 10
const REQUEST_TIMEOUT_MS = 20000
const TAVILY_ENDPOINT = 'https://api.tavily.com/search'
const ANYSEARCH_ENDPOINT = 'https://api.anysearch.com/mcp'

const LABELS = {
  tavily: 'Tavily',
  anysearch: 'AnySearch',
  xiaohongshu: '小红书',
  zhihu: '知乎',
}

const SOURCE_IDS = Object.keys(LABELS)

// 站点限定搜索的目标域名（不带 www.，匹配时容忍 www. 前缀与子域）
const SITE_HOSTS = {
  xiaohongshu: ['xiaohongshu.com', 'xhslink.com'],
  zhihu: ['zhihu.com'],
}

const msg = (e) => (e && e.message ? e.message : String(e))
const clampInt = (n, lo, hi) => Math.max(lo, Math.min(hi, Number.isFinite(n) ? Math.floor(n) : lo))

/** 组合调用方取消信号与固定超时（AbortSignal.any 不接受 undefined 元素）。 */
function withTimeout(signal, timeoutMs) {
  const signals = []
  if (signal) signals.push(signal)
  signals.push(AbortSignal.timeout(timeoutMs))
  return AbortSignal.any(signals)
}

function uniqueByUrl(results) {
  const seen = new Set()
  const out = []
  for (const r of results) {
    if (!r || typeof r.url !== 'string' || r.url.length === 0 || seen.has(r.url)) continue
    seen.add(r.url)
    out.push(r)
  }
  return out
}

// ── 密钥解析 ────────────────────────────────────────────────────────────────

async function resolveKey(ctx, literal, envName) {
  if (typeof literal === 'string' && literal.length > 0) return literal
  const ref = credentialRef(envName)
  try {
    const creds = ctx.get('credentials')
    if (creds && typeof creds.resolve === 'function') {
      const resolved = await creds.resolve(ref)
      if (resolved && typeof resolved.value === 'string' && resolved.value.length > 0) return resolved.value
    }
  } catch { /* 回退到环境变量 */ }
  try {
    const entry = launchEnvironmentOf(ctx).get(envName)
    if (entry && typeof entry.value === 'string' && entry.value.length > 0) return entry.value
  } catch { /* 回退 */ }
  if (typeof process !== 'undefined' && process.env && typeof process.env[envName] === 'string' && process.env[envName].length > 0) return process.env[envName]
  return undefined
}

/** available() 需要同步判定：只查字面量配置与环境变量。 */
function hasAnyKey(ctx, cfg) {
  if (typeof cfg.tavilyApiKey === 'string' && cfg.tavilyApiKey.length > 0) return true
  if (typeof cfg.anysearchApiKey === 'string' && cfg.anysearchApiKey.length > 0) return true
  for (const envName of ['TAVILY_API_KEY', 'ANYSEARCH_API_KEY']) {
    if (typeof process !== 'undefined' && process.env && process.env[envName]) return true
    try {
      const entry = launchEnvironmentOf(ctx).get(envName)
      if (entry && entry.value) return true
    } catch { /* ignore */ }
  }
  return false
}

// ── Tavily 适配器 ───────────────────────────────────────────────────────────

async function tavilySearch(query, key, maxResults, signal, timeoutMs, opts = {}) {
  const body = {
    api_key: key,
    query,
    search_depth: 'advanced',
    include_answer: true,
    max_results: maxResults,
  }
  if (Array.isArray(opts.includeDomains) && opts.includeDomains.length > 0) body.include_domains = opts.includeDomains
  const res = await fetch(TAVILY_ENDPOINT, {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'user-agent': 'deepseek-harness/multi-search' },
    body: JSON.stringify(body),
    signal: withTimeout(signal, timeoutMs),
  })
  if (!res.ok) throw new Error(`Tavily HTTP ${res.status}: ${(await res.text()).slice(0, 300)}`)
  const data = await res.json()
  return {
    answer: typeof data.answer === 'string' && data.answer.length > 0 ? data.answer : undefined,
    results: (Array.isArray(data.results) ? data.results : [])
      .map((r) => ({
        title: typeof r.title === 'string' ? r.title : '',
        url: typeof r.url === 'string' ? r.url : '',
        snippet: typeof r.content === 'string' ? r.content : '',
        publishedAt: typeof r.published_date === 'string' ? r.published_date : '',
      }))
      .filter((r) => r.url.length > 0),
  }
}

// ── AnySearch 适配器（JSON-RPC 2.0 over MCP 端点）──────────────────────────

/** 兼容 SSE 包装（text/event-stream）与纯 JSON 响应。 */
function parseMaybeSse(text) {
  const t = String(text ?? '')
  if (!/^\s*data\s*:/m.test(t)) {
    try { return JSON.parse(t) } catch { return undefined }
  }
  const lines = t.split(/\r?\n/).filter((l) => /^\s*data\s*:/.test(l)).map((l) => l.replace(/^\s*data\s*:\s*/, '').trim())
  try { return JSON.parse(lines.join('')) } catch { /* try first line */ }
  try { return JSON.parse(lines[0]) } catch { return undefined }
}

function mapAnysearchItem(it) {
  if (!it || typeof it !== 'object') return undefined
  const url = it.url || it.link || it.href
  if (typeof url !== 'string' || url.length === 0) return undefined
  return {
    title: it.title || it.name || '',
    url,
    snippet: it.snippet || it.content || it.description || it.summary || '',
    publishedAt: it.published_at || it.publishedAt || it.date || '',
  }
}

/**
 * 解析 AnySearch 的 Markdown 结果格式（实测样例）：
 *   ## Search Results (3 results, ...)
 *   ### 1. 标题
 *   - **URL**: https://...
 *   - **Published**: ...（可选字段行）
 *   - 摘要正文……
 */
function parseAnysearchMarkdown(text) {
  const results = []
  const blocks = String(text ?? '').split(/(?=^###\s+\d+\.\s+)/m)
  for (const block of blocks) {
    const head = block.match(/^###\s+\d+\.\s+(.*)$/m)
    if (!head) continue
    const urlMatch = block.match(/^\s*-\s*\*\*URL\*\*\s*:\s*(.+)$/m)
    if (!urlMatch) continue
    const url = urlMatch[1].trim()
    if (url.length === 0) continue
    const snippetLines = block.split(/\r?\n/)
      .map((l) => l.trim())
      .filter((l) => l.startsWith('- ') && !/^-\s*\*\*[^*]+\*\*\s*:/.test(l))
      .map((l) => l.slice(2).trim())
    const dateMatch = block.match(/^\s*-\s*\*\*(?:Published|Date|日期)\*\*\s*:\s*(.+)$/m)
    results.push({
      title: head[1].trim(),
      url,
      snippet: snippetLines.join('\n').slice(0, 800),
      publishedAt: dateMatch ? dateMatch[1].trim() : '',
    })
  }
  return results
}

/** AnySearch 返回的 content[0].text 可能是 JSON 或 Markdown，做宽容解析。 */
function parseAnysearchPayload(text) {
  const t = (text || '').trim()
  if (!t) return { results: [] }
  // 1) JSON
  let parsed
  try { parsed = JSON.parse(t) } catch { parsed = undefined }
  if (parsed !== undefined && typeof parsed === 'object') {
    const items = Array.isArray(parsed)
      ? parsed
      : (parsed.results ?? parsed.items ?? parsed.data ?? (parsed.result && (parsed.result.results || parsed.result.items)))
    if (Array.isArray(items)) {
      const results = items.map(mapAnysearchItem).filter(Boolean)
      if (results.length > 0) return { results }
    }
  }
  // 2) Markdown 块解析（### N. 标题 + - **URL**: ...）
  const mdResults = parseAnysearchMarkdown(t)
  if (mdResults.length > 0) return { results: mdResults }
  // 3) Markdown 链接兜底
  const results = []
  const re = /\[([^\]]*)\]\((https?:\/\/[^)\s]+)\)/g
  let m
  while ((m = re.exec(t)) && results.length < 20) results.push({ title: (m[1] || m[2]).trim(), url: m[2] })
  return { results, raw: t.slice(0, 1500) }
}

async function anysearchSearch(query, key, maxResults, signal, timeoutMs) {
  const res = await fetch(ANYSEARCH_ENDPOINT, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      accept: 'application/json, text/event-stream',
      ...(key ? { authorization: `Bearer ${key}` } : {}),
      'user-agent': 'deepseek-harness/multi-search',
    },
    body: JSON.stringify({
      jsonrpc: '2.0',
      id: 1,
      method: 'tools/call',
      params: { name: 'search', arguments: { query, max_results: maxResults } },
    }),
    signal: withTimeout(signal, timeoutMs),
  })
  if (!res.ok) throw new Error(`AnySearch HTTP ${res.status}: ${(await res.text()).slice(0, 300)}`)
  const json = parseMaybeSse(await res.text())
  if (!json) throw new Error('AnySearch: 无法解析响应')
  if (json.error) throw new Error(`AnySearch RPC 错误: ${JSON.stringify(json.error).slice(0, 300)}`)
  const content = json.result && Array.isArray(json.result.content) ? json.result.content : []
  if (json.result && json.result.isError === true) {
    const text = content.map((c) => (c && c.text) || '').join('\n')
    throw new Error(`AnySearch 返回错误: ${(text || 'isError=true').slice(0, 300)}`)
  }
  const text = content.map((c) => (c && c.text) || '').join('\n')
  return parseAnysearchPayload(text)
}

// ── 小红书 / 知乎：站点限定搜索 ──────────────────────────────────────────────

function hostMatches(url, hosts) {
  try {
    let h = new URL(url).hostname.toLowerCase()
    if (h.startsWith('www.')) h = h.slice(4)
    return hosts.some((x) => {
      const base = x.toLowerCase().replace(/^www\./, '')
      return h === base || h.endsWith('.' + base)
    })
  } catch { return false }
}

async function siteSearch(ctx, cfg, id, query, maxResults, signal) {
  const hosts = SITE_HOSTS[id]
  const siteClause = hosts.map((h) => `site:${h}`).join(' OR ')
  const siteQuery = `${query} ${siteClause}`
  const results = []
  const via = []
  const errors = []

  // 两个后端都尝试（有 key 时），合并去重 —— 小红书/知乎在通用索引里命中率低，双后端提高覆盖率
  const tavilyKey = await resolveKey(ctx, cfg.tavilyApiKey, 'TAVILY_API_KEY')
  if (tavilyKey) {
    try {
      const out = await tavilySearch(siteQuery, tavilyKey, maxResults, signal, cfg.requestTimeoutMs, { includeDomains: hosts })
      results.push(...out.results.filter((r) => hostMatches(r.url, hosts)))
      via.push('tavily')
    } catch (e) { errors.push(`tavily: ${msg(e)}`) }
  }

  const anyKey = await resolveKey(ctx, cfg.anysearchApiKey, 'ANYSEARCH_API_KEY')
  if (anyKey) {
    try {
      const out = await anysearchSearch(siteQuery, anyKey, maxResults, signal, cfg.requestTimeoutMs)
      results.push(...out.results.filter((r) => hostMatches(r.url, hosts)))
      via.push('anysearch')
    } catch (e) { errors.push(`anysearch: ${msg(e)}`) }
  }

  if (via.length === 0) {
    throw new Error(
      `站点限定搜索（${LABELS[id]}）需要 TAVILY_API_KEY 或 ANYSEARCH_API_KEY`
      + (errors.length ? `；后端错误：${errors.join('; ')}` : '')
    )
  }
  return { via: via.join('+'), results: uniqueByUrl(results).slice(0, maxResults) }
}

// ── 编排 ────────────────────────────────────────────────────────────────────

async function runOne(ctx, cfg, id, query, maxResults, signal) {
  if (id === 'tavily') {
    const key = await resolveKey(ctx, cfg.tavilyApiKey, 'TAVILY_API_KEY')
    if (!key) throw new Error('缺少 TAVILY_API_KEY（环境变量 / DSH 凭据 / 插件配置）')
    return await tavilySearch(query, key, maxResults, signal, cfg.requestTimeoutMs)
  }
  if (id === 'anysearch') {
    const key = await resolveKey(ctx, cfg.anysearchApiKey, 'ANYSEARCH_API_KEY')
    if (!key) throw new Error('缺少 ANYSEARCH_API_KEY（环境变量 / DSH 凭据 / 插件配置）')
    return await anysearchSearch(query, key, maxResults, signal, cfg.requestTimeoutMs)
  }
  return await siteSearch(ctx, cfg, id, query, maxResults, signal)
}

async function searchAll(ctx, cfg, query, maxResults, signal) {
  const ids = Array.isArray(cfg.sources) && cfg.sources.length > 0
    ? cfg.sources.filter((s) => SOURCE_IDS.includes(s))
    : SOURCE_IDS
  const settled = await Promise.allSettled(ids.map((id) => runOne(ctx, cfg, id, query, maxResults, signal)))
  const groups = []
  const answers = []
  settled.forEach((s, i) => {
    const id = ids[i]
    if (s.status === 'fulfilled') {
      const v = s.value
      if (typeof v.answer === 'string' && v.answer.length > 0) answers.push(v.answer)
      groups.push({
        id,
        label: LABELS[id],
        ok: true,
        via: typeof v.via === 'string' ? v.via : undefined,
        count: Array.isArray(v.results) ? v.results.length : 0,
        results: Array.isArray(v.results) ? v.results : [],
      })
    } else {
      groups.push({ id, label: LABELS[id], ok: false, error: msg(s.reason), count: 0, results: [] })
    }
  })
  return { groups, answers }
}

function projectSource(r) {
  return {
    url: r.url,
    ...(r.title ? { title: r.title } : {}),
    ...(r.snippet ? { snippet: r.snippet } : {}),
    ...(r.publishedAt ? { publishedAt: r.publishedAt } : {}),
  }
}

// ── 插件主体 ────────────────────────────────────────────────────────────────

export function apply(ctx, config = {}) {
  const cfg = {
    defaultMaxResults: DEFAULT_MAX_RESULTS,
    requestTimeoutMs: REQUEST_TIMEOUT_MS,
    ...config,
  }

  const disposers = []

  // 1) 模型工具 search_multi
  const tool = defineTool({
    name: 'search_multi',
    description:
      '多信息源聚合搜索：一次调用并行检索 Tavily、AnySearch、小红书、知乎四个信息源，按源分组返回结构化 JSON（含每源结果与跨源去重总数）。小红书与知乎没有公开 API（知乎带 x-zse-96 签名反爬），通过 Tavily/AnySearch 的 site: 站点限定搜索实现，结果仅保留对应域名。需要 API 密钥：TAVILY_API_KEY、ANYSEARCH_API_KEY（可放环境变量、DSH 凭据服务或插件配置）。',
    parameters: {
      query: { type: 'string', required: true, description: '搜索查询' },
      sources: {
        type: 'array',
        items: { type: 'string', enum: ['tavily', 'anysearch', 'xiaohongshu', 'zhihu'] },
        description: '要查询的信息源（默认全部四个）',
      },
      max_results: { type: 'integer', description: '每个信息源最多返回条数，1-10，默认 5' },
    },
    output: {
      schema: { type: 'string' },
      render(_a, v) { return [{ type: 'text', text: String(v) }] },
    },
    timeoutMs: 120000,
    isConcurrencySafe: () => true,
    async execute(args, exec) {
      const query = String(args && args.query ? args.query : '').trim()
      if (!query) return JSON.stringify({ ok: false, error: 'query 不能为空' })
      const maxResults = clampInt(Number(args && args.max_results) || cfg.defaultMaxResults, 1, MAX_RESULTS_CAP)
      const runCfg = {
        ...cfg,
        ...(Array.isArray(args && args.sources) && args.sources.length > 0 ? { sources: args.sources.map(String) } : {}),
      }
      const { groups, answers } = await searchAll(ctx, runCfg, query, maxResults, exec && exec.signal)
      const okCount = groups.filter((g) => g.ok).length
      const total = uniqueByUrl(groups.flatMap((g) => g.results)).length
      return JSON.stringify({
        ok: okCount > 0,
        query,
        max_results: maxResults,
        sources: groups,
        total_unique: total,
        ...(answers.length > 0 ? { answer: answers.join('\n\n') } : {}),
        hint: '小红书/知乎无公开 API，经 Tavily/AnySearch 的 site: 站点限定搜索实现；引用结果时用 markdown 链接标注来源。',
      }, null, 1)
    },
  })
  disposers.push(ctx.tools.register(tool))

  // 2) ctx.web 搜索 provider `multi`（内置 web_search 可选路由：searchProvider: multi）
  const web = ctx.web
  if (web && typeof web.registerSearchProvider === 'function') {
    const provider = {
      id: 'multi',
      available: () => hasAnyKey(ctx, cfg),
      async search(request, signal) {
        const maxResults = request && request.maxResults ? request.maxResults : cfg.defaultMaxResults
        const { groups, answers } = await searchAll(ctx, cfg, request.query, maxResults, signal)
        if (!groups.some((g) => g.ok)) {
          throw new WebError(`multi 搜索全部失败: ${groups.map((g) => g.error).filter(Boolean).join('; ')}`, 'WEB_PROVIDER_ERROR')
        }
        const sources = uniqueByUrl(groups.flatMap((g) => g.results)).map(projectSource)
        return {
          ...(answers.length > 0 ? { content: answers.join('\n\n') } : {}),
          sources,
          truncated: sources.length > maxResults,
        }
      },
    }
    disposers.push(web.registerSearchProvider(provider))
  }

  return () => {
    for (const dispose of disposers) {
      try { dispose() } catch { /* ignore */ }
    }
  }
}
