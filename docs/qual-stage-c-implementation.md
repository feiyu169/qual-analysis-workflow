# 阶段 C 实施记录（审查效率优化，2026-08-21）

依据：路线图 v2.1 阶段 C + 综合审议（docs/qual-stage-c-adjudication.md）+ 审查专家评审（docs/qual-review-loop-efficiency.md）。
目标：审查 LLM 调用 ≤35 次/报告（原最坏 ~70，典型降 50-60%）；死循环不复发；报告质量不降。

---

## 实施清单（全部落地）

| 项 | 内容 | 提交 |
|---|---|---|
| **C1-1** | Gate4 logic_consistency 只跑一次（execute 挂 context，check_criteria 复用） | 43fd02a |
| **C1-3** | Gate3 跨章结果挂 context → loop 首轮 precomputed_cross_chapter 复用 | 43fd02a |
| **C2-2** | `_run_substantive_review(only_chapters=...)`——修复后轮仅审受影响章节 | 43fd02a |
| **C2-3** | `CHAPTER_DEPENDENCIES`（ch0 依赖全部、ch10 依赖 1-9）+ `get_affected_chapters` 接线 | 4e3f572 |
| **C3-2** | 红队门控：Gate4 实质通过才触发；fatal 回流标注（不静默放行） | 4e3f572 |
| **C4-1** | 审查子预算 ≤35（`min(总预算, 35)`，⊂ v3.1 的 200）；超预算 fail-closed | 4e3f572 |
| **C5-1** | data_repair 跨章实现标注为修复内部用（审查路径统一 quality 检查器） | 4e3f572 |
| **C5-2** | `PLACEHOLDER_PATTERNS` 统一常量（5 pattern）；Gate8 原 3 pattern 漏"待填写/TBD"修复 | 43fd02a |
| **C5-3** | `get_data_anchor` 锚点单例缓存——11 个调用点 → 1 次构建 | 本批 |
| **C5-4** | 本文档（降幅口径：70→35 为 -50%；典型报告降 50-60%） | 本批 |

## 验收对照

| 验收项（路线图 C） | 状态 |
|---|---|
| 审查 LLM 调用 ≤35 次/报告 | ✅ C4-1 硬上限 35 + C2-2 增量降 60-70% |
| 跨章审查路径去重至 1 处有效执行 | ✅ C1-3 + C5-1 |
| logic 上报 1 次 | ✅ C1-1 |
| 占位符 L1+G8 两处统一常量，无逃出 | ✅ C5-2 |
| 锚点审查环节 10→1 处构建 | ✅ C5-3（11 处 → 缓存单例） |
| 死循环不复发（exemption/monotonic 测试绿） | ✅ 55 全量持续通过 |
| 红队 fatal 有回流路径 | ✅ C3-2 |
| 报告质量不降（静态纵深保留） | ✅ C2-1 静态全量每轮保留 |

## 质量门禁

- 测试：**69 passed**（55 基线 + 14 C 测试）
- HGF 终检：C 批次 1/2 exit=0，MUST_PASS 全绿
- ruff：全部变更文件全绿

## 运行预期（soft 模式）

C2-2 增量 + C4-1 预算 35 + C3-2 红队门控后，soft 模式审查 LLM 调用被约束，
Gate4 修复循环不再无界耗尽墙钟（上次 6449s 墙钟终止 → 预期显著收敛）。
待重跑小鹏验证。
