# R6 LLM 超时问题核查 + 直连 API 方案评估

> 核查 R6 过程中 42 次 "llm bridge 调用失败" 的根因，评估"直接配置模型 API"是否能避免。

---

## 一、R6 超时事实（实测数据）

| 指标 | 值 |
|---|---|
| 桥接失败次数 | 42 次（llm-calls.log） |
| 失败平均耗时 | 72.2s（峰值 124.2s） |
| 成功调用 | 156 次，平均 30.5s（峰值 182.6s） |
| 失败原因 | 全部 "llm bridge 调用失败"（RuntimeError） |
| 失败集中点 | 事实提取批次8、辩论 bear_ch5、patch 修复 ch2/ch4/ch6/ch7 等长 prompt 调用 |

## 二、超时根因定位（分层排查）

```
Python harness_llm (urllib, timeout=300s)
  → POST /api/llm-bridge (桥接插件, handler)
    → llm.stream(provider=deepseek-official, model=deepseek-v4-flash, maxTokens=...)
      → 宿主 llm 服务 → DeepSeek 模型 API
```

**失败发生在哪一层**：
- ❌ 不是 Python 层超时（300s > 失败 72s）
- ❌ 不是 HTTP 层（urllib 拿到响应但 ok=false）
- ✅ **是宿主 `llm.stream` 内部**：deepseek-v4-flash 是**推理模型**，长 prompt（事实提取 32K 字符、patch 修复、辩论 bear 反驳）下思考+生成可能 >60-120s，宿主 llm 服务侧**流中断/超时/限流** → handler 捕获 → send(500) → Python 抛 "llm bridge 调用失败"

**本质**：超时是**模型推理时长**问题（推理模型长任务慢），叠加**宿主 llm 服务的流式处理上限**（可能无长任务超时配置或 provider 限流），而非桥接代码缺陷。

## 三、直连 API 方案评估

### 3.1 现状（llm_caller.py create_deepseek_caller）

| 参数 | 直连现状 | 问题 |
|---|---|---|
| timeout | **60s 硬编码** | 比桥接 300s 更严，**长任务必超时** |
| max_tokens | **4096 硬编码** | 远小于桥接 12000，长章节截断 |
| 重试 | **无** | 失败即抛 |
| API key | **DEEPSEEK_API_KEY 为空** | **当前无法直连**（用户未提供） |

### 3.2 直连能否避免超时？—— **能缓解，但需先修 3 个缺陷**

**能避免的部分**：
1. **绕过宿主 llm 服务的流式限制**：直连 DeepSeek API（openai 兼容）可设 `timeout` 为长值（如 300s）+ 流式或非流式，宿主侧的中断/限流不再存在
2. **可调 max_tokens**：按任务设 12000-24000，避免截断
3. **可加重试**：指数退避重试瞬时错误

**但不能避免的部分（诚实）**：
1. **推理模型本身慢**：deepseek-v4-flash 思考+生成长任务就是需要 60-180s，直连只是"不会因宿主侧限制中断"，模型速度不变
2. **需真实 API key**：当前 DEEPSEEK_API_KEY 为空——**无 key 直连不可用**，这是硬前提
3. **直连时绕开宿主路由**：失去宿主的多模型切换/审计/配额管理

### 3.3 结论

| 方案 | 是否避免超时 | 前提 | 风险 |
|---|---|---|---|
| **桥接（现状）** | ❌ 42 次失败 | 无需 key | 宿主 llm 流式限制 |
| **直连（改好）** | ✅ 缓解（宿主层限制消除） | **需 DEEPSEEK_API_KEY** + 修 timeout/max_tokens/重试 | 模型速度不变；失去宿主管理 |

**建议**：
1. **短期（不改架构）**：调桥接参数——harness_llm 的 timeout 300s 保持，但**辩论/patch 用 max_tokens 减半（4000）+ 更长 timeout**，减少推理时长；或宿主 llm 服务侧调大流式超时
2. **中期（可选）**：用户提供 DEEPSEEK_API_KEY 后，修 `create_deepseek_caller`（timeout=300, max_tokens=12000, 加重试），作为**桥接失败的 fallback**——`run_qual_full.py` 里 `create_harness_caller()` 失败时自动降级到直连
3. **不建议**：直接用直连替代桥接（失去宿主路由/审计；且需用户提供 key）

### 3.4 直连 fallback 设计（若用户提供 key）

```python
# run_qual_full.py
try:
    llm_caller = create_harness_caller()   # 桥接（主）
except Exception as e:
    logger.warning(f"桥接不可用，降级直连: {e}")
    llm_caller = create_deepseek_caller(   # 直连（备，需修 timeout/max_tokens/重试）
        model="deepseek-chat", timeout=300, max_tokens=12000
    )
```

---

## 四、最终答复

**问题**：R6 的 LLM 超时（42 次）根因是**宿主 llm 服务对推理模型（deepseek-v4-flash）长任务的流式限制/中断**，不是桥接代码 bug。

**直连 API 能否避免**：**可以缓解**（消除宿主层限制 + 可调超时/重试），但：
1. **必须先有 DEEPSEEK_API_KEY**（当前为空，硬前提）
2. **必须修 `create_deepseek_caller` 的 3 个缺陷**（60s→300s、4096→12000、加重试）——否则直连比桥接更容易超时
3. 模型本身推理速度不变（长任务 60-180s 是常态）

**推荐路径**：用户提供 key → 修直连调用器 → 作为桥接的 **fallback**（非替代），双保险。

---

## 五、落地状态（2026-08-18）

| 项 | 状态 |
|---|---|
| `DEEPSEEK_API_KEY` 写入 `config/.env` | ✅（用户提供） |
| `create_deepseek_caller` 修复：timeout 60→300、max_tokens 4096→12000、加 max_retries=2 指数退避 | ✅ |
| 直连实测：真实 key 1s 返回 OK | ✅ |
| `run_qual_full.py` 桥接 fallback：桥接连续失败≥3 次自动切直连（运行期降级 + 初始化降级） | ✅ |
| fallback 逻辑实测：前 2 次失败计数、第 3 次触发切换、之后走直连 | ✅ |

> 安全提醒：API key 以聊天形式提供，已写入 .env；建议定期轮换。
