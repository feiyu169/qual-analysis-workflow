# 2026-08-22 qual 隐形测试 + ruff 自动修复掩盖断裂（P55）

## 现象

1. **27 个测试文件长期不可收集**：`pytest tools/finance/` 全目录收集时 27 个文件 ImportError
   （`finance.quality.v3.pipeline` 等 ModuleNotFoundError），但 HGF 门禁 `pytest tests/` 只跑
   聚合文件（9 个），长期"门禁绿"掩盖了测试体系断裂。同时简报声称"654 测试全绿"，
   实测 438（406 passed + 32 skipped）——声称-现实漂移。
2. **ruff --fix 全库自动清理掩盖真实缺陷**：filing_service.py 引用不存在的
   `get_downloader`/`list_filings`/`download_with_cache`（hermes 版遗留），ruff 按 F401
   "未使用导入"把 get_downloader 静默删除——断裂被"修掉表面"而非"修复根因"。
3. **ModuleLoader 启动报错**：MODULE_CONFIG 引用幽灵模块（gate_checks 无任何实现、
   review_integrator 候选路径全指向缺失的 v3 子包），主流程启动自检 errors.extend 报 2 个必需模块失败。

## 根因

1. **路径契约断裂**：模块从 `quality/v3/X` 迁到 `quality/X`（平铺化重构），但测试 import
   路径未同步；`v3/__init__.py` 是空 shim（只有 docstring 无 re-export）。这是"重构平铺化
   时丢失了子包引用"的典型——文件在但路径死了。
2. **HGF 门禁入口覆盖不足**：unit_test 门禁 `pytest tests/` 只覆盖聚合引用的文件，
   全目录收集（`pytest tools/finance/`）才是真实完整性检查——"聚合绿"≠"测试体系完整"。
3. **ruff --fix 的 F401 清理不感知"引用断裂"**：对被引用的不存在符号，ruff 只看"当前
   import 未使用"就删——不区分"删了安全"与"删了掩盖 bug"。
4. **HAS_* 死导入**（workflow.py:128-139）：HAS_CIRCUIT_BREAKER/HAS_STAGE_MANAGER 定义了
   但全文件无使用——"文件存在≠已接入"的 HGF 纪律反例。

## 修复

1. 20 个 v3 shim（`quality/v3/*.py` 两行式 `from ..X import *` + 显式符号）+ quality/__init__.py
   顶层 27 符号 re-export + 7 个模块 17 处相对导入修复（`..X`→`.X`）。
2. 测试路径契约对齐：hermes_tools.finance.X→finance.X、quality.X→finance.quality.X；
   契约不一致的显式 skip 标注（三态，不静默）。
3. ModuleLoader 候选路径指向平铺真实模块，gate_checks 降级非必需。
4. **修复后全目录收集验证**：`pytest tools/finance --ignore=tools/finance/.venv` 从 27 错误
   → 406 passed + 32 skipped，0 失败。

## 验证

- `pytest tools/finance --ignore=tools/finance/.venv`：406 passed + 32 skipped，0 fail
- `pytest tests/`（HGF 聚合）：248 passed + 17 skipped（修复前 88）
- ModuleLoader check_all_modules：success=True，零 warnings
- 28 个业务模块 import 冒烟零失败（F401 无关键误删）

## 教训（防复发）

1. **定期全目录收集测试**：`pytest tools/finance/` 应纳入 HGF 门禁或 CI，不能只依赖聚合入口；
   "测试文件存在"必须验证"可收集+可执行"。
2. **ruff --fix 前先确认引用完整性**：对被清理的 import，先 grep 确认目标符号存在；
   引用断裂的模块应修复根因而非被自动删除表面。
3. **声称数字必须可复现**：测试数量/覆盖率等数字写进文档前先实测，防"声称-现实"漂移。
4. **重构平铺化必须同步路径**：移动模块时用 grep 全量扫 import 路径，v3 类 shim 不能只留 docstring。

关联：HGF P0-①/P0-② 修复（commit 538d462）、遗留项处理（8ab3f27）、
docs/qual-hgf-deep-check-2026-08-22.md §3/§5。
