"""HeavySkill 优化方案 V3 - 检查清单解析器"""

import re
import json
import logging
from typing import List, Dict, Optional

from .models import Severity, Issue

logger = logging.getLogger(__name__)


class ChecklistResultParser:
    """将检查清单输出解析为 Issue 对象"""
    
    # 严重级别映射
    SEVERITY_MAPPING = {
        # 英文
        "critical": Severity.P0, "blocker": Severity.P0, "fatal": Severity.P0,
        "major": Severity.P1, "high": Severity.P1, "important": Severity.P1,
        "minor": Severity.P2, "medium": Severity.P2, "normal": Severity.P2,
        "info": Severity.P3, "low": Severity.P3, "suggestion": Severity.P3,
        # 中文
        "致命": Severity.P0, "阻断": Severity.P0, "严重": Severity.P0,
        "重大": Severity.P1, "重要": Severity.P1, "高": Severity.P1,
        "一般": Severity.P2, "中": Severity.P2, "中等": Severity.P2,
        "建议": Severity.P3, "低": Severity.P3, "优化": Severity.P3,
        # 符号
        "❌": Severity.P0, "⚠️": Severity.P1, "⚡": Severity.P2, "💡": Severity.P3,
    }
    
    # 领域映射
    DOMAIN_MAPPING = {
        "security": "安全", "安全": "安全", "auth": "安全", "认证": "安全",
        "architecture": "架构", "架构": "架构", "design": "架构", "设计": "架构",
        "performance": "性能", "性能": "性能", "perf": "性能",
        "功能": "功能", "function": "功能", "feature": "功能",
    }
    
    def parse_markdown_table(self, markdown: str) -> List[Issue]:
        """解析 Markdown 表格格式的检查清单结果"""
        issues = []
        lines = markdown.strip().split('\n')
        
        # 找到表头
        header_idx = -1
        for i, line in enumerate(lines):
            if '|' in line and ('ID' in line.upper() or '检查' in line):
                header_idx = i
                break
        
        if header_idx < 0:
            return []
        
        # 解析数据行
        for line in lines[header_idx + 2:]:  # 跳过表头和分隔线
            if '|' not in line or '---' in line:
                continue
            
            cols = [c.strip() for c in line.split('|')]
            if len(cols) < 5:
                continue
            
            # 提取字段
            check_id = cols[1] if len(cols) > 1 else ""
            title = cols[2] if len(cols) > 2 else ""
            result = cols[3] if len(cols) > 3 else ""
            severity_str = cols[4] if len(cols) > 4 else ""
            description = cols[5] if len(cols) > 5 else ""
            suggestion = cols[6] if len(cols) > 6 else ""
            
            # 解析严重级别
            severity = Severity.P2  # 默认
            for key, sev in self.SEVERITY_MAPPING.items():
                if key in severity_str.lower():
                    severity = sev
                    break
            
            # 解析领域
            domain = "其他"
            for key, dom in self.DOMAIN_MAPPING.items():
                if key in title.lower() or key in description.lower():
                    domain = dom
                    break
            
            # 只有问题才创建 Issue
            if result and any(kw in result for kw in ["❌", "FAIL", "失败", "不通过"]):
                issue = Issue(
                    id=check_id,
                    title=title,
                    severity=severity,
                    domain=domain,
                    description=description,
                    suggestion=suggestion,
                    confidence=0.9,  # 检查清单结果置信度较高
                    source="checklist"
                )
                issues.append(issue)
        
        return issues
    
    def parse_json(self, json_str: str) -> List[Issue]:
        """解析 JSON 格式的检查清单结果"""
        try:
            data = json.loads(json_str)
            if isinstance(data, list):
                return [self._dict_to_issue(item) for item in data]
            elif isinstance(data, dict) and 'issues' in data:
                return [self._dict_to_issue(item) for item in data['issues']]
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.debug(f"JSON 解析失败: {e}")
        return []
    
    def _dict_to_issue(self, d: Dict) -> Issue:
        """将字典转换为 Issue"""
        return Issue(
            id=d.get('id', ''),
            title=d.get('title', ''),
            severity=Severity.from_str(d.get('severity', 'P2')),
            domain=d.get('domain', '其他'),
            description=d.get('description', ''),
            suggestion=d.get('suggestion', ''),
            confidence=d.get('confidence', 0.8),
            source=d.get('source', 'checklist')
        )
    
    def parse_plaintext(self, text: str) -> List[Issue]:
        """解析纯文本格式的检查清单结果"""
        issues = []
        lines = text.strip().split('\n')
        
        current_issue = None
        for line in lines:
            # 检测问题标题（如 "1. SQL注入风险"）
            match = re.match(r'^\d+\.\s*(.+)', line)
            if match:
                if current_issue:
                    issues.append(current_issue)
                
                title = match.group(1)
                # 从标题推断严重级别和领域
                severity = self._infer_severity(title)
                domain = self._infer_domain(title)
                
                current_issue = Issue(
                    id=f"issue-{len(issues) + 1}",
                    title=title,
                    severity=severity,
                    domain=domain,
                    description="",
                    suggestion="",
                    confidence=0.7,  # 纯文本解析置信度较低
                    source="plaintext"
                )
            elif current_issue and line.strip():
                # 累积描述
                if not current_issue.description:
                    current_issue.description = line.strip()
                else:
                    current_issue.description += " " + line.strip()
        
        if current_issue:
            issues.append(current_issue)
        
        return issues
    
    def _infer_severity(self, text: str) -> Severity:
        """从文本推断严重级别"""
        text_lower = text.lower()
        for key, sev in self.SEVERITY_MAPPING.items():
            if key in text_lower:
                return sev
        return Severity.P2
    
    def _infer_domain(self, text: str) -> str:
        """从文本推断领域"""
        text_lower = text.lower()
        for key, dom in self.DOMAIN_MAPPING.items():
            if key in text_lower:
                return dom
        return "其他"
    
    def parse(self, content: str) -> List[Issue]:
        """统一入口：解析各种格式"""
        # 尝试 JSON
        if content.strip().startswith('{') or content.strip().startswith('['):
            issues = self.parse_json(content)
            if issues:
                return issues
        
        # 尝试 Markdown 表格
        if '|' in content:
            issues = self.parse_markdown_table(content)
            if issues:
                return issues
        
        # 回退到纯文本
        return self.parse_plaintext(content)
