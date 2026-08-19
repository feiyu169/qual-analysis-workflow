#!/usr/bin/env python3
"""
HeavySkill 增强版批量评测脚本

运行 7 个评测用例，对比优化前后的效果。
"""

import sys
import os
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

# 添加优化模块路径
sys.path.insert(0, str(Path(__file__).parent))

from src.models import Severity, Verdict
from src.validator import ConclusionValidator, ConclusionValidatorConfig
from src.parser import ChecklistResultParser
from src.utils import infer_llm_verdict

# 默认配置
DEFAULT_HEAVYSKILL_DIR = os.path.expanduser("~/.hermes/skills/heavyskill")
DEFAULT_PROPOSAL_DIR = os.path.expanduser("~/.hermes/evals/proposals")
DEFAULT_OUTPUT_DIR = os.path.expanduser("~/.hermes/output")


# 评测用例配置
CASES = [
    {
        "id": "case-004",
        "name": "技术方案审查",
        "proposal": "/tmp/heavyskill-eval-test-proposal.md",
        "query": "请从技术可行性、架构设计、安全性、风险遗漏 4 个维度审查这个方案，输出 P0/P1/P2 问题清单和总体结论",
        "missing": ["并发安全", "数据备份", "错误处理", "性能优化", "安全防护"]
    },
    {
        "id": "case-005",
        "name": "代码架构审查",
        "proposal": "/tmp/heavyskill-eval-case005-proposal.md",
        "query": "请从服务拆分、服务间通信、数据管理、部署架构 4 个维度审查这个微服务架构方案，输出 P0/P1/P2 问题清单和总体结论",
        "missing": ["循环依赖", "服务发现", "熔断机制", "日志体系", "配置管理"]
    },
    {
        "id": "case-006",
        "name": "安全漏洞审查",
        "proposal": "/tmp/heavyskill-eval-security-auth-system-proposal.md",
        "query": "请从认证安全、数据安全、传输安全、配置安全 4 个维度审查这个用户认证系统方案，输出 P0/P1/P2 问题清单和总体结论",
        "missing": ["SQL注入", "XSS攻击", "CSRF防护", "密钥硬编码", "会话管理"]
    },
    {
        "id": "case-007",
        "name": "性能瓶颈审查",
        "proposal": "/tmp/heavyskill-eval-high-concurrency-system-proposal.md",
        "query": "请从数据库性能、缓存策略、异步处理、负载均衡、限流机制 5 个维度审查这个高并发系统方案，输出 P0/P1/P2 问题清单和总体结论",
        "missing": ["连接池", "缓存策略", "异步处理", "负载均衡", "限流机制"]
    },
    {
        "id": "case-008",
        "name": "API设计审查",
        "proposal": "/tmp/heavyskill-eval-restful-api-proposal.md",
        "query": "请从版本控制、分页设计、错误处理、幂等性、速率限制 5 个维度审查这个RESTful API方案，输出 P0/P1/P2 问题清单和总体结论",
        "missing": ["版本控制", "分页缺失", "错误码", "幂等性", "速率限制"]
    },
    {
        "id": "case-009",
        "name": "数据库设计审查",
        "proposal": "/tmp/heavyskill-eval-ecommerce-database-proposal.md",
        "query": "请从索引设计、数据归档、读写分离、备份恢复、迁移策略 5 个维度审查这个数据库设计方案，输出 P0/P1/P2 问题清单和总体结论",
        "missing": ["索引缺失", "数据归档", "读写分离", "备份恢复", "迁移策略"]
    },
    {
        "id": "case-010",
        "name": "部署方案审查",
        "proposal": "/tmp/heavyskill-eval-k8s-deployment-proposal.md",
        "query": "请从健康检查、滚动更新、资源限制、日志收集、监控告警 5 个维度审查这个K8s部署方案，输出 P0/P1/P2 问题清单和总体结论",
        "missing": ["健康检查", "滚动更新", "资源限制", "日志收集", "监控告警"]
    }
]


