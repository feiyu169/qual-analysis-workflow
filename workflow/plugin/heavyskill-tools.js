// HeavySkill → DSH 动态插件（一期，2026-08-22，参照 hgf-tools.js 模式）
// =========================================
// 把 HeavySkill 审查引擎（Python，skills/heavyskill/）以原生工具暴露给模型。
// 架构：模型调用工具 → 插件通过"长驻 stdio 桥"复用同一个 Python 进程
// （heavyskill_bridge.py --serve），消除每次调用的解释器冷启动。
//
// 与 hgf-tools.js 同款机制：
//   1. 长驻进程复用（apply 时懒启动 --serve，后续写 stdin/读 stdout）；
//   2. 命令级超时（COMMAND_TIMEOUT 表 + ctx.timeout，超时 terminate 进程树并自动重建）；
//   3. 并发限流（请求队列串行）；
//   4. 结构化错误（JSON.parse 失败/进程退出/超时 → 带命令名的可读错误）；
//   5. env fail-fast（HSK_BRIDGE / HSK_PYTHON 缺失回退硬编码路径）。
//
// 裁判准出（2026-08-22 裁决书）：
//   - 桥返回 ≤5KB 摘要（完整结果写临时文件），工具回传 {summary, file}；
//   - 蜜罐自检：hsk_review 内置已知结果用例，防止缓存/硬编码伪装。
//
// 生命周期说明：动态插件是"会话级"——进程重启后消失。本文件是持久化源码，
// 需要时重建：cordis_define（kind new，idPrefix 'hsk'）+ cordis_run。
// 工具集（4 个）：hsk_review / hsk_verify / hsk_history / hsk_adjudicate。

