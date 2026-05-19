"""C1 Carlisle 测试。"""
from __future__ import annotations

import random

from paperguard.core.types import Severity
from paperguard.detectors.c1_carlisle import (
    BaselineVariable,
    C1CarlisleDetector,
    CarlisleInput,
    _stouffer_combine,
)


def test_stouffer_p_half_centered() -> None:
    """所有 p=0.5 → Stouffer 给出最大可能合并 p。"""
    ps = [0.5] * 20
    combined = _stouffer_combine(ps)
    assert combined > 0.9


def test_stouffer_average_of_seeded_uniform() -> None:
    """1000 个独立 uniform 模拟，combined p 自身应近似 uniform(0,1)；
    则 < 0.05 的比例应在 5% 附近。"""
    random.seed(0)
    n_runs = 200
    flags = 0
    for _ in range(n_runs):
        ps = [random.random() for _ in range(15)]
        if _stouffer_combine(ps) < 0.05:
            flags += 1
    # 期望约 10/200，宽松界限：5~30
    assert 1 < flags < 40, f"flagged {flags}/{n_runs} (expected ~10)"


def test_stouffer_all_high_flags() -> None:
    """全部 p 都接近 1（过度平衡）→ 合并 p 应极小。"""
    ps = [0.95] * 10
    combined = _stouffer_combine(ps)
    assert combined < 0.05


def test_c1_overly_balanced_baseline() -> None:
    """模拟 6 个 baseline 变量，组间几乎相同 → 应触发。"""
    vars_ = [
        BaselineVariable(f"var{i}", n1=50, mean1=10.0, sd1=2.0, n2=50, mean2=10.01, sd2=2.0)
        for i in range(8)
    ]
    inp = CarlisleInput(trial_id="T1", variables=vars_)
    result = C1CarlisleDetector().detect(inp, seed=42)
    assert result.applicable
    assert len(result.findings) >= 1
    assert result.findings[0].severity >= Severity.NOTE


def test_c1_inapplicable_too_few_vars() -> None:
    vars_ = [
        BaselineVariable(f"var{i}", n1=50, mean1=10.0, sd1=2.0, n2=50, mean2=10.1, sd2=2.0)
        for i in range(3)
    ]
    inp = CarlisleInput(trial_id="T1", variables=vars_)
    result = C1CarlisleDetector().detect(inp, seed=42)
    assert not result.applicable
