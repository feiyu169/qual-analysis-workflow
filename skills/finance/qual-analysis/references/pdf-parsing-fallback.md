# PDF 解析降级方案 (Verified 2026-06-23)

## 解析器优先级

1. **MinerU** → 专业中文 PDF 解析，支持表格提取
2. **pdfplumber** → 纯 Python，表格提取能力强
3. **PyPDF2** → 基础文本提取，无表格支持

## 安装方式

### MinerU
```bash
pip install mineru paddlepaddle paddleocr
```
**⚠️ 依赖较重，安装可能失败**

### pdfplumber (推荐降级方案)
```bash
# 使用系统 Python 安装到用户目录
/usr/bin/python3 -m pip install --user pdfplumber
```

**⚠️ 关键**：
- venv 中可能没有 pip，必须用 `/usr/bin/python3`
- 安装后需要添加路径：`~/.local/lib/python3.8/site-packages`

### PyPDF2
```bash
/usr/bin/python3 -m pip install --user PyPDF2
```

## 使用方式

```python
import sys
sys.path.insert(0, '/home/lff7767162/.local/lib/python3.8/site-packages')

from finance.parsers.mineru_parser import MinerUParser

parser = MinerUParser()
result = parser.parse(pdf_path, "1357", "annual_report")

# result.markdown → 文本内容
# result.tables → 表格列表
# result.page_count → 页数
# result.metadata["parser"] → 使用的解析器
```

## 验证解析结果

```python
assert len(result.markdown) > 0, "解析结果为空"
assert result.page_count > 0, "页数为 0"
assert result.metadata.get("parser") != "none", "未使用任何解析器"
```

## 常见问题

### Q: pdfplumber 返回空内容
A: 检查 PDF 是否为扫描件（图片），pdfplumber 只能提取文本 PDF

### Q: 中文乱码
A: pdfplumber 对中文支持良好，如果乱码可能是 PDF 编码问题

### Q: 表格提取不完整
A: 复杂表格可能需要手动处理，pdfplumber 的 `extract_tables()` 对简单表格效果好
