# Design-to-Implementation Workflow

> HeavySkill 审查驱动的完整开发工作流
> Verified: 2026-06-12 (气田异常管理系统)

## 工作流概览

```
技术设计文档
    ↓
HeavySkill 多轮审查 (2-3轮)
    ↓ 用户修复问题
生成开发任务清单
    ↓
生成 API 接口文档
    ↓
生成项目骨架代码
```

## 阶段 1: HeavySkill 审查

### 多文件审查命令

```bash
cat > /tmp/heavyskill-query.txt << 'EOF'
请审查以下系统设计方案（修订版），从以下6个维度进行详细评估：
1. 业务流程设计
2. 数据库设计
3. 架构设计
4. 安全性
5. 可行性
6. 风险遗漏
请重点关注与前一版相比的改进点，以及是否仍存在遗漏。
EOF

cd ~/.hermes/skills/heavyskill && python3 scripts/run_heavyskill.py \
  --query "$(cat /tmp/heavyskill-query.txt)" \
  --include-file /path/to/design.md \
  --include-file /path/to/schema.sql \
  --reason_k 6 --summary_k 3 --language cn \
  --output /tmp/heavyskill-review.json \
  --quiet
```

### 提取审查结果

```python
import json

with open('/tmp/heavyskill-review.json') as f:
    data = json.load(f)

# 提取各轨迹结论（最后 2000 字符）
for i, t in enumerate(data['reasoning']['trajectories']):
    print(f"【专家 {i+1}】")
    print(t[-2000:])

# 提取综合结论
print(data.get('consensus_answer', 'N/A')[:3000])
```

## 阶段 2: 生成开发任务清单

基于所有轮次的审查建议，生成结构化的任务清单：

```markdown
## 任务分类
- P0 - 核心功能 (MVP)
- P1 - 增强功能
- P2 - 优化体验
- P3 - 运维保障

## 任务结构
| 任务ID | 任务名称 | 优先级 | 预计工时 | 说明 |
```

## 阶段 3: 生成 API 接口文档

基于设计文档的业务流程和数据模型：

```markdown
## API 结构
- 认证模块 (登录/登出/刷新)
- 核心业务模块 (CRUD + 状态流转)
- 统计报表模块
- 基础数据管理模块

## 接口格式
- RESTful 风格
- 统一响应格式: { code, message, data }
- JWT Bearer Token 认证
```

## 阶段 4: 生成项目骨架

Flask 项目标准结构：

```
project/
├── app/
│   ├── __init__.py      # 应用工厂
│   ├── api/             # API 蓝图
│   ├── models/          # 数据库模型
│   ├── services/        # 业务服务层
│   └── utils/           # 工具函数
├── config/              # 配置文件
├── migrations/          # 数据库迁移
├── scripts/             # 脚本工具
├── .env.example         # 环境变量示例
├── requirements.txt     # 依赖清单
└── run.py               # 主入口
```

## 案例: 气田异常管理系统 (2026-06-12)

### 审查收敛过程

| 轮次 | 结论 | Tokens | 文档大小 |
|------|------|--------|----------|
| V1 | 附意见通过 | 82,100 | 16,746 字符 |
| V2 | 有条件通过 | 99,400 | 23,744 字符 |
| V3 | 通过审查 | 108,688 | 26,843 字符 |

### V3 关键修复

- JWT 认证 + 权限矩阵
- 退回重报流程闭环
- 延期审批机制
- 处置历史记录表
- 异常编号并发控制

### 生成的交付物

1. 开发任务清单 (68项任务)
2. API 接口文档 (38个接口)
3. 数据库迁移脚本 (8张表 + 初始数据)
4. Flask 项目骨架 (完整可运行)
