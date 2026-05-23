"""T7 perplexity detector tests (mocked LLM).

Covers:
  - Skipped when PAPERGUARD_PERPLEXITY_CHECK is unset
  - Skipped on short text
  - Skipped when OPENAI_API_KEY missing
  - Low perplexity → CRITICAL / SUSPICIOUS / NOTE tiers
  - High perplexity → no finding
  - API failure → NOTE-level inconclusive
  - Segment splitter respects sentence boundaries
"""
from __future__ import annotations

import math
from unittest.mock import patch

import pytest

from paperguard.detectors.t7_perplexity import (
    T7PerplexityDetector,
    _logprobs_to_perplexity,
    _segment_text,
    compute_perplexity,
)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PAPERGUARD_PERPLEXITY_CHECK", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("PAPERGUARD_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("PAPERGUARD_LLM_MODEL", raising=False)


def _long_text(words: int = 600) -> str:
    base = (
        "We examined the experimental data using a robust statistical "
        "framework that combined classical hypothesis testing with modern "
        "Bayesian inference techniques. The cohort was sampled across "
        "three independent sites between 2019 and 2023. "
    )
    out = ""
    while len(out.split()) < words:
        out += base
    return out


def test_disabled_without_optin() -> None:
    det = T7PerplexityDetector()
    ok, reason = det.check_applicability(_long_text())
    assert ok is False
    assert "opt-in" in reason


def test_disabled_on_short_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAPERGUARD_PERPLEXITY_CHECK", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    det = T7PerplexityDetector()
    ok, reason = det.check_applicability("Short sentence.")
    assert ok is False
    assert "short" in reason.lower()


def test_disabled_when_api_key_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAPERGUARD_PERPLEXITY_CHECK", "1")
    det = T7PerplexityDetector()
    ok, reason = det.check_applicability(_long_text())
    assert ok is False
    assert "OPENAI_API_KEY" in reason


def test_logprobs_to_perplexity() -> None:
    # logprobs are natural log; -1 per token → perplexity e^1 ≈ 2.718
    p = _logprobs_to_perplexity([-1.0, -1.0, -1.0])
    assert math.isclose(p, math.e, rel_tol=1e-6)
    # Empty list → +inf
    assert _logprobs_to_perplexity([]) == float("inf")


def test_segment_text_respects_sentences() -> None:
    text = "First sentence. Second sentence. Third sentence."
    segments = _segment_text(text, max_chars_per_segment=20)
    # Each segment ends on a period
    for s in segments:
        assert s.endswith(".")
    # Concatenation matches the original (modulo whitespace)
    rebuilt = " ".join(segments)
    assert rebuilt.replace(" ", "") == text.replace(" ", "")


def test_segment_text_empty() -> None:
    assert _segment_text("") == []
    assert _segment_text("   ") == []


