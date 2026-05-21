"""Tests for T6 abstract-only mode (PaperGuard 2.1.3).

Empirically motivated by recall_test_v8: full-text T6 has LR+ ≈ 0
on post-publication Nature-tier retracted papers because copy-editing
removes lexical LLM markers from Methods / Results / Discussion.
The abstract-only mode restricts T6's scan to the abstract +
introduction (the author-written zone least touched by copy-editing).
"""
from __future__ import annotations

import pytest

from paperguard.detectors.t6_ai_text_heuristic import (
    T6AITextHeuristicDetector,
    _abstract_only_enabled,
    _extract_unedited_zone,
)


def test_default_mode_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PAPERGUARD_T6_ABSTRACT_ONLY", raising=False)
    assert _abstract_only_enabled() is False


def test_env_var_enables_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    for val in ("1", "true", "yes", "TRUE"):
        monkeypatch.setenv("PAPERGUARD_T6_ABSTRACT_ONLY", val)
        assert _abstract_only_enabled() is True


def test_extract_unedited_zone_slices_at_methods() -> None:
    text = (
        "Abstract: This study investigates the role of foo.\n"
        "We measured X across Y and found Z. " * 30
        + "\n\nMethods\n"
        + "We sampled N=100 participants. " * 100
    )
    extracted = _extract_unedited_zone(text)
    assert "Abstract" in extracted
    assert "foo" in extracted
    # Methods boilerplate must NOT be in the extracted slice
    assert "sampled N=100" not in extracted


def test_extract_unedited_zone_caps_at_max_chars() -> None:
    text = "Abstract: " + "padding " * 5000
    extracted = _extract_unedited_zone(text, max_chars=2000)
    assert len(extracted) <= 2000


def test_extract_unedited_zone_no_abstract_header_falls_back() -> None:
    text = "Introduction. We study the topic. " * 100
    extracted = _extract_unedited_zone(text, max_chars=1000)
    assert extracted == text[:1000]


def test_extract_unedited_zone_empty() -> None:
    assert _extract_unedited_zone("") == ""


def test_abstract_mode_uses_lower_min_words(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """In abstract-only mode the MIN_WORDS requirement drops to
    MIN_WORDS_ABSTRACT_MODE (150) so short abstracts pass."""
    monkeypatch.setenv("PAPERGUARD_T6_ABSTRACT_ONLY", "1")
    det = T6AITextHeuristicDetector()
    # 200-word abstract — fails default 300-word threshold but should
    # pass the abstract-mode 150-word threshold.
    text = "Abstract: " + " ".join(
        ["word"] * 200
    ) + ". And we examine the system."
    ok, reason = det.check_applicability(text)
    assert ok, reason


def test_full_text_mode_still_requires_300_words(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PAPERGUARD_T6_ABSTRACT_ONLY", raising=False)
    det = T6AITextHeuristicDetector()
    text = " ".join(["word"] * 200)
    ok, reason = det.check_applicability(text)
    assert ok is False
    assert "short" in reason.lower()


def test_abstract_mode_finds_phrase_in_abstract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM-style phrase concentrated in the abstract should fire even
    when surrounded by clean methods boilerplate."""
    monkeypatch.setenv("PAPERGUARD_T6_ABSTRACT_ONLY", "1")
    # Abstract has heavy LLM markers
    abstract = (
        "Abstract\nIn the realm of modern academic inquiry, we delve "
        "into the intricate interplay between robust frameworks and the "
        "multifaceted nature of complex phenomena. This comprehensive "
        "analysis sheds light on the pivotal role of cutting-edge "
        "methodology, underscoring the importance of meticulous data "
        "stewardship. We embark on a journey through the rich tapestry "
        "of empirical findings, leveraging the power of advanced "
        "techniques to unveil novel insights. Our results demonstrate "
        "a paradigm shift in how we navigate the complex landscape of "
        "this emerging field. "
    )
    # Methods section is clean technical writing
    methods = (
        "Methods\nWe sampled N=100 subjects between 2019 and 2023. "
        "Each participant received a 200 ug intraperitoneal injection "
        "of compound A. Behavior was scored every 30 minutes via "
        "automated tracking. Statistics: one-way ANOVA with Tukey HSD "
        "post-hoc, alpha=0.05. " * 20
    )
    det = T6AITextHeuristicDetector()
    result = det.detect(abstract + methods)
    assert result.applicable, result.skip_reason
    # Should fire — abstract-only restricts the scan so the heavy
    # LLM signal in the abstract dominates and methods doesn't dilute.
    assert result.findings, "expected T6 to fire on LLM-heavy abstract"


def test_abstract_mode_skips_methods_dilution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same paper scanned in FULL-TEXT mode has its abstract LLM
    signal diluted by clean methods boilerplate, so density drops.
    Abstract-only mode keeps the signal sharp."""
    abstract = (
        "Abstract\nIn the realm of modern academic inquiry, we delve "
        "into the intricate interplay between robust frameworks. "
        * 4
    )
    methods = (
        "Methods\n"
        + "We sampled N=100 subjects. Each got 200 ug compound A. " * 50
    )
    text = abstract + methods

    # Full-text mode
    monkeypatch.delenv("PAPERGUARD_T6_ABSTRACT_ONLY", raising=False)
    det = T6AITextHeuristicDetector()
    full_result = det.detect(text)
    full_density = 0.0
    for f in full_result.findings:
        if "density" in f.evidence:
            full_density = f.evidence["density"]
            break

    # Abstract-only mode
    monkeypatch.setenv("PAPERGUARD_T6_ABSTRACT_ONLY", "1")
    abs_result = det.detect(text)
    abs_density = 0.0
    for f in abs_result.findings:
        if "density" in f.evidence:
            abs_density = f.evidence["density"]
            break

    # Abstract-only density should be strictly higher (signal is
    # concentrated, not diluted).
    assert abs_density > full_density, (
        f"abstract-only density {abs_density} should exceed "
        f"full-text density {full_density}"
    )
