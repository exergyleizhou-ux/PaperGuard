"""W3: small-n (10 <= n < threshold) graceful degradation tests.

Verify that A1, A2, A7 detectors:
- Accept data with 10 <= n < original threshold
- Cap severity at NOTE (low-power mode)
- Still skip data with n < 10
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from paperguard.core.types import Severity
from paperguard.detectors.a1_terminal_digit import A1TerminalDigitDetector
from paperguard.detectors.a2_benford import A2BenfordDetector
from paperguard.detectors.a7_last_digit_five_zero import A7LastDigitFiveZeroDetector


def _make_rigged_df(n: int) -> pd.DataFrame:
    """Create a DataFrame with values whose last digits are heavily biased to 0/5."""
    rng = np.random.default_rng(42)
    # All values end in .0 or .5 -> extreme last-digit bias
    base = rng.integers(10, 100, size=n).astype(float)
    base = base + rng.choice([0.0, 0.5], size=n)
    return pd.DataFrame({"val": base})


def _make_benford_rigged(n: int) -> pd.DataFrame:
    """Create values with uniform first-digit distribution (violates Benford).

    Values span >2 decades so Benford applicability is met.
    """
    rng = np.random.default_rng(99)
    # Uniform first digits 1-9, each with random magnitude -> flat distribution
    digits = rng.integers(1, 10, size=n)
    magnitudes = 10.0 ** rng.uniform(0, 3, size=n)
    values = digits * magnitudes
    return pd.DataFrame({"val": values})


# -- A1 TerminalDigit --


class TestA1SmallN:
    def test_a1_small_n_note(self) -> None:
        """With 15 samples (10 <= 15 < 20), A1 should run but cap at NOTE."""
        det = A1TerminalDigitDetector()
        df = _make_rigged_df(15)
        ok, _ = det.check_applicability(df)
        assert ok, "A1 should accept n=15"
        result = det.detect(df)
        # With heavily biased data, should produce findings
        if result.findings:
            for f in result.findings:
                if f.detector_id == "A1" and "Lag-1" not in f.detector_name:
                    assert f.severity == Severity.NOTE, (
                        f"Expected NOTE in low-power, got {f.severity}"
                    )

    def test_a1_skip_below_10(self) -> None:
        """With n=8 (< 10), A1 should report not applicable."""
        det = A1TerminalDigitDetector()
        df = _make_rigged_df(8)
        ok, reason = det.check_applicability(df)
        assert not ok, "A1 should reject n=8"
        assert "10" in reason


# -- A2 Benford --


class TestA2SmallN:
    def test_a2_small_n_note(self) -> None:
        """With 20 samples (10 <= 20 < 50), A2 should run but cap at NOTE."""
        det = A2BenfordDetector()
        df = _make_benford_rigged(20)
        ok, _ = det.check_applicability(df)
        assert ok, "A2 should accept n=20"
        result = det.detect(df)
        if result.findings:
            for f in result.findings:
                if "segment" not in f.detector_name:
                    assert f.severity == Severity.NOTE, (
                        f"Expected NOTE in low-power, got {f.severity}"
                    )

    def test_a2_skip_below_10(self) -> None:
        """With n=8 (< 10), A2 should report not applicable."""
        det = A2BenfordDetector()
        df = _make_benford_rigged(8)
        ok, reason = det.check_applicability(df)
        assert not ok, "A2 should reject n=8"


# -- A7 LastDigitFiveZero --


class TestA7SmallN:
    def test_a7_small_n_note(self) -> None:
        """With 15 samples (10 <= 15 < 30), A7 should run but cap at NOTE."""
        det = A7LastDigitFiveZeroDetector()
        df = _make_rigged_df(15)
        ok, _ = det.check_applicability(df)
        assert ok, "A7 should accept n=15"
        result = det.detect(df)
        if result.findings:
            for f in result.findings:
                assert f.severity == Severity.NOTE, (
                    f"Expected NOTE in low-power, got {f.severity}"
                )

    def test_a7_skip_below_10(self) -> None:
        """With n=8 (< 10), A7 should report not applicable."""
        det = A7LastDigitFiveZeroDetector()
        df = _make_rigged_df(8)
        ok, reason = det.check_applicability(df)
        assert not ok, "A7 should reject n=8"
        assert "10" in reason
