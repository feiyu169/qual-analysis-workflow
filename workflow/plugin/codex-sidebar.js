// Codex 风格侧边栏（HGF Phase 1）
// ==============================
// 替换 `sidebar.workspaces` 座为仿 Codex 的会话浏览器：
// 深色极简、紧凑会话列表（标题+相对时间）、激活项高亮、新建会话、rail 折叠态。
//
// 依赖（Client 服务，与 ui-workspace 同源）：
//   - slots: 注册座
//   - sessions: open(id) 切换会话
//   - workspaces: startSession(workspaceId) 新建会话
// 数据（座 standardProps）：
//   - useSessions: { ids, byId, current }
//   - useWorkspaces: { items: [{ workspaceId, title, sessionIds }] }
// 结构（ownerProps）：wide（宽/rail）、expandSidebar
//
// 生命周期：动态插件会话级（DSH 重启后需按 hgf 技能重建）；
// 重建 = cordis_define（kind new, idPrefix cdx）+ cordis_run。
//
// 风险与处置：替换 single 座 = shadows-shipped-ui；组件渲染失败会留白，
// 故内置错误边界（渲染异常时退回极简可用的按钮列表）。

return {
  name: 'codex-sidebar',
  inject: ['slots', 'sessions', 'workspaces'],
  apply(ctx) {
    const slots = ctx.get('slots')
    if (slots === undefined) return

    const root = { display: 'flex', flexDirection: 'column', height: '100%', background: '#0d0d0f', color: '#e6e6e6', fontFamily: 'system-ui, sans-serif' }
    const headerStyle = { display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 14px 8px', borderBottom: '1px solid #26262b' }
    const titleStyle = { fontSize: 13, fontWeight: 600, color: '#9a9aa3', textTransform: 'uppercase', letterSpacing: '0.05em' }
    const newBtn = { background: 'transparent', border: '1px solid #3a3a42', color: '#e6e6e6', borderRadius: 6, padding: '3px 10px', fontSize: 12, cursor: 'pointer' }
    const listStyle = { flex: 1, overflowY: 'auto', padding: '6px' }
    const row = { display: 'flex', flexDirection: 'column', gap: 2, width: '100%', textAlign: 'left', background: 'transparent', border: 'none', borderRadius: 8, padding: '8px 10px', color: '#d6d6dc', cursor: 'pointer' }
    const rowActive = { background: '#26262c' }
    const rowTitle = { fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }
    const rowMeta = { fontSize: 11, color: '#7d7d86' }
    const rail = { display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, padding: '8px 4px', height: '100%', background: '#0d0d0f' }
    const railBtn = { width: 32, height: 32, borderRadius: 8, background: 'transparent', border: 'none', color: '#9a9aa3', cursor: 'pointer', fontSize: 14 }
    const railActive = { background: '#26262c', color: '#e6e6e6' }

    function relTime(iso) {
      if (!iso) return ''
      const diff = Date.now() - new Date(iso).getTime()
      const m = Math.floor(diff / 60000)
      if (m < 1) return '刚刚'
      if (m < 60) return m + ' 分钟前'
      const h = Math.floor(m / 60)
      if (h < 24) return h + ' 小时前'
      return Math.floor(h / 24) + ' 天前'
    }

    function SessionRow(props) {
      const s = props.session
      const active = s.id === props.currentId
      return React.createElement('button', {
        onClick: () => props.open(s.id),
        style: Object.assign({}, row, active ? rowActive : null),
        title: s.displayTitle || s.id,
      }, [
        React.createElement('span', { key: 't', style: rowTitle }, s.blank ? '新会话' : (s.displayTitle || s.id)),
        React.createElement('span', { key: 'm', style: rowMeta }, (s.running ? '● ' : '') + relTime(s.updatedAt)),
      ])
    }

    function CodexBrowser(props) {
      const list = props.useSessions((s) => s)
      const workspaces = props.useWorkspaces((s) => s.items)
      const currentId = list ? list.current : null
      const sessions = (list && list.ids ? list.ids.map((id) => list.byId[id]).filter(Boolean) : [])

      const safeRender = function () {
        if (!props.wide) {
          // rail：垂直图标列（Codex 收缩态）
          return React.createElement('div', { style: rail }, [
            React.createElement('button', { key: 'new', onClick: () => props.startSession(), style: railBtn, title: '新建会话' }, '+'),
          ].concat(sessions.map(function (s) {
            return React.createElement('button', {
              key: s.id,
              onClick: () => props.open(s.id),
              style: Object.assign({}, railBtn, s.id === currentId ? railActive : null),
              title: s.displayTitle || s.id,
            }, s.running ? '●' : '○')
          })))
        }
        // wide：标题 + 新建 + 会话列表
        const header = React.createElement('div', { style: headerStyle }, [
          React.createElement('span', { key: 't', style: titleStyle }, '会话'),
          React.createElement('button', { key: 'n', onClick: () => props.startSession(), style: newBtn }, '+ 新建'),
        ])
        const rows = sessions.map(function (s) {
          return React.createElement(SessionRow, {
            key: s.id, session: s, currentId: currentId, open: props.open,
          })
        })
        return React.createElement('div', { style: root }, [
          header,
          React.createElement('div', { key: 'list', style: listStyle }, rows.length ? rows : React.createElement('div', { style: { padding: 16, fontSize: 12, color: '#7d7d86' } }, '暂无会话')),
        ])
      }

      try {
        return safeRender()
      } catch (e) {
        // 错误边界：渲染失败退回极简可用列表，不吞掉错误信息
        return React.createElement('div', { style: root }, [
          React.createElement('div', { style: headerStyle },
            React.createElement('span', { style: titleStyle }, '会话')),
          React.createElement('button', { onClick: () => props.startSession(), style: newBtn }, '+ 新建'),
          React.createElement('div', { style: { padding: 12, fontSize: 12, color: '#b45353' } }, '渲染失败: ' + String(e && e.message ? e.message : e)),
        ])
      }
    }

    slots.inject('sidebar.workspaces', function () {
      return slots.register({
        name: 'sidebar.workspaces',
        // 注意：不声明 children——官方 ui-workspace 已声明
        // `sidebar.workspaces.directoryFlow`，重复声明会冲突
        //（run-3 失败教训：slot already declared）
        inject: function () {
          return {
            open: function (id) { ctx.sessions.open(id) },
            startSession: function (workspaceId) { ctx.workspaces.startSession(workspaceId) },
          }
        },
      }, CodexBrowser)
    })
  },
}