def test_critical_when_perplexity_very_low(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAPERGUARD_PERPLEXITY_CHECK", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    # logprob -0.5 per token → perplexity ≈ 1.65 → CRITICAL
    with patch(
        "paperguard.detectors.t7_perplexity._call_openai_logprobs",
        return_value=[-0.5] * 20,
    ):
        det = T7PerplexityDetector()
        result = det.detect(_long_text())
    assert result.applicable, result.skip_reason
    assert len(result.findings) == 1
    f = result.findings[0]
    assert f.severity.name == "CRITICAL"
    assert f.test_statistic is not None
    assert f.test_statistic < 5.0


def test_suspicious_tier(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAPERGUARD_PERPLEXITY_CHECK", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    # -2 / token → perplexity ≈ 7.39 → SUSPICIOUS (between 5 and 10)
    with patch(
        "paperguard.detectors.t7_perplexity._call_openai_logprobs",
        return_value=[-2.0] * 20,
    ):
        det = T7PerplexityDetector()
        result = det.detect(_long_text())
    assert result.findings
    assert result.findings[0].severity.name == "SUSPICIOUS"


def test_note_tier(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAPERGUARD_PERPLEXITY_CHECK", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    # -2.8 / token → ppl ≈ 16.4 → NOTE (between 10 and 20)
    with patch(
        "paperguard.detectors.t7_perplexity._call_openai_logprobs",
        return_value=[-2.8] * 20,
    ):
        det = T7PerplexityDetector()
        result = det.detect(_long_text())
    assert result.findings
    assert result.findings[0].severity.name == "NOTE"


def test_no_finding_when_perplexity_high(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAPERGUARD_PERPLEXITY_CHECK", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    # -4 / token → ppl ≈ 54.6 → no finding
    with patch(
        "paperguard.detectors.t7_perplexity._call_openai_logprobs",
        return_value=[-4.0] * 20,
    ):
        det = T7PerplexityDetector()
        result = det.detect(_long_text())
    assert result.applicable
    assert result.findings == []


def test_api_failure_yields_inconclusive_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAPERGUARD_PERPLEXITY_CHECK", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    # The provider call returns None for every segment.
    with patch(
        "paperguard.detectors.t7_perplexity._call_openai_logprobs",
        return_value=None,
    ):
        det = T7PerplexityDetector()
        result = det.detect(_long_text())
    assert result.applicable
    assert len(result.findings) == 1
    f = result.findings[0]
    assert f.severity.name == "NOTE"
    assert "inconclusive" in f.applicability_notes.lower()
    assert f.evidence.get("outcome") == "api_no_logprobs"


def test_compute_perplexity_helper_returns_none_without_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert compute_perplexity(_long_text()) is None




def test_finding_has_innocent_explanations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Privacy rule: every Finding must have ≥3 innocent explanations."""
    monkeypatch.setenv("PAPERGUARD_PERPLEXITY_CHECK", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    with patch(
        "paperguard.detectors.t7_perplexity._call_openai_logprobs",
        return_value=[-1.0] * 20,
    ):
        det = T7PerplexityDetector()
        result = det.detect(_long_text())
    for f in result.findings:
        assert len(f.innocent_explanations) >= 3, (
            f"Finding {f.summary!r} has too few innocent explanations"
        )


def test_t7_does_not_say_fraud(monkeypatch: pytest.MonkeyPatch) -> None:
    """Privacy iron rule: no verdict language."""
    forbidden = ("fraud", "fabrication", "misconduct", "造假", "cheating")
    monkeypatch.setenv("PAPERGUARD_PERPLEXITY_CHECK", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    with patch(
        "paperguard.detectors.t7_perplexity._call_openai_logprobs",
        return_value=[-1.0] * 20,
    ):
        det = T7PerplexityDetector()
        result = det.detect(_long_text())
    for f in result.findings:
        bag = (
            f.summary
            + " "
            + f.detail
            + " "
            + " ".join(f.innocent_explanations)
        ).lower()
        for word in forbidden:
            assert word not in bag, f"Forbidden word {word!r} in T7 finding"


# ---------------------------------------------------------------------------
# 2.4.2 — PAPERGUARD_T7_INVERT_THRESHOLD
# ---------------------------------------------------------------------------


def test_inverted_mode_high_perplexity_triggers_critical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAPERGUARD_PERPLEXITY_CHECK", "1")
    monkeypatch.setenv("PAPERGUARD_T7_INVERT_THRESHOLD", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    # logprob -0.55 / token → perplexity ≈ 1.73 → inverted CRITICAL (> 1.70)
    with patch(
        "paperguard.detectors.t7_perplexity._call_openai_logprobs",
        return_value=[-0.55] * 20,
    ):
        det = T7PerplexityDetector()
        result = det.detect(_long_text())
    assert result.applicable
    assert len(result.findings) == 1
    f = result.findings[0]
    assert f.severity.name == "CRITICAL"
    assert f.evidence["inverted_threshold_mode"] is True
    # inverted summary mentions the > sign
    assert "inverted-mode" in f.summary or "inverted" in f.detail


def test_inverted_mode_low_perplexity_no_finding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """In inverted mode, low ppl (canonical AI signal) must NOT fire."""
    monkeypatch.setenv("PAPERGUARD_PERPLEXITY_CHECK", "1")
    monkeypatch.setenv("PAPERGUARD_T7_INVERT_THRESHOLD", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    # logprob -0.1 / token → perplexity ≈ 1.10 → below the inverted NOTE
    # threshold (1.46), so no finding in inverted mode.
    with patch(
        "paperguard.detectors.t7_perplexity._call_openai_logprobs",
        return_value=[-0.1] * 20,
    ):
        det = T7PerplexityDetector()
        result = det.detect(_long_text())
    assert result.applicable
    assert result.findings == []


def test_inverted_mode_note_tier(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAPERGUARD_PERPLEXITY_CHECK", "1")
    monkeypatch.setenv("PAPERGUARD_T7_INVERT_THRESHOLD", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    # logprob -0.4 / token → perplexity ≈ 1.49 → between NOTE 1.46 and
    # SUSPICIOUS 1.56 in inverted mode.
    with patch(
        "paperguard.detectors.t7_perplexity._call_openai_logprobs",
        return_value=[-0.40] * 20,
    ):
        det = T7PerplexityDetector()
        result = det.detect(_long_text())
    assert result.findings
    assert result.findings[0].severity.name == "NOTE"


def test_classical_mode_unaffected_by_invert_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sanity: classical-mode behaviour unchanged when env var unset."""
    monkeypatch.setenv("PAPERGUARD_PERPLEXITY_CHECK", "1")
    monkeypatch.delenv("PAPERGUARD_T7_INVERT_THRESHOLD", raising=False)
    monkeypatch.delenv("PAPERGUARD_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("PAPERGUARD_LLM_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    # logprob -0.55 / token → ppl 1.73 → classical CRITICAL (< 5)
    with patch(
        "paperguard.detectors.t7_perplexity._call_openai_logprobs",
        return_value=[-0.55] * 20,
    ):
        det = T7PerplexityDetector()
        result = det.detect(_long_text())
    assert result.findings
    f = result.findings[0]
    assert f.severity.name == "CRITICAL"
    assert f.evidence["inverted_threshold_mode"] is False


# ---------------------------------------------------------------------------
# 2.6.0 — endpoint-based auto-detect (PAPERGUARD_LLM_BASE_URL + MODEL)
# ---------------------------------------------------------------------------


def test_auto_detect_openai_gpt4o_enables_inverted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OpenAI + gpt-4o → auto-detect picks inverted mode."""
    from paperguard.detectors.t7_perplexity import _invert_enabled

    monkeypatch.delenv("PAPERGUARD_T7_INVERT_THRESHOLD", raising=False)
    monkeypatch.setenv("PAPERGUARD_LLM_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("PAPERGUARD_LLM_MODEL", "gpt-4o")
    assert _invert_enabled() is True


def test_auto_detect_openai_gpt35_enables_inverted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from paperguard.detectors.t7_perplexity import _invert_enabled

    monkeypatch.delenv("PAPERGUARD_T7_INVERT_THRESHOLD", raising=False)
    monkeypatch.setenv("PAPERGUARD_LLM_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("PAPERGUARD_LLM_MODEL", "gpt-3.5-turbo")
    assert _invert_enabled() is True


def test_auto_detect_openai_o1_does_not_invert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """o1 / o3-mini / o4-mini are reasoning models that API-block logprobs.

    Auto-detect should NOT enable inverted mode for them — they cannot
    actually run T7 at all, but if someone tries, classical mode is the
    safer fallback (returns no finding rather than a misleading inverted
    one). The detector itself will then no-op on the API 400.
    """
    from paperguard.detectors.t7_perplexity import _invert_enabled

    monkeypatch.delenv("PAPERGUARD_T7_INVERT_THRESHOLD", raising=False)
    monkeypatch.setenv("PAPERGUARD_LLM_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("PAPERGUARD_LLM_MODEL", "o1")
    assert _invert_enabled() is False


def test_auto_detect_groq_qwen_does_not_invert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Groq's qwen3-32b is the lone textbook-direction data point (2.5.1)."""
    from paperguard.detectors.t7_perplexity import _invert_enabled

    monkeypatch.delenv("PAPERGUARD_T7_INVERT_THRESHOLD", raising=False)
    monkeypatch.setenv("PAPERGUARD_LLM_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("PAPERGUARD_LLM_MODEL", "qwen/qwen3-32b")
    assert _invert_enabled() is False


def test_explicit_override_beats_auto_detect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PAPERGUARD_T7_INVERT_THRESHOLD=0 overrides auto-detect even on OpenAI."""
    from paperguard.detectors.t7_perplexity import _invert_enabled

    monkeypatch.setenv("PAPERGUARD_LLM_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("PAPERGUARD_LLM_MODEL", "gpt-4o")
    # Force off — auto-detect would have said True.
    monkeypatch.setenv("PAPERGUARD_T7_INVERT_THRESHOLD", "0")
    assert _invert_enabled() is False
    # Force on — auto-detect would also say True; check explicit still wins.
    monkeypatch.setenv("PAPERGUARD_T7_INVERT_THRESHOLD", "1")
    assert _invert_enabled() is True
