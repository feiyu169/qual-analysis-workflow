"""Unit tests for the demo calculator module (real assertions, no stubs)."""

import pytest
from calc import add, apply_discount, divide


def test_add_positive() -> None:
    assert add(2, 3) == 5


def test_add_negative() -> None:
    assert add(-1, 1) == 0


def test_add_floats() -> None:
    assert add(0.1, 0.2) == pytest.approx(0.3)


def test_divide_normal() -> None:
    assert divide(10, 4) == 2.5


def test_divide_by_zero() -> None:
    with pytest.raises(ValueError):
        divide(1, 0)


def test_discount_normal() -> None:
    assert apply_discount(100, 10) == 90.0


def test_discount_clamped_to_zero() -> None:
    assert apply_discount(100, 200) == 0.0


def test_discount_full_percent() -> None:
    assert apply_discount(100, 100) == 0.0


def test_discount_invalid_percent() -> None:
    with pytest.raises(ValueError):
        apply_discount(100, -5)
