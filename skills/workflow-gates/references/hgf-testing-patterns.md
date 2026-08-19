# HGF 测试集成模式

## 概述

在HGF（Hermes Gate Flow）工作流中，测试不是独立阶段，而是贯穿整个交付流程的质量门禁。

## Gate T 设计原则

1. **左移测试**: 测试尽早介入，从代码提交就开始
2. **分级执行**: 不同阶段执行不同级别的测试
3. **自动阻断**: 测试失败自动阻断流程，不依赖人工判断
4. **持续回归**: 定期执行全量回归，发现潜在问题

## 测试用例设计规范

### 用例模板

```yaml
test_case:
  id: TC-XXX-001
  module: 模块名
  feature: 功能名
  priority: P0  # P0=阻塞 P1=严重 P2=一般 P3=低优
  
  preconditions:
    - 前置条件1
    - 前置条件2
  
  steps:
    - action: HTTP方法 /api/v1/xxx
      body: {参数}
  
  expected:
    - status_code: 200
    - response.code: 200
    - database.table.field: 预期值
  
  cleanup:
    - 清理操作
```

### 断言深度要求

**Level 1 (表面)**: 仅验证HTTP状态码
**Level 2 (响应)**: 验证响应字段存在性和基本值
**Level 3 (数据库)**: 验证数据库字段值与输入一致
**Level 4 (关联)**: 验证关联数据（日志、通知、缓存）正确性
**Level 5 (业务)**: 验证业务规则（时间顺序、状态机、权限）

## 实战经验

### 案例: 气田异常管理系统测试方案审查

**HeavySkill审查结果**: 6/6轨迹成功, 66,637 tokens

**发现的P0问题**:
1. 字典管理/统计/调度器/日志模块测试严重不足
2. 异常流程/容错测试完全缺失
3. 权限矩阵测试不完整（越权风险）
4. 大数据量性能测试缺失
5. 调度器触发的业务规则未验证

**关键教训**:
- 测试不能只验证"能用"，要验证"正确"
- 权限测试必须覆盖IDOR（水平越权）
- 并发测试需要真实多线程模拟
- 状态流转测试必须覆盖所有允许/禁止路径

### 测试覆盖检查清单

```
功能覆盖:
  [ ] 所有API接口 100%覆盖
  [ ] 所有HTTP方法 100%覆盖
  [ ] 所有状态流转 100%覆盖
  [ ] 所有角色权限 100%覆盖

边界覆盖:
  [ ] 分页边界 (page=0, page=-1, page=999999)
  [ ] 输入边界 (空值、超长、格式错误)
  [ ] 时间边界 (跨天、跨月、跨年)
  [ ] 权限边界 (越权、IDOR)

异常覆盖:
  [ ] 服务不可用 (DB/Redis/外部服务)
  [ ] 无效输入 (格式错误、类型错误)
  [ ] 并发冲突 (重复提交、竞态条件)
  [ ] 资源耗尽 (连接池、磁盘空间)
```

## 自动化框架建议

```
技术栈:
  - Python 3.11 + pytest 7.x
  - requests (HTTP客户端)
  - allure (测试报告)
  - threading (并发测试)

目录结构:
  tests/
  ├── conftest.py           # fixtures
  ├── test_smoke/           # 冒烟测试
  ├── test_functional/      # 功能测试
  ├── test_boundary/        # 边界测试
  ├── test_workflow/        # 状态流转
  ├── test_concurrent/      # 并发测试
  ├── test_security/        # 安全测试
  ├── test_performance/     # 性能测试
  └── utils/
      ├── api_client.py     # API客户端
      ├── assertions.py     # 断言
      └── report.py         # 报告
```
