// DSH 桌面壳 POC（HGF Phase 1）
// 单窗口内嵌现有 Web UI（默认 http://127.0.0.1:3080），不改宿主核心。
// 后续阶段可升级为 sidecar spawn dsh 宿主（自启独立实例）。
const { app, BrowserWindow, shell } = require('electron')

const DSH_URL = process.env.DSH_WEB_URL || 'http://127.0.0.1:3080'

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    title: 'DeepSeek Harness',
    autoHideMenuBar: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  win.loadURL(DSH_URL)

  // 外部链接交给系统浏览器，避免在壳内导航离开
  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })

  win.webContents.on('did-finish-load', () => {
    console.log('[dsh-desktop] loaded:', DSH_URL)
    // SMOKE=1 冒烟模式（HGF 真实验证）：加载成功后自动退出
    if (process.env.SMOKE) {
      console.log('[smoke] loaded OK, exiting in 3s')
      setTimeout(() => app.quit(), 3000)
    }
  })
  win.webContents.on('did-fail-load', (_e, code, desc) => {
    console.error('[dsh-desktop] load failed:', code, desc)
    if (process.env.SMOKE) {
      console.error('[smoke] load FAILED')
      app.exit(1)
    }
  })
}

app.whenReady().then(() => {
  createWindow()
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
