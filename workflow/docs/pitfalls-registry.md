# HGF P 库状态注册表（V3.2.5）

P 库（P0-P52）是 hermes 踩坑纪律库，原始清单在
`skills/software-development/gate-driven-development/SKILL.md`。本注册表是**精选索引**：
给每条 P 打状态标记（已门禁化 / 文档纪律 / 已过时）与对应机制，并标注重复编号。

## 状态图例

- ✅ **已门禁化**：有可执行门禁/测试强制（不是靠 agent 自觉）
- 📄 **文档纪律**：只在文档中约束，需 agent 执行
- ⚠️ **编号重复**：同一编号被不同年份文档多次使用

## 已门禁化（本会话验证）

| P# | 主题 | 对应机制 |
|----|------|----------|
| P0 | 文件存在 ≠ 能用 | fail-loud 解析器（ERROR 拒绝判定）+ lifecycle 准出检查器（内容校验） |
| P4 | 失败要记录/禁止静默调参 | failure-log 门禁（自动落盘 + root_cause/fix 必填） |
| P16 | CONDITIONAL PASS | lifecycle `--confirm` 兜底（无检查器条件需人工确认） |
| P20 | 空测试桩 | test-quality 门禁（AST 解析断言） |
| P31 | 映射语言不一致/未接线 | risk_assessor 中文 keyword_mapping 已接线 + 测试 |
| P32 | 高危因子禁止降级 | risk_assessor 护栏 + 测试 |
| P33 | 增量覆盖率 | unit_test 的 `incremental_coverage_min` |
| P36 | 字段存在 ≠ 功能完成 | integration-probe 门禁（调用点探针） |
| P50 | 配置字段定义未使用 | L2-L5 证据机制（`evidence` 必填校验） |
| P53 | 元门禁自律（V3.3.3 自审查沉淀） | self_audit 检查器（gate_5_3，4 项机械验证）+ 7 防回归测试 + pre-push/CI |
| P54 | 审查结果被截断（heavyskill 模式2） | 预算配置打通（max_tokens/summary_max_tokens）+ finish_reason 显性化 + 截断轨迹剔除 + 输出 JSON `truncation` 摘要 + `tests/test_truncation.py` 9 项防回归 |
| P55 | 隐形测试 + ruff 自动修复掩盖断裂（2026-08-22） | **建议门禁化**：unit_test 门禁增加全目录收集验证（`pytest tools/finance/` 非仅聚合入口）；ruff --fix 前 grep 确认被清理 import 的目标符号存在（防 F401 静默删断裂引用）；声称数字（测试数/覆盖率）写文档前实测复现 |

## 文档纪律（无自动门禁，需 agent 遵守）

P1（集成测试）、P2（cron 触发）、P3（合规落地）、P5（后期不放松）、
P6（全文件扫描同模式）、P7/P10/P18/P19（共享实例）、P11（git rm 说明）、
P12（返回值契约）、P13（pydantic .env）、P14（shell 变量）、P15（退出码判据）、
P17（SQLite naive datetime）、P21（CSRF）、P22（PNG/JPEG）、
P23（grep 全部同类）、P24（SSH 自动化）、P25（数据源核验）、
P26（多层同步）、P27（CSRF 前缀）、P28（不发明流程名）、P29（Nginx 413）、
P30（axios/formData、getMe、cookie fetch）、P34（混合变更）、
P35/P37（密钥脱敏）、P38（MCP 依赖）、P40（nginx alias）、
P45（并发写入/多阶段 todo）、P46（修复后重审）、P48（多 python 版本）、
P49（原地修改）、P51（返回过滤后数据）、P52（正负用例）

## 编号重复（需重排）

P17、P30、P31、P36、P37 在原始文档中出现 2+ 次（不同年份各自编号）。
建议后续以本注册表为准进行重排。

## 已过时 / 环境相关

P35/P37（密钥脱敏）——DSH 沙箱与脱敏行为与 hermes 不同，已由 DSH 自身机制覆盖。
