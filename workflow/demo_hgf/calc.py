"""Demo calculator module for the HGF gate-driven workflow demo."""


def add(a: float, b: float) -> float:
    """Return the sum of two numbers."""
    return a + b


def divide(a: float, b: float) -> float:
    """Return a divided by b, raising on division by zero."""
    if b == 0:
        raise ValueError("division by zero")
    return a / b


def apply_discount(price: float, percent: float) -> float:
    """Return price after percent discount, clamped to zero.

    Args:
        price: original price, non-negative.
        percent: discount percentage; values above 100 clamp to a zero
            price, negative values are rejected.

    Returns:
        Discounted price, never below zero.

    Raises:
        ValueError: if percent is negative.
    """
    if percent < 0:
        raise ValueError("percent must be non-negative")
    return max(0.0, price * (1 - min(percent, 100) / 100))
