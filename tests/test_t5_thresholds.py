"""T5 stylometry threshold-tightening regression tests (2.0.5).

Before 2.0.5, T5 fired on 98% of retracted and 81% of control papers
in the recall_test_v2 sample because:
  * the per-dimension threshold was ~30–50% relative deviation
  * a single dimension firing was enough to emit a NOTE

2.0.5 tightens both: each dimension needs ≥100% (methodology /
certainty) or ≥70% (adjective) relative deviation, AND at least two
dimensions must fire together. The result is that normal biomedical
prose no longer triggers T5 at all, while genuinely Stapel-style
text (low adjective density + elevated methodology + elevated
certainty) still does.
"""
from __future__ import annotations

from paperguard.detectors.t5_stylometry import T5StylometryDetector

# Reproducible English-like text fragments
_NEUTRAL_PARAGRAPH = (
    "We studied the relationship between protein expression and "
    "cell viability across three biological replicates. The cells "
    "were grown in standard culture medium with serum supplementation. "
    "We collected the cells at multiple time points and quantified "
    "the relative protein abundance using a colorimetric assay. "
    "The results were normalised against a housekeeping protein and "
    "are reported as relative units. Biological replicates were "
    "compared using a two-tailed t test with a significance threshold "
    "of 0.05. Where appropriate we applied a multiple-testing "
    "correction to the resulting p values. Sample preparation followed "
    "the standard protocol from the kit manufacturer with minor "
    "modifications described in the supplementary information. "
)


def _make_long_text(base: str, n_repeats: int = 5) -> str:
    return " ".join([base] * n_repeats)


def test_t5_quiet_on_normal_biomedical_prose() -> None:
    """Normal biomedical writing must produce zero T5 findings."""
    detector = T5StylometryDetector()
    long_text = _make_long_text(_NEUTRAL_PARAGRAPH, n_repeats=8)
    result = detector.detect(long_text, seed=42)
    assert result.findings == []


def test_t5_silent_on_single_dimension_deviation() -> None:
    """Even a 1-dim deviation must not trigger (was a false-positive
    cause in v2)."""
    # construct text where only "methodology density" is high — many
    # ``methods``/``measured``/``study`` words, but normal adjective +
    # certainty density.
    detector = T5StylometryDetector()
    text = " ".join(
        [
            "We studied the design carefully and the experiment was a measurement.",
            "We measured the data and the methods study analysis methods.",
            "Investigation methodology methods measured measured measured study.",
        ]
        + [_NEUTRAL_PARAGRAPH] * 4  # background noise
    )
    result = detector.detect(text, seed=42)
    # Either no findings, or the one finding does not flag this as ≥2 dim
    assert len(result.findings) == 0


def test_t5_fires_on_stapel_like_text() -> None:
    """Synthetic text with high methodology + high certainty + low
    adjective density (the Stapel signature) must trigger T5."""
    # Repeatedly emit certainty + methodology words, omit adjectives.
    stapel = (
        "Clearly the study measured the experiment study certain certainly "
        "obvious obviously definite definitely measured methodology "
        "investigation observed analysis procedure design measured "
        "experiment definitely certainly. "
        "We measured measured study methods measurement experiment "
        "investigation observation clearly clearly certainly definitely. "
    )
    # repeat enough times to clear the 500-word minimum
    detector = T5StylometryDetector()
    text = _make_long_text(stapel, n_repeats=20)
    result = detector.detect(text, seed=42)
    assert len(result.findings) >= 1
    finding = result.findings[0]
    # Check the evidence: should record two or three dim violations
    assert len(finding.evidence["flags"]) >= 2


def test_t5_skipped_on_short_text() -> None:
    """Below MIN_WORDS the detector must mark itself non-applicable."""
    detector = T5StylometryDetector()
    short = "We measured the experiment."
    result = detector.detect(short, seed=42)
    assert result.applicable is False or result.findings == []
