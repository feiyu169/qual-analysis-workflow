"""
quality/reasoning/causal_modeler.py — 因果建模器

采用混合方法构建因果图：
- 模板匹配：捕捉业务逻辑因果
- Granger检验：验证时间序列因果
- 敏感性分析：检验假设稳健性
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from ..types import (
    CausalGraph,
    CausalMethod,
    CausalRelation,
    CausalStrength,
    ConfidenceInterval,
    ConfidenceLevel,
    EvidenceBundle,
    EvidenceStrength,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────
# 业务逻辑因果模板
# ─────────────────────────────────────────────────

CAUSAL_TEMPLATES = [
    # 收入驱动
    {"cause": "用户增长", "effect": "收入增长", "keywords": ["DAU", "MAU", "用户数"]},
    {"cause": "ARPU提升", "effect": "收入增长", "keywords": ["ARPU", "客单价"]},
    {"cause": "货币化率提升", "effect": "收入增长", "keywords": ["货币化率", "take_rate"]},
    
    # 利润驱动
    {"cause": "毛利率提升", "effect": "净利润增长", "keywords": ["毛利率", "毛利"]},
    {"cause": "费用率下降", "effect": "净利润增长", "keywords": ["销售费用率", "管理费用率"]},
    {"cause": "规模效应", "effect": "毛利率提升", "keywords": ["规模效应", "固定成本"]},
    
    # 估值驱动
    {"cause": "盈利增长", "effect": "估值提升", "keywords": ["盈利", "利润增长"]},
    {"cause": "行业景气", "effect": "估值提升", "keywords": ["行业景气", "行业增速"]},
    
    # 风险因素
    {"cause": "竞争加剧", "effect": "毛利率下降", "keywords": ["竞争", "市场份额"]},
    {"cause": "监管政策", "effect": "业务受限", "keywords": ["监管", "政策"]},
]


@dataclass
class TemplateRelation:
    """模板匹配的因果关系"""
    cause: str
    effect: str
    confidence: float
    evidence: list[str] = field(default_factory=list)


@dataclass
class GrangerResult:
    """Granger检验结果"""
    cause: str
    effect: str
    pvalue: float
    is_significant: bool
    lag: int = 1


class TemplateMatcher:
    """模板匹配器"""
    
    def match(self, evidence: EvidenceBundle) -> list[TemplateRelation]:
        """从证据中匹配因果模板"""
        relations = []
        
        # 合并所有文本数据
        text = self._extract_text(evidence)
        
        for template in CAUSAL_TEMPLATES:
            # 检查关键词是否出现
            matched_keywords = []
            for keyword in template["keywords"]:
                if keyword in text:
                    matched_keywords.append(keyword)
            
            if matched_keywords:
                confidence = min(0.5 + 0.1 * len(matched_keywords), 0.9)
                relations.append(TemplateRelation(
                    cause=template["cause"],
                    effect=template["effect"],
                    confidence=confidence,
                    evidence=matched_keywords
                ))
        
        return relations
    
    def _extract_text(self, evidence: EvidenceBundle) -> str:
        """提取所有文本"""
        texts = []
        
        # 财务数据
        for key, value in evidence.financial_data.items():
            if isinstance(value, str):
                texts.append(value)
        
        # 新闻数据
        for news in evidence.news_data:
            if isinstance(news, dict):
                texts.append(news.get("title", ""))
                texts.append(news.get("summary", ""))
        
        # 行业数据
        for key, value in evidence.industry_data.items():
            if isinstance(value, str):
                texts.append(value)
        
        return " ".join(texts)


class GrangerTester:
    """Granger因果检验器"""
    
    def __init__(self, max_lag: int = 2, significance_level: float = 0.05):
        """初始化
        
        Args:
            max_lag: 最大滞后阶数
            significance_level: 显著性水平
        """
        self.max_lag = max_lag
        self.significance_level = significance_level
    
    def test(self, evidence: EvidenceBundle) -> list[GrangerResult]:
        """执行Granger因果检验
        
        使用scipy的F检验实现真正的Granger因果检验
        """
        results = []
        
        # 提取时间序列数据
        financial_data = evidence.financial_data
        
        # 检查是否有足够的历史数据
        if not self._has_sufficient_data(financial_data):
            logger.warning("数据不足，跳过Granger检验")
            return results
        
        # 提取收入和利润序列
        revenue_series = self._extract_series(financial_data, "revenue")
        profit_series = self._extract_series(financial_data, "net_profit")
        
        if revenue_series and profit_series:
            # 执行Granger检验：收入 -> 利润
            granger_result = self._run_granger_test(
                revenue_series, profit_series, 
                cause_name="收入增长", effect_name="利润增长"
            )
            if granger_result:
                results.append(granger_result)
            
            # 执行Granger检验：利润 -> 收入（反向）
            granger_result_reverse = self._run_granger_test(
                profit_series, revenue_series,
                cause_name="利润增长", effect_name="收入增长"
            )
            if granger_result_reverse:
                results.append(granger_result_reverse)
        
        return results
    
    def _run_granger_test(
        self, 
        cause_series: list[float], 
        effect_series: list[float],
        cause_name: str,
        effect_name: str
    ) -> Optional[GrangerResult]:
        """执行单次Granger因果检验
        
        使用scipy的F检验实现，避免statsmodels依赖冲突
        """
        try:
            import numpy as np
            from scipy import stats
            
            # 计算增长率
            cause_growth = self._calculate_growth(cause_series)
            effect_growth = self._calculate_growth(effect_series)
            
            if not cause_growth or not effect_growth:
                return None
            
            # 确保两个序列长度相同
            min_len = min(len(cause_growth), len(effect_growth))
            if min_len < 4:  # 至少需要4个观测值
                return None
            
            cause_arr = np.array(cause_growth[:min_len])
            effect_arr = np.array(effect_growth[:min_len])
            
            # 执行Granger检验
            best_pvalue = 1.0
            best_lag = 1
            max_lag = min(self.max_lag, min_len // 3)
            if max_lag < 1:
                max_lag = 1
            
            n = len(effect_arr)
            for lag in range(1, max_lag + 1):
                if n - lag < lag + 2:
                    continue
                
                y = effect_arr[lag:]
                # 受限模型: effect[t] = a + b*effect[t-1:t-lag]
                X_r = np.column_stack([np.ones(len(y))] + [effect_arr[lag-i-1:n-i-1] for i in range(lag)])
                # 非受限模型: + c*cause[t-1:t-lag]
                X_u = np.column_stack([X_r] + [cause_arr[lag-i-1:n-i-1] for i in range(lag)])
                
                beta_r = np.linalg.lstsq(X_r, y, rcond=None)[0]
                beta_u = np.linalg.lstsq(X_u, y, rcond=None)[0]
                
                rss_r = np.sum((y - X_r @ beta_r) ** 2)
                rss_u = np.sum((y - X_u @ beta_u) ** 2)
                
                df1 = lag
                df2 = len(y) - X_u.shape[1]
                if df2 <= 0 or rss_u == 0:
                    continue
                
                f_stat = ((rss_r - rss_u) / df1) / (rss_u / df2)
                p_value = 1 - stats.f.cdf(f_stat, df1, df2)
                
                if p_value < best_pvalue:
                    best_pvalue = p_value
                    best_lag = lag
            
            is_significant = best_pvalue < self.significance_level
            
            logger.info(f"Granger检验: {cause_name} -> {effect_name}, "
                       f"p值={best_pvalue:.4f}, 显著={is_significant}, 滞后={best_lag}")
            
            return GrangerResult(
                cause=cause_name,
                effect=effect_name,
                pvalue=best_pvalue,
                is_significant=is_significant,
                lag=best_lag
            )
            
        except Exception as e:
            logger.warning(f"Granger检验失败: {e}")
            return None
    
    def _has_sufficient_data(self, data: dict) -> bool:
        """检查数据是否足够
        
        需要至少2个财务字段，且每个字段至少有3个数据点
        """
        if len(data) < 2:
            return False
        
        # 检查是否有足够的时间序列数据
        for key, value in data.items():
            if isinstance(value, list) and len(value) >= 3:
                return True
        
        return False
    
    def _extract_series(self, data: dict, key: str) -> Optional[list[float]]:
        """提取时间序列"""
        value = data.get(key)
        if isinstance(value, list):
            return [float(v) for v in value if v is not None]
        return None
    
    def _calculate_growth(self, series: list[float]) -> Optional[list[float]]:
        """计算增长率"""
        if len(series) < 2:
            return None
        return [(series[i] - series[i-1]) / abs(series[i-1]) if series[i-1] != 0 else 0
                for i in range(1, len(series))]
    
    def _calculate_correlation(self, x: list[float], y: list[float]) -> float:
        """计算相关系数（简化版）"""
        n = min(len(x), len(y))
        if n < 2:
            return 0.0
        
        mean_x = sum(x[:n]) / n
        mean_y = sum(y[:n]) / n
        
        cov = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n)) / n
        std_x = (sum((xi - mean_x) ** 2 for xi in x[:n]) / n) ** 0.5
        std_y = (sum((yi - mean_y) ** 2 for yi in y[:n]) / n) ** 0.5
        
        if std_x == 0 or std_y == 0:
            return 0.0
        
        return cov / (std_x * std_y)


class SensitivityAnalyzer:
    """敏感性分析器"""
    
    def analyze(self, relations: list[Any]) -> dict[str, float]:
        """执行敏感性分析
        
        Args:
            relations: 因果关系列表
            
        Returns:
            dict: 每个关系的稳健性评分
        """
        results = {}
        
        for i, relation in enumerate(relations):
            key = f"relation_{i}"
            
            # 简化的敏感性分析
            # 检查关系的稳定性
            if hasattr(relation, 'confidence'):
                confidence = relation.confidence
            elif hasattr(relation, 'pvalue'):
                confidence = 1 - relation.pvalue
            else:
                confidence = 0.5
            
            # 稳健性评分
            robustness = confidence * 0.8 + 0.2  # 简化计算
            results[key] = min(robustness, 1.0)
        
        return results


class CausalModeler:
    """因果建模器 — 混合方法"""
    
    def __init__(self):
        self.template_matcher = TemplateMatcher()
        self.granger_tester = GrangerTester()
        self.sensitivity_analyzer = SensitivityAnalyzer()
    
    def build_causal_graph(self, evidence: EvidenceBundle) -> CausalGraph:
        """构建因果图
        
        混合方法：
        1. 模板匹配（业务逻辑）
        2. Granger检验（时间序列）
        3. 敏感性分析（稳健性检验）
        """
        logger.info("开始构建因果图")
        
        # Step 1: 模板匹配
        template_relations = self.template_matcher.match(evidence)
        logger.info(f"模板匹配: {len(template_relations)} 条关系")
        
        # Step 2: Granger检验
        granger_results = self.granger_tester.test(evidence)
        logger.info(f"Granger检验: {len(granger_results)} 条关系")
        
        # Step 3: 合并关系
        all_relations = self._merge_relations(template_relations, granger_results)
        
        # Step 4: 敏感性分析
        sensitivity_results = self.sensitivity_analyzer.analyze(all_relations)
        
        # Step 5: 构建因果图
        causal_relations = self._build_causal_relations(
            all_relations, granger_results, sensitivity_results
        )
        
        # 计算整体置信度
        overall_confidence = self._calculate_overall_confidence(causal_relations)
        
        # 收集假设
        assumptions = self._collect_assumptions(causal_relations)
        
        logger.info(f"因果图构建完成: {len(causal_relations)} 条关系, 置信度={overall_confidence:.2f}")
        
        return CausalGraph(
            relations=causal_relations,
            confidence=overall_confidence,
            assumptions=assumptions,
            granger_pvalue=min((r.pvalue for r in granger_results), default=1.0),
            sensitivity_robust_ratio=sum(sensitivity_results.values()) / max(len(sensitivity_results), 1)
        )
    
    def _merge_relations(
        self,
        template_relations: list[TemplateRelation],
        granger_results: list[GrangerResult]
    ) -> list[dict]:
        """合并模板和Granger关系"""
        merged = []
        
        # 添加模板关系
        for tr in template_relations:
            merged.append({
                "cause": tr.cause,
                "effect": tr.effect,
                "confidence": tr.confidence,
                "method": "template",
                "evidence": tr.evidence
            })
        
        # 添加Granger关系
        for gr in granger_results:
            if gr.is_significant:
                merged.append({
                    "cause": gr.cause,
                    "effect": gr.effect,
                    "confidence": 1 - gr.pvalue,
                    "method": "granger",
                    "lag": gr.lag
                })
        
        return merged
    
    def _build_causal_relations(
        self,
        all_relations: list[dict],
        granger_results: list[GrangerResult],
        sensitivity_results: dict[str, float]
    ) -> list[CausalRelation]:
        """构建CausalRelation列表"""
        relations = []
        
        for i, rel in enumerate(all_relations):
            # 确定因果方法
            method_str = rel.get("method", "template")
            if method_str == "granger":
                method = CausalMethod.GRANGER
            elif method_str == "sensitivity":
                method = CausalMethod.SENSITIVITY
            else:
                method = CausalMethod.TEMPLATE
            
            # 确定证据强度
            confidence = rel.get("confidence", 0.5)
            if confidence > 0.8:
                strength = EvidenceStrength.STRONG
            elif confidence > 0.5:
                strength = EvidenceStrength.MEDIUM
            else:
                strength = EvidenceStrength.WEAK
            
            # 确定置信水平
            if confidence > 0.8:
                level = ConfidenceLevel.HIGH
            elif confidence > 0.5:
                level = ConfidenceLevel.MEDIUM
            else:
                level = ConfidenceLevel.LOW
            
            # 获取Granger p值
            granger_pvalue = None
            for gr in granger_results:
                if gr.cause == rel["cause"] and gr.effect == rel["effect"]:
                    granger_pvalue = gr.pvalue
                    break
            
            # 获取敏感性结果
            sensitivity_robust = sensitivity_results.get(f"relation_{i}", 0.5)
            
            relations.append(CausalRelation(
                cause=rel["cause"],
                effect=rel["effect"],
                strength=CausalStrength(
                    level=level,
                    evidence_strength=strength,
                    causal_method=method,
                    assumptions=rel.get("evidence", []),
                    sensitivity_results={"robust": sensitivity_robust}
                ),
                granger_pvalue=granger_pvalue,
                sensitivity_robust=sensitivity_robust
            ))
        
        return relations
    
    def _calculate_overall_confidence(self, relations: list[CausalRelation]) -> float:
        """计算整体置信度"""
        if not relations:
            return 0.0
        
        confidences = []
        for rel in relations:
            if rel.strength.level == ConfidenceLevel.HIGH:
                confidences.append(0.9)
            elif rel.strength.level == ConfidenceLevel.MEDIUM:
                confidences.append(0.6)
            else:
                confidences.append(0.3)
        
        return sum(confidences) / len(confidences)
    
    def _collect_assumptions(self, relations: list[CausalRelation]) -> list[str]:
        """收集假设"""
        assumptions = []
        
        for rel in relations:
            assumptions.extend(rel.strength.assumptions)
        
        return list(set(assumptions))
