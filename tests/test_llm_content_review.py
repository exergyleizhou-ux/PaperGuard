"""LLM content reviewer tests (mocked network).

The reviewer is opt-in via PAPERGUARD_LLM_PROVIDER. These tests
verify:

  - Returns None when not configured
  - Returns empty list on too-short input
  - Drops malformed LLM JSON
  - Filters out hallucinated passages (passage not in input text)
  - Filters out out-of-vocabulary categories
  - issues_to_findings produces the right Severity per category
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from paperguard.core.types import Severity
from paperguard.llm.content_review import (
    ContentIssue,
    LLMContentReviewer,
    issues_to_findings,
)


def test_disabled_when_no_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PAPERGUARD_LLM_PROVIDER", raising=False)
    r = LLMContentReviewer()
    assert r.enabled is False
    assert r.review("any text here that is longer than 200 chars " * 10) is None


def test_returns_empty_on_short_text() -> None:
    r = LLMContentReviewer(provider="openai")
    assert r.review("short") == []


def test_drops_malformed_json() -> None:
    r = LLMContentReviewer(provider="openai")
    with patch.object(r, "_call_provider", return_value="not json {{"):
        result = r.review("a" * 500)
    assert result == []


def test_drops_hallucinated_passages() -> None:
    """LLM tried to quote a passage that wasn't in the input."""
    r = LLMContentReviewer(provider="openai")
    text = "We measured X with a precision of 0.01 mg in 50 samples. " * 20
    fake_response = (
        '{"issues": [{"category": "arithmetic", '
        '"passage": "Totally fabricated quote not in input", '
        '"explanation": "made-up issue"}]}'
    )
    with patch.object(r, "_call_provider", return_value=fake_response):
        result = r.review(text)
    assert result == []


def test_keeps_legitimate_passages() -> None:
    r = LLMContentReviewer(provider="openai")
    text = (
        "We measured X with a precision of 0.01 mg in 50 samples. "
        "The mean was 3.14159265358979 mg. "
    ) * 5
    fake = (
        '{"issues": [{"category": "implausible_precision", '
        '"passage": "The mean was 3.14159265358979 mg", '
        '"explanation": "15-digit precision for a 50-sample mean "}]}'
    )
    with patch.object(r, "_call_provider", return_value=fake):
        result = r.review(text)
    assert result is not None
    assert len(result) == 1
    assert result[0].category == "implausible_precision"


def test_drops_invalid_categories() -> None:
    r = LLMContentReviewer(provider="openai")
    text = "x" * 500
    fake = (
        '{"issues": [{"category": "INVENTED_CATEGORY", '
        '"passage": "xxxx", "explanation": "y"}]}'
    )
    with patch.object(r, "_call_provider", return_value=fake):
        result = r.review(text)
    assert result == []


def test_caps_at_5_issues() -> None:
    r = LLMContentReviewer(provider="openai")
    text = "valid passage prefix " * 50
    issues = [
        {
            "category": "arithmetic",
            "passage": "valid passage prefix",
            "explanation": f"issue {i}",
        }
        for i in range(20)
    ]
    fake = '{"issues": ' + str(issues).replace("'", '"') + "}"
    with patch.object(r, "_call_provider", return_value=fake):
        result = r.review(text)
    assert result is not None
    assert len(result) <= 5


def test_issues_to_findings_severity_mapping() -> None:
    issues = [
        ContentIssue(category="arithmetic", passage="x", explanation="y"),
        ContentIssue(category="contradiction", passage="x", explanation="y"),
        ContentIssue(category="missing", passage="x", explanation="y"),
        ContentIssue(category="implausible_precision", passage="x", explanation="y"),
        ContentIssue(category="stat_misuse", passage="x", explanation="y"),
    ]
    findings = issues_to_findings(issues)
    assert len(findings) == 5
    sev_by_cat = {f.evidence["category"]: f.severity for f in findings}
    assert sev_by_cat["arithmetic"] == Severity.SUSPICIOUS
    assert sev_by_cat["contradiction"] == Severity.SUSPICIOUS
    assert sev_by_cat["missing"] == Severity.CONCERN
    assert sev_by_cat["implausible_precision"] == Severity.CONCERN
    assert sev_by_cat["stat_misuse"] == Severity.CONCERN


def test_findings_carry_innocent_explanations() -> None:
    issues = [ContentIssue(category="arithmetic", passage="x", explanation="y")]
    findings = issues_to_findings(issues)
    assert len(findings[0].innocent_explanations) >= 3
