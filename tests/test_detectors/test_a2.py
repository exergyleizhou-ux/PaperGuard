"""A2 Benford 检测器测试。"""
from __future__ import annotations

import numpy as np
import pandas as pd

from paperguard.core.types import Severity
from paperguard.detectors.a2_benford import A2BenfordDetector, _first_digit


def test_first_digit_basic() -> None:
    assert _first_digit(123.4) == 1
    assert _first_digit(0.045) == 4
    assert _first_digit(-7000) == 7
    assert _first_digit(0) is None
    assert _first_digit(float("nan")) is None


def test_a2_flags_uniform_first_digits() -> None:
    """编造数据：首位均匀（每个 1..9 各 ~60 个）+ 跨 4 个数量级。"""
    rng = np.random.default_rng(42)
    n_per = 60
    uniforms = []
    for d in range(1, 10):
        # 在 [d*10^k, (d+1)*10^k) 内采样，k 跨 0..3
        for k in range(4):
            uniforms.extend(rng.uniform(d * 10**k, (d + 1) * 10**k, size=n_per // 4))
    df = pd.DataFrame({"col": uniforms})

    result = A2BenfordDetector().detect(df, seed=42)
    assert result.applicable
    assert len(result.findings) >= 1
    assert max(f.severity for f in result.findings) >= Severity.CONCERN


def test_a2_passes_benford_distributed_data() -> None:
    """Benford 分布数据：用 10^uniform(0,4) 生成，应不被标记。"""
    rng = np.random.default_rng(42)
    values = 10 ** rng.uniform(0, 4, size=300)
    df = pd.DataFrame({"col": values})

    result = A2BenfordDetector().detect(df, seed=42)
    # 应通过或仅给极弱信号
    severe = [f for f in result.findings if f.severity >= Severity.SUSPICIOUS]
    assert len(severe) == 0


def test_a2_skips_narrow_range() -> None:
    """动态范围 < 2 个数量级 → 不适用。"""
    df = pd.DataFrame({"col": list(range(10, 100))})  # 1 个数量级
    result = A2BenfordDetector().detect(df, seed=42)
    assert not result.applicable
