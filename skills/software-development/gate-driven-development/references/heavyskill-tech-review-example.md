# 技术文档 HeavySkill 审查示例 (2026-06-10)

## 审查对象
Hermes Agent P0 增强方案技术设计文档（40KB，7个方案，含数据库Schema、接口定义、CLI命令）

## HeavySkill 参数
```bash
--reason_k 6 --summary_k 3 --language cn
```

## 资源消耗
- Total Tokens: 113,298
- Total Latency: 175.73s
- Stage 1 (Parallel Reasoning): 91,398 tokens, 98.64s
- Trajectories: 6/6 successful

## 审查结果汇总

### P0 发现（6个）
| # | 问题 | 来源轨道 |
|---|------|---------|
| 1 | 接口缺少统一异常契约（返回值无法区分成功/失败） | T1/T3/T6 |
| 2 | record_user_feedback 的 session_id 应为必填 | T4 |
| 3 | check_alerts 缺少调度间隔数据源 | T5/T6 |
| 4 | experience_recall.py CLI 接口未文档化 | T3 |
| 5 | Python 脚本无法直接调用 MCP 工具（桥接层缺失） | T5/T6 |
| 6 | task_outcomes 表 Schema 未文档化 | T2/T5 |

### P1 发现（17个）
主要集中在：SQLite 并发安全、错误处理降级、模块耦合度、工时低估

### 关键教训
1. **接口设计必须定义异常契约** — 不是"能用就行"，而是"失败时调用方知道怎么处理"
2. **Schema 文档必须完整** — 不是"代码里有"，而是"文档中可查"
3. **MCP 调用路径必须明确** — Python 脚本和 Agent 是不同进程，不能假设 MCP 可用
4. **工时估算要留缓冲** — 涉及外部集成的方案（如 MCP 桥接层）往往被低估

## 提取审查结论的方法
```python
import json
with open('/tmp/review.json') as f:
    data = json.load(f)
trajectories = data['reasoning']['trajectories']
# 找 P0: 搜索 '| P0' 或 '**P0**'
# 找汇总表: 搜索 '维度' + 'P0' + 'P1'
# 注意: consensus_answer 可能被截断，必须从 trajectories 提取
```
