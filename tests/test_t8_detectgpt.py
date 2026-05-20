"""T8 DetectGPT detector tests (mocked LLM)."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from paperguard.detectors.t8_detectgpt import (
    _RATING_RE,
    T8DetectGPTDetector,
    _segment_text,
    compute_detection_score,
)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PAPERGUARD_DETECTGPT_CHECK", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("PAPERGUARD_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("PAPERGUARD_LLM_MODEL", raising=False)


def _long_text(words: int = 500) -> str:
    base = (
        "We examined the experimental data using a robust statistical "
        "framework. The cohort was sampled across three independent sites. "
        "Outcomes were assessed at six and twelve months. "
    )
    out = ""
    while len(out.split()) < words:
        out += base
    return out


def test_disabled_without_optin() -> None:
    det = T8DetectGPTDetector()
    ok, reason = det.check_applicability(_long_text())
    assert ok is False
    assert "opt-in" in reason


def test_disabled_on_short_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAPERGUARD_DETECTGPT_CHECK", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    det = T8DetectGPTDetector()
    ok, reason = det.check_applicability("Short.")
    assert ok is False
    assert "short" in reason.lower()


def test_disabled_when_api_key_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAPERGUARD_DETECTGPT_CHECK", "1")
    det = T8DetectGPTDetector()
    ok, reason = det.check_applicability(_long_text())
    assert ok is False
    assert "OPENAI_API_KEY" in reason


def test_rating_regex_extracts_plain_int() -> None:
    m = _RATING_RE.search("7")
    assert m and m.group(1) == "7"


def test_rating_regex_extracts_out_of_ten() -> None:
    m = _RATING_RE.search("Score: 8/10")
    assert m and m.group(1) == "8"


def test_rating_regex_extracts_ten() -> None:
    m = _RATING_RE.search("10")
    assert m and m.group(1) == "10"


def test_rating_regex_rejects_eleven() -> None:
    """\\b word boundary blocks "11" from matching as 1 — safer to drop."""
    m = _RATING_RE.search("Score: 11")
    assert m is None


def test_segment_text_splits_on_sentences() -> None:
    text = "First sentence. Second sentence. Third sentence."
    segments = _segment_text(text, max_chars_per_segment=20)
    for s in segments:
        assert s.endswith(".")


def test_critical_when_strongly_negative_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Original rated much higher than paraphrases → strong LM signal."""
    monkeypatch.setenv("PAPERGUARD_DETECTGPT_CHECK", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    # Original gets 9, paraphrases get 5,5,5 → mean 5, stdev 0 → use 0.5 floor
    # score = (5 - 9) / 0.5 = -8.0 → CRITICAL
    score_call_count = [0]

    def fake_score(text: str, **kw: object) -> float:
        score_call_count[0] += 1
        # First call per segment is the original; subsequent are perturbations.
        # Make originals 9, perturbations 5.
        if score_call_count[0] % 4 == 1:
            return 9.0
        return 5.0

    with patch(
        "paperguard.detectors.t8_detectgpt._score_naturalness",
        side_effect=fake_score,
    ), patch(
        "paperguard.detectors.t8_detectgpt._generate_perturbation",
        return_value="paraphrased version of the text " * 30,
    ):
        det = T8DetectGPTDetector()
        result = det.detect(_long_text())
    assert result.applicable, result.skip_reason
    assert result.findings
    assert result.findings[0].severity.name == "CRITICAL"


def test_no_finding_when_score_positive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Paraphrases rated higher than original → human-like."""
    monkeypatch.setenv("PAPERGUARD_DETECTGPT_CHECK", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    score_call_count = [0]

    def fake_score(text: str, **kw: object) -> float:
        score_call_count[0] += 1
        # Original 5, perturbations 8 → (8-5)/0.5 = +6 → no finding
        if score_call_count[0] % 4 == 1:
            return 5.0
        return 8.0

    with patch(
        "paperguard.detectors.t8_detectgpt._score_naturalness",
        side_effect=fake_score,
    ), patch(
        "paperguard.detectors.t8_detectgpt._generate_perturbation",
        return_value="paraphrased version of the text " * 30,
    ):
        det = T8DetectGPTDetector()
        result = det.detect(_long_text())
    assert result.applicable
    assert result.findings == []


def test_inconclusive_when_all_segments_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAPERGUARD_DETECTGPT_CHECK", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    with patch(
        "paperguard.detectors.t8_detectgpt._score_naturalness",
        return_value=None,
    ), patch(
        "paperguard.detectors.t8_detectgpt._generate_perturbation",
        return_value=None,
    ):
        det = T8DetectGPTDetector()
        result = det.detect(_long_text())
    assert result.applicable
    assert len(result.findings) == 1
    assert result.findings[0].evidence.get("outcome") == "no_scores"


def test_compute_detection_score_returns_none_without_key() -> None:
    score, diags = compute_detection_score(_long_text())
    assert score is None
    assert diags == []


def test_innocent_explanations_present_on_finding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAPERGUARD_DETECTGPT_CHECK", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    score_call_count = [0]

    def fake_score(text: str, **kw: object) -> float:
        score_call_count[0] += 1
        if score_call_count[0] % 4 == 1:
            return 9.0
        return 5.0

    with patch(
        "paperguard.detectors.t8_detectgpt._score_naturalness",
        side_effect=fake_score,
    ), patch(
        "paperguard.detectors.t8_detectgpt._generate_perturbation",
        return_value="paraphrased version " * 50,
    ):
        det = T8DetectGPTDetector()
        result = det.detect(_long_text())
    for f in result.findings:
        assert len(f.innocent_explanations) >= 3


def test_t8_no_verdict_language(monkeypatch: pytest.MonkeyPatch) -> None:
    """Privacy iron rule: no verdict words in any finding."""
    forbidden = ("fraud", "fabrication", "misconduct", "造假", "cheating")
    monkeypatch.setenv("PAPERGUARD_DETECTGPT_CHECK", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    score_call_count = [0]

    def fake_score(text: str, **kw: object) -> float:
        score_call_count[0] += 1
        return 9.0 if score_call_count[0] % 4 == 1 else 5.0

    with patch(
        "paperguard.detectors.t8_detectgpt._score_naturalness",
        side_effect=fake_score,
    ), patch(
        "paperguard.detectors.t8_detectgpt._generate_perturbation",
        return_value="paraphrased " * 100,
    ):
        det = T8DetectGPTDetector()
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
            assert word not in bag
