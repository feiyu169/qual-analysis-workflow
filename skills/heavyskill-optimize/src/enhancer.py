"""HeavySkill 增强模块 - 领域识别器 + 检查清单管理器 + Query 增强器"""

import os
import yaml
from typing import List, Dict, Optional
from pathlib import Path


class DomainClassifier:
    """领域识别器 - 自动识别待审查方案的领域"""
    
    DOMAIN_KEYWORDS = {
        "security": [
            "认证", "授权", "密码", "token", "jwt", "session", "登录", "权限",
            "加密", "解密", "hash", "bcrypt", "md5", "sha", "ssl", "tls", "https",
            "安全", "漏洞", "注入", "xss", "csrf", "攻击", "防护"
        ],
        "architecture": [
            "微服务", "服务", "架构", "模块", "组件", "依赖", "通信", "网关",
            "注册中心", "配置中心", "熔断", "降级", "限流", "负载均衡",
            "消息队列", "事件驱动", "ddd", "cqrs", "分层", "解耦"
        ],
        "performance": [
            "并发", "性能", "缓存", "队列", "异步", "负载", "优化",
            "连接池", "线程池", "内存", "cpu", "io", "响应时间", "吞吐量",
            "压力测试", "基准测试", "profiling", "调优"
        ],
        "database": [
            "数据库", "表", "索引", "查询", "sql", "事务", "备份", "恢复",
            "mysql", "postgresql", "mongodb", "redis", "elasticsearch",
            "主从", "分库分表", "读写分离", "迁移", "归档"
        ],
        "api": [
            "api", "接口", "rest", "graphql", "请求", "响应", "版本", "分页",
            "swagger", "openapi", "文档", "mock", "测试", "幂等", "限流"
        ],
        "deployment": [
            "部署", "容器", "docker", "kubernetes", "k8s", "ci/cd", "jenkins",
            "github actions", "gitlab ci", "helm", "istio", "prometheus",
            "监控", "日志", "告警", "灰度", "蓝绿", "金丝雀"
        ]
    }
    
    def classify(self, content: str) -> List[str]:
        """
        识别领域
        
        Args:
            content: 待审查方案的内容
            
        Returns:
            识别出的领域列表
        """
        domains = []
        content_lower = content.lower()
        
        for domain, keywords in self.DOMAIN_KEYWORDS.items():
            # 统计关键词出现次数
            match_count = sum(1 for kw in keywords if kw in content_lower)
            
            # 如果匹配到 2 个以上关键词，认为属于该领域
            if match_count >= 2:
                domains.append(domain)
        
        return domains if domains else ["general"]
    
    def get_primary_domain(self, content: str) -> str:
        """获取主要领域"""
        domains = self.classify(content)
        return domains[0] if domains else "general"


