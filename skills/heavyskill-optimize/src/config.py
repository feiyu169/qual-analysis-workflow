"""HeavySkill 优化方案 V3 - 配置系统"""

from typing import List
import yaml

from .models import Severity
from .validator import (
    ConclusionValidatorConfig,
    PVetoConfig,
    ThresholdRuleConfig,
    WeightedScoreConfig,
    DomainCoverageConfig
)


def validate_config(config: ConclusionValidatorConfig) -> List[str]:
    """验证配置有效性"""
    errors = []
    
    # 置信度阈值
    if config.confidence_threshold < 0 or config.confidence_threshold > 1:
        errors.append("confidence_threshold 必须在 0-1 之间")
    
    # P0 否决配置
    if config.p0_veto.min_count < 1:
        errors.append("p0_veto.min_count 必须 >= 1")
    
    # 领域覆盖率
    if config.domain_coverage.min_coverage > 1:
        errors.append("domain_coverage.min_coverage 不能 > 1")
    
    # 阈值配置
    for severity, threshold in config.threshold_rule.thresholds.items():
        if threshold < 1:
            errors.append(f"threshold_rule.thresholds[{severity.value}] 必须 >= 1")
    
    # 权重配置
    for severity, weight in config.weighted_score.weights.items():
        if weight < 0:
            errors.append(f"weighted_score.weights[{severity.value}] 必须 >= 0")
    
    return errors


def load_config_from_yaml(yaml_path: str) -> ConclusionValidatorConfig:
    """从 YAML 文件加载配置"""
    with open(yaml_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    
    config = ConclusionValidatorConfig()
    
    # 基础配置
    config.enabled = data.get('enabled', True)
    config.shadow_mode = data.get('shadow_mode', False)
    config.fallback_to_llm = data.get('fallback_to_llm', True)
    config.human_review_queue = data.get('human_review_queue', True)
    config.confidence_threshold = data.get('confidence_threshold', 0.8)
    
    # P0 否决配置
    if 'p0_veto' in data:
        p0_data = data['p0_veto']
        config.p0_veto = PVetoConfig(
            enabled=p0_data.get('enabled', True),
            min_count=p0_data.get('min_count', 1),
            min_confidence=p0_data.get('min_confidence', 0.8)
        )
    
    # 阈值规则配置
    if 'threshold_rule' in data:
        tr_data = data['threshold_rule']
        thresholds = {}
        for k, v in tr_data.get('thresholds', {}).items():
            thresholds[Severity.from_str(k)] = v
        config.threshold_rule = ThresholdRuleConfig(
            enabled=tr_data.get('enabled', True),
            thresholds=thresholds
        )
    
    # 加权评分配置
    if 'weighted_score' in data:
        ws_data = data['weighted_score']
        weights = {}
        for k, v in ws_data.get('weights', {}).items():
            weights[Severity.from_str(k)] = v
        config.weighted_score = WeightedScoreConfig(
            enabled=ws_data.get('enabled', True),
            weights=weights,
            reject_threshold=ws_data.get('reject_threshold', 15.0),
            warn_threshold=ws_data.get('warn_threshold', 8.0)
        )
    
    # 领域覆盖率配置
    if 'domain_coverage' in data:
        dc_data = data['domain_coverage']
        config.domain_coverage = DomainCoverageConfig(
            enabled=dc_data.get('enabled', True),
            required_domains=dc_data.get('required_domains', ["安全", "架构", "性能"]),
            min_coverage=dc_data.get('min_coverage', 0.6)
        )
    
    # 验证配置
    errors = validate_config(config)
    if errors:
        raise ValueError(f"配置验证失败: {errors}")
    
    return config
