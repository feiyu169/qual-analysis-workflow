# HeavySkill 检查清单汇总

> 版本：2.0
> 日期：2026-06-21
> 来源：内置静态清单（builtin）
> 更新：修复 P0 问题（领域名不匹配）

---

## 清单概览

| 领域 | 文件名 | 检查项数 | P0 | P1 | P2 | 说明 |
|------|--------|----------|----|----|-----|------|
| security | security.yaml | 14 | 4 | 7 | 3 | 安全审查 |
| architecture | architecture.yaml | 13 | 1 | 9 | 3 | 架构审查 |
| performance | performance.yaml | 14 | 0 | 9 | 5 | 性能审查 |
| api | api.yaml | 18 | 0 | 9 | 9 | API 审查 |
| database | database.yaml | 18 | 0 | 10 | 8 | 数据库审查 |
| deployment | deployment.yaml | 20 | 0 | 9 | 11 | 部署审查 |
| frontend | frontend.yaml | 8 | 0 | 4 | 4 | 前端审查 ⭐ 新增 |
| general | general.yaml | 15 | 0 | 7 | 8 | 通用审查 |
| **总计** | - | **120** | **5** | **64** | **51** | - |

---

## V2 更新内容

### 修复 P0 问题

1. **领域名对齐**：V3 文档中的 `maintainability` 等不存在的领域已移除
2. **README 更新**：与实际文件状态对齐

### 修复 P1 问题

1. **增加 check_scope 字段**：区分 code/config/process
2. **S-02 XSS 降级**：从 P0 降为 P1，增加升级条件
3. **增加 languages 字段**：按项目语言加载检查点
4. **fix_suggestion 分步骤**：改为 steps + example 格式

### 新增清单

1. **frontend.yaml**：前端审查清单（8项）

---

## 领域映射表

| 领域 | 文件扩展名 | 说明 |
|------|-----------|------|
| security | * | 所有代码都需要安全检查 |
| architecture | * | 所有代码都需要架构检查 |
| performance | * | 所有代码都需要性能检查 |
| api | .py, .java, .go, .js (路由/控制器) | API 相关代码 |
| database | .sql, .py (模型), .java (Entity) | 数据库相关代码 |
| deployment | .yaml, .yml, .tf, Dockerfile | 部署相关配置 |
| frontend | .jsx, .tsx, .vue, .css, .scss | 前端代码 |
| general | * | 通用检查 |

---

## check_scope 字段说明

| 值 | 说明 | HeavySkill 处理方式 |
|----|------|---------------------|
| code | 可从代码中检查 | 自动检查，影响 verdict |
| config | 可从配置中检查 | 自动检查，影响 verdict |
| process | 流程问题，无法自动化 | 仅提醒，不影响 verdict |

---

## 严重等级说明

| 等级 | 说明 | 处理方式 |
|------|------|----------|
| P0 | 致命问题 | 必须修复，阻断合并 |
| P1 | 重大问题 | 应该修复，警告 |
| P2 | 一般问题 | 建议修复，仅记录 |

### 项目级别覆盖

某些检查项的严重等级可根据项目类型升级：

```yaml
# 项目配置示例
severity_overrides:
  finance:
    D-07: P0  # 金融项目：事务管理升级为 P0
    S-06: P0  # 金融项目：密码加密必须 P0
  
  healthcare:
    S-11: P0  # 医疗项目：数据加密传输必须 P0
    D-16: P0  # 医疗项目：数据加密必须 P0
```

---

## languages 字段说明

检查项支持按项目语言加载：

```yaml
check_points:
  - "是否使用参数化查询？"
languages: [python, java, go, js, php, ruby]
```

如果项目语言不在列表中，该检查项会被跳过。

---

## 动态加载策略

HeavySkill 不会加载全部 120 项检查，而是根据 MR 涉及的文件动态加载：

**映射规则**：
- .jsx, .tsx, .vue, .css, .scss → frontend
- .sql, model, entity → database
- .yaml, .yml, .tf, Dockerfile → deployment
- api, controller, route → api
- 所有代码 → security, architecture, performance

**示例**：
- 只改 API 文件 → 加载 security + architecture + performance + api = ~60 项
- 只改前端文件 → 加载 security + architecture + performance + frontend = ~50 项
- 改数据库 + API → 加载 security + architecture + performance + database + api = ~80 项

---

## 清单文件位置

```
~/.hermes/skills/heavyskill-optimize/checklists/
├── security.yaml      # 安全审查清单（14项）
├── architecture.yaml  # 架构审查清单（13项）
├── performance.yaml   # 性能审查清单（14项）
├── api.yaml           # API 审查清单（18项）
├── database.yaml      # 数据库审查清单（18项）
├── deployment.yaml    # 部署审查清单（20项）
├── frontend.yaml      # 前端审查清单（8项）⭐ 新增
├── general.yaml       # 通用审查清单（15项）
└── README.md          # 本文件
```
