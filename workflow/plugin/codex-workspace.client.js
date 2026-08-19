// Codex 工作台 Client 半（与 codex-workspace.host.js 配对）
// =========================================================
// shell.overlay 注册右侧浮动面板：模型选择 + 迷你对话 + Goal 卡片。
// 面板自包含开关（默认收起为右侧小按钮），不动任何官方座。

return {
  name: 'codex-workspace-client',
  inject: ['slots', 'sessions', 'workspaces', 'remote.goals'],
  apply(ctx) {
    const slots = ctx.get('slots')
    if (slots === undefined) return

    const dark = {
      bg: '#0d0d0f', panelBg: '#141417', border: '#26262b',
      text: '#e6e6e6', sub: '#9a9aa3', dim: '#7d7d86',
      accent: '#3b82f6', error: '#b45353', hover: '#1c1c21',
    }
    const css = {
      fab: { position: 'fixed', right: 0, top: '50%', transform: 'translateY(-50%)', zIndex: 1000, width: 28, height: 28, background: dark.bg, border: '1px solid ' + dark.border, borderRight: 'none', borderTopLeftRadius: 8, borderBottomLeftRadius: 8, color: dark.sub, cursor: 'pointer', fontSize: 13 },
      panel: { position: 'fixed', right: 0, top: 0, bottom: 0, width: 320, background: dark.panelBg, borderLeft: '1px solid ' + dark.border, zIndex: 1000, display: 'flex', flexDirection: 'column', color: dark.text, fontFamily: 'system-ui, sans-serif' },
      header: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 12px', borderBottom: '1px solid ' + dark.border },
      headerTitle: { fontSize: 13, fontWeight: 600, color: dark.sub, textTransform: 'uppercase', letterSpacing: '0.05em' },
      closeBtn: { background: 'transparent', border: 'none', color: dark.dim, cursor: 'pointer', fontSize: 14 },
      section: { padding: '10px 12px', borderBottom: '1px solid ' + dark.border },
      label: { fontSize: 11, color: dark.dim, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.05em' },
      select: { width: '100%', background: dark.bg, color: dark.text, border: '1px solid ' + dark.border, borderRadius: 6, padding: '6px 8px', fontSize: 12, outline: 'none' },
      chat: { flex: 1, overflowY: 'auto', padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 8, fontSize: 12, lineHeight: 1.5 },
      bubbleUser: { alignSelf: 'flex-end', background: dark.accent, color: '#fff', borderRadius: 10, borderBottomRightRadius: 2, padding: '6px 10px', maxWidth: '85%', whiteSpace: 'pre-wrap' },
      bubbleBot: { alignSelf: 'flex-start', background: dark.bg, color: dark.text, borderRadius: 10, borderBottomLeftRadius: 2, padding: '6px 10px', maxWidth: '85%', whiteSpace: 'pre-wrap' },
      inputRow: { display: 'flex', gap: 6, padding: '10px 12px', borderTop: '1px solid ' + dark.border },
      input: { flex: 1, background: dark.bg, color: dark.text, border: '1px solid ' + dark.border, borderRadius: 6, padding: '6px 8px', fontSize: 12, outline: 'none' },
      sendBtn: { background: dark.accent, border: 'none', color: '#fff', borderRadius: 6, padding: '6px 12px', fontSize: 12, cursor: 'pointer' },
      sendBtnDisabled: { opacity: 0.5, cursor: 'default' },
      goalCard: { background: dark.bg, border: '1px solid ' + dark.border, borderRadius: 8, padding: 8, fontSize: 12 },
      goalObj: { color: dark.text, wordBreak: 'break-all' },
      goalMeta: { color: dark.dim, fontSize: 11, marginTop: 4 },
      goalBtns: { display: 'flex', gap: 6, marginTop: 8 },
      goalBtn: { background: 'transparent', border: '1px solid ' + dark.border, color: dark.sub, borderRadius: 4, padding: '2px 8px', fontSize: 11, cursor: 'pointer' },
      error: { color: dark.error, fontSize: 11, padding: '0 12px 8px' },
      empty: { color: dark.dim, fontSize: 12, padding: 8, textAlign: 'center' },
    }

    function WorkspacePanel(props) {
      const list = props.useSessions((s) => s)
      const currentId = list ? list.current : null
      const [open, setOpen] = React.useState(false)
      const [groups, setGroups] = React.useState([])
      const [sel, setSel] = React.useState(null)
      const [history, setHistory] = React.useState([])
      const [input, setInput] = React.useState('')
      const [busy, setBusy] = React.useState(false)
      const [goal, setGoal] = React.useState(null)
      const [error, setError] = React.useState(null)

      React.useEffect(function () {
        if (!currentId) return
        props.models().then(function (v) {
          if (v && v.error) { setError(v.error); return }
          setGroups(v.groups || [])
          if (v.current) setSel({ provider: v.current.provider, model: v.current.model })
        }).catch(function (e) { setError(String(e && e.message ? e.message : e)) })
        props.loadGoal(currentId).then(function (g) { setGoal(g) }).catch(function () { setGoal(null) })
      }, [currentId])

      function send() {
        const text = input.trim()
        if (!text || !sel || busy) return
        const next = history.concat([{ role: 'user', content: text }])
        setHistory(next)
        setInput('')
        setBusy(true)
        setError(null)
        props.chat({ provider: sel.provider, model: sel.model, messages: next }).then(function (res) {
          setBusy(false)
          if (res && res.error) { setError(res.error); return }
          setHistory(next.concat([{ role: 'assistant', content: res.reply || '' }]))
        }).catch(function (e) { setBusy(false); setError(String(e && e.message ? e.message : e)) })
      }

      const modelOptions = []
      ;(groups || []).forEach(function (g) {
        ;(g.models || []).forEach(function (m) {
          modelOptions.push({ provider: g.provider || g.name, model: m.id, label: (g.name || g.provider || '') + ' / ' + (m.name || m.id) })
        })
      })

      const panel = React.createElement('div', { style: css.panel }, [
        React.createElement('div', { key: 'h', style: css.header }, [
          React.createElement('span', { key: 't', style: css.headerTitle }, '工作台'),
          React.createElement('button', { key: 'x', style: css.closeBtn, onClick: function () { setOpen(false) } }, '✕'),
        ]),
        React.createElement('div', { key: 'm', style: css.section }, [
          React.createElement('div', { key: 'ml', style: css.label }, '模型'),
          React.createElement('select', {
            key: 'ms', style: css.select, value: sel ? sel.provider + '|' + sel.model : '',
            onChange: function (e) {
              const v = e.target.value
              const idx = v.indexOf('|')
              if (idx > 0) setSel({ provider: v.slice(0, idx), model: v.slice(idx + 1) })
            },
          }, modelOptions.map(function (o) {
            return React.createElement('option', { key: o.provider + '|' + o.model, value: o.provider + '|' + o.model }, o.label)
          })),
        ]),
        React.createElement('div', { key: 'c', style: css.chat }, history.length === 0
          ? React.createElement('div', { style: css.empty }, '用所选模型在此对话（不影响主会话）')
          : history.map(function (m, i) {
            return React.createElement('div', {
              key: i, style: m.role === 'user' ? css.bubbleUser : css.bubbleBot,
            }, m.content)
          })),
        React.createElement('div', { key: 'e', style: css.error }, error || ''),
        React.createElement('div', { key: 'i', style: css.inputRow }, [
          React.createElement('input', {
            key: 'in', style: css.input, value: input, placeholder: '输入指令…',
            onChange: function (e) { setInput(e.target.value) },
            onKeyDown: function (e) { if (e.key === 'Enter') send() },
          }),
          React.createElement('button', {
            key: 'btn', style: Object.assign({}, css.sendBtn, busy ? css.sendBtnDisabled : null),
            onClick: send, disabled: busy,
          }, busy ? '…' : '发送'),
        ]),
        React.createElement('div', { key: 'g', style: css.section }, [
          React.createElement('div', { key: 'gl', style: css.label }, '工作安排 · Goal'),
          goal && goal.goal
            ? React.createElement('div', { style: css.goalCard }, [
              React.createElement('div', { key: 'o', style: css.goalObj }, String(goal.goal.objective || '')),
              React.createElement('div', { key: 'm', style: css.goalMeta },
                'phase: ' + (goal.goal.phase || '?') + (goal.goal.blockedReason && goal.goal.blockedReason.message ? ' · ' + goal.goal.blockedReason.message : '')),
              React.createElement('div', { key: 'b', style: css.goalBtns }, [
                React.createElement('button', { key: 'p', style: css.goalBtn, onClick: function () { props.goalAction(currentId, 'pause', goal.goal) } }, '暂停'),
                React.createElement('button', { key: 'r', style: css.goalBtn, onClick: function () { props.goalAction(currentId, 'resume', goal.goal) } }, '恢复'),
                React.createElement('button', { key: 'c', style: css.goalBtn, onClick: function () { props.goalAction(currentId, 'clear', goal.goal) } }, '清除'),
              ]),
            ])
            : React.createElement('div', { style: css.empty }, '暂无目标（/goal 创建）'),
        ]),
      ])

      return React.createElement('div', null, [
        React.createElement('button', {
          key: 'fab', style: css.fab, title: '工作台', onClick: function () { setOpen(!open) },
        }, open ? '»' : '«'),
        open ? panel : null,
      ])
    }

    slots.inject('shell.overlay', function () {
      return slots.register({
        name: 'shell.overlay',
        id: 'codex-workspace', order: 0, label: '工作台',
        inject: function () {
          return {
            // 模型目录（Host 桥：llm.listConfigurableProviders + listModels + agentDefaultModel）
            models: function () {
              return host.call('workspace-models')
            },
            // Goal 读取（session projection）
            loadGoal: function (sessionId) {
              const binding = ctx.sessions.binding(sessionId)
              const face = binding && binding.session ? binding.session.projections.faceOf('goal') : undefined
              return Promise.resolve(face ? face.getSnapshot() : null)
            },
            // 迷你对话（Host 桥 → ctx.llm.stream）
            chat: function (args) { return host.call('workspace-chat', args) },
            // Goal 操作（Remote）
            goalAction: function (sessionId, action, goal) {
              const ref = { id: goal.id, revision: goal.revision }
              const remote = ctx.get('remote.goals')
              if (remote === undefined) return Promise.reject(new Error('remote.goals 不可用'))
              if (action === 'pause') return remote.pause(sessionId, ref)
              if (action === 'resume') return remote.resume(sessionId, ref)
              if (action === 'clear') return remote.clear(sessionId, ref)
              return Promise.reject(new Error('未知 goal 操作: ' + action))
            },
          }
        },
      }, WorkspacePanel)
    })
  },
}
