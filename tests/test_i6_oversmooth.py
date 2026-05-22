"""Tests for I6 trend over-smoothness detector."""
from __future__ import annotations

import numpy as np
import pandas as pd

from paperguard.detectors.i6_trend_oversmooth import (
    I6TrendOversmoothDetector,
    TrendSmoothnessInput,
)


def _real_noisy_trend(n: int = 200) -> pd.DataFrame:
    """Realistic DCS trend: slow drift + 2% Gaussian noise."""
    rng = np.random.default_rng(42)
    t = np.arange(n) / n
    signal = 80 + 5 * np.sin(2 * np.pi * t * 2)  # slow oscillation
    noise = rng.normal(0, 1.5, n)
    return pd.DataFrame({"temp_C": signal + noise})


def _perfectly_smooth_curve(n: int = 200) -> pd.DataFrame:
    """Painted-by-Excel: pure sine wave, no noise."""
    t = np.arange(n) / n
    return pd.DataFrame({"temp_C": 80 + 5 * np.sin(2 * np.pi * t * 2)})


def _linear_ramp(n: int = 200) -> pd.DataFrame:
    """Linear ramp = all Δx identical → CRITICAL."""
    return pd.DataFrame({"temp_C": np.linspace(50, 100, n)})


def _setpoint_constant(n: int = 200) -> pd.DataFrame:
    """Constant setpoint — std(x)=0; detector should skip."""
    return pd.DataFrame({"temp_C": [85.0] * n})


def test_real_noisy_trend_no_finding() -> None:
    det = I6TrendOversmoothDetector()
    result = det.detect(TrendSmoothnessInput(df=_real_noisy_trend(), column="temp_C"))
    assert result.applicable
    assert result.findings == []


def test_perfectly_smooth_curve_fires() -> None:
    det = I6TrendOversmoothDetector()
    result = det.detect(
        TrendSmoothnessInput(df=_perfectly_smooth_curve(), column="temp_C")
    )
    assert result.findings
    assert result.findings[0].severity.name in {"SUSPICIOUS", "CONCERN", "CRITICAL"}


def test_linear_ramp_fires_critical() -> None:
    det = I6TrendOversmoothDetector()
    result = det.detect(TrendSmoothnessInput(df=_linear_ramp(), column="temp_C"))
    assert result.findings
    assert result.findings[0].severity.name == "CRITICAL"


def test_constant_setpoint_skipped() -> None:
    """std(x)=0 → can't compute noise ratio → no finding."""
    det = I6TrendOversmoothDetector()
    result = det.detect(
        TrendSmoothnessInput(df=_setpoint_constant(), column="temp_C")
    )
    assert result.applicable
    assert result.findings == []


def test_missing_column_not_applicable() -> None:
    det = I6TrendOversmoothDetector()
    df = pd.DataFrame({"other": [1.0] * 100})
    ok, reason = det.check_applicability(TrendSmoothnessInput(df=df, column="temp_C"))
    assert ok is False
    assert "missing" in reason


def test_short_trend_not_applicable() -> None:
    det = I6TrendOversmoothDetector()
    df = pd.DataFrame({"temp_C": [85.0, 85.1, 85.2]})
    ok, _ = det.check_applicability(TrendSmoothnessInput(df=df, column="temp_C"))
    assert ok is False


def test_innocent_explanations_count() -> None:
    det = I6TrendOversmoothDetector()
    result = det.detect(
        TrendSmoothnessInput(df=_perfectly_smooth_curve(), column="temp_C")
    )
    for f in result.findings:
        assert len(f.innocent_explanations) >= 4


def test_no_verdict_words() -> None:
    det = I6TrendOversmoothDetector()
    result = det.detect(
        TrendSmoothnessInput(df=_perfectly_smooth_curve(), column="temp_C")
    )
    forbidden = ("fraud", "fabrication", "misconduct", "造假", "cheating")
    for f in result.findings:
        bag = (f.summary + " " + f.detail + " " + " ".join(f.innocent_explanations)).lower()
        for w in forbidden:
            assert w not in bag
