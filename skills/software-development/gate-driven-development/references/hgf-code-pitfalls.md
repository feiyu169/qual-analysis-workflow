# HGF Code Pitfalls — 从实际评审中发现的常见问题

## 来源
2026-07-10 代码评审会话，对 ~/.hermes/workflow/ 的完整审查。
第一轮：35 个问题（7 P0 + 14 P1 + 14 P2），评分 50/100
第二轮：18 个新问题（3 P0 + 11 P1 + 4 P2），评分 72/100
修复后：~80/100

## P0 级问题（必须修复）

### 1. 空壳实现（Empty Shell Implementations）
**文件**: gate_manager.py L155-160, verification_engine.py L162-190
**问题**: `_verify_criteria()` 始终返回 True；L3/L4/L5 验证器返回 passed=True
**教训**: 搜索 `return True` 和 `passed=True` 找到所有空壳。空壳比缺失更危险——它们让测试通过但功能失效。
**修复**: 对接 VerificationEngine；未实现的验证器返回 `VerificationResult(passed=False)` 或 raise NotImplementedError（但必须在 verify() 中捕获）

### 2. 变量名遮蔽（Variable Shadowing）
**文件**: gate_manager.py L139
**问题**: `result = self._verify_criteria(criteria, result)` 在循环中覆盖了外部传入的 `result`
**教训**: 循环体内不要复用外部参数名。用 `criteria_result` 等独立变量名。

### 3. 计数器双重递增（Double Increment）
**文件**: gate_manager.py L230-237
**问题**: `transition(FAILED)` 已递增 failure_count，`handle_failure` 又递增一次
**教训**: 状态转移和业务逻辑不要在两处都修改同一计数器。统一在一个地方计数。

### 4. 类型错误（Type Mismatch）
**文件**: risk_assessor.py L162
**问题**: `RISK_MAPPING["business"] = 2`（int），但 RISK_MAPPING 的值应该是 str（映射到 RISK_FACTORS 的键）
**教训**: 修复 bug 时要确认放入的是正确的数据结构。int 放入 str-only 映射表会被静默忽略。

### 5. 命名冲突（Naming Conflict）
**文件**: gate_types.py vs state_machine.py
**问题**: 两个模块都定义 `GateStatus`，同名不同义
**教训**: 包内模块的公共类型名必须唯一。用 `GateExecutionStatus` 区分。

### 6. NotImplementedError 传播
**文件**: verification_engine.py L162-190
**问题**: 抛出 NotImplementedError 会向上层传播导致 Gate 执行崩溃
**教训**: 在 verify() 中 try/except NotImplementedError，返回 VerificationResult(passed=False)

## P1 级问题

### 7. 时区不一致
**文件**: state_machine.py L172 vs L125
**问题**: transition() 用 datetime.now()，_save_state() 用 datetime.now(timezone.utc)
**修复**: 统一使用 UTC

### 8. shell=True 注入
**文件**: verification_engine.py L59, L124
**修复**: shlex.split(command) + shell=False

### 9. 裸 except
**文件**: verification_engine.py L204, L220
**修复**: except Exception

### 10. FORBIDDEN_VERIFICATIONS 检查逻辑错误
**文件**: verification_engine.py L44-45
**问题**: 检查 level in FORBIDDEN，但 level 是 "L1" 而 FORBIDDEN 里是 "file_exists"
**修复**: 检查 command 参数中是否包含禁止的验证方式

## 评审流程要点

1. **自评必须读代码**：不能只看文档，必须 read_file 实际源码
2. **专家必须独立**：delegate_task 到独立 subagent，避免自我确认偏差
3. **修复必须对照文档**：创建 fix-plan.md，逐项核对
4. **每 Gate 运行测试**：P0 修完跑一次，P1 修完跑一次，不能到最后才跑
5. **二轮评审必须**：第一轮修复可能引入新问题（如 P0-NEW-02 类型错误）