class ChecklistManager:
    """检查清单管理器 - 管理各领域的检查清单"""
    
    DEFAULT_CHECKLISTS_DIR = os.path.expanduser(
        "~/.hermes/skills/heavyskill-optimize/checklists"
    )
    
    # 内置检查清单（当 YAML 文件不存在时使用）
    BUILTIN_CHECKLISTS = {
        "security": {
            "name": "安全审查清单",
            "items": [
                {"id": "S-01", "question": "是否存在SQL注入风险？", "severity": "P0", "category": "输入验证"},
                {"id": "S-02", "question": "是否存在XSS攻击风险？", "severity": "P0", "category": "输入验证"},
                {"id": "S-03", "question": "是否有CSRF防护机制？", "severity": "P1", "category": "输入验证"},
                {"id": "S-04", "question": "是否有密钥硬编码问题？", "severity": "P0", "category": "配置安全"},
                {"id": "S-05", "question": "会话管理是否安全？", "severity": "P1", "category": "认证授权"},
                {"id": "S-06", "question": "密码是否加密存储？", "severity": "P0", "category": "数据保护"},
                {"id": "S-07", "question": "是否有输入验证？", "severity": "P1", "category": "输入验证"},
                {"id": "S-08", "question": "是否有输出转义？", "severity": "P1", "category": "输入验证"},
                {"id": "S-09", "question": "是否有权限检查？", "severity": "P1", "category": "认证授权"},
                {"id": "S-10", "question": "是否有日志审计？", "severity": "P2", "category": "可观测性"}
            ]
        },
        "architecture": {
            "name": "架构审查清单",
            "items": [
                {"id": "A-01", "question": "是否存在循环依赖？", "severity": "P0", "category": "依赖管理"},
                {"id": "A-02", "question": "是否有服务发现机制？", "severity": "P1", "category": "服务治理"},
                {"id": "A-03", "question": "是否有熔断机制？", "severity": "P1", "category": "服务治理"},
                {"id": "A-04", "question": "是否有日志体系？", "severity": "P1", "category": "可观测性"},
                {"id": "A-05", "question": "是否有配置管理？", "severity": "P1", "category": "配置管理"},
                {"id": "A-06", "question": "模块职责是否清晰？", "severity": "P1", "category": "模块设计"},
                {"id": "A-07", "question": "是否有监控告警？", "severity": "P1", "category": "可观测性"},
                {"id": "A-08", "question": "是否有容错设计？", "severity": "P1", "category": "可靠性"},
                {"id": "A-09", "question": "是否有扩展性设计？", "severity": "P2", "category": "模块设计"},
                {"id": "A-10", "question": "是否有文档说明？", "severity": "P2", "category": "文档"}
            ]
        },
        "performance": {
            "name": "性能审查清单",
            "items": [
                {"id": "P-01", "question": "是否有连接池？", "severity": "P1", "category": "数据库性能"},
                {"id": "P-02", "question": "是否有缓存策略？", "severity": "P1", "category": "缓存"},
                {"id": "P-03", "question": "是否有异步处理？", "severity": "P1", "category": "并发"},
                {"id": "P-04", "question": "是否有负载均衡？", "severity": "P1", "category": "分布式"},
                {"id": "P-05", "question": "有限流机制？", "severity": "P1", "category": "流量控制"},
                {"id": "P-06", "question": "是否有数据库优化？", "severity": "P1", "category": "数据库性能"},
                {"id": "P-07", "question": "是否有代码优化？", "severity": "P2", "category": "代码质量"},
                {"id": "P-08", "question": "是否有资源限制？", "severity": "P1", "category": "资源管理"},
                {"id": "P-09", "question": "是否有性能监控？", "severity": "P2", "category": "可观测性"},
                {"id": "P-10", "question": "是否有压力测试？", "severity": "P2", "category": "测试"}
            ]
        },
        "database": {
            "name": "数据库审查清单",
            "items": [
                {"id": "D-01", "question": "索引设计是否合理？", "severity": "P1", "category": "索引"},
                {"id": "D-02", "question": "是否有数据归档策略？", "severity": "P2", "category": "数据管理"},
                {"id": "D-03", "question": "是否有读写分离？", "severity": "P1", "category": "架构"},
                {"id": "D-04", "question": "是否有备份恢复机制？", "severity": "P1", "category": "可靠性"},
                {"id": "D-05", "question": "是否有迁移策略？", "severity": "P2", "category": "运维"},
                {"id": "D-06", "question": "是否有慢查询优化？", "severity": "P1", "category": "性能"},
                {"id": "D-07", "question": "是否有连接池配置？", "severity": "P1", "category": "性能"},
                {"id": "D-08", "question": "是否有事务管理？", "severity": "P1", "category": "可靠性"},
                {"id": "D-09", "question": "是否有数据加密？", "severity": "P1", "category": "安全"},
                {"id": "D-10", "question": "是否有监控告警？", "severity": "P2", "category": "可观测性"}
            ]
        },
        "api": {
            "name": "API 审查清单",
            "items": [
                {"id": "API-01", "question": "是否有版本控制？", "severity": "P1", "category": "版本管理"},
                {"id": "API-02", "question": "是否有分页设计？", "severity": "P1", "category": "数据量"},
                {"id": "API-03", "question": "是否有错误处理？", "severity": "P1", "category": "错误处理"},
                {"id": "API-04", "question": "是否有幂等性设计？", "severity": "P1", "category": "可靠性"},
                {"id": "API-05", "question": "有限流机制？", "severity": "P1", "category": "流量控制"},
                {"id": "API-06", "question": "是否有API文档？", "severity": "P2", "category": "文档"},
                {"id": "API-07", "question": "是否有参数验证？", "severity": "P1", "category": "输入验证"},
                {"id": "API-08", "question": "是否有响应格式规范？", "severity": "P2", "category": "规范"},
                {"id": "API-09", "question": "是否有认证授权？", "severity": "P1", "category": "安全"},
                {"id": "API-10", "question": "是否有日志记录？", "severity": "P2", "category": "可观测性"}
            ]
        },
        "deployment": {
            "name": "部署审查清单",
            "items": [
                {"id": "DEP-01", "question": "是否有健康检查？", "severity": "P1", "category": "可靠性"},
                {"id": "DEP-02", "question": "是否有滚动更新？", "severity": "P1", "category": "发布策略"},
                {"id": "DEP-03", "question": "是否有资源限制？", "severity": "P1", "category": "资源管理"},
                {"id": "DEP-04", "question": "是否有日志收集？", "severity": "P1", "category": "可观测性"},
                {"id": "DEP-05", "question": "是否有监控告警？", "severity": "P1", "category": "可观测性"},
                {"id": "DEP-06", "question": "是否有回滚机制？", "severity": "P1", "category": "发布策略"},
                {"id": "DEP-07", "question": "是否有配置管理？", "severity": "P1", "category": "配置"},
                {"id": "DEP-08", "question": "是否有密钥管理？", "severity": "P1", "category": "安全"},
                {"id": "DEP-09", "question": "是否有CI/CD？", "severity": "P2", "category": "自动化"},
                {"id": "DEP-10", "question": "是否有灾备方案？", "severity": "P2", "category": "可靠性"}
            ]
        },
        "general": {
            "name": "通用审查清单",
            "items": [
                {"id": "G-01", "question": "需求是否完整？", "severity": "P1", "category": "需求"},
                {"id": "G-02", "question": "设计是否合理？", "severity": "P1", "category": "设计"},
                {"id": "G-03", "question": "是否有风险遗漏？", "severity": "P1", "category": "风险"},
                {"id": "G-04", "question": "是否有实施计划？", "severity": "P2", "category": "计划"},
                {"id": "G-05", "question": "是否有测试方案？", "severity": "P1", "category": "测试"}
            ]
        }
    }
    
    def __init__(self, checklists_dir: Optional[str] = None):
        self.checklists_dir = checklists_dir or self.DEFAULT_CHECKLISTS_DIR
        self._checklists = None
    
    def _load_checklists(self) -> Dict:
        """加载检查清单（从 YAML 文件或内置）"""
        if self._checklists is not None:
            return self._checklists
        
        self._checklists = {}
        
        # 尝试从 YAML 文件加载
        if os.path.exists(self.checklists_dir):
            for filename in os.listdir(self.checklists_dir):
                if filename.endswith('.yaml') or filename.endswith('.yml'):
                    filepath = os.path.join(self.checklists_dir, filename)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            data = yaml.safe_load(f)
                            if data and 'domain' in data:
                                self._checklists[data['domain']] = data
                    except Exception as e:
                        print(f"Warning: Failed to load {filepath}: {e}")
        
        # 使用内置检查清单补充
        for domain, checklist in self.BUILTIN_CHECKLISTS.items():
            if domain not in self._checklists:
                self._checklists[domain] = checklist
        
        return self._checklists
    
    def get_checklist(self, domains: List[str]) -> Dict:
        """
        获取检查清单
        
        Args:
            domains: 领域列表
            
        Returns:
            合并后的检查清单
        """
        checklists = self._load_checklists()
        
        merged = {
            "name": "综合审查清单",
            "items": [],
            "domains": domains
        }
        
        seen_ids = set()
        for domain in domains:
            if domain in checklists:
                for item in checklists[domain].get("items", []):
                    if item["id"] not in seen_ids:
                        merged["items"].append(item)
                        seen_ids.add(item["id"])
        
        return merged
    
    def format_checklist(self, checklist: Dict) -> str:
        """
        格式化检查清单为文本
        
        Args:
            checklist: 检查清单
            
        Returns:
            格式化后的文本
        """
        lines = [f"# {checklist['name']}\n"]
        
        # 按严重程度分组
        p0_items = [i for i in checklist["items"] if i.get("severity") == "P0"]
        p1_items = [i for i in checklist["items"] if i.get("severity") == "P1"]
        p2_items = [i for i in checklist["items"] if i.get("severity") == "P2"]
        
        if p0_items:
            lines.append("## P0 - 致命问题（必须检查）")
            for item in p0_items:
                lines.append(f"- [{item['id']}] {item['question']}")
            lines.append("")
        
        if p1_items:
            lines.append("## P1 - 重大问题（应该检查）")
            for item in p1_items:
                lines.append(f"- [{item['id']}] {item['question']}")
            lines.append("")
        
        if p2_items:
            lines.append("## P2 - 一般问题（建议检查）")
            for item in p2_items:
                lines.append(f"- [{item['id']}] {item['question']}")
            lines.append("")
        
        return "\n".join(lines)


