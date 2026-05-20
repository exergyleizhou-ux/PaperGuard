"""测试 A1 末位数字检测器。"""
from __future__ import annotations

import pandas as pd

from paperguard.core.types import Severity
from paperguard.detectors.a1_terminal_digit import A1TerminalDigitDetector


def test_a1_flags_fabricated(fabricated_data: pd.DataFrame) -> None:
    detector = A1TerminalDigitDetector()
    result = detector.detect(fabricated_data, seed=42)

    assert result.applicable
    assert len(result.findings) >= 1, "应至少标记一列末位偏差"

    severities = [f.severity for f in result.findings]
    assert max(severities) >= Severity.CONCERN

    # 2.0.13 加了 Lag-1 autocorr + joint-column findings,这些用不同
    # 的 evidence 键。原 χ² findings 仍然要有 frequency_table。
    chi2_findings = [
        f
        for f in result.findings
        if "frequency_table" in f.evidence
    ]
    assert len(chi2_findings) >= 1, (
        f"expected ≥1 χ² finding with frequency_table; got "
        f"{[f.detector_name for f in result.findings]}"
    )
    for f in chi2_findings:
        assert "n" in f.evidence
        assert f.p_value is not None
        assert f.p_value < 0.01


def test_a1_passes_genuine(genuine_data: pd.DataFrame) -> None:
    detector = A1TerminalDigitDetector()
    result = detector.detect(genuine_data, seed=42)

    assert result.applicable
    severe_findings = [
        f for f in result.findings if f.severity >= Severity.SUSPICIOUS
    ]
    assert len(severe_findings) == 0, (
        f"genuine data was flagged: {[f.summary for f in severe_findings]}"
    )


def test_a1_inapplicable_small_data() -> None:
    detector = A1TerminalDigitDetector()
    tiny = pd.DataFrame({"x": [1.5, 2.5, 3.5]})
    result = detector.detect(tiny, seed=42)
    assert not result.applicable
    assert "N ≥" in (result.skip_reason or "")


def test_a1_no_numeric_columns() -> None:
    detector = A1TerminalDigitDetector()
    df = pd.DataFrame({"name": ["a", "b", "c"]})
    result = detector.detect(df, seed=42)
    assert not result.applicable
