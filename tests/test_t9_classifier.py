"""Tests for the T9 TF-IDF/LR LLM-text classifier detector.

These run in CI with no GPU and no network: the bundled artifact
(``data/t9_classifier.npz``) and golden fixture are committed. The golden
test proves the shipped artifact reproduces the training-time probabilities
through the pure-NumPy scorer.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from paperguard.core.registry import DetectorRegistry
from paperguard.core.types import Severity
from paperguard.detectors.t9_classifier import (
    T9ClassifierDetector,
    _load_model,
)

_GOLDEN = json.loads(
    (Path(__file__).parent / "fixtures" / "t9_golden.json").read_text(encoding="utf-8")
)
_BANNED = ("fraud", "fabrication", "misconduct", "造假", "学术不端")


def _llm_sample() -> dict:
    return max(_GOLDEN, key=lambda g: g["prob"])


def test_t9_skips_when_not_opted_in(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    monkeypatch.delenv("PAPERGUARD_ML_CHECK", raising=False)
    det = T9ClassifierDetector()
    # Act
    applicable, reason = det.check_applicability("word " * 300)
    # Assert
    assert applicable is False
    assert "opt-in" in reason


def test_t9_skips_short_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAPERGUARD_ML_CHECK", "1")
    det = T9ClassifierDetector()
    applicable, reason = det.check_applicability("only a few words here")
    assert applicable is False
    assert "short" in reason.lower()


def test_t9_golden_probs_match_bundled_artifact() -> None:
    # The shipped artifact + NumPy scorer must reproduce training-time probs.
    model = _load_model()
    assert model is not None, "bundled t9_classifier.npz must load"
    for sample in _GOLDEN:
        assert abs(model.prob_llm(sample["text"]) - sample["prob"]) < 1e-8


def test_t9_flags_llm_text(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange — a high-probability LLM sample, doubled to clear the word floor.
    monkeypatch.setenv("PAPERGUARD_ML_CHECK", "1")
    text = (_llm_sample()["text"] + " ") * 2
    det = T9ClassifierDetector()
    # Act
    result = det.detect(text)
    # Assert
    assert result.applicable is True
    assert result.findings, "expected a finding on high-probability LLM text"
    finding = result.findings[0]
    assert finding.severity >= Severity.SUSPICIOUS
    assert len(finding.innocent_explanations) >= 3  # iron rule


def test_t9_finding_has_no_verdict_language(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAPERGUARD_ML_CHECK", "1")
    text = (_llm_sample()["text"] + " ") * 2
    finding = T9ClassifierDetector().detect(text).findings[0]
    blob = " ".join(
        [finding.summary, finding.detail, finding.applicability_notes]
        + finding.innocent_explanations
    ).lower()
    for word in _BANNED:
        assert word not in blob


def test_t9_registered_in_default_registry() -> None:
    registry = DetectorRegistry().register_default(load_plugins=False)
    assert "T9" in registry._detectors


def test_t9_ml_check_flag_on_all_commands() -> None:
    # The opt-in --ml-check flag must be wired into every text-scan command.
    from click.testing import CliRunner

    from paperguard.cli import batch, notify, scan, scan_pmc

    runner = CliRunner()
    for cmd in (scan, batch, scan_pmc, notify):
        result = runner.invoke(cmd, ["--help"])
        assert result.exit_code == 0
        assert "--ml-check" in result.output
