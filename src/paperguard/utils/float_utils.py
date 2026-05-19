"""浮点数比较工具。"""
from __future__ import annotations

import math


def safe_equal(a: float, b: float, rel_tol: float = 1e-9, abs_tol: float = 1e-12) -> bool:
    """浮点近似相等。"""
    return math.isclose(a, b, rel_tol=rel_tol, abs_tol=abs_tol)


def get_decimal_places(value: float | str) -> int:
    """获取数字的小数位数（去除末尾零后）。"""
    s = str(value)
    if "." not in s:
        return 0
    decimal_part = s.split(".")[1].rstrip("0")
    return len(decimal_part)


def get_last_significant_digit(value: float | str) -> int:
    """获取数字的最后一个非零有效数字。

    >>> get_last_significant_digit(2.51)
    1
    >>> get_last_significant_digit("2.50")
    5
    """
    if isinstance(value, float):
        s = repr(value)
    else:
        s = str(value).strip()

    if "." in s:
        stripped = s.rstrip("0").rstrip(".")
        if not stripped or stripped == "-":
            return 0
        last_char = stripped[-1]
    else:
        cleaned = s.rstrip("0") or "0"
        last_char = cleaned[-1]

    return int(last_char)
