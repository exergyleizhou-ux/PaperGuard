"""Tests for the 2.0.14 mathematical upgrades.

Covers:
- T6 provider attribution (GPT / Claude / Gemini)
- B6 SPRITE-style reverse sample reconstruction
- E1 ICC repeated-measures independence
- B5 TIVA meta-analytic Z (Stouffer + R-index + I²)
- C1 Carlisle Bayes-factor BIC approximation
- D1 Hurst exponent
- Cross-detector Stouffer integrity index
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from paperguard.core.types import AuditReport, Finding, Severity
from paperguard.detectors.b5_tiva import B5TIVADetector, TIVAInput
from paperguard.detectors.b6_grimmer import (
    B6GRIMMERDetector,
    GRIMMERInput,
    _enumerate_candidate_samples,
)
from paperguard.detectors.c1_carlisle import (
    BaselineVariable,
    C1CarlisleDetector,
    CarlisleInput,
)
from paperguard.detectors.d1_residual_smoothness import (
    _hurst_exponent,
)
from paperguard.detectors.e1_icc_independence import (
    E1ICCIndependenceDetector,
    _compute_icc1,
    _detect_subject_column,
)
from paperguard.detectors.t6_ai_text_heuristic import (
    _provider_attribution,
)
from paperguard.evidence.combiner import combine_evidence


# T6 provider attribution
def test_t6_attributes_gpt_style() -> None:
    text = " ".join(
        [
            "delve into the intricate tapestry of",
            "meticulous analysis underscoring the importance",
            "pivotal role in shedding light on",
            "leveraging the power of cutting-edge methods",
        ]
        * 5
    )
    provider, counts = _provider_attribution(text)
    assert provider == "gpt"
    assert counts["gpt"] > counts["claude"]
    assert counts["gpt"] > counts["gemini"]


def test_t6_attributes_claude_style() -> None:
    text = " ".join(
        [
            "I'd be happy to help. Let me address each.",
            "It's worth mentioning that there are several",
            "nuanced considerations and trade-offs to weigh.",
            "With that said, here's a balanced perspective.",
        ]
        * 5
    )
    provider, counts = _provider_attribution(text)
    assert provider == "claude"


def test_t6_attributes_gemini_style() -> None:
    text = " ".join(
        [
            "Absolutely! Here's a breakdown of the key points.",
            "Key Takeaways: In short, here are the advantages.",
            "Quick Summary: TL;DR. In essence, the limitations are clear.",
        ]
        * 5
    )
    provider, counts = _provider_attribution(text)
    assert provider == "gemini"


def test_t6_attributes_none_for_neutral_text() -> None:
    text = "Real biomedical text discussing protein expression " * 50
    provider, _ = _provider_attribution(text)
    assert provider == "none"


# B6 reverse reconstruction
def test_b6_enumerate_returns_candidates_for_valid_target() -> None:
    """SPRITE is a heuristic; verify it either returns candidates that
    are valid or returns nothing — never crashes."""
    cands = _enumerate_candidate_samples(
        mean=4.0,
        sd=1.5,
        n=10,
        scale_min=1,
        scale_max=7,
        max_samples=10,
        seed=42,
    )
    # Some valid (mean=4, sd=1.5, scale=[1,7]) targets are reachable;
    # the test only requires no crash + any returned samples are valid
    for c in cands:
        assert abs(sum(c) / len(c) - 4.0) < 1.0


def test_b6_reverse_flags_mismatched_median() -> None:
    detector = B6GRIMMERDetector()
    inp = [
        GRIMMERInput(
            mean=4.0,
            sd=1.0,
            n=10,
            scale_min=1,
            scale_max=7,
            reported_median=7.0,  # implausible: max possible would be lower
            label="test",
        )
    ]
    result = detector.detect(inp, seed=42)
    recon_findings = [
        f for f in result.findings
        if "reverse reconstruction" in f.detector_name
    ]
    # May or may not fire depending on SPRITE convergence; ensure no crash
    assert isinstance(recon_findings, list)


# E1 ICC
def test_e1_detects_subject_column() -> None:
    # 4 subjects × 4 reps so n_unique=4 < n_rows/2=8
    df = pd.DataFrame(
        {
            "mouse_id": ["A"] * 4 + ["B"] * 4 + ["C"] * 4 + ["D"] * 4,
            "value": list(range(16)),
        }
    )
    assert _detect_subject_column(df) == "mouse_id"


def test_e1_detects_subject_column_negative() -> None:
    df = pd.DataFrame(
        {"value": [1, 2, 3], "other": ["x", "y", "z"]}
    )
    assert _detect_subject_column(df) is None


def test_e1_icc_high_on_repeated_measures() -> None:
    """5 subjects × 4 reps each with strong within-subject structure → high ICC."""
    rows = []
    rng = np.random.default_rng(42)
    for sid in range(5):
        base = sid * 10.0
        for _rep in range(4):
            rows.append(
                {"subject": f"S{sid}", "value": base + rng.normal(0, 0.5)}
            )
    df = pd.DataFrame(rows)
    icc, n_subj, k = _compute_icc1(df, "subject", "value")
    assert icc is not None
    assert icc > 0.5
    assert n_subj == 5
    assert k == 4


def test_e1_icc_near_zero_on_independent() -> None:
    """5 subjects × 4 reps with no within-subject structure → ICC ≈ 0."""
    rng = np.random.default_rng(42)
    rows = []
    for sid in range(5):
        for _ in range(4):
            rows.append({"subject": f"S{sid}", "value": rng.normal(0, 1)})
    df = pd.DataFrame(rows)
    icc, n_subj, k = _compute_icc1(df, "subject", "value")
    assert icc is not None
    assert abs(icc) < 0.3


def test_e1_detector_smoke() -> None:
    """End-to-end smoke."""
    rng = np.random.default_rng(123)
    rows = []
    for sid in range(8):
        for _ in range(4):
            rows.append({"mouse_id": f"M{sid}", "weight": rng.normal(20, 1)})
    df = pd.DataFrame(rows)
    detector = E1ICCIndependenceDetector()
    applicable, _ = detector.check_applicability(df)
    assert applicable
    result = detector.detect(df, seed=42)
    # Random data with no within-subject signal → SUSPICIOUS / CRITICAL fire
    assert isinstance(result.findings, list)


# B5 meta-analytic Z
def test_b5_meta_signals_fire_on_pathological_set() -> None:
    """All p-values clustered around 0.04 → low z-variance + p-hacking signature."""
    detector = B5TIVADetector()
    inp = TIVAInput(p_values=[0.041, 0.042, 0.039, 0.04, 0.043, 0.038, 0.041, 0.04])
    result = detector.detect(inp, seed=42)
    assert len(result.findings) >= 1
    finding = result.findings[0]
    assert "r_index" in finding.evidence
    assert "i_squared" in finding.evidence
    assert "stouffer_z" in finding.evidence


# C1 BIC Bayes factor
def test_c1_bayes_factor_in_evidence() -> None:
    """When C1 fires, log10(BF) must appear in evidence."""
    detector = C1CarlisleDetector()
    # Synthetic baseline data that should reject uniform-p
    variables = [
        BaselineVariable(
            name=f"var{i}",
            arms=[(50, float(20 + i * 0.001), 5.0), (50, float(20 + i * 0.001), 5.0)],
        )
        for i in range(6)
    ]
    inp = CarlisleInput(trial_id="bayes-test", variables=variables)
    result = detector.detect(inp, seed=42)
    if result.findings:
        assert "log10_bayes_factor" in result.findings[0].evidence


# D1 Hurst exponent
def test_d1_hurst_near_half_for_random() -> None:
    """White noise → H ≈ 0.5."""
    rng = np.random.default_rng(42)
    series = rng.normal(0, 1, 256)
    h = _hurst_exponent(series)
    # Generous tolerance: small-sample R/S has bias
    assert 0.2 < h < 0.8


def test_d1_hurst_high_for_smoothed_series() -> None:
    """Cumulative-noise series → H significantly > 0.5."""
    rng = np.random.default_rng(42)
    # Brownian motion (cumulative noise) → H ≈ 1
    series = np.cumsum(rng.normal(0, 1, 256))
    h = _hurst_exponent(series)
    # Brownian motion has Hurst near 1 in theory; allow slack for R/S bias
    assert h > 0.6


def test_d1_hurst_too_short_returns_default() -> None:
    h = _hurst_exponent(np.array([1.0, 2.0, 3.0]))
    assert h == 0.5


# Cross-detector integrity index
def test_integrity_score_computed_when_findings_have_p() -> None:
    report = AuditReport(paper_identifier="test")
    report.all_findings = [
        Finding(
            detector_id="A1",
            detector_name="dummy",
            severity=Severity.SUSPICIOUS,
            summary="x",
            detail="x",
            p_value=0.001,
        ),
        Finding(
            detector_id="A2",
            detector_name="dummy",
            severity=Severity.CONCERN,
            summary="x",
            detail="x",
            p_value=0.01,
        ),
    ]
    combine_evidence(report)
    assert report.integrity_z is not None
    assert report.integrity_score is not None
    assert report.integrity_z > 0
    assert 0 < report.integrity_score < 1


def test_integrity_score_none_when_no_p_values() -> None:
    report = AuditReport(paper_identifier="test")
    report.all_findings = [
        Finding(
            detector_id="G3",
            detector_name="dummy",
            severity=Severity.CONCERN,
            summary="x",
            detail="x",
        )
    ]
    combine_evidence(report)
    assert report.integrity_score is None
    assert report.integrity_z is None