def run_heavyskill(query: str, file_path: str, 
                   heavyskill_dir: Optional[str] = None, 
                   output_dir: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """运行 HeavySkill"""
    heavyskill_dir = heavyskill_dir or DEFAULT_HEAVYSKILL_DIR
    output_dir = output_dir or DEFAULT_OUTPUT_DIR
    
    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)
    
    output_file = os.path.join(output_dir, f"heavyskill-batch-{datetime.now().strftime('%H%M%S')}.json")
    
    cmd = f'cd {heavyskill_dir} && python3 scripts/run_heavyskill.py -q "{query}" -f {file_path} --reason_k 4 --summary_k 2 --language cn -o {output_file} --quiet'
    
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
    
    if result.returncode != 0:
        return None
    
    with open(output_file) as f:
        return json.load(f)


def analyze_with_enhancement(heavyskill_output: Dict[str, Any], case: Dict) -> Dict[str, Any]:
    """使用增强版分析 HeavySkill 输出"""
    parser = ChecklistResultParser()
    validator = ConclusionValidator()
    
    # 提取轨迹
    trajectories = heavyskill_output.get('reasoning', {}).get('trajectories', [])
    all_text = ' '.join(trajectories)
    
    # 提取问题
    all_issues = []
    for i, traj in enumerate(trajectories):
        issues = parser.parse(traj)
        for issue in issues:
            issue.source = f"trajectory-{i}"
        all_issues.extend(issues)
    
    # 去重
    seen = set()
    unique_issues = []
    for issue in all_issues:
        key = (issue.title, issue.severity, issue.domain)
        if key not in seen:
            seen.add(key)
            unique_issues.append(issue)
    
    # 推断 LLM 结论
    final_answer = heavyskill_output.get('final_answer', '')
    llm_verdict = infer_llm_verdict(final_answer)
    
    # 运行规则引擎
    validation_result = validator.validate(unique_issues, llm_verdict)
    
    # 检查问题发现率
    found = []
    for issue_name in case['missing']:
        keywords = issue_name.split('（')[0] if '（' in issue_name else issue_name
        if any(kw in all_text for kw in [keywords, issue_name]):
            found.append(issue_name)
    
    discovery_rate = len(found) / len(case['missing'])
    
    return {
        "case_id": case['id'],
        "case_name": case['name'],
        "llm_verdict": llm_verdict.value,
        "enhanced_verdict": validation_result.verdict.value,
        "verdict_changed": validation_result.verdict != llm_verdict,
        "discovery_rate": discovery_rate,
        "found_issues": found,
        "missing_issues": [i for i in case['missing'] if i not in found],
        "issue_count": len(unique_issues),
        "p0_count": len([i for i in unique_issues if i.severity == Severity.P0]),
        "p1_count": len([i for i in unique_issues if i.severity == Severity.P1]),
        "rules_triggered": [r.rule_name for r in validation_result.rules_applied if r.triggered],
        "token_count": heavyskill_output.get('total_tokens', 0),
        "latency": heavyskill_output.get('total_latency', 0)
    }


def run_batch_evaluation(heavyskill_dir: Optional[str] = None, proposal_dir: Optional[str] = None):
    """运行批量评测"""
    results = []
    
    print("=" * 70)
    print("HeavySkill 增强版批量评测")
    print("=" * 70)
    print()
    
    for i, case in enumerate(CASES):
        print(f"[{i+1}/7] {case['id']}: {case['name']}")
        print(f"  测试方案: {case['proposal']}")
        print(f"  故意遗漏: {len(case['missing'])} 个问题")
        
        # 运行 HeavySkill
        heavyskill_output = run_heavyskill(case['query'], case['proposal'])
        
        if not heavyskill_output:
            print(f"  ❌ HeavySkill 执行失败")
            continue
        
        # 增强分析
        result = analyze_with_enhancement(heavyskill_output, case)
        results.append(result)
        
        print(f"  ✅ 完成")
        print(f"  发现率: {result['discovery_rate']*100:.0f}%")
        print(f"  LLM 结论: {result['llm_verdict']}")
        print(f"  增强结论: {result['enhanced_verdict']}")
        print(f"  结论覆盖: {'是' if result['verdict_changed'] else '否'}")
        print()
    
    return results


