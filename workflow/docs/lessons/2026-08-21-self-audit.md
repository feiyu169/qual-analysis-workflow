# HGF 自审查 3 个 P0 根因（2026-08-21）

> 档案：2026-08-21-self-audit.md | 关联 P53（元门禁自律）
> 背景：用 HGF 审查 HGF 自身（对 workflow/ 跑 L2 门禁），发现并修复 3 个 P0。
> 全部是**运行时才暴露**的状态/文件问题——纯代码评审（heavyskill 静态看代码）抓不到，
> 只有"跑真门禁"能发现。这证明"文件存在 ≠ 它工作"同样适用于 HGF 工具链自身。

## 现象、根因、修复（逐条）

### S1：failure_log 失败雪崩自锁（最严重）

- **现象**：232+ 条失败记录中 196 条未解决（缺 root_cause/fix），同一秒最多 232 条
  写入，呈指数增长（6→16→64→118→292→370→400 条"记录不完整"），failure_log 门禁永远 FAIL。
- **根因**：gate_executor 在每次 run 后把**所有** MUST_PASS 失败（含 failure_log 自身）
  写入 failures.jsonl。failure_log 门禁因"记录不完整"FAIL 时，它自己的失败也被记录
  （必然缺 root_cause/fix）→ 下次检查到更多不完整 → 更多失败记录 → **自指循环指数爆炸**。
- **修复**（V3.3.2）：
  1. gate_executor 排除 failure_log 自身失败入日志（元门禁失败只进 runs.jsonl 历史）；
  2. `--failures --archive` 批量归档不完整历史记录到 failures-archived.jsonl（保留可审计性）。
- **验证**：归档 201 条后 232→32 条全 resolved；L2 门禁 failure_log PASS。

### S2：baseline.json 损坏导致 canary 崩溃

- **现象**：`.hgf/baseline.json` 末尾多一个 `}`（JSON 无效，V3.2.x 裸写入遗留），
  `python workflow_cli.py --canary` 直接抛未捕获 JSONDecodeError 崩溃。
- **根因**：`baseline.load` 无容错（不捕获 JSONDecodeError），`canary.drift_from_baseline`
  未处理 load 失败——**状态文件损坏 → 工具链崩溃而非告警降级**。
- **修复**（V3.3.2）：`baseline.load` 捕获 JSONDecodeError → 返回 None + 告警；
  `canary` 检测到 None 自动重建基线快照（把"损坏状态"收敛为"已重建"）。
- **验证**：`--canary` 从崩溃 → 降级重建成功运行；baseline.json 自动重建为有效 JSON。

### S3：requirements-hgf.txt 是 Markdown 伪文件

- **现象**：文件内容实际是 Markdown 文档（说明文字/代码块/表格），
  `pip install -r requirements-hgf.txt` 实测报 `Invalid requirement`。
- **根因**：文档冒充 requirements 文件——违反 HGF 自己的 P0 纪律"文件存在 ≠ 它工作"。
- **修复**（V3.3.2）：改为真 pip 文件（9 个依赖 `包==版本` 锁定行），说明移入 README。
- **验证**：`pip install --dry-run -r requirements-hgf.txt` 正常解析全部依赖。

## 通用教训

1. **元门禁也要被门禁约束**（P53）：failure_log/baseline/canary/checker 自身的
   状态数据、失败行为、文件格式必须同样受纪律约束。
2. **状态文件损坏必须容错**：load 任何 .hgf/ 状态文件都要处理 JSONDecodeError，
   降级重建而非崩溃。
3. **声称可用的文件必须实测**：README 里写 `pip install -r X`，就跑一次验证；
   "文档说能用"与"真的能用"之间永远有距离。

## 防回归机制（V3.3.3 落地）

- `_check_self_audit` 检查器 4 项机械验证（自锁/损坏/伪文件/索引）→ gate_5_3
- 7 个防回归测试（tests/test_self_audit.py）
- pre-push + CI self-audit job 双保险（防 --no-verify 绕过）
