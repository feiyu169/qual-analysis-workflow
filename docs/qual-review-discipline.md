# 深度审查规范化方案（防审查引入新矛盾）

> 问题：审查修复循环中，LLM 修复时**整章重写**，可能：
> - 顺带改坏未点名的正确部分（改 A 弄坏 B）
> - 引入新数字/新事实（无锚点约束下自由发挥）
> - 改变原文观点/结构（修复即重写）
> 目标：**审查只发现问题，修复只动点名位置，且修复后必须通过全量校验**——让审查收敛而非发散。

---

## 一、现状三条修复路径的共同缺陷

| 路径 | 位置 | 修复方式 | 缺陷 |
|---|---|---|---|
| P1 | `quality/repairer.py` `repair_chapter` | 输出**完整章节** | 无 Wind 锚点；整章重写可破坏未点名部分 |
| P2 | `quality/review_repair_loop.py` `_repair_chapters` | `{content[:3000]}` + 问题列表 | 无锚点；内容截断前 3000 字（后面的被丢弃）；整章重写 |
| P3 | `quality/review_integrator.py` `fix_report` | 完整报告重写 + 完整性校验 | 有锚点表但**整份报告重写**；完整性只查长度/章节存在，不查数字 |

**共同根因**：修复=重写 → LLM 的统计性漂移在每次"修复"中被放大（R5 的 ch8/ch9 模板泄漏极可能是修复循环引入的）。

---

## 二、规范方案：五条铁律

### 铁律 1：修复最小侵入 —— Patch 模式（替换整章重写）

**只允许 LLM 输出"修改点"（位置 + 新片段），由程序应用，不整章重写。**

```
修复输出格式（强制 JSON）：
{
  "patches": [
    {"target": "原文中的唯一锚字符串", "replacement": "替换后的文本"},
    ... 最多 N 处（默认 5）
  ]
}
程序应用：
  content.replace(target, replacement)   # target 必须唯一匹配，否则拒绝该 patch
```

- `target` 必须是原文中的**唯一子串**（程序校验），防止误替换
- 未点名的内容**原样保留**（物理上不可能被改坏）
- patch 数超限 → 本轮修复失败，进入下一轮（或人工）

### 铁律 2：修复必须携带锚点（杜绝自由发挥）

修复 prompt 强制注入：
1. **Wind canonical 锚点表**（`_build_wind_anchor_table`，v8 已有）
2. **仲裁后事实表**（`_reconcile_facts_with_wind` 结果）
3. **数据源权威契约**（SOURCE_AUTHORITY）
4. **指令**："修复后的任何财务数字必须与锚点一致；禁止引入锚点外的新数字/新事实"

### 铁律 3：修复后必须重跑全量校验（收敛闭环）

每次修复后，强制运行（任一失败 → 该轮修复作废，恢复修复前版本）：
| 校验器 | 检查 | 来源 |
|---|---|---|
| `structural_check` | H1 唯一性/固定小节/占位符 | quality/structural_check.py |
| `cross_chapter_consistency` | 跨章数字一致 | quality/cross_chapter_consistency.py |
| DataAnchor 数字校验 | 报告数字 vs Wind 锚点（1% 容差） | qual_v8/data_anchor.py |
| 模板指纹 | 组合构建/沪深300/元/股/买入 | Gate8 检测逻辑 |

**校验不通过 → 回滚到修复前版本**（保存原内容），而不是接受"部分修复"。

### 铁律 4：修复预算与收敛上限

- 每轮修复最多 **5 个 patch**（超限即失败）
- 修复循环最多 **3 轮**（现状）
- **单调性守卫**：每轮修复后校验分必须 ≥ 上轮；下降 → 回滚并记录"该轮修复引入回退"
- 3 轮后仍未通过 → **停止修复，报告剩余问题**（不再无限重写）

### 铁律 5：修复审计日志（可追溯）

每条修复记录：
```
{round, patch_index, target摘要, 原因(对应哪个审查问题), before, after, 校验结果}
```
- 落盘到 `.pip-tmp/repair-log.jsonl`
- 报告头部（或附注）注明"本报告经 X 轮审查修复，修复记录见 ..."

---

## 三、实现落地清单

| 优先级 | 改动 | 文件 | 状态 |
|---|---|---|---|
| P0 | 新增 `quality/patch_applier.py`：patch JSON 解析 + 唯一匹配 + 预算 + 校验闭环 | 新文件 | ✅ 已建 |
| P0 | P2 改 patch 模式：`_repair_chapters` 输出 patch JSON，注入锚点 + 校验闭环 | review_repair_loop.py | ✅ 已改 |
| P0 | P3 改 patch 模式：`fix_report` 不再整报告重写 | review_integrator.py | ⏳ 待改 |
| P1 | P1 改 patch 模式 + 锚点注入 | repairer.py | ⏳ 待改 |
| P1 | 校验闭环复用：structural + cross_chapter + DataAnchor + 模板指纹 | patch_applier.py 内组合 | ✅ 已内置（structural/consistency/numeric） |
| P1 | 修复预算/单调性守卫/审计日志 | patch_applier.py + review_repair_loop | ✅ 预算已内置；单调性/日志待补 |

### 已验证（patch_applier 单测）
- T1 唯一匹配成功 ✅  T2 非唯一拒绝 ✅  T3 预算超限 ✅  T4 校验失败回滚 ✅  T5 代码块解析 ✅
- quick 回归：Gate0-7 PASS，Gate8 正确拒绝 R5 ✅

---

## 四、预期效果

- **不引入新矛盾**：patch 只动点名位置 → 未点名内容物理不变
- **数字不漂移**：锚点注入 + 校验闭环 → 新数字必须与 Wind 一致
- **修复收敛**：单调性守卫 + 预算 → 3 轮内要么通过要么报告剩余问题，不无限发散
- **可追溯**：修复日志 → 每次改动可审计（HGF P4 原则）

---

## 五、边界与权衡

- **patch 模式对"重写型问题"（整章模板泄漏）不适用**：ch8/ch9 整章是错的，需要"整章重写"而非 patch。
  处理：检测到整章主题漂移（模板指纹命中）→ 走**专用重写路径**（注入锚点 + 权威契约 + 骨架，单章重写），
  其余问题走 patch。即：**patch 治局部，重写治整章，两者分开**。
- patch 的 target 匹配对 LLM 输出的格式要求高（唯一锚串）；失败时降级为"带上下文的片段替换"。
- 修复仍需要 LLM（patch 生成），但**影响面从"整章"缩到"点名片段"**，污染概率大幅下降。
