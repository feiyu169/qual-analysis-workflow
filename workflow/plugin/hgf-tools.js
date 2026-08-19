// HGF → DSH 动态插件（V3.2.6 / V3.2.10）
// =========================================
// 把 HGF 引擎（Python，workflow/）以原生工具暴露给模型。
// 架构（V3.2.10 效能评审修复）：模型调用工具 → 插件通过"长驻 stdio 桥"
// 复用同一个 Python 进程（hgf_bridge.py --serve），消除每次调用的
// 解释器冷启动（实测 300ms→~10ms）。
//
// 改进（对照 heavyskill 插件效能评审）：
//   1. 长驻进程复用：apply 时懒启动 --serve，后续请求写 stdin/读 stdout；
//   2. 命令级超时：COMMAND_TIMEOUT 表 + Promise.race，超时 terminate 进程树
//      并自动重建（下次请求时）；
//   3. 并发限流：请求队列串行（单进程 stdin 天然串行），满队列排队；
//   4. 结构化错误：JSON.parse 失败/进程退出/超时 → 带命令名的可读错误；
//   5. env fail-fast：HGF_BRIDGE/HGF_PYTHON 缺失时回退硬编码路径；
//      若 spawn 失败则抛错提示设置 env（不再静默用坏路径）。
//
// 生命周期说明（重要）：
//   动态插件是"会话级"的——进程重启后消失。本文件是持久化源码，
//   需要时由 hgf 技能指引重建：cordis_define（kind existing 或 new）+
//   cordis_run。重建只需 2 次调用，桥接与引擎零改动。
//
// 用法（在 DSH 会话中）：
//   cordis_define({ plugin: { kind: 'new', idPrefix: 'hgf' }, name, purpose, code: { host: <本文件函数体> } })
//   cordis_run({ pluginId, packageId, mode: 'run' })

