"""Tests for the 2.0.13 mathematical upgrades.

Covers:
- A1 Lag-1 autocorrelation (digit-sequence independence)
- A1 joint multi-column entropy (cross-column digit independence)
- A3 multivariate OLS synthetic-combination detector
- A2 segment Pareto-stability of Benford fit
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from paperguard.core.types import Severity
from paperguard.detectors.a1_terminal_digit import (
    A1TerminalDigitDetector,
    _joint_column_chi2,
    _lag1_autocorr_pvalue,
)
from paperguard.detectors.a2_benford import (
    A2BenfordDetector,
    _segment_benford_chi2,
)
from paperguard.detectors.a3_arithmetic import (
    A3ArithmeticRelationDetector,
    _multivariate_synthetic_check,
)


# A1 Lag-1
def test_lag1_autocorr_random_passes() -> None:
    rng = np.random.default_rng(42)
    digits = rng.integers(0, 10, 200).tolist()
    _z, p = _lag1_autocorr_pvalue(digits)
    assert p > 0.01


def test_lag1_autocorr_pure_repetition_caught() -> None:
    _z, p = _lag1_autocorr_pvalue([3] * 200)
    assert p < 0.001


def test_lag1_autocorr_avoiding_repeats_caught() -> None:
    digits = [(i % 10) for i in range(200)]
    _z, p = _lag1_autocorr_pvalue(digits)
    assert p < 0.001


def test_lag1_autocorr_too_short() -> None:
    _z, p = _lag1_autocorr_pvalue([1, 2, 3, 4, 5])
    assert p == 1.0


# A1 joint multi-column
def test_joint_column_random_passes() -> None:
    rng = np.random.default_rng(123)
    matrix = rng.integers(0, 10, (100, 3)).tolist()
    _c, p, n = _joint_column_chi2(matrix)
    assert p > 0.01
    assert n == 100


def test_joint_column_correlated_caught() -> None:
    rng = np.random.default_rng(123)
    base = rng.integers(0, 10, 100)
    matrix = [[int(base[i]), int(base[i]), int(base[i])] for i in range(100)]
    _c, p, _n = _joint_column_chi2(matrix)
    assert p < 0.01


def test_joint_column_too_short() -> None:
    _c, p, _n = _joint_column_chi2([[1, 2], [3, 4]])
    assert p == 1.0


# A3 multivariate
def test_multivariate_synthetic_caught() -> None:
    rng = np.random.default_rng(42)
    n = 50
    col1 = rng.normal(5, 1, n)
    col2 = rng.normal(3, 1, n)
    col3 = rng.normal(0, 1, n)
    synthetic = 2.0 * col1 + col2 - 0.3
    df = pd.DataFrame(
        {"col1": col1, "col2": col2, "col3": col3, "synth": synthetic}
    )
    hits = _multivariate_synthetic_check(df, ["col1", "col2", "col3", "synth"])
    targets = {h["target"] for h in hits}
    assert "synth" in targets
    synth_hit = next(h for h in hits if h["target"] == "synth")
    assert synth_hit["severity_label"] == "CRITICAL"


def test_multivariate_independent_passes() -> None:
    rng = np.random.default_rng(42)
    n = 50
    df = pd.DataFrame(
        {
            "a": rng.normal(0, 1, n),
            "b": rng.normal(0, 1, n),
            "c": rng.normal(0, 1, n),
        }
    )
    hits = _multivariate_synthetic_check(df, ["a", "b", "c"])
    crit_hits = [h for h in hits if h["severity_label"] == "CRITICAL"]
    assert crit_hits == []


def test_multivariate_too_few_columns() -> None:
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [4.0, 5.0, 6.0]})
    assert _multivariate_synthetic_check(df, ["a", "b"]) == []


# A2 segment Benford
def test_segment_benford_returns_three_chi2s_for_long_input() -> None:
    digits = [1, 2, 3, 4, 5, 6, 7, 8, 9] * 20
    chi2s = _segment_benford_chi2(digits, n_segments=3)
    assert len(chi2s) == 3


def test_segment_benford_repeated_template_zero_variance() -> None:
    pattern = [1, 2, 3, 4, 5, 6, 7, 8, 9] * 4
    digits = pattern * 3
    chi2s = _segment_benford_chi2(digits, n_segments=3)
    assert len(chi2s) == 3
    # Identical inputs → variance is float-precision zero
    assert float(np.var(chi2s, ddof=1)) < 1e-10


def test_segment_benford_short_input() -> None:
    assert _segment_benford_chi2([1, 2, 3], n_segments=3) == []


# Full detector smoke
def test_a1_detector_emits_new_findings_on_repeated_data() -> None:
    df = pd.DataFrame(
        {
            "col_a": [1.0, 2.0, 3.0] * 25,
            "col_b": [4.0, 5.0, 6.0] * 25,
        }
    )
    detector = A1TerminalDigitDetector()
    result = detector.detect(df, seed=42)
    assert len(result.findings) > 0


def test_a3_detector_catches_multivariate_synthetic() -> None:
    rng = np.random.default_rng(99)
    n = 50
    col1 = rng.normal(5, 1, n)
    col2 = rng.normal(3, 1, n)
    col3 = rng.normal(0, 1, n)
    synth = 2.0 * col1 + col2 - 0.3
    df = pd.DataFrame(
        {"col1": col1, "col2": col2, "col3": col3, "synth": synth}
    )
    detector = A3ArithmeticRelationDetector()
    result = detector.detect(df, seed=42)
    mv_findings = [
        f for f in result.findings if "multivariate" in f.detector_name
    ]
    assert len(mv_findings) >= 1
    assert max(f.severity for f in mv_findings) >= Severity.SUSPICIOUS


def test_a2_detector_does_not_overfire_on_natural() -> None:
    rng = np.random.default_rng(42)
    log_vals = rng.uniform(0, 6, 200)
    df = pd.DataFrame({"x": 10**log_vals})
    detector = A2BenfordDetector()
    result = detector.detect(df, seed=42)
    seg_findings = [
        f for f in result.findings if "segment" in f.detector_name
    ]
    assert seg_findings == [] or all(
        f.severity == Severity.CONCERN for f in seg_findings
    )
