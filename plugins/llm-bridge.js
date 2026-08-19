// llm-bridge 动态插件（Host 半部源码）
// 用途：在宿主 web 服务器注册 POST /api/llm-bridge，Python 侧工作流经它调用宿主 llm 服务。
// 重建：用 cordis_define(kind new, idPrefix 'lbr', code.host = 本文件内容) + cordis_run。
// 注意：动态插件进程级，DSH 重启后需重建（本预设启动指令会自动检查并重建）。
return {
  apply(ctx) {
    const llm = ctx.get('llm')
    const webServer = ctx.get('webServer')
    if (llm === undefined || webServer === undefined) return

    const dispose = webServer.register({
      kind: 'exact',
      path: '/api/llm-bridge',
      handler: async (req, res) => {
        const send = (status, obj) => {
          try {
            res.writeHead(status, { 'Content-Type': 'application/json' })
            res.end(JSON.stringify(obj))
          } catch (_) { /* ignore */ }
        }
        if (req.method !== 'POST') return send(405, { ok: false, error: 'method not allowed' })

        let body = ''
        for await (const chunk of req) {
          body += chunk
          if (body.length > 1024 * 1024) return send(413, { ok: false, error: 'body too large' })
        }
        let args
        try { args = JSON.parse(body) } catch (_) { return send(400, { ok: false, error: 'bad json' }) }

        let provider, model
        try {
          const svc = ctx.get('agentDefaultModel')
          const sel = svc && svc.currentSelection && svc.currentSelection()
          provider = args.provider || (sel && sel.provider)
          model = args.model || (sel && sel.model)
        } catch (_) { /* keep defaults */ }
        provider = provider || 'deepseek-official'
        model = model || 'deepseek-v4-flash'

        const system = typeof args.system === 'string' ? args.system : undefined
        const temperature = typeof args.temperature === 'number' ? args.temperature : 0.7
        const maxTokens = typeof args.maxTokens === 'number' ? args.maxTokens : 4096
        const msgs = Array.isArray(args.messages) ? args.messages : []
        if (msgs.length === 0) return send(400, { ok: false, error: 'no messages' })
        const messages = msgs.map((m, i) => ({
          id: 'lb-' + i + '-' + Math.random().toString(36).slice(2),
          role: m.role === 'assistant' ? 'assistant' : 'user',
          content: [{ type: 'text', text: String(m.content || '') }],
          source: { kind: 'user' },
        }))

        try {
          let text = ''
          let ok = false
          let finishReason = null
          for await (const chunk of llm.stream({ provider, model, messages, system, temperature, maxTokens })) {
            if (chunk.type === 'text-delta') text += chunk.text
            if (chunk.type === 'finish') {
              finishReason = chunk.reason && chunk.reason.kind
              ok = finishReason === 'stop'
            }
          }
          return send(200, { ok, text, provider, model, finishReason })
        } catch (e) {
          return send(500, { ok: false, error: (e && e.message) || String(e) })
        }
      },
    })

    ctx.effect(() => dispose)
  },
}
