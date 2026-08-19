# Changelog

## 3.2.0 (2026-08-17) — HGF 演进路线图全量实施

### 阶段 0：止血与可复现
- 死代码归档：9 个未接线模块移入 `_legacy/`（含复活条件说明）；`__init__.py` 不再 re-export
- 版本号归一：`__version__ = "3.2.0"`，CLI `--version`，YAML 头部同步
- 补齐文档引用的缺失产物：`templates/gate-plugin-template.py`、`scripts/test_quality_metrics.py`
- 门禁基线 `.hgf/baseline.json`：配置哈希 + 工具版本，每次执行检测漂移并告警
- 离线提速注释：safety/semgrep 首次下载说明

### 阶段 1：让门禁可信
- **假通过防线（fail-loud）**：`GateResult.parse_error` + `GatePlugin._safe_parse`；
  detect-secrets/semgrep/safety/checkov 解析失败 → ERROR 拒绝判定（checkov 假通过普适化修复）
- **重试/升级接线**：failure_handler 接入 GateExecutor（超时/网络/限流指数退避重试、
  连续失败升级"通知负责人/冻结流程"）
- **运行历史**：`.hgf/runs.jsonl` + CLI `--history`（通过率、反复失败门禁）

### 阶段 2：生命周期真接线
- `lifecycle.py`：gates.yaml（16 gate Phase 0-5）变成可执行 DAG 状态机
  （准入=依赖完成，准出=检查器真实执行，状态存 `.hgf/lifecycle.json`）
- 准出条件检查器：文档（内容≥100 字符，拒空壳）、评审记录、pytest/ruff 真实执行、
  健康检查、`--confirm` 人工兜底
- L2-L5 证据机制：`GateConfig.evidence`，声明高级别验证必须有证据文件

### 阶段 3：生态与工程化
- CI：`.github/workflows/hgf-gates.yml`（PR/推送对变更文件跑完整 HGF，退出码即结果）
- 生态门禁：format-check（ruff format）、pin-check（依赖固定）、docs-check（README 章节）
- 文档治理：`workflow/README.md`（模块地图 + 12 YAML 职责表 + P 库门禁化对照）

### 工程修复
- ruff 规则集固定（pyproject [tool.ruff.lint]），消除随版本漂移
- 全库迁移残留扫描：3 处硬编码路径修复

### 测试
- 测试套件 90+ 个，核心覆盖率 ≥84%
- L2 狗粮化（HGF 检查 HGF）：8/8 门禁全绿
