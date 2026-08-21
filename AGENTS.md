# AGENTS.md — 工作区指令（HGF 记忆继承协议）

> 本文件由 dsh-agent-instructions 自动加载（每个新会话注入为 durable baseline）。
> V3.3.3（V2 记忆长效机制 L1）：把"HGF 经验继承"从 agent 自觉升级为**自动加载的会话基线**。

## 工作区定位

- 本工作区：`D:\OneDrive\文档\deepseek harness workspace`
- 含 HGF（`workflow/`）、qual（`tools/finance/`）、heavyskill（`skills/heavyskill/`）等资产
- 项目记录：`PROJECT_RECORD.md`（HGF 会话持久化存档，跨会话恢复用）

## HGF 记忆继承协议（所有会话适用）

### 1. 改动 HGF 前：先查经验索引

涉及 `workflow/` 代码/配置改动时，先读：

- `workflow/docs/pitfalls-summary.json`（**机器可读摘要，几 KB**——首选，省 token）
- `workflow/docs/pitfalls-registry.md`（完整 P 库，需细节时再读）
- `workflow/docs/lessons/README.md`（经验档案索引）

目的：避免重复踩已沉淀的坑（如 failure_log 自锁、baseline 损坏、requirements 伪文件）。

### 2. 涉及 workflow/ 代码改动：结束前跑自律门禁

```
python workflow_cli.py --lifecycle advance gate_5_3 --dir .
```

gate_5_3（P53 元门禁自律）检查 4 项：failures 无自锁记录 / baseline 可解析 /
requirements 可解析 / lessons 有索引。失败 = HGF 自身状态不健康，先修复再收尾。

### 3. 新踩坑：沉淀闭环（不留在会话里）

新坑 → 三步：

1. 建档案 `workflow/docs/lessons/<日期>-<主题>.md`（现象/根因/修复/验证）
2. 登记 `workflow/docs/lessons/README.md` 索引（self_audit 第 4 项强制）
3. 更新 `workflow/docs/pitfalls-registry.md`（新 P# 或状态）+ `pitfalls-summary.json` + `CHANGELOG.md`

**SKILL.md 只在操作流程变化时更新**（防膨胀；具体经验进 lessons，不进 SKILL）。

### 4. 会话收尾：三问自检

结束工作前（或 goal 完成前）跑：

```
python workflow/scripts/self_check.py
```

- Q1: workflow/ 有未提交改动？
- Q2: gate_5_3 状态是 done？（读 .hgf/lifecycle.json）
- Q3: 最近 workflow 提交是否含 docs/PROJECT_RECORD 变更（无则提示记录未同步）？

任一不满足 → 补沉淀再收尾。

---

## 其他约定

- 沙箱：danger-full-access（不请求升级）；审批：never
- 动态插件（hgf-tools 等）DSH 重启即失，需从 `workflow/plugin/*.js` 重建
- 版本号四处同步：`__init__.py` / `config/workflow.yaml` / `config/mcp-gates.yaml` 头 / `pyproject.toml`
