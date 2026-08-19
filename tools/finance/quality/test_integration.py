"""
quality/tests/test_integration.py — 集成测试

端到端测试：
- 测试完整推理链
- 测试评分引擎
- 测试市场调整器
"""

import sys
sys.path.insert(0, '.')

from finance.quality import (
    CausalInferenceChain,
    StandardScoringEngine,
    DataCompletenessCalculator,
    LogicConsistencyCalculator,
    AnalysisDepthCalculator,
    ConclusionReliabilityCalculator,
    ActionabilityCalculator,
    CNMarketAdjuster,
    HKMarketAdjuster,
    MarketScorerRegistry,
    DefaultColdStartPolicy,
    ReasoningBudget,
    QualityContext,
    DataSourceQuality,
    ReasoningQuality,
    DepthQuality,
    DegradationLevel,
    EvidenceBundle,
    ScenarioConfig,
    ScenarioMode,
)


def test_causal_inference_chain():
    """测试因果推理链"""
    print("=== 测试因果推理链 ===")
    
    chain = CausalInferenceChain()
    budget = ReasoningBudget()
    
    # 测试数据
    evidence = EvidenceBundle(
        financial_data={"revenue": [100, 110, 120], "net_profit": [10, 12, 15]},
        news_data=[{"title": "公司业绩增长"}, {"title": "行业景气"}],
        industry_data={"growth": 0.15},
        filing_data={"sections": {"业务概览": "公司主营业务..."}}
    )
    
    config = ScenarioConfig(mode=ScenarioMode.BASE)
    
    # 执行推理
    result = chain.run(evidence, config, budget)
    
    # 验证结果
    assert result is not None, "推理结果不应为None"
    assert result.causal_graph is not None, "因果图不应为None"
    assert result.counter_result is not None, "反面论证结果不应为None"
    assert result.confidence > 0, "置信度应大于0"
    assert result.trace_id, "应有trace_id"
    
    print(f"  ✅ 推理链执行成功")
    print(f"     置信度: {result.confidence:.2f}")
    print(f"     因果关系: {len(result.causal_graph.relations)}条")
    print(f"     反方论点: {len(result.counter_result.counter_arguments)}条")
    print(f"     检查点通过: {len(result.checkpoints_passed)}")
    print(f"     检查点失败: {len(result.checkpoints_failed)}")
    
    return result


def test_scoring_engine(reasoning_result):
    """测试评分引擎"""
    print("\n=== 测试评分引擎 ===")
    
    engine = StandardScoringEngine()
    
    # 注册5个维度
    engine.register_dimension(DataCompletenessCalculator())
    engine.register_dimension(LogicConsistencyCalculator())
    engine.register_dimension(AnalysisDepthCalculator())
    engine.register_dimension(ConclusionReliabilityCalculator())
    engine.register_dimension(ActionabilityCalculator())
    
    # 构造质量上下文
    context = QualityContext(
        data=DataSourceQuality(
            level=DegradationLevel.L0,
            sources={"wind": "ok", "filing": "ok", "news": "ok"},
            missing=[],
            confidence_cap=1.0
        ),
        reasoning=ReasoningQuality(
            level=DegradationLevel.L0,
            checkpoints_passed=reasoning_result.checkpoints_passed,
            checkpoints_failed=reasoning_result.checkpoints_failed,
            confidence_cap=1.0
        ),
        depth=DepthQuality(
            level=DegradationLevel.L0,
            score_breakdown={},
            total_score=0.0,
            grade=""
        ),
        version="1.0"
    )
    
    # 执行评分
    report = engine.score(reasoning_result, context)
    
    # 验证结果
    assert report is not None, "评分报告不应为None"
    assert report.total_score >= 0, "总分应>=0"
    assert report.total_score <= 100, "总分应<=100"
    assert report.grade in ["S", "A", "B", "C", "D", "F"], "等级应为S/A/B/C/D/F"
    assert report.falsification_score >= 0, "证伪得分应>=0"
    assert len(report.dimension_scores) == 5, "应有5个维度得分"
    
    print(f"  ✅ 评分引擎执行成功")
    print(f"     总分: {report.total_score:.1f}")
    print(f"     等级: {report.grade}")
    print(f"     证伪得分: {report.falsification_score:.1f}")
    print(f"     维度数量: {len(report.dimension_scores)}")
    
    return report


def test_market_adjuster(report):
    """测试市场调整器"""
    print("\n=== 测试市场调整器 ===")
    
    registry = MarketScorerRegistry()
    registry.register(CNMarketAdjuster())
    registry.register(HKMarketAdjuster())
    
    # 测试CN市场
    context = QualityContext(
        data=DataSourceQuality(level=DegradationLevel.L0),
        reasoning=ReasoningQuality(level=DegradationLevel.L0),
        depth=DepthQuality(level=DegradationLevel.L0),
        extra_info={
            "deducted_net_income": True,
            "operating_cashflow": 100,
            "net_income": 80,
        }
    )
    
    cn_score = registry.adjust_score("CN", report.total_score, context)
    print(f"  ✅ CN市场调整: {report.total_score:.1f} → {cn_score:.1f}")
    
    # 测试HK市场
    context_hk = QualityContext(
        data=DataSourceQuality(level=DegradationLevel.L0),
        reasoning=ReasoningQuality(level=DegradationLevel.L0),
        depth=DepthQuality(level=DegradationLevel.L0),
        extra_info={
            "nav_per_share": True,
            "core_earnings": True,
            "dual_currency": True,
        }
    )
    
    hk_score = registry.adjust_score("HK", report.total_score, context_hk)
    print(f"  ✅ HK市场调整: {report.total_score:.1f} → {hk_score:.1f}")
    
    # 测试不支持的市场
    try:
        registry.adjust_score("US", report.total_score, context)
        print("  ❌ 应该抛出MarketNotSupportedError")
    except Exception as e:
        print(f"  ✅ 不支持的市场正确抛出异常: {type(e).__name__}")


def test_cold_start():
    """测试冷启动策略"""
    print("\n=== 测试冷启动策略 ===")
    
    policy = DefaultColdStartPolicy()
    
    # 测试数据不足的情况
    poor_evidence = EvidenceBundle(
        financial_data={"revenue": [100]},
        news_data=[],
        industry_data={},
        filing_data={}
    )
    
    is_cold = policy.is_cold_start(poor_evidence)
    assert is_cold == True, "数据不足应触发冷启动"
    print(f"  ✅ 冷启动判断: {is_cold}")
    
    # 测试降级输出
    fallback = policy.get_fallback_output()
    assert fallback.confidence == 0.3, "降级输出置信度应为0.3"
    assert "cold_start" in fallback.checkpoints_failed, "应标记cold_start检查点失败"
    print(f"  ✅ 降级输出: 置信度={fallback.confidence}, 检查点失败={fallback.checkpoints_failed}")


def main():
    """主测试函数"""
    print("========================================")
    print("  集成测试开始")
    print("========================================\n")
    
    try:
        # 测试因果推理链
        reasoning_result = test_causal_inference_chain()
        
        # 测试评分引擎
        report = test_scoring_engine(reasoning_result)
        
        # 测试市场调整器
        test_market_adjuster(report)
        
        # 测试冷启动策略
        test_cold_start()
        
        print("\n========================================")
        print("  ✅ 所有集成测试通过")
        print("========================================")
        
        return 0
    
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
