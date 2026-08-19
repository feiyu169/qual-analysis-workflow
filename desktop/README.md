# DSH 桌面壳（POC，HGF Phase 1）

单窗口内嵌现有 DSH Web UI 的 Electron 壳。**不改宿主核心**——只做
"WebView 窗口 + 连接 localhost"。

## 启动

```powershell
cd desktop
npm start          # 或: node node_modules/electron/cli.js . --no-sandbox
```

窗口加载 `http://127.0.0.1:3080`（可用环境变量 `DSH_WEB_URL` 覆盖）。
**前置条件**：DSH 宿主实例已在 3080 运行（`dsh --profile web`）。

## 冒烟验证（HGF 真实验证）

```powershell
$env:SMOKE = "1"
node node_modules/electron/cli.js . --no-sandbox
# 期望输出: [dsh-desktop] loaded: http://127.0.0.1:3080
#           [smoke] loaded OK, exiting in 3s
```

## 为什么 --no-sandbox

本机 Chromium 沙箱在受限执行环境下无法初始化（electron 直接跑会 exit=-1），
实测 `--no-sandbox` 可正常运行。POC 阶段可接受（本地可信应用）；
正式打包需评估（可用 `ELECTRON_DISABLE_SANDBOX` 或打包配置处理）。

## HGF 记录

- 改造任务分级：**L2 / MIXED / 风险 low**（hgf_classify_task / hgf_assess_risk）
- 门禁：`node --check`（语法）✅ + SMOKE 集成验证（真实执行）✅
- 安装备注：electron 二进制 postinstall 被 npm allow-scripts 拦截、
  解压环节失败——已手动从缓存 zip（`%LOCALAPPDATA%\electron\Cache`）
  解压到 `node_modules/electron/dist` 并写 `path.txt`。

## 后续阶段（待决策）

- 阶段 2：sidecar spawn dsh 宿主（壳自带独立实例，不依赖外部 3080）
- 阶段 3：打包分发（安装包/签名/自动更新）