return {
  name: 'hgf-tools',
  inject: ['timer'],
  apply(ctx) {
    // 路径解析：env 优先，回退硬编码默认值（V3.2.9 修复 D）。
    const BRIDGE = (typeof process !== 'undefined' && process.env && process.env.HGF_BRIDGE)
      ? process.env.HGF_BRIDGE
      : 'D:\\OneDrive\\文档\\deepseek harness workspace\\workflow\\hgf_bridge.py'
    const FALLBACK_PYTHON = (typeof process !== 'undefined' && process.env && process.env.HGF_PYTHON)
      ? process.env.HGF_PYTHON
      : 'C:\\Users\\79902\\AppData\\Local\\Programs\\Python\\Python314\\python.exe'

    // 命令级超时（毫秒）：轻命令 15s；门禁执行可达 30min（L3 含 pytest+semgrep+safety+checkov）
    const COMMAND_TIMEOUT = {
      execute_gates: 30 * 60 * 1000,
      classify_task: 15 * 1000,
      assess_risk: 15 * 1000,
      lifecycle: 30 * 1000,
      history: 15 * 1000,
    }
    const DEFAULT_TIMEOUT = 15 * 1000

    let proc = null          // 当前长驻子进程 handle
    let procDied = false     // 进程是否已退出/被杀（需要重建）
    let nextId = 1           // 请求自增 id
    let queue = []           // 待发请求 { id, command, args, resolve, reject, timer, timeoutMs }
    let current = null       // 正在处理的请求
    let lineBuf = ''         // stdout 行缓冲
    let pythonPath = null    // resolveExecutable 缓存

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
          // 桥返回非法 JSON：结构化错误（V3.2.10 修复 4）
          if (current) {
            if (current.timer) { try { current.timer() } catch (e2) {} }
            const err = new Error('HGF 桥返回非法 JSON: ' + line.slice(0, 500))
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
        else req.reject(new Error('HGF 桥错误: ' + (resp.error || '未知错误')))
        pump()
      }
    }

    function onProcDone(outcome) {
      procDied = true
      const reason = 'HGF 桥进程退出 (exit ' + outcome.exitCode + (outcome.signal ? ', signal ' + outcome.signal : '') + ')'
      failAll(reason)
      proc = null
    }

    function onProcSpawnError(e) {
      procDied = true
      // env fail-fast（V3.2.10 修复 5）：spawn 失败提示配置 env
      failAll('HGF 桥启动失败: ' + String(e && e.message ? e.message : e) +
        '（如需移动工作区，请设置 HGF_BRIDGE / HGF_PYTHON 环境变量）')
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
      // 命令级超时（V3.2.10 修复 2）：timer 服务（沙箱无 setTimeout），
      // 超时 terminate 进程树，下次请求自动重建
      req.timer = ctx.timeout(function () {
        const err = new Error('HGF 命令超时 (' + req.command + ', ' + req.timeoutMs + 'ms)')
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
        req.reject(new Error('HGF 桥写入失败: ' + String(e && e.message ? e.message : e)))
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

    function renderResult(_a, v) {
      let text = 'OK'
      try { text = JSON.stringify(v) } catch (e) {}
      if (v && typeof v === 'object') {
        if (v.total_gates !== undefined) {
          text = 'HGF 门禁 等级 ' + v.level + ' | 通过 ' + v.passed + '/' + v.total_gates + ' | 失败 ' + v.failed + ((v.must_pass_failed || []).length ? ' | 阻断: ' + v.must_pass_failed.join(',') : '')
        } else if (v.matched_factors !== undefined) {
          text = 'HGF 风险评级: ' + v.risk + ' | score ' + v.score + ' | 因子: ' + ((v.matched_factors || []).join(',') || '无') + (v.reduction_applied ? ' | 已降级' : '')
        } else if (v.type !== undefined && v.level !== undefined) {
          text = 'HGF 分级: ' + v.level + ' | ' + v.type + (v.risk ? ' | 风险 ' + v.risk : '')
        } else if (v.status !== undefined) {
          const counts = {}
          Object.values(v.status).forEach(function (s) { counts[s] = (counts[s] || 0) + 1 })
          text = 'HGF 生命周期: ' + JSON.stringify(counts) + ' | 可推进: ' + Object.keys(v.status).filter(function (k) { return v.status[k] === 'runnable' }).join(',')
        } else if (v.summary !== undefined) {
          text = 'HGF 历史: ' + (v.summary.runs || 0) + ' 次 | 通过率 ' + (v.summary.success_rate || 0) + '%' + (v.summary.last_success ? ' | 最近通过' : '')
        } else if (v.advanced) {
          text = 'HGF 生命周期推进: ' + v.advanced + ' 完成'
        }
      }
      return [{ type: 'text', text: String(text) }]
    }

    const tools = [
      harness.defineTool({
        name: 'hgf_execute_gates',
        description: '运行 HGF 质量门禁：按任务等级真实执行 ruff/pytest/detect-secrets/semgrep/safety/checkov 等，返回结构化报告。',
        parameters: {
          level: { type: 'string', required: true, description: '任务等级: L0/L1/L2/L3/L3_LITE/IAC/CONFIG/DOCS' },
          files: { type: 'array', items: { type: 'string' }, required: true, description: '变更文件列表（相对 working_dir）' },
          working_dir: { type: 'string', required: true, description: '门禁执行的工作目录（绝对路径）' },
        },
        output: { schema: { type: 'object', additionalProperties: true }, render: renderResult },
        async execute(args) { return runBridge('execute_gates', args) },
      }),
      harness.defineTool({
        name: 'hgf_classify_task',
        description: 'HGF 任务分级：按描述/文件数/行数/影响区域判定等级 L0-L3 与类型（热修复→L0，关键模块升级等）。',
        parameters: {
          description: { type: 'string', required: true, description: '任务描述' },
          files: { type: 'array', items: { type: 'string' }, required: true, description: '变更文件列表' },
          line_count: { type: 'integer', description: '变更行数（默认 0）' },
          affected_areas: { type: 'array', items: { type: 'string' }, description: '影响区域（如 auth/payment）' },
          labels: { type: 'array', items: { type: 'string' }, description: '标签（如 hotfix）' },
        },
        output: { schema: { type: 'object', additionalProperties: true }, render: renderResult },
        async execute(args) { return runBridge('classify_task', args) },
      }),
      harness.defineTool({
        name: 'hgf_assess_risk',
        description: 'HGF 风险评级：关键词映射（含中文）+ 组合加成 + 高风险降级护栏，返回风险等级/分数/命中因子。',
        parameters: {
          affected_areas: { type: 'array', items: { type: 'string' }, required: true, description: '影响区域列表' },
          description: { type: 'string', description: '任务描述（触发中文关键词映射与降级规则）' },
        },
        output: { schema: { type: 'object', additionalProperties: true }, render: renderResult },
        async execute(args) { return runBridge('assess_risk', args) },
      }),
      harness.defineTool({
        name: 'hgf_lifecycle',
        description: 'HGF 生命周期（config/gates.yaml 的 Phase 0-5 DAG）：status=查看门禁状态，advance=推进门禁（准入=依赖完成，准出=检查器真实执行）。',
        parameters: {
          action: { type: 'string', required: true, description: 'status 或 advance' },
          working_dir: { type: 'string', required: true, description: '工作目录（.hgf 状态所在）' },
          gate: { type: 'string', description: 'advance 时的 gate id（如 gate_0_1）' },
          file: { type: 'string', description: '准出检查器的证据文件路径' },
          confirm: { type: 'boolean', description: '人工确认兜底（无自动检查器的条件）' },
          notes: { type: 'string', description: '推进备注' },
        },
        output: { schema: { type: 'object', additionalProperties: true }, render: renderResult },
        async execute(args) { return runBridge('lifecycle', args) },
      }),
      harness.defineTool({
        name: 'hgf_history',
        description: 'HGF 运行历史：.hgf/runs.jsonl 的趋势摘要（通过率、反复失败门禁）。',
        parameters: {
          working_dir: { type: 'string', required: true, description: '工作目录（.hgf 状态所在）' },
          n: { type: 'integer', description: '最近 N 次（默认 10）' },
        },
        output: { schema: { type: 'object', additionalProperties: true }, render: renderResult },
        async execute(args) { return runBridge('history', args) },
      }),
    ]

    const disposers = tools.map(function (t) { return harness.registerTool(ctx, t) })

    // 清理：停插件时终止长驻进程（V3.2.10：生命周期副作用必须可逆）
    return function () {
      disposers.forEach(function (d) { try { d() } catch (e) {} })
      if (proc) { try { proc.terminate() } catch (e) {} }
      failAll('HGF 插件已停止')
      proc = null
    }
  },
}
