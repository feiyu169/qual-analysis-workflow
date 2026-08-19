"""
交付后健康工具 - V3.0 方案
1. check_deployment: 部署检查
2. setup_monitoring: 监控告警
"""

import os
import json
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict

import structlog
logger = structlog.get_logger()


@dataclass
class DeploymentCheckResult:
    """部署检查结果"""
    environment: str
    config_check: Dict
    dependency_check: Dict
    security_check: Dict
    rollback_check: Dict
    all_passed: bool
    recommendations: List[str]
    
    def to_dict(self) -> dict:
        return {
            "environment": self.environment,
            "config_check": self.config_check,
            "dependency_check": self.dependency_check,
            "security_check": self.security_check,
            "rollback_check": self.rollback_check,
            "all_passed": self.all_passed,
            "recommendations": self.recommendations,
        }


@dataclass
class MonitoringSetup:
    """监控设置结果"""
    health_endpoint: Dict
    performance_monitor: Dict
    error_alerts: Dict
    feedback_collector: Dict
    all_configured: bool
    
    def to_dict(self) -> dict:
        return {
            "health_endpoint": self.health_endpoint,
            "performance_monitor": self.performance_monitor,
            "error_alerts": self.error_alerts,
            "feedback_collector": self.feedback_collector,
            "all_configured": self.all_configured,
        }


class DeploymentChecker:
    """部署检查器"""
    
    # 环境配置要求
    ENV_REQUIREMENTS = {
        "dev": {
            "required_vars": [],
            "optional_vars": ["DEBUG", "LOG_LEVEL"],
            "security_level": "low",
        },
        "staging": {
            "required_vars": ["DATABASE_URL", "SECRET_KEY"],
            "optional_vars": ["DEBUG"],
            "security_level": "medium",
        },
        "prod": {
            "required_vars": ["DATABASE_URL", "SECRET_KEY", "ALLOWED_HOSTS"],
            "optional_vars": [],
            "security_level": "high",
        },
    }
    
    def check(self, config: Dict, environment: str) -> DeploymentCheckResult:
        """
        执行部署检查
        
        Args:
            config: 部署配置
            environment: 环境（dev/staging/prod）
        
        Returns:
            DeploymentCheckResult: 检查结果
        """
        logger.info("checking_deployment", environment=environment)
        
        # 配置检查
        config_check = self._check_config(config, environment)
        
        # 依赖检查
        dependency_check = self._check_dependencies(config)
        
        # 安全检查
        security_check = self._check_security(config, environment)
        
        # 回滚预案检查
        rollback_check = self._check_rollback(config)
        
        # 生成建议
        recommendations = self._generate_recommendations(
            config_check, dependency_check, security_check, rollback_check
        )
        
        # 判断是否全部通过
        all_passed = all([
            config_check.get("passed", False),
            dependency_check.get("passed", False),
            security_check.get("passed", False),
            rollback_check.get("passed", False),
        ])
        
        result = DeploymentCheckResult(
            environment=environment,
            config_check=config_check,
            dependency_check=dependency_check,
            security_check=security_check,
            rollback_check=rollback_check,
            all_passed=all_passed,
            recommendations=recommendations,
        )
        
        logger.info(
            "deployment_checked",
            environment=environment,
            all_passed=all_passed
        )
        
        return result
    
    def _check_config(self, config: Dict, environment: str) -> Dict:
        """检查配置"""
        requirements = self.ENV_REQUIREMENTS.get(environment, {})
        missing_vars = []
        
        # 检查必需变量
        for var in requirements.get("required_vars", []):
            if var not in config:
                missing_vars.append(var)
        
        # 检查环境变量
        for var in requirements.get("required_vars", []):
            if var not in os.environ:
                missing_vars.append(f"{var} (环境变量)")
        
        passed = len(missing_vars) == 0
        
        return {
            "passed": passed,
            "missing_vars": missing_vars,
            "message": "配置检查通过" if passed else f"缺少配置: {', '.join(missing_vars)}",
        }
    
    def _check_dependencies(self, config: Dict) -> Dict:
        """检查依赖"""
        issues = []
        
        # 检查 requirements.txt
        if os.path.exists("requirements.txt"):
            with open("requirements.txt", "r", encoding="utf-8") as f:
                requirements = f.read()
                
                # 检查是否固定版本
                for line in requirements.split("\n"):
                    if line.strip() and "==" not in line and ">=" not in line:
                        issues.append(f"依赖未固定版本: {line}")
        
        # 检查 package.json
        if os.path.exists("package.json"):
            with open("package.json", "r", encoding="utf-8") as f:
                package = json.load(f)
                
                # 检查是否有 lock 文件
                if not os.path.exists("package-lock.json") and not os.path.exists("yarn.lock"):
                    issues.append("缺少 lock 文件")
        
        passed = len(issues) == 0
        
        return {
            "passed": passed,
            "issues": issues,
            "message": "依赖检查通过" if passed else f"发现 {len(issues)} 个问题",
        }
    
    def _check_security(self, config: Dict, environment: str) -> Dict:
        """检查安全"""
        issues = []
        requirements = self.ENV_REQUIREMENTS.get(environment, {})
        security_level = requirements.get("security_level", "low")
        
        # 检查 SECRET_KEY
        secret_key = config.get("SECRET_KEY") or os.environ.get("SECRET_KEY", "")
        if security_level in ["medium", "high"]:
            if not secret_key or len(secret_key) < 32:
                issues.append("SECRET_KEY 不安全")
        
        # 检查 DEBUG
        debug = config.get("DEBUG", "false").lower()
        if security_level == "high" and debug == "true":
            issues.append("生产环境不应开启 DEBUG")
        
        # 检查 ALLOWED_HOSTS
        if security_level == "high":
            allowed_hosts = config.get("ALLOWED_HOSTS", "")
            if not allowed_hosts or allowed_hosts == "*":
                issues.append("ALLOWED_HOSTS 配置不安全")
        
        passed = len(issues) == 0
        
        return {
            "passed": passed,
            "issues": issues,
            "message": "安全检查通过" if passed else f"发现 {len(issues)} 个安全问题",
        }
    
    def _check_rollback(self, config: Dict) -> Dict:
        """检查回滚预案"""
        issues = []
        
        # 检查是否有备份
        if not config.get("backup_enabled", False):
            issues.append("未启用备份")
        
        # 检查是否有回滚脚本
        if not os.path.exists("rollback.sh") and not os.path.exists("rollback.py"):
            issues.append("缺少回滚脚本")
        
        # 检查是否有版本标记
        if not config.get("version_tag"):
            issues.append("缺少版本标记")
        
        passed = len(issues) == 0
        
        return {
            "passed": passed,
            "issues": issues,
            "message": "回滚预案检查通过" if passed else f"发现 {len(issues)} 个问题",
        }
    
    def _generate_recommendations(self, *checks) -> List[str]:
        """生成建议"""
        recommendations = []
        
        for check in checks:
            if not check.get("passed", False):
                issues = check.get("issues", []) or check.get("missing_vars", [])
                for issue in issues:
                    recommendations.append(f"建议修复: {issue}")
        
        return recommendations


