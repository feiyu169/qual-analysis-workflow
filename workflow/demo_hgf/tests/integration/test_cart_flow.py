"""demo_hgf 集成测试（V3.2.11 Phase 1/待办 1）。

跨模块业务链路：calc 模块的 add/divide/apply_discount 组合成一个真实业务流
（购物车结算：加价→折扣→均摊），验证模块内真实协作与边界行为。
标记 integration：常规单测排除，生命周期 gate_3_1（_check_integration_tests）
才执行——保证 L2"真实数据端到端"有真实用例。
"""

import pytest
from calc import add, apply_discount, divide


@pytest.mark.integration
def test_cart_checkout_flow():
    """真实业务流：3 件商品加总 → 打 8 折 → 三人均摊，全链路无 mock"""
    total = add(add(100.0, 200.0), 150.0)  # 450.0
    discounted = apply_discount(total, 20)  # 360.0
    per_person = divide(discounted, 3)  # 120.0
    assert per_person == 120.0
    # 边界：折扣上限与零价
    assert apply_discount(100.0, 150) == 0.0
    assert apply_discount(0.0, 50) == 0.0


@pytest.mark.integration
def test_checkout_invariant_holds():
    """业务不变量：折扣后金额 ≤ 原价，均摊后总和不丢精度"""
    total = add(add(99.9, 0.1), 300.0)  # 400.0
    discounted = apply_discount(total, 30)  # 280.0
    assert discounted <= total
    share1 = divide(discounted, 2)
    share2 = divide(discounted, 2)
    assert abs(add(share1, share2) - discounted) < 1e-9


@pytest.mark.integration
def test_invalid_inputs_rejected():
    """非法输入在集成层同样被拒（负折扣/除零）"""
    with pytest.raises(ValueError):
        apply_discount(100.0, -10)
    with pytest.raises(ValueError):
        divide(10.0, 0)