return {
  name: 'heavyskill-tools',
  inject: ['timer'],
  apply(ctx) {
    const BRIDGE = (typeof process !== 'undefined' && process.env && process.env.HSK_BRIDGE)
      ? process.env.HSK_BRIDGE
      : 'D:\\OneDrive\\文档\\deepseek harness workspace\\skills\\heavyskill\\heavyskill_bridge.py'
    const FALLBACK_PYTHON = (typeof process !== 'undefined' && process.env && process.env.HSK_PYTHON)
      ? process.env.HSK_PYTHON
      : 'C:\\Users\\79902\\AppData\\Local\\Programs\\Python\\Python314\\python.exe'

    // 命令级超时（毫秒）：K=8 实测 3-8 分钟；verify/轻命令短
    const COMMAND_TIMEOUT = {
      review: 10 * 60 * 1000,
      verify: 3 * 60 * 1000,
      history: 15 * 1000,
      adjudicate: 15 * 1000,
    }
    const DEFAULT_TIMEOUT = 15 * 1000

    let proc = null
    let procDied = false
    let nextId = 1
    let queue = []
    let current = null
    let lineBuf = ''
    let pythonPath = null

    async function getPython(sub) {
      if (pythonPath) return pythonPath
      try {
        pythonPath = await sub.resolveExecutable('python')
      } catch (e) {
        pythonPath = FALLBACK_PYTHON
      }
      return pythonPath
    }

    function failAll(message) {
      if (current) {
        if (current.timer) { try { current.timer() } catch (e) {} }
        current.reject(new Error(message))
        current = null
      }
      while (queue.length) {
        const req = queue.shift()
        if (req.timer) { try { req.timer() } catch (e) {} }
        req.reject(new Error(message))
      }
    }

    function onStdoutData(chunk) {
      lineBuf += String(chunk)
      let idx
      while ((idx = lineBuf.indexOf('\n')) >= 0) {
        const line = lineBuf.slice(0, idx).trim()
        lineBuf = lineBuf.slice(idx + 1)
        if (!line) continue
        let resp
        try {
          resp = JSON.parse(line)
        } catch (e) {
          // 桥返回非法 JSON：结构化错误；若行超长（>1MB）可能是摘要压缩失效，提示
          if (current) {
            if (current.timer) { try { current.timer() } catch (e2) {} }
            const err = new Error('HeavySkill 桥返回非法 JSON: ' + line.slice(0, 500) + (line.length > 1048576 ? '（行超长，摘要压缩可能失效）' : ''))
            current.reject(err)
            current = null
          }
          continue
        }
        if (!current || resp.id !== current.id) continue
        if (current.timer) { try { current.timer() } catch (e2) {} }
        const req = current
        current = null
        if (resp.ok) req.resolve(resp.result)
        else req.reject(new Error('HeavySkill 桥错误: ' + (resp.error || '未知错误')))
        pump()
      }
    }

    function onProcDone(outcome) {
      procDied = true
      const reason = 'HeavySkill 桥进程退出 (exit ' + outcome.exitCode + (outcome.signal ? ', signal ' + outcome.signal : '') + ')'
      failAll(reason)
      proc = null
    }

    function onProcSpawnError(e) {
      procDied = true
      failAll('HeavySkill 桥启动失败: ' + String(e && e.message ? e.message : e) +
        '（如需移动工作区，请设置 HSK_BRIDGE / HSK_PYTHON 环境变量）')
      proc = null
    }

    async function spawnProc() {
      const sub = ctx.get('subprocess')
      if (sub === undefined) throw new Error('subprocess 服务不可用')
      const python = await getPython(sub)
      const handle = sub.spawn({
        argv: [python, BRIDGE, '--serve'],
        cwd: '.',
        stdio: {
          stdin: 'pipe',
          stdout: 'pipe',
          stderr: { maxBytes: 256 * 1024 },
        },
        graceMs: 3000,
      })
      proc = handle
      procDied = false
      lineBuf = ''
      handle.stdout.on('data', onStdoutData)
      handle.done.then(onProcDone).catch(onProcSpawnError)
    }

    function pump() {
      if (current || !proc || procDied || queue.length === 0) return
      const req = queue.shift()
      current = req
      req.timer = ctx.timeout(function () {
        const err = new Error('HeavySkill 命令超时 (' + req.command + ', ' + req.timeoutMs + 'ms)')
        if (proc) { try { proc.terminate() } catch (e) {} }
        current = null
        req.reject(err)
      }, req.timeoutMs)
      try {
        proc.stdin.write(JSON.stringify({ id: req.id, command: req.command, args: req.args }) + '\n')
      } catch (e) {
        if (req.timer) { try { req.timer() } catch (e2) {} }
        current = null
        procDied = true
        req.reject(new Error('HeavySkill 桥写入失败: ' + String(e && e.message ? e.message : e)))
        if (proc) { try { proc.terminate() } catch (e3) {} }
        proc = null
      }
    }

    function runBridge(command, args) {
      const timeoutMs = COMMAND_TIMEOUT[command] || DEFAULT_TIMEOUT
      return new Promise(function (resolve, reject) {
        const req = { id: nextId++, command: command, args: args, resolve: resolve, reject: reject, timeoutMs: timeoutMs, timer: null }
        const enqueue = function () {
          queue.push(req)
          pump()
        }
        if (!proc || procDied) {
          spawnProc().then(enqueue).catch(function (e) { reject(e) })
        } else {
          enqueue()
        }
      })
    }

    // 蜜罐：内置已知结果用例（裁判准出——防缓存/硬编码伪装）
    // 用明确数字答案 + 足够预算，避免小预算截断导致误报
    const HONEYPOT = { query: '只输出数字：2+2=?', expectContains: '4', k: 1, max_tokens: 512, model: 'deepseek-chat' }
    async function honeypotCheck() {
      try {
        const r = await runBridge('review', { query: HONEYPOT.query, k: HONEYPOT.k, max_tokens: HONEYPOT.max_tokens, model: HONEYPOT.model })
        const ans = String((r.summary && r.summary.final_answer) || '')
        return ans.indexOf(HONEYPOT.expectContains) >= 0
      } catch (e) {
        return false
      }
    }

    function renderResult(_a, v) {
      let text = 'OK'
      if (v && typeof v === 'object') {
        if (v.summary) {
          const s = v.summary
          text = 'HeavySkill 审查完成 | 最终答案: ' + String(s.final_answer || 'None').slice(0, 120)
          if (s.truncation && (s.truncation.reasoning_truncated_count > 0 || s.truncation.deliberation_truncated)) {
            text += ' | ⚠️ 存在截断: ' + JSON.stringify(s.truncation)
          }
          if (s.validation && s.validation.verdict) {
            text += ' | 验证: ' + s.validation.verdict + '（' + s.validation.issues.length + ' issue）'
          }
          if (s.second_review && s.second_review.final_verdict) {
            text += ' | 二审: ' + s.second_review.final_verdict + (s.second_review.conflict ? '（分歧）' : '')
          }
          text += ' | tokens ' + s.total_tokens + ' | ' + s.total_latency_seconds + 's | 完整结果: ' + String(v.file)
        } else if (v.samples !== undefined) {
          text = '样本库: ' + v.total + ' 条' + (v.samples.length ? ' | 最近: ' + v.samples.map(function (s) { return s.sample_id }).join(',') : '')
        } else if (v.updated !== undefined) {
          text = '裁决已更新: ' + v.sample_id
        } else if (v.verdict !== undefined) {
          text = '验证: ' + v.verdict + (v.issues && v.issues.length ? ' | ' + v.issues.length + ' issue' : '') + (v.llm_checked ? '（mimo 已校验）' : '（仅规则）')
        }
      }
      return [{ type: 'text', text: String(text) }]
    }

    const tools = [
      harness.defineTool({
        name: 'hsk_review',
        description: 'HeavySkill 多轨迹深度审查：K 路并行推理 + 顺序审议（可含 mimo 验证/二审/分批）。返回摘要 + 完整结果文件路径。mode=basic 常规 / enhanced 双模型（需 mimo key）/ chunked 大内容分批。',
        parameters: {
          query: { type: 'string', required: true, description: '审查请求（内联被审内容或描述任务；大内容用 content 参数）' },
          content: { type: 'string', description: '被审内容全文（>18000 字符时用 mode=chunked 自动分批）' },
          k: { type: 'integer', description: '并行轨迹数（默认 8，K=4 快速 / K=8 标准）' },
          mode: { type: 'string', description: 'basic|enhanced|chunked（默认 basic）' },
          api_key: { type: 'string', description: 'deepseek API key（默认环境 DEEPSEEK_API_KEY）' },
          validator_api_key: { type: 'string', description: 'mimo key（enhanced 模式，默认环境 XIAOMI_KEY）' },
          max_tokens: { type: 'integer', description: '单轨迹输出预算（默认 32768）' },
          summary_max_tokens: { type: 'integer', description: '审议输出预算（默认 16384）' },
          language: { type: 'string', description: 'cn|en（默认 cn）' },
        },
        output: { schema: { type: 'object', additionalProperties: true }, render: renderResult },
        async execute(args) {
          // 蜜罐自检（裁判准出：防缓存/硬编码伪装）——低频率开销（K=1 极简 query）
          const healthy = await honeypotCheck()
          if (!healthy) {
            return { summary: { final_answer: '⚠️ 蜜罐自检失败：审查可能未真实调用 LLM（缓存/硬编码伪装）' }, file: '' }
          }
          return runBridge('review', args)
        },
      }),
      harness.defineTool({
        name: 'hsk_verify',
        description: '对已有审议结论做 mimo 验证（规则 + 异质 LLM 校验：逻辑矛盾/遗漏维度/过度自信），返回 verdict/issues。',
        parameters: {
          conclusion: { type: 'string', required: true, description: '待验证的审议结论' },
          trajectories: { type: 'array', items: { type: 'string' }, description: '推理轨迹文本（供 mimo 参考）' },
          query: { type: 'string', description: '原审查请求' },
          validator_api_key: { type: 'string', description: 'mimo key（默认环境 XIAOMI_KEY）' },
        },
        output: { schema: { type: 'object', additionalProperties: true }, render: renderResult },
        async execute(args) { return runBridge('verify', args) },
      }),
      harness.defineTool({
        name: 'hsk_history',
        description: '读取 HeavySkill 样本库最近记录（审查历史，用于校准/复盘）。',
        parameters: {
          limit: { type: 'integer', description: '最近 N 条（默认 10）' },
        },
        output: { schema: { type: 'object', additionalProperties: true }, render: renderResult },
        async execute(args) { return runBridge('history', args) },
      }),
      harness.defineTool({
        name: 'hsk_adjudicate',
        description: '人工裁决一条审查样本（adopt/reject/amend）——写入样本库 + audit log（双签名防伪造）。',
        parameters: {
          sample_id: { type: 'string', required: true, description: '样本 id（hsk_history 可见）' },
          verdict: { type: 'string', required: true, description: 'adopt|reject|amend' },
          notes: { type: 'string', description: '裁决理由' },
          adjudicator: { type: 'string', description: '裁决人标识（默认 agent）' },
        },
        output: { schema: { type: 'object', additionalProperties: true }, render: renderResult },
        async execute(args) { return runBridge('adjudicate', args) },
      }),
    ]

    const disposers = tools.map(function (t) { return harness.registerTool(ctx, t) })

    return function () {
      disposers.forEach(function (d) { try { d() } catch (e) {} })
      if (proc) { try { proc.terminate() } catch (e) {} }
      failAll('HeavySkill 插件已停止')
      proc = null
    }
  },
}
