"""
quality/tests/test_golden_set.py - Golden set test

Test the quality system with known good data to verify correctness.
"""

import sys
sys.path.insert(0, '.')

from finance.quality import (
    StandardScoringEngine,
    DataCompletenessCalculator,
    LogicConsistencyCalculator,
    AnalysisDepthCalculator,
    ConclusionReliabilityCalculator,
    ActionabilityCalculator,
    CausalInferenceChain,
    ReasoningBudget,
    QualityContext,
    DataSourceQuality,
    ReasoningQuality,
    DepthQuality,
    DegradationLevel,
    EvidenceBundle,
    ScenarioConfig,
    ScenarioMode,
    Formulas,
    Validators,
)


def test_wanhua_golden_set():
    """Test with Wanhua Chemical (600309.SH) golden data"""
    print("=== Wanhua Chemical Golden Set Test ===")
    
    # Known good data from Wind
    market_cap = 2152.0
    net_income = 125.27
    equity_parent = 1083.0
    share_price = 68.62
    total_shares = 31.31  # 亿股
    
    # Test formulas
    pe_result = Formulas.pe_ratio(market_cap, net_income)
    pb_result = Formulas.pb_ratio(market_cap, equity_parent)
    mc_result = Formulas.market_cap(share_price, total_shares)
    
    print(f"  PE(TTM): {pe_result.value:.2f}x")
    print(f"  PB: {pb_result.value:.2f}x")
    print(f"  Market Cap: {mc_result.value:.2f}亿")
    
    # Test validators
    pb_validation = Validators.validate_pb(
        pb_value=pb_result.value,
        equity_type="parent",
        market_cap=market_cap,
        equity=equity_parent
    )
    
    print(f"  PB Validation: {'PASS' if pb_validation.is_valid else 'FAIL'}")
    if pb_validation.warnings:
        for w in pb_validation.warnings:
            print(f"    Warning: {w}")
    
    return pb_validation.is_valid


def test_kuaishou_golden_set():
    """Test with Kuaishou (1024.HK) golden data"""
    print("\n=== Kuaishou Golden Set Test ===")
    
    # Known good data from Wind
    market_cap = 1800.0  # Approximate
    net_income_gaap = 186.17  # GAAP
    net_income_adjusted = 206.0  # Non-IFRS
    share_price = 41.60
    total_shares = 43.5
    
    # Test formulas
    pe_gaap = Formulas.pe_ratio(market_cap, net_income_gaap)
    pe_adjusted = Formulas.pe_ratio(market_cap, net_income_adjusted, net_income_type="adjusted")
    mc_result = Formulas.market_cap(share_price, total_shares)
    
    print(f"  PE(GAAP): {pe_gaap.value:.2f}x")
    print(f"  PE(Adjusted): {pe_adjusted.value:.2f}x")
    print(f"  Market Cap: {mc_result.value:.2f}亿")
    
    # Test validators
    pe_validation = Validators.validate_pe(
        pe_value=pe_adjusted.value,
        net_income_type="adjusted",
        market_cap=market_cap,
        net_income=net_income_adjusted
    )
    
    print(f"  PE Validation: {'PASS' if pe_validation.is_valid else 'FAIL'}")
    if pe_validation.warnings:
        for w in pe_validation.warnings:
            print(f"    Warning: {w}")
    
    return pe_validation.is_valid


def test_reasoning_chain():
    """Test reasoning chain with sample data"""
    print("\n=== Reasoning Chain Test ===")
    
    chain = CausalInferenceChain()
    budget = ReasoningBudget()
    config = ScenarioConfig(mode=ScenarioMode.BASE)
    
    evidence = EvidenceBundle(
        financial_data={"revenue": [100, 110, 120], "net_profit": [10, 12, 15]},
        news_data=[{"title": "Company growth"}, {"title": "Industry positive"}],
        industry_data={"growth": 0.15},
        filing_data={"sections": {"overview": "Business description"}}
    )
    
    result = chain.run(evidence, config, budget)
    
    print(f"  Confidence: {result.confidence:.2f}")
    print(f"  Checkpoints passed: {len(result.checkpoints_passed)}")
    print(f"  Checkpoints failed: {len(result.checkpoints_failed)}")
    print(f"  Causal relations: {len(result.causal_graph.relations)}")
    print(f"  Counter arguments: {len(result.counter_result.counter_arguments)}")
    
    return result.confidence > 0


def test_scoring_engine():
    """Test scoring engine"""
    print("\n=== Scoring Engine Test ===")
    
    from finance.quality.types import (
        CausalGraph, CounterResult, ReasoningResult, FalsificationIndicator, MonitoringPlan
    )
    
    engine = StandardScoringEngine()
    engine.register_dimension(DataCompletenessCalculator())
    engine.register_dimension(LogicConsistencyCalculator())
    engine.register_dimension(AnalysisDepthCalculator())
    engine.register_dimension(ConclusionReliabilityCalculator())
    engine.register_dimension(ActionabilityCalculator())
    
    reasoning_result = ReasoningResult(
        causal_graph=CausalGraph(relations=[], confidence=0.7),
        scenario_results=[],
        counter_result=CounterResult(
            counter_arguments=["Arg1", "Arg2"],
            counter_strengths=[0.8, 0.6],
            falsification_indicators=[
                FalsificationIndicator(name="ind1", description="Test", measurement_method="quantitative", threshold=0.5)
            ],
            monitoring_plan=MonitoringPlan(triggers=[{"indicator": "ind1"}])
        ),
        confidence=0.7,
        checkpoints_passed=["CP-1", "CP-3", "CP-4"],
        checkpoints_failed=["CP-2", "CP-5"]
    )
    
    context = QualityContext(
        data=DataSourceQuality(level=DegradationLevel.L0, sources={"wind": "ok"}),
        reasoning=ReasoningQuality(level=DegradationLevel.L0),
        depth=DepthQuality(level=DegradationLevel.L0),
        version="1.0"
    )
    
    report = engine.score(reasoning_result, context)
    
    print(f"  Total Score: {report.total_score:.1f}")
    print(f"  Grade: {report.grade}")
    print(f"  Falsification Score: {report.falsification_score:.1f}")
    print(f"  Dimension Count: {len(report.dimension_scores)}")
    
    return report.total_score > 0


def main():
    """Run all golden set tests"""
    print("=" * 50)
    print("  Golden Set Tests")
    print("=" * 50)
    
    results = []
    
    try:
        results.append(("Wanhua Chemical", test_wanhua_golden_set()))
        results.append(("Kuaishou", test_kuaishou_golden_set()))
        results.append(("Reasoning Chain", test_reasoning_chain()))
        results.append(("Scoring Engine", test_scoring_engine()))
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    print("\n" + "=" * 50)
    print("  Test Results Summary")
    print("=" * 50)
    
    all_passed = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False
    
    print("\n" + "=" * 50)
    if all_passed:
        print("  All golden set tests passed!")
    else:
        print("  Some tests failed!")
    print("=" * 50)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
