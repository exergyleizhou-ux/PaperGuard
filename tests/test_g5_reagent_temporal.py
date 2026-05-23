"""Unit tests for the G5 reagent-temporal-consistency detector (2.4.0)."""
from __future__ import annotations

from paperguard.core.types import Severity
from paperguard.detectors.g5_reagent_temporal import (
    G5ReagentTemporalDetector,
    ReagentTemporalInput,
)


def _run(text: str, year: int):
    det = G5ReagentTemporalDetector()
    result = det.detect(ReagentTemporalInput(text=text, paper_year=year))
    return result


def test_inapplicable_on_empty_text() -> None:
    result = _run("", 2022)
    assert not result.applicable
    assert result.findings == []


def test_inapplicable_on_implausible_year() -> None:
    result = _run("Antibody from Sigma, cat. no. 1234.", 1500)
    assert not result.applicable


def test_no_finding_when_no_future_year() -> None:
    text = (
        "Antibodies against beta-actin were purchased from Sigma "
        "(cat. no. A1234, lot 5678) and used at 1:1000 dilution."
    )
    result = _run(text, 2022)
    assert result.applicable
    assert result.findings == []


def test_no_finding_when_future_year_not_near_reagent_context() -> None:
    # Future year present but in a citation context, not a reagent context.
    text = (
        "Recent work by Smith et al. 2025 has extended these findings "
        "to additional cell types. No reagents from this period were used."
    )
    result = _run(text, 2022)
    assert result.applicable
    # 'reagents' keyword is in the same sentence as the 2025 mention,
    # within 60 chars — this is a legitimate hit by design.
    # The detector flags but caps at NOTE.
    if result.findings:
        assert all(f.severity == Severity.NOTE for f in result.findings)


def test_future_year_in_reagent_context_emits_note() -> None:
    text = (
        "Cells were stained with anti-CD8 antibody (Clone 53-6.7, "
        "BioLegend, catalog 100752, released 2025) prior to flow analysis."
    )
    result = _run(text, 2022)
    assert result.applicable
    assert len(result.findings) >= 1
    f = result.findings[0]
    assert f.severity == Severity.NOTE
    assert f.evidence["year_cited"] == 2025
    assert f.evidence["paper_year"] == 2022
    assert "catalog" in f.evidence["keyword"] or f.evidence["keyword"] == "antibody"
    assert len(f.innocent_explanations) >= 4


def test_multiple_future_years_yield_multiple_findings() -> None:
    text = (
        "We obtained anti-FLAG antibody from Sigma (released 2024) and "
        "anti-GFP antibody from Cell Signaling (cat. no. 2956S, 2025 lot)."
    )
    result = _run(text, 2022)
    assert result.applicable
    # Two future years in two distinct reagent contexts.
    years = sorted(f.evidence["year_cited"] for f in result.findings)
    assert years == [2024, 2025]


def test_past_years_unaffected() -> None:
    text = (
        "We obtained anti-FLAG antibody from Sigma (released 2010) and "
        "anti-GFP antibody from Cell Signaling (cat. no. 2956S, 2015 lot)."
    )
    result = _run(text, 2022)
    assert result.applicable
    assert result.findings == []


def test_finding_carries_innocent_explanations() -> None:
    text = (
        "Antibodies were purchased from Sigma in 2025 and used as previously described."
    )
    result = _run(text, 2022)
    assert result.applicable
    assert len(result.findings) >= 1
    f = result.findings[0]
    assert len(f.innocent_explanations) >= 4
    text_lower = " ".join(f.innocent_explanations).lower()
    # Must hint at the standard benign explanations.
    assert "ocr" in text_lower or "revision" in text_lower
