// heavyskill-tool 动态插件（Host 半部源码）
// 用途：注册模型工具 heavyskill（两阶段多轨迹推理），走宿主 llm 服务。
// 重建：cordis_define(kind new, idPrefix 'hvy', code.host = 本文件内容) + cordis_run。
// 注意：动态插件进程级，DSH 重启后需重建。
return {
  apply(ctx) {
    const llm = ctx.get('llm')
    if (llm === undefined) return

    harness.registerTool(ctx, harness.defineTool({
      name: 'heavyskill',
      description: 'HeavySkill 两阶段多轨迹推理工具：先并行生成 K 条独立推理轨迹（temperature 1.0），再让模型审议全部轨迹、找错、交叉验证并综合出最终答案。适用于复杂推理、技术方案/代码/文档深度审查、多步推导。重要：所有待分析内容必须完整内联在 query 中（模型无法读取本地文件）。返回 JSON。',
      parameters: {
        type: 'object',
        properties: {
          query: { type: 'string', description: '待推理/审查的完整内容（必须内联全部材料、代码、清单）' },
          reason_k: { type: 'integer', description: '并行推理轨迹数，1-16，默认 8（越大越慢越贵）' },
          summary_k: { type: 'integer', description: '审议使用的轨迹数，1~reason_k，默认 4' },
          language: { type: 'string', enum: ['cn', 'en'], description: '提示词语言，默认 cn' },
          provider: { type: 'string', description: '模型 provider（默认取当前会话模型路由）' },
          model: { type: 'string', description: '模型名（默认取当前会话模型路由）' },
        },
        required: ['query'],
      },
      output: {
        schema: { type: 'string' },
        render(_a, v) { return [{ type: 'text', text: String(v) }] },
      },
      async execute(args) {
        const query = String(args.query || '').trim()
        if (!query) return JSON.stringify({ ok: false, error: 'query 为空' })
        const k = Math.max(1, Math.min(16, Number(args.reason_k) || 8))
        const s = Math.max(1, Math.min(k, Number(args.summary_k) || 4))
        const lang = args.language === 'en' ? 'en' : 'cn'

        let provider, model
        try {
          const sel = ctx.get('agentDefaultModel')?.currentSelection?.()
          provider = args.provider || sel?.provider
          model = args.model || sel?.model
        } catch (_) { /* keep defaults */ }
        provider = provider || 'deepseek-official'
        model = model || 'deepseek-v4-flash'

        const sysPrompt = lang === 'cn'
          ? '你是一个有用的助手。请逐步思考来解决这个问题，清晰地展示推理过程，最后一行给出：最终答案：<答案>'
          : 'You are a helpful assistant. Think step-by-step to solve the problem, show your reasoning, and end with: **Final Answer:** <answer>'
        const delibSys = lang === 'cn'
          ? '你是一个高级推理分析专家。请仔细分析多个推理尝试，找出逻辑错误、计算错误与错误假设，交叉验证答案，并综合给出最终结论。最后一行给出：最终答案：<答案>'
          : 'You are an expert reasoning analyst. Carefully analyze multiple reasoning attempts, identify errors, cross-validate answers, and synthesize a final conclusion. End with: **Final Answer:** <answer>'

        async function callOnce(temp, system, userPrompt) {
          const msg = {
            id: 'hs-' + Math.random().toString(36).slice(2),
            role: 'user',
            content: [{ type: 'text', text: userPrompt }],
            source: { kind: 'user' },
          }
          let text = ''
          let ok = false
          try {
            for await (const chunk of llm.stream({ provider, model, messages: [msg], system, temperature: temp, maxTokens: 2048 })) {
              if (chunk.type === 'text-delta') text += chunk.text
              if (chunk.type === 'finish') ok = chunk.reason?.kind === 'stop'
            }
          } catch (e) {
            text += '\n[ERROR: ' + ((e && e.message) || String(e)) + ']'
          }
          return { text, ok }
        }

        function extract(text) {
          const pats = [
            /\*\*(?:最终)?答案[：:]\s*\*\*\s*([^\n]+)/,
            /\*\*(?:Final\s+)?Answer[:\\s]*\*\*\s*([^\n]+)/,
            /(?:最终)?答案[为是：:]\s*([^\n。]+)/,
            /(?:final|the)\s+answer\s+(?:is|:)\s*([^\n]+)/,
          ]
          for (const p of pats) { const m = text.match(p); if (m) return m[1].trim() }
          const lines = text.trim().split('\n').filter(Boolean)
          return lines.length ? lines[lines.length - 1].trim().slice(0, 200) : ''
        }

        const tasks = Array.from({ length: k }, () => callOnce(1.0, sysPrompt, query))
        const results = await Promise.all(tasks)
        const trajectories = results.map((r) => r.text)
        const answers = trajectories.map(extract).filter(Boolean)
        const okCount = results.filter((r) => r.ok).length

        const freq = {}
        answers.forEach((a) => { freq[a] = (freq[a] || 0) + 1 })
        let consensus = ''
        let maxN = 0
        for (const a in freq) { if (freq[a] > maxN) { maxN = freq[a]; consensus = a } }

        const picked = trajectories.slice(0, s)
        const delibPrompt = lang === 'cn'
          ? '以下是针对同一问题的 ' + s + ' 个独立推理尝试：\n\n' + picked.map((t, i) => '--- 轨迹' + (i + 1) + ' ---\n' + t).join('\n\n') + '\n\n请逐条找出错误、交叉验证、综合出最终答案。'
          : 'Here are ' + s + ' independent reasoning attempts for the same problem:\n\n' + picked.map((t, i) => '--- Attempt ' + (i + 1) + ' ---\n' + t).join('\n\n') + '\n\nIdentify errors, cross-validate, and synthesize a final answer.'
        const delib = await callOnce(0.7, delibSys, delibPrompt)
        const final = extract(delib.text) || consensus

        return JSON.stringify({
          ok: okCount > 0,
          final_answer: final,
          consensus_answer: consensus,
          trajectories_ok: okCount + '/' + k,
          used_for_deliberation: s,
          answer_frequency: freq,
          error: okCount === 0 ? ((trajectories.find((t) => t.includes('[ERROR:')) || '全部轨迹失败')) : undefined,
        }, null, 1)
      },
    }))
  },
}
