# ANCH投资论点锚定实现记录

**实施日期**: 2026-07-11
**实施阶段**: Gate 2 (数据可信度+论点锚定)

## 修改的文件

| 文件 | 修改内容 |
|------|----------|
| `workflow.py` | 新增`_generate_anch_hypothesis()`和`_format_anch_for_prompt()`函数 |
| `workflow.py` | Step 2.5 ANCH锚定步骤 |
| `workflow.py` | `_write_chapters()`接收`anch_hypothesis`参数 |
| `workflow.py` | 章节prompt注入ANCH上下文 |

## 核心函数

### `_generate_anch_hypothesis(ctx, llm_caller)`

生成投资论点锚定，返回结构化JSON：

```python
{
    "core_thesis": "顺丰的重资产壁垒在价格战中形成逆周期盈利能力",
    "key_arguments": [
        {
            "argument": "时效件定价权保障利润底线",
            "evidence": "单票收入16元vs行业3-5元",
            "verification": "Q3时效件单价是否企稳",
            "falsification": "时效件单价跌破15元/票"
        }
    ],
    "bear_case": "价格战蔓延至时效件+需求结构降级",
    "catalysts": ["Q3财报", "鄂州机场产能利用率"]
}
```

### `_format_anch_for_prompt(anch)`

将ANCH格式化为prompt文本，注入到章节写作prompt中。

## 闭环机制

```
ANCH (Step 2.5) → 投资假设JSON
    ↓
T1-T12 (Step 3-4) → 各章分析，引用ANCH key_argument
    ↓
ANCH Update (Step 4.5) → 汇总证据，更新验证状态
    ↓
T3 综合结论 (Step 5) → 显式引用ANCH:
  - key_argument[0]: confirmed ✅
  - key_argument[1]: pending ⏳
  - key_argument[2]: falsified ❌
```

## JSON解析三层防护

1. 直接`json.loads()`
2. 从markdown代码块中提取```json...```
3. 找第一个`{`和最后一个`}`之间的内容

## 验证结果

```
✅ ANCH格式化测试:
  长度: 163字符
  包含核心论点: True
  包含证伪条件: True
```
