#!/usr/bin/env python3
"""
Test Quality Metrics Calculator
Calculates assertions/test, boundary coverage, integration ratio
"""
import re
import sys
from pathlib import Path


def count_tests_and_assertions(test_dir: str = "tests"):
    """Count tests and assertions in test files"""
    test_path = Path(test_dir)
    
    total_tests = 0
    total_assertions = 0
    boundary_tests = 0
    integration_tests = 0
    
    for py_file in test_path.glob("test_*.py"):
        content = py_file.read_text()
        
        # Count test methods
        tests = re.findall(r'def test_\w+', content)
        total_tests += len(tests)
        
        # Count assertions
        assertions = re.findall(r'assert ', content)
        total_assertions += len(assertions)
        
        # Count boundary tests (keywords: raises, None, empty, invalid, error)
        boundary_keywords = ['raises', 'None', 'empty', 'invalid', 'error', 'corrupted']
        for kw in boundary_keywords:
            if kw.lower() in content.lower():
                boundary_tests += 1
                break
        
        # Count integration tests (marked with @pytest.mark.integration)
        if '@pytest.mark.integration' in content:
            integration_tests += len(tests)
    
    return {
        'total_tests': total_tests,
        'total_assertions': total_assertions,
        'assertions_per_test': total_assertions / max(total_tests, 1),
        'boundary_tests': boundary_tests,
        'integration_tests': integration_tests,
        'boundary_ratio': boundary_tests / max(total_tests, 1) * 100,
        'integration_ratio': integration_tests / max(total_tests, 1) * 100,
    }


def main():
    test_dir = sys.argv[1] if len(sys.argv) > 1 else "tests"
    metrics = count_tests_and_assertions(test_dir)
    
    print("=" * 50)
    print("Test Quality Metrics")
    print("=" * 50)
    print(f"Total tests: {metrics['total_tests']}")
    print(f"Total assertions: {metrics['total_assertions']}")
    print(f"Assertions/test: {metrics['assertions_per_test']:.1f}")
    print(f"Boundary tests: {metrics['boundary_tests']}")
    print(f"Integration tests: {metrics['integration_tests']}")
    print(f"Boundary ratio: {metrics['boundary_ratio']:.1f}%")
    print(f"Integration ratio: {metrics['integration_ratio']:.1f}%")
    print()
    
    # Check against targets
    targets = {
        'assertions_per_test': 2.0,
        'boundary_ratio': 30.0,
        'integration_ratio': 20.0,
    }
    
    print("Target Comparison:")
    for metric, target in targets.items():
        actual = metrics[metric]
        status = "✅" if actual >= target else "❌"
        print(f"  {metric}: {actual:.1f} (target: {target}) {status}")


if __name__ == '__main__':
    main()