class QueryEnhancer:
    """Query 增强器 - 将检查清单注入到 HeavySkill 的 query 中"""
    
    def __init__(self, checklists_dir: Optional[str] = None):
        self.classifier = DomainClassifier()
        self.checklist_manager = ChecklistManager(checklists_dir)
    
    def enhance(self, original_query: str, file_content: str) -> str:
        """
        增强 query
        
        Args:
            original_query: 原始查询
            file_content: 待审查文件内容
            
        Returns:
            增强后的查询
        """
        # 1. 识别领域
        domains = self.classifier.classify(file_content)
        
        # 2. 获取检查清单
        checklist = self.checklist_manager.get_checklist(domains)
        checklist_text = self.checklist_manager.format_checklist(checklist)
        
        # 3. 构建增强 query
        enhanced_query = f"""{original_query}

---

## 专项检查清单（必须回答）

请务必检查以下问题，对每个检查项给出评估：

{checklist_text}

## 输出格式要求

1. 对每个检查项，给出以下评估之一：
   - ✅ 通过：方案中已正确处理
   - ❌ 不通过：方案中存在此问题
   - ⚠️ 部分通过：方案中部分处理
   - ➖ 不适用：此检查项不适用于本方案

2. 对不通过的项，必须说明：
   - 具体问题是什么
   - 在方案的哪个位置
   - 如何修复

3. 最后给出总体结论（通过/附意见通过/不通过）
"""
        
        return enhanced_query
    
    def enhance_from_file(self, original_query: str, file_path: str) -> str:
        """
        从文件增强 query
        
        Args:
            original_query: 原始查询
            file_path: 待审查文件路径
            
        Returns:
            增强后的查询
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            file_content = f.read()
        
        return self.enhance(original_query, file_content)
