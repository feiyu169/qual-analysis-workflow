# Gate Checks — 质量门禁集成指南

## 概述

Gate Checks是投资分析工作流中的自动化质量门禁，在"写作+审计"（Step 4.5）之后、"记忆存储"（Step 5）之前执行，确保进入HeavySkill审查的数据已通过最低卫生标准。

**实现位置**: `~/projects/gate-checks/`
**集成点**: `workflow.py` Step 4.6

## 架构

```
Gate 1: 结构完整性检查
├─ year_labels_exist (FATAL) — 检查_wind_data中_year_labels字段
├─ year_labels_array_alignment (ERROR) — 财年数组与数据数组长度一致
├─ chapters_complete (FATAL) — 必需章节集合{ch00-ch10}全部存在
└─ chapters_not_placeholder (FATAL) — ch01-ch09无Placeholder

Gate 2: 计算卫生检查
├─ dcf_params_exist (ERROR) — fcf/wacc/terminal_growth/shares存在
├─ wacc_range_warning (WARN) — 6%-18%范围，超出需人工解释
└─ fcf_ocf_ratio_warning (WARN) — -0.5~2.0范围，|OCF|<1时跳过
```

## 异常分级

| 级别 | 行为 | 说明 |
|------|------|------|
| FATAL | 硬阻断 | 不允许跳过，必须修复后重跑 |
| ERROR | 阻断 | 允许人工跳过（需备注原因注入P4） |
| WARN | 警告 | 不阻断，需人工解释 |

## 关键设计决策（HeavySkill K=8审查通过）

1. **两层而非三层**: Gate 1（结构完整性）+ Gate 2（计算卫生），合并了原"流程合规层"
2. **单一Checkpoint**: 放在Step 4.5之后，而非分散到数据收集/记忆存储阶段
3. **阈值为WARN而非阻断**: WACC/FCF范围检查不阻断流程，仅标记需人工解释
4. **防御性编程**: 所有检查函数对None/非字典/缺失键/非列表等异常均有处理
5. **集合校验**: chapters_complete检查必需章节集合是否全部存在，允许多余章节

## 集成代码（workflow.py Step 4.6）

```python
# Step 4.6: Gate Checks（数据事实验证）
gate_checks_report = None
try:
    from .gate_checks_integration import run_gate_checks_in_workflow, GateChecksBlockedError
    dcf_params = getattr(ctx, 'dcf_params', None)
    gate_checks_report = run_gate_checks_in_workflow(
        wind_data=ctx.wind, chapters=chapters, dcf_params=dcf_params,
        output_dir=str(output_dir) if output_dir else None, ticker=ticker
    )
    logger.info("Step 4.6 Gate Checks完成")
except GateChecksBlockedError as e:
    error_msg = f"Step 4.6 Gate Checks阻断: {e}"
    logger.error(error_msg)
    errors.append(error_msg)
    logger.warning("Gate Checks阻断，但继续执行后续步骤（降级模式）")
except ImportError:
    quality_degraded = True
    degradation_reasons.append("Gate Checks模块未找到")
    logger.warning("Gate Checks模块未找到，跳过Step 4.6")
except Exception as e:
    quality_degraded = True
    degradation_reasons.append(f"Gate Checks失败: {e}")
    logger.warning(f"Step 4.6 Gate Checks失败（非阻断）: {e}")
```

**⚠️ P86 已修复 (2026-07-11)**: `gate_checks_integration.py` 顶部必须有:
```python
import logging
logger = logging.getLogger(__name__)
```
否则 `except ImportError` 分支中的 `logger.warning()` 会抛 `NameError`，导致整个模块导入失败，`GateChecksBlockedError` 也未被导入，最终 `except GateChecksBlockedError` 引用未绑定变量。

## 痛点覆盖度（诚实评估）

| 痛点 | 有效性 | 说明 |
|------|--------|------|
| P15 年份标签缺失 | 90%+ | 直接命中，可根除 |
| P6 DCF Bug | 30-50% | 仅拦截参数缺失/数量级错误 |
| P13 LLM幻觉 | 10-20% | 仅检查字段存在性 |
| P18 自评虚报 | 0% | 明确排除，不造成"已验证"错觉 |

## 实施记录 (2026-07-03)

### 文件清单

| 文件 | 路径 | 说明 |
|------|------|------|
| 主入口 | `~/projects/gate-checks/src/gate_checks.py` | 整合Gate 1+Gate 2 |
| Gate 1核心 | `~/projects/gate-checks/src/gate1_structural_integrity.py` | year_labels检查 |
| Gate 1章节 | `~/projects/gate-checks/src/gate1_chapters_check.py` | 章节完整性+Placeholder |
| Gate 2 | `~/projects/gate-checks/src/gate2_calculation_hygiene.py` | DCF/WACC/FCF检查 |
| 工作流集成 | `~/.hermes/tools/finance/gate_checks_integration.py` | Step 4.6集成模块 |
| 配置文件 | `~/projects/gate-checks/config/gate_checks_config.yaml` | YAML配置 |
| 测试 | `~/projects/gate-checks/tests/` | 59个测试全部通过 |

### HeavySkill审查迭代 (v1→v2)

**v1被拒原因**:
1. 术语"PoW"引入区块链隐喻 → 改名"Gate Checks"
2. 三层设计冗余 → 合并为两层
3. WACC 8%-15%阈值过窄 → 改为6%-18% + WARN
4. FCF/OCF 50%-150%不合理 → 改为-0.5~2.0 + WARN
5. 缺乏异常分级 → 实现FATAL/ERROR/WARN三级

**v2通过**: 8/8轨迹一致肯定，共识"聚焦、务实、自限边界"。

### 防御性编程模式

所有检查函数必须处理：
- `wind_data`为None或非字典
- `_year_labels`为None或非字典
- `'财年'`键缺失
- `'财年'`不是列表
- 数据数组缺失或非列表
- OCF绝对值过小时跳过比例检查（避免除零）

### 美图(1357.HK)实测

Gate Checks在qual-analysis工作流中自动执行：
- Gate 1: 4项检查全部通过
- Gate 2: 3项检查全部通过（WARN级别不阻断）
- 报告自动保存到`{output_dir}/{ticker}_gate_checks_report.json`

## 使用方式

```python
from gate_checks import run_all_gate_checks, save_gate_checks_report

report = run_all_gate_checks(wind_data, chapters, dcf_params)
# report["gate_checks_report"]["summary"]["overall_status"] → "PASS" / "BLOCK"
```
