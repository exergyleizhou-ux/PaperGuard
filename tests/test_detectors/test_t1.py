"""T1 文本相似度测试。"""
from __future__ import annotations

from paperguard.core.types import Severity
from paperguard.detectors.t1_text_similarity import (
    T1TextSimilarityDetector,
    TextSimilarityInput,
    _jaccard,
    _normalize,
    _shingles,
)


def test_jaccard_basic() -> None:
    assert _jaccard(set(), set()) == 0.0
    assert _jaccard({"a", "b"}, {"a", "b"}) == 1.0
    assert _jaccard({"a", "b"}, {"a", "c"}) == 1 / 3


def test_shingles() -> None:
    words = _normalize("the quick brown fox jumps")
    sh = _shingles(words, n=3)
    assert "the quick brown" in sh
    assert "quick brown fox" in sh
    assert "brown fox jumps" in sh


def test_t1_flags_high_overlap() -> None:
    q = (
        "The mitochondria is the powerhouse of the cell, generating ATP "
        "through oxidative phosphorylation."
    )
    src = (
        "The mitochondria is the powerhouse of the cell, generating ATP "
        "through oxidative phosphorylation. Additional sentence."
    )
    inp = TextSimilarityInput(query_text=q, corpus={"draft_v1": src}, n=4)
    result = T1TextSimilarityDetector().detect(inp, seed=42)
    assert result.applicable
    assert len(result.findings) >= 1
    assert result.findings[0].severity >= Severity.CONCERN


def test_t1_no_finding_on_distinct_text() -> None:
    q = "Photosynthesis occurs in chloroplasts and produces glucose from CO2 and water."
    src = (
        "Quantum entanglement is a phenomenon in physics where particles "
        "become correlated regardless of distance."
    )
    inp = TextSimilarityInput(query_text=q, corpus={"unrelated": src}, n=4)
    result = T1TextSimilarityDetector().detect(inp, seed=42)
    assert result.applicable
    assert len(result.findings) == 0


def test_t1_inapplicable_short_query() -> None:
    inp = TextSimilarityInput(
        query_text="too short", corpus={"x": "y" * 100}, n=5
    )
    result = T1TextSimilarityDetector().detect(inp, seed=42)
    assert not result.applicable
