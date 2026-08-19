# LLM Caller 配置 (Verified 2026-06-30)

## 文件位置

`~/.hermes/tools/finance/llm_caller.py`

## 创建 DeepSeek Caller

```python
from finance.llm_caller import create_deepseek_caller

llm_caller = create_deepseek_caller(
    model="deepseek-chat",      # DeepSeek V3
    temperature=0.7,
    max_tokens=4096,
)
```

## API Key 来源 (按优先级)

1. 环境变量: `DEEPSEEK_API_KEY`
2. 文件: `~/.hermes/.env` 中 `DEEPSEEK_API_KEY=xxx`
3. 配置: `~/.hermes/config.yaml` → `mcp_servers.gbrain.env.DEEPSEEK_API_KEY`

## 签名

```python
llm_caller(chapter_name: str, prompt: str) -> str
```

- `chapter_name`: 章节名称 (如 "第1章: 公司做的是什么生意")
- `prompt`: 写作提示 (包含数据上下文和 must_answer 要求)
- 返回: 生成的章节内容 (Markdown)

## 与 run_analysis 集成

```python
from finance.llm_caller import create_deepseek_caller
from finance.workflow import run_analysis

llm_caller = create_deepseek_caller()
result = run_analysis(
    ticker="1024.HK",
    company_name="快手",
    market="hk",
    wind_data=wind_data,
    llm_caller=llm_caller,
    shares=43.4,
)
```

## 常见问题

### Q: llm_caller 为 None 会怎样?
A: workflow.py v3 会发出 DeprecationWarning 并使用 placeholder 输出。
但审计会全部 failed (score=0)，因为 placeholder 不满足 must_answer。

### Q: DeepSeek API 调用失败?
A: llm_caller.py 会 raise exception，不会静默吞掉。
检查 API Key 是否有效: `curl https://api.deepseek.com/v1/models -H "Authorization: Bearer $DEEPSEEK_API_KEY"`

### Q: 能否用其他模型?
A: `create_deepseek_caller()` 内部使用 OpenAI 兼容 API。
如果要换模型，修改 `model` 参数即可 (需 base_url 支持)。
