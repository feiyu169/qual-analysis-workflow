#!/usr/bin/env python3
"""
契约测试覆盖率度量脚本
读取 required_interfaces.yaml，检查所有关键接口是否被契约测试覆盖
"""
import os
import subprocess
import sys

import yaml


def main():
    # 读取接口清单
    config_path = os.path.join(os.path.dirname(__file__), '..', 'contracts', 'required_interfaces.yaml')
    with open(config_path, encoding='utf-8') as f:
        data = yaml.safe_load(f)

    # 构建必需接口列表
    required = []
    for item in data['interfaces']:
        for method in item['methods']:
            required.append(f"{item['module']}.{item['class']}.{method}")

    # 收集契约测试
    result = subprocess.run(
        [sys.executable, '-m', 'pytest', '-m', 'contract', '--collect-only', '-q', 'tests/'],
        capture_output=True, text=True, timeout=30,
        check=False,
    )

    # 解析测试函数名
    tests = [ln.strip() for ln in result.stdout.split('\n') if '::' in ln and 'test_' in ln]

    # 匹配接口和测试
    covered = []
    for req in required:
        method_name = req.split('.')[-1]
        # 检查方法名是否在测试函数名中
        for test in tests:
            test_func = test.split('::')[-1] if '::' in test else test
            if method_name in test_func:
                covered.append(req)
                break

    ratio = (len(covered) * 100) // len(required) if required else 0

    print(f"关键接口: {len(required)}")
    print(f"已覆盖: {len(covered)}")
    print(f"覆盖比例: {ratio}%")

    if ratio < 100:
        uncovered = [r for r in required if r not in covered]
        print(f"未覆盖: {uncovered}")
        sys.exit(1)

    print("✅ 契约测试覆盖 100%")


if __name__ == '__main__':
    main()