def generate_report(results: List[Dict]):
    """生成评测报告"""
    print("=" * 70)
    print("HeavySkill 增强版评测报告")
    print("=" * 70)
    print()
    
    # 基本统计
    print("【基本统计】")
    print(f"  评测用例数: {len(results)}")
    
    # 发现率统计
    discovery_rates = [r['discovery_rate'] for r in results]
    avg_discovery = sum(discovery_rates) / len(discovery_rates) if results else 0
    print(f"  平均发现率: {avg_discovery*100:.0f}%")
    
    # 结论准确率（使用增强版）
    correct = sum(1 for r in results if r['enhanced_verdict'] == 'REJECT')
    print(f"  增强版结论准确率: {correct}/{len(results)} = {correct/len(results)*100:.0f}%")
    
    # LLM 原始结论准确率
    llm_correct = sum(1 for r in results if r['llm_verdict'] == 'REJECT')
    print(f"  LLM 原始结论准确率: {llm_correct}/{len(results)} = {llm_correct/len(results)*100:.0f}%")
    
    # 结论覆盖统计
    verdict_changed = sum(1 for r in results if r['verdict_changed'])
    print(f"  结论被覆盖: {verdict_changed}/{len(results)}")
    print()
    
    # 各用例详情
    print("【各用例详情】")
    print(f"{'用例ID':<12} {'名称':<12} {'发现率':<10} {'LLM结论':<12} {'增强结论':<12} {'覆盖':<6}")
    print("-" * 70)
    for r in results:
        changed = "是" if r['verdict_changed'] else "否"
        print(f"{r['case_id']:<12} {r['case_name']:<12} {r['discovery_rate']*100:.0f}%{'':<6} {r['llm_verdict']:<12} {r['enhanced_verdict']:<12} {changed:<6}")
    print()
    
    # 规则触发统计
    print("【规则触发统计】")
    rule_counts = {}
    for r in results:
        for rule in r['rules_triggered']:
            rule_counts[rule] = rule_counts.get(rule, 0) + 1
    
    for rule, count in sorted(rule_counts.items(), key=lambda x: -x[1]):
        print(f"  {rule}: {count}/{len(results)} 次触发")
    print()
    
    # 优化效果对比
    print("=" * 70)
    print("优化效果对比")
    print("=" * 70)
    print()
    print(f"{'指标':<20} {'优化前':<15} {'优化后':<15} {'提升':<10}")
    print("-" * 60)
    print(f"{'结论准确率':<20} {'14%':<15} {f'{correct/len(results)*100:.0f}%':<15} {f'+{(correct/len(results)*100-14):.0f}%':<10}")
    print(f"{'平均发现率':<20} {'74%':<15} {f'{avg_discovery*100:.0f}%':<15} {f'+{(avg_discovery*100-74):.0f}%':<10}")
    print()


def save_results(results: List[Dict], output_dir: Optional[str] = None):
    """保存评测结果"""
    output_dir = output_dir or DEFAULT_OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)
    
    output_file = os.path.join(output_dir, "heavyskill-enhanced-batch-results.json")
    
    with open(output_file, 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "case_count": len(results),
            "results": results,
            "summary": {
                "avg_discovery_rate": sum(r['discovery_rate'] for r in results) / len(results),
                "enhanced_accuracy": sum(1 for r in results if r['enhanced_verdict'] == 'REJECT') / len(results),
                "llm_accuracy": sum(1 for r in results if r['llm_verdict'] == 'REJECT') / len(results),
                "verdict_changed_count": sum(1 for r in results if r['verdict_changed'])
            }
        }, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 评测结果已保存到: {output_file}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="HeavySkill 增强版批量评测")
    parser.add_argument("--heavyskill-dir", help="HeavySkill 目录路径")
    parser.add_argument("--proposal-dir", help="评测方案目录路径")
    parser.add_argument("--output-dir", help="输出目录路径")
    args = parser.parse_args()
    
    results = run_batch_evaluation(args.heavyskill_dir, args.proposal_dir)
    generate_report(results)
    save_results(results, args.output_dir)
