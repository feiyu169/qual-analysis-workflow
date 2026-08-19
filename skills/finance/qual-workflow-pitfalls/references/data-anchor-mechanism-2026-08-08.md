# Data Anchor Mechanism — 跨章节数据同步

> Verified 2026-08-08, 小鹏汽车9868.HK实测

## 问题

审查修复循环3轮后仍有191个跨章节一致性问题未修复：
- 经营现金流在第3章=35.0亿，第5章=35.2亿，第6章=12.0亿，第7章=365.0亿
- 净利润在第3章=28.4亿，第5章=30.0亿，第6章=-57.0亿

**根因**：各章节独立生成，LLM每次生成时使用不同的数据值。修复模块无法确定"正确值"是什么。

## 解决方案：数据锚点机制

在Gate 2（数据收集）提取的数据作为**唯一数据源**（锚点），在Gate 4（审计修复）检查各章节引用的数据是否与锚点一致，不一致时使用锚点数据替换。

## 核心实现

```python
class DataAnchor:
    """数据锚点（唯一数据源）"""
    
    def __init__(self):
        self.anchors: Dict[str, DataPoint] = {}
    
    def set_anchor(self, key: str, value: float, unit: str = "亿元", source: str = "Wind"):
        self.anchors[key] = DataPoint(key=key, value=value, unit=unit, source=source)
    
    def get_anchor(self, key: str) -> Optional[float]:
        if key in self.anchors:
            return self.anchors[key].value
        return None
    
    def init_from_wind_data(self, wind_data: Dict[str, Any]):
        """从Wind数据初始化锚点"""
        income = wind_data.get("income", {})
        balance = wind_data.get("balance", {})
        cashflow = wind_data.get("cashflow", {})
        
        # 利润表
        if "年营业收入" in income and income["年营业收入"]:
            self.set_anchor("营业收入", income["年营业收入"][-1])
        if "年净利润" in income and income["年净利润"]:
            self.set_anchor("净利润", income["年净利润"][-1])
        
        # 资产负债表
        if "年资产总计" in balance and balance["年资产总计"]:
            self.set_anchor("总资产", balance["年资产总计"][-1])
        
        # 现金流量表
        if "经营活动现金流量净额" in cashflow and cashflow["经营活动现金流量净额"]:
            self.set_anchor("经营现金流", cashflow["经营活动现金流量净额"][-1])
    
    def validate_chapter(self, chapter_num: int, chapter_content: str) -> List[str]:
        """验证章节数据是否与锚点一致"""
        errors = []
        chapter_data = self._extract_data(chapter_content)
        for key, value in chapter_data.items():
            anchor_value = self.get_anchor(key)
            if anchor_value is not None:
                if abs(value - anchor_value) / abs(anchor_value) > 0.01:  # 1%误差
                    errors.append(f"第{chapter_num}章{key}={value}，锚点={anchor_value}")
        return errors
    
    def fix_chapter(self, chapter_num: int, chapter_content: str) -> Tuple[str, List[str]]:
        """修复章节数据（替换为锚点值）"""
        fixes = []
        chapter_data = self._extract_data(chapter_content)
        for key, value in chapter_data.items():
            anchor_value = self.get_anchor(key)
            if anchor_value is not None:
                if abs(value - anchor_value) / abs(anchor_value) > 0.01:
                    chapter_content = chapter_content.replace(str(value), str(anchor_value))
                    fixes.append(f"{key}: {value} -> {anchor_value}")
        return chapter_content, fixes
```

## 集成点

```python
# Gate 2: 数据收集后初始化锚点
data_anchor = DataAnchor()
data_anchor.init_from_wind_data(wind_data)

# Gate 4: 审查修复循环中使用锚点
for chapter_num, content in chapters.items():
    errors = data_anchor.validate_chapter(chapter_num, content)
    if errors:
        fixed_content, fixes = data_anchor.fix_chapter(chapter_num, content)
        chapters[chapter_num] = fixed_content
```

## 关键教训

1. **锚点必须来自Wind数据**：不能使用LLM生成的数据作为锚点
2. **锚点必须在Gate 2初始化**：确保后续Gate有统一数据源
3. **替换时保留上下文**：不能简单替换数字，需要考虑上下文（如"35.2亿"vs"35.0亿"）
4. **当前实现的局限**：简单的字符串替换可能误替换其他数字，需要更精确的提取逻辑

## 待改进

- [ ] 使用正则表达式精确提取数据（带上下文）
- [ ] 支持多单位（亿元、万元、港元）
- [ ] 支持百分比数据（如毛利率、增长率）
- [ ] 支持跨年数据（2023/2024/2025年各自独立锚点）
