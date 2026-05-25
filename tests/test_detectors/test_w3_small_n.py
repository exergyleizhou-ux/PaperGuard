"""W3: small-n (10 <= n < 50) graceful degradation tests.

Verify that A1, A2, A7, B5, B7 detectors:
- Accept data with 10 <= n < 50
- Cap severity at NOTE (low-power mode) and set low_power_note=True
- Still skip data with n < 10
- Work normally with n >= 50 (no cap)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from paperguard.core.types import Severity
from paperguard.detectors.a1_terminal_digit import A1TerminalDigitDetector
from paperguard.detectors.a2_benford import A2BenfordDetector
from paperguard.detectors.a7_last_digit_five_zero import A7LastDigitFiveZeroDetector
from paperguard.detectors.b5_tiva import B5TIVADetector, TIVAInput
from paperguard.detectors.b7_pcurve import B7PCurveDetector, PCurveInput


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
        """With 15 samples (10 <= 15 < 50), A1 should run but cap at NOTE."""
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
                    assert f.evidence.get("low_power_note") is True

    def test_a1_skip_below_10(self) -> None:
        """With n=8 (< 10), A1 should report not applicable."""
        det = A1TerminalDigitDetector()
        df = _make_rigged_df(8)
        ok, reason = det.check_applicability(df)
        assert not ok, "A1 should reject n=8"
        assert "10" in reason

    def test_a1_normal_n100(self) -> None:
        """With n=100 (>= 50), A1 should run at normal severity."""
        det = A1TerminalDigitDetector()
        df = _make_rigged_df(100)
        result = det.detect(df)
        assert result.applicable
        if result.findings:
            chi2_findings = [
                f for f in result.findings
                if f.detector_id == "A1" and "Lag-1" not in f.detector_name
                and "joint" not in f.detector_name
            ]
            for f in chi2_findings:
                assert f.evidence.get("low_power_note") is False
                # Severity should NOT be capped — could be CONCERN+
                assert f.severity >= Severity.NOTE


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
                    assert f.evidence.get("low_power_note") is True

    def test_a2_skip_below_10(self) -> None:
        """With n=8 (< 10), A2 should report not applicable."""
        det = A2BenfordDetector()
        df = _make_benford_rigged(8)
        ok, reason = det.check_applicability(df)
        assert not ok, "A2 should reject n=8"

    def test_a2_normal_n100(self) -> None:
        """With n=100 (>= 50), A2 should run at normal severity."""
        det = A2BenfordDetector()
        df = _make_benford_rigged(100)
        result = det.detect(df)
        assert result.applicable
        if result.findings:
            main = [f for f in result.findings if "segment" not in f.detector_name]
            for f in main:
                assert f.evidence.get("low_power_note") is False


# -- A7 LastDigitFiveZero --


class TestA7SmallN:
    def test_a7_small_n_note(self) -> None:
        """With 15 samples (10 <= 15 < 50), A7 should run but cap at NOTE."""
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
                assert f.evidence.get("low_power_note") is True

    def test_a7_skip_below_10(self) -> None:
        """With n=8 (< 10), A7 should report not applicable."""
        det = A7LastDigitFiveZeroDetector()
        df = _make_rigged_df(8)
        ok, reason = det.check_applicability(df)
        assert not ok, "A7 should reject n=8"
        assert "10" in reason

    def test_a7_normal_n100(self) -> None:
        """With n=100 (>= 50), A7 should run at normal severity."""
        det = A7LastDigitFiveZeroDetector()
        df = _make_rigged_df(100)
        result = det.detect(df)
        assert result.applicable
        if result.findings:
            for f in result.findings:
                assert f.evidence.get("low_power_note") is False


# -- B5 TIVA --


class TestB5SmallN:
    def test_b5_small_n_note(self) -> None:
        """With 15 p-values (10 <= 15 < 50), B5 should run but cap at NOTE."""
        # All near 0.05 -> low variance -> should trigger
        ps = [0.045, 0.048, 0.051, 0.049, 0.046, 0.047, 0.050,
              0.044, 0.052, 0.048, 0.046, 0.049, 0.047, 0.051, 0.045]
        inp = TIVAInput(p_values=ps, label="W3-test-15")
        det = B5TIVADetector()
        ok, _ = det.check_applicability(inp)
        assert ok, "B5 should accept n=15"
        result = det.detect(inp)
        if result.findings:
            for f in result.findings:
                assert f.severity <= Severity.NOTE, (
                    f"Expected NOTE max in low-power, got {f.severity}"
                )
                assert f.evidence.get("low_power_note") is True

    def test_b5_skip_below_10(self) -> None:
        """With n=5 (< 10), B5 should report not applicable."""
        ps = [0.01, 0.02, 0.03, 0.04, 0.05]
        inp = TIVAInput(p_values=ps)
        result = B5TIVADetector().detect(inp)
        assert not result.applicable

    def test_b5_normal_n100(self) -> None:
        """With n=100 (>= 50), B5 should run without cap."""
        rng = np.random.default_rng(42)
        # All clustered near 0.05 -> low variance
        ps = (0.048 + rng.normal(0, 0.002, size=100)).clip(0.001, 0.999).tolist()
        inp = TIVAInput(p_values=ps, label="W3-test-100")
        result = B5TIVADetector().detect(inp)
        assert result.applicable
        if result.findings:
            for f in result.findings:
                assert f.evidence.get("low_power_note") is False


# -- B7 P-Curve --


class TestB7SmallN:
    def test_b7_small_n_note(self) -> None:
        """With 15 significant p-values (10 <= 15 < 50), B7 caps at NOTE."""
        # Mostly high p (near 0.05) -> left-skewed -> should trigger
        ps = [0.048, 0.049, 0.046, 0.045, 0.0495, 0.047, 0.046,
              0.0497, 0.044, 0.043, 0.048, 0.049, 0.047, 0.046, 0.001]
        inp = PCurveInput(p_values=ps, label="W3-test-15")
        det = B7PCurveDetector()
        ok, _ = det.check_applicability(inp)
        assert ok, "B7 should accept 15 significant p-values"
        result = det.detect(inp)
        if result.findings:
            for f in result.findings:
                assert f.severity <= Severity.NOTE, (
                    f"Expected NOTE max in low-power, got {f.severity}"
                )
                assert f.evidence.get("low_power_note") is True

    def test_b7_skip_below_10(self) -> None:
        """With n=5 significant p-values (< 10), B7 should skip."""
        ps = [0.01, 0.02, 0.03, 0.04, 0.045]
        inp = PCurveInput(p_values=ps)
        result = B7PCurveDetector().detect(inp)
        assert not result.applicable

    def test_b7_normal_n100(self) -> None:
        """With n>=50 significant p-values, B7 should run without cap."""
        rng = np.random.default_rng(42)
        # Mostly near-alpha -> should trigger concern/suspicious without cap
        ps = (0.047 + rng.normal(0, 0.002, size=60)).clip(0.001, 0.049).tolist()
        inp = PCurveInput(p_values=ps, label="W3-test-60")
        result = B7PCurveDetector().detect(inp)
        assert result.applicable
        if result.findings:
            for f in result.findings:
                assert f.evidence.get("low_power_note") is False
