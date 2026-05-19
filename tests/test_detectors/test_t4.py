"""T4 tortured-phrases 测试。"""
from __future__ import annotations

from paperguard.core.types import Severity
from paperguard.detectors.t4_tortured_phrases import (
    TORTURED_PHRASES,
    T4TorturedPhrasesDetector,
)


def test_t4_dictionary_nonempty() -> None:
    assert len(TORTURED_PHRASES) >= 40


def test_t4_flags_classic_signature() -> None:
    text = (
        "Our model uses a profound neural organization with attention. "
        "Trained on colossal information from various sensors, the haze "
        "figuring backend predicts user intent. Results show "
        "counterfeit consciousness can match human performance. " * 3
    )
    result = T4TorturedPhrasesDetector().detect(text, seed=42)
    assert result.applicable
    assert len(result.findings) >= 1
    # 4 个不同短语 → CRITICAL
    assert result.findings[0].severity == Severity.CRITICAL


def test_t4_single_hit_suspicious() -> None:
    """1 类短语，单次命中 → SUSPICIOUS。"""
    text = (
        "Our experiment shows that the irregular esteem of the parameter "
        "stabilizes around 0.7 across all trials, validating our model. "
        + "Additional control results follow standard protocols. " * 20
    )
    result = T4TorturedPhrasesDetector().detect(text, seed=42)
    assert result.applicable
    assert len(result.findings) == 1
    # 1 类、1 次 → SUSPICIOUS（< 3 类且 < 5 次）
    assert result.findings[0].severity == Severity.SUSPICIOUS


def test_t4_clean_text_no_findings() -> None:
    text = (
        "Our deep neural network uses big data and cloud computing to "
        "achieve face recognition. Tested with naïve Bayes baseline. " * 5
    )
    result = T4TorturedPhrasesDetector().detect(text, seed=42)
    assert result.applicable
    assert len(result.findings) == 0


def test_t4_inapplicable_short() -> None:
    result = T4TorturedPhrasesDetector().detect("short", seed=42)
    assert not result.applicable