class MonitoringSetupper:
    """监控设置器"""
    
    def setup(self, config: Dict, environment: str) -> MonitoringSetup:
        """
        设置监控
        
        Args:
            config: 监控配置
            environment: 环境
        
        Returns:
            MonitoringSetup: 设置结果
        """
        logger.info("setting_up_monitoring", environment=environment)
        
        # 健康检查端点
        health_endpoint = self._setup_health_check(config)
        
        # 性能监控
        performance_monitor = self._setup_performance_monitor(config)
        
        # 错误告警
        error_alerts = self._setup_error_alerts(config)
        
        # 反馈收集
        feedback_collector = self._setup_feedback_collector(config)
        
        all_configured = all([
            health_endpoint.get("configured", False),
            performance_monitor.get("configured", False),
            error_alerts.get("configured", False),
            feedback_collector.get("configured", False),
        ])
        
        result = MonitoringSetup(
            health_endpoint=health_endpoint,
            performance_monitor=performance_monitor,
            error_alerts=error_alerts,
            feedback_collector=feedback_collector,
            all_configured=all_configured,
        )
        
        logger.info("monitoring_setup_complete", all_configured=all_configured)
        
        return result
    
    def _setup_health_check(self, config: Dict) -> Dict:
        """设置健康检查"""
        endpoint = config.get("health_endpoint", "/health")
        interval = config.get("health_interval", 30)
        
        return {
            "configured": True,
            "endpoint": endpoint,
            "interval": interval,
            "message": f"健康检查端点: {endpoint}, 间隔: {interval}s",
        }
    
    def _setup_performance_monitor(self, config: Dict) -> Dict:
        """设置性能监控"""
        metrics = config.get("metrics", ["latency", "error_rate", "throughput"])
        
        return {
            "configured": True,
            "metrics": metrics,
            "message": f"监控指标: {', '.join(metrics)}",
        }
    
    def _setup_error_alerts(self, config: Dict) -> Dict:
        """设置错误告警"""
        channels = config.get("alert_channels", ["email"])
        threshold = config.get("error_threshold", 10)
        
        return {
            "configured": True,
            "channels": channels,
            "threshold": threshold,
            "message": f"告警渠道: {', '.join(channels)}, 阈值: {threshold}",
        }
    
    def _setup_feedback_collector(self, config: Dict) -> Dict:
        """设置反馈收集"""
        enabled = config.get("feedback_enabled", True)
        
        return {
            "configured": enabled,
            "enabled": enabled,
            "message": "反馈收集已启用" if enabled else "反馈收集未启用",
        }


# 全局实例
deployment_checker = DeploymentChecker()
monitoring_setupper = MonitoringSetupper()


def check_deployment(config: Dict, environment: str) -> dict:
    """部署检查（对外接口）"""
    result = deployment_checker.check(config, environment)
    return result.to_dict()


def setup_monitoring(config: Dict, environment: str) -> dict:
    """监控设置（对外接口）"""
    result = monitoring_setupper.setup(config, environment)
    return result.to_dict()
