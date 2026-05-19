"""B6 GRIMMER 测试。"""
from __future__ import annotations

from paperguard.core.types import Severity
from paperguard.detectors.b6_grimmer import (
    B6GRIMMERDetector,
    GRIMMERInput,
    _grim_passes,
)


def test_grim_helper() -> None:
    # mean=3.2, N=10 → sum=32 (integer) ✓
    assert _grim_passes(3.2, 10, 2) is True
    # mean=3.15, N=10 → sum=31.5 (not integer, tol = 0.05) ✗
    assert _grim_passes(3.15, 10, 2) is False


def test_b6_flags_grim_failure() -> None:
    """mean=3.15, sd=1.0, n=10 → GRIM fails."""
    inputs = [GRIMMERInput(mean=3.15, n=10, sd=1.0, mean_decimals=2,
                            sd_decimals=2, label="Q1")]
    result = B6GRIMMERDetector().detect(inputs, seed=42)
    assert result.applicable
    assert len(result.findings) == 1
    assert result.findings[0].severity == Severity.SUSPICIOUS  # GRIM 不通过 → 严重


def test_b6_passes_valid_likert() -> None:
    """mean=3.20, sd≈1.0, n=10 → 应该通过。"""
    # 构造一组确实可能的整数样本：1,2,3,3,3,3,4,4,5,4 → sum=32, mean=3.2
    inputs = [GRIMMERInput(mean=3.2, n=10, sd=1.135, mean_decimals=2,
                            sd_decimals=2,
                            scale_min=1, scale_max=5, label="Q1")]
    result = B6GRIMMERDetector().detect(inputs, seed=42)
    assert result.applicable
    # GRIM 通过；SD 也大致合理 → 不应报告
    assert len(result.findings) == 0


def test_b6_inapplicable() -> None:
    result = B6GRIMMERDetector().detect("not a list", seed=42)
    assert not result.applicable
