"""测试 A3 列间算术关系检测器。"""
from __future__ import annotations

import pandas as pd

from paperguard.core.types import Severity
from paperguard.detectors.a3_arithmetic import A3ArithmeticRelationDetector


def test_a3_flags_constant_difference(fabricated_data: pd.DataFrame) -> None:
    detector = A3ArithmeticRelationDetector()
    result = detector.detect(fabricated_data, seed=42)

    assert result.applicable
    constant_diff_findings = [
        f
        for f in result.findings
        if "Treatment_OD"
        in str(f.evidence.get("col_a", "")) + str(f.evidence.get("col_b", ""))
        and abs(abs(f.evidence.get("diff_mean", 0)) - 0.3) < 0.01
    ]
    assert len(constant_diff_findings) >= 1
    assert constant_diff_findings[0].severity == Severity.CRITICAL


def test_a3_passes_genuine(genuine_data: pd.DataFrame) -> None:
    detector = A3ArithmeticRelationDetector()
    result = detector.detect(genuine_data, seed=42)

    severe = [f for f in result.findings if f.severity >= Severity.SUSPICIOUS]
    assert len(severe) == 0


def test_a3_inapplicable_single_column() -> None:
    detector = A3ArithmeticRelationDetector()
    df = pd.DataFrame({"x": [1.0, 2.0, 3.0, 4.0, 5.0] * 5})
    result = detector.detect(df, seed=42)
    assert not result.applicable
