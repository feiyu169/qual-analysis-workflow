# DSH 动态插件持久化源码（V3.2.7 / V3.2.10）

动态插件是**会话级**的（DSH 进程重启后消失）。本目录存放插件源码，
需要时按"重建步骤"恢复——每次重建只需 2 次调用（define + run）。

## 插件清单

| 文件 | 平台 | 作用 | 重建方式 |
|------|------|------|----------|
| `hgf-tools.js` | Host | 注册 5 个 HGF 原生工具（execute_gates/classify/assess/lifecycle/history），**长驻 stdio 桥**（V3.2.10） | `cordis_define`(kind new, idPrefix hgf) + `cordis_run`(run) |
| `codex-sidebar.js` | Client | 仿 Codex 风格侧边栏：替换 `sidebar.workspaces` 座为深色极简会话浏览器 | 同上（idPrefix cdx） |
| ~~`codex-workspace.js` / `codex-workspace.client.js`~~ | ~~Host+Client~~ | ~~右侧工作台浮动面板~~（**2026-08 已移除**：用户决定删除；源码保留备查，需要时可重建） | — |

## 通用重建步骤

```text
1. 读取插件源码文件（本目录）
2. cordis_define：kind=new（进程重启后旧 pluginId 失效，需新 id），idPrefix 见上表，
   code.host / code.client = 文件中的 `return {...}` 函数体
3. cordis_run：mode=run
4. 验证：cordis_inspect_self 查 state=running / client 无渲染错误；
   UI 插件再查 Slots 座 occupants（dyn/<id> active）
```

## V3.2.10 效能改进（hgf-tools 长驻桥）

- **架构**：插件懒启动 `python hgf_bridge.py --serve`（stdio JSON-RPC 长驻进程），
  后续工具调用写 stdin / 读 stdout 复用进程——不再每次 spawn Python。
- **实测**：classify 418→37ms（11×）、assess_risk 1275→39ms（32×）、
  lifecycle 439→49ms（9×）。
- **命令级超时**：`COMMAND_TIMEOUT`（execute_gates 30min，其余 15-30s），
  超时 `proc.terminate()` 进程树，下次请求自动重建。**必须用 timer 服务
  （ctx.timeout），沙箱无 setTimeout**（run-9 失败教训）。
- **并发**：请求队列串行（单进程 stdin 天然串行）。
- **错误**：桥返回非法 JSON / 进程退出 / 超时 → 带命令名的可读错误。
- **env fail-fast**：`HGF_BRIDGE`/`HGF_PYTHON` 优先，回退硬编码；spawn 失败
  抛错提示设置 env。

## 经验教训（已按 HGF 纪律记录在 .hgf/failures.jsonl）

- **替换 single 座时禁止重复声明其 children**：官方已声明的 child slot
  （如 `sidebar.workspaces.directoryFlow`）会被 slots 系统判为
  "slot already declared" → Client apply 失败（run-3 教训）。修复：注册时
  去掉 children，直接使用官方声明的 child。
- **Client 插件需要浏览器批准**：`cordis_run` 返回 awaiting-approval 是正常流程，
  批准后异步加载；technical failure 会以 client-half-failed 汇报。
- **沙箱无 Node 定时器全局**：`setTimeout`/`clearTimeout` 在动态包沙箱不可用，
  必须 `inject: ['timer']` + `ctx.timeout(fn, ms)`（返回 disposer）（run-9 教训）。

## 客户端关键契约（本目录插件依赖）

- `sidebar.workspaces`（single, root）standardProps：
  `useSessions({ ids, byId, current })` / `useWorkspaces({ items })`；
  ownerProps：`wide`（宽/rail）、`expandSidebar`
- Client 服务（inject）：`sessions.open(id)`、`workspaces.startSession(workspaceId)`
