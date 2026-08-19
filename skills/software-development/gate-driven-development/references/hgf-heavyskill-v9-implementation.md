# HGF + HeavySkill V9 实施经验

## 实施时间线

2026-06-21：从 V3 迭代到 V9，经历 6 轮审查

## 关键修复清单

### P0 问题（致命）

1. **verdict=dict 笔误**（V8→V9）
   - `return ValidationResult(verdict=verdict=dict, ...)` 是语法错误
   - 正确：`return ValidationResult(verdict=verdict, ...)`

2. **正则表达式语法错误**（V7→V8）
   - `r'[_.\\-/\\]'` 中 `\\-/` 是无效范围（92 > 47）
   - 正确：`r'[_.\\/\\-]'`（`-` 放在末尾）

3. **industry 名称不一致**（V7→V8）
   - `project.industries: [healthcare, finance]` vs `industry: healthcare`
   - 必须统一，否则 severity_overrides 永远无法匹配

4. **confirm_false_positive 逻辑 bug**（专家发现）
   - `collect_false_positive` 未生成 `feedback_id`
   - `confirm_false_positive` 永远无法匹配任何记录

### P1 问题（严重）

1. **snake_case 文件名匹配失效**
   - Python `\b` 在 `_` 两侧不生效
   - 必须用分隔符切分后精确匹配

2. **asyncio.wait 缺少超时控制**
   - 单个 LLM 调用挂起会导致整个审查卡住
   - 使用 `asyncio.wait(tasks, timeout=90)` 替代

3. **process_items_handling 三种模式实现缺失**
   - `skip`：完全跳过
   - `warn`：只入 warnings，不入 issues
   - `check`：只入 issues，不入 warnings

4. **severity_overrides 只支持单行业**
   - 改为 `industries: [healthcare, finance]` 列表
   - 取最高严重等级

5. **filter_by_languages 大小写敏感**
   - 统一转小写：`{lang.lower() for lang in languages}`

### P2 问题（一般）

1. **_TOKENIZER 正则重复定义**
   - 提取到 utils.py 统一管理

2. **print 改 logging**
   - 生产环境需要日志级别控制

3. **YAML 键加引号**
   - `.jsx` 等键必须加引号避免解析歧义

4. **配置路径嵌套**
   - `config.get("checklists", {}).get(...)` 而非 `config.get("file_extension_mapping")`

## 测试覆盖

- 12 个单元测试，全部通过
- 覆盖：RiskAssessor、ConclusionValidator、AppealHandler、ReportGenerator
- 缺少：ChecklistManager 测试、边界测试

## 专家审查模式

- 编程专家：4 P1 + 9 P2
- 架构专家：4 中等 + 3 低
- 关键发现：confirm_false_positive bug、配置路径不匹配

## 迭代收敛

V3 → V4 → V5 → V6 → V7 → V8 → V9（7 轮）
- 每轮修复 3-10 个问题
- 最终所有 P0/P1/P2 问题全部修复
