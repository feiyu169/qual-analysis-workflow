// Codex 工作台（右侧浮动面板）— HGF Phase 1
// ============================================
// 会话运行中的右侧工作台：模型选择（侧边栏独立对话用所选模型，不改主会话）
// + 迷你对话（Host 桥调 ctx.llm.stream）+ Goal 卡片（工作安排）。
//
// 架构：
//   Host 半：harness.handle('workspace-chat') → ctx.llm.stream(provider/model/messages)
//   Client 半：shell.overlay 注册面板（additive，不动官方座）
//     - 模型列表: sessions.models({sessionId}) → { current, groups }
//     - Goal: sessions.binding(sessionId)?.session.projections.faceOf('goal')
//     - 对话: host.call('workspace-chat', {provider, model, messages})
//
// 生命周期：动态插件会话级；重建 = cordis_define(kind new, idPrefix wkp) + cordis_run。
//
// 契约要点（已取证）：
//   - GenerateOptions: { provider, model, messages: Message[], system? }
//   - Message: { role, content: [{ type:'text', text }] }
//   - StreamChunk: { type:'text-delta', text }（收集文本增量）
//   - overlay standardProps: useSessions/useWorkspaces（无 useProjection → goal 走 binding）
//   - 模型选择是 Agent(会话) 级 → 侧边栏对话独立调 llm，不影响主会话

// ── Host 半 ──────────────────────────────────────────────────────────────
return {
  name: 'codex-workspace',
  apply(ctx) {
    // Host RPC：模型目录（llm 服务构造可选列表 + agentDefaultModel 取当前）
    harness.handle('workspace-models', async () => {
      const llm = ctx.get('llm')
      const adm = ctx.get('agentDefaultModel')
      if (llm === undefined) return { error: 'llm 服务不可用' }
      try {
        const groups = []
        const providers = llm.listConfigurableProviders ? llm.listConfigurableProviders() : []
        for (const p of providers || []) {
          let models = []
          try {
            const infos = await llm.listModels(p.provider)
            models = (infos || []).map(function (m) { return { id: m.id, name: m.name || m.id } })
          } catch (e) { models = [] }
          groups.push({ provider: p.provider, name: p.name || p.provider, models: models })
        }
        const current = adm ? adm.currentSelection() : null
        return { current: current ? { provider: current.provider, model: current.model } : null, groups: groups }
      } catch (e) {
        return { error: String(e && e.message ? e.message : e) }
      }
    })

    // Host RPC：侧边栏对话（用所选 provider/model 独立调用，非流式聚合返回）
    harness.handle('workspace-chat', async (args) => {
      const llm = ctx.get('llm')
      if (llm === undefined) return { error: 'llm 服务不可用' }
      try {
        const messages = (args.messages || []).map(function (m) {
          return { role: m.role, content: [{ type: 'text', text: String(m.content) }] }
        })
        const options = {
          provider: args.provider,
          model: args.model,
          messages: messages,
        }
        if (args.system) options.system = String(args.system)
        const textParts = []
        for await (const chunk of llm.stream(options)) {
          if (chunk && chunk.type === 'text-delta' && chunk.text) {
            textParts.push(chunk.text)
          }
        }
        return { reply: textParts.join('') }
      } catch (e) {
        return { error: String(e && e.message ? e.message : e) }
      }
    })
  },
}
