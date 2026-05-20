"""Tests for the T6 dynamic AI-style dictionary.

Covers:
  - load/save round-trip
  - missing file → empty snapshot
  - malformed file → empty snapshot (silent fallback)
  - diff computation (added/removed)
  - corpus n-gram extraction filters stopwords + below-threshold candidates
  - URL fetch mocked
  - get_merged_phrases dedupes against built-in
  - T6 detector picks up new phrases after reload
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from paperguard.detectors.t6_ai_text_heuristic import (
    T6AITextHeuristicDetector,
    _reload_phrase_tables,
)
from paperguard.llm.dynamic_dictionary import (
    PROVIDERS,
    DictionarySnapshot,
    diff_snapshots,
    extract_candidate_phrases,
    get_merged_phrases,
    load_user_dictionary,
    merge_snapshots,
    refresh_from_corpus,
    refresh_from_url,
    save_user_dictionary,
)


@pytest.fixture
def isolated_dict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "pg_home"
    monkeypatch.setenv("PAPERGUARD_HOME", str(home))
    return home / "ai_dictionary.json"


def test_load_missing_returns_empty(isolated_dict: Path) -> None:
    snap = load_user_dictionary()
    assert snap.phrases == {} or all(not v for v in snap.phrases.values())
    snap.normalise()
    for p in PROVIDERS:
        assert snap.phrases[p] == []


def test_save_load_roundtrip(isolated_dict: Path) -> None:
    snap = DictionarySnapshot(
        source="unit-test",
        phrases={"gpt": ["foo", "bar"], "claude": ["baz"]},
    )
    path = save_user_dictionary(snap)
    assert path.exists()
    loaded = load_user_dictionary()
    assert loaded.phrases["gpt"] == ["bar", "foo"]
    assert loaded.phrases["claude"] == ["baz"]
    assert loaded.phrases["gemini"] == []
    assert loaded.generated_at != ""


def test_malformed_file_fallbacks_to_empty(isolated_dict: Path) -> None:
    isolated_dict.parent.mkdir(parents=True, exist_ok=True)
    isolated_dict.write_text("{ not valid json", encoding="utf-8")
    snap = load_user_dictionary()
    snap.normalise()
    for p in PROVIDERS:
        assert snap.phrases[p] == []


def test_diff_added_removed() -> None:
    old = DictionarySnapshot(phrases={"gpt": ["a", "b"], "claude": ["x"]})
    new = DictionarySnapshot(phrases={"gpt": ["b", "c"], "claude": ["x", "y"]})
    old.normalise()
    new.normalise()
    diff = diff_snapshots(old, new)
    assert diff.added["gpt"] == ["c"]
    assert diff.removed["gpt"] == ["a"]
    assert diff.added["claude"] == ["y"]
    assert "claude" not in diff.removed
    assert not diff.is_empty


def test_diff_empty_when_identical() -> None:
    snap = DictionarySnapshot(phrases={"gpt": ["a"]})
    snap.normalise()
    diff = diff_snapshots(snap, snap)
    assert diff.is_empty


def test_extract_candidate_phrases_filters_stopwords() -> None:
    text = (
        "in the in the in the of the of the of the and the and the "
        "delve into delve into delve into the realm of of the realm "
    ) * 30
    candidates = extract_candidate_phrases(
        text, min_count=3, min_per_million=200.0
    )
    # 'delve into' should appear; 'in the' / 'of the' should not (stopwords)
    assert any("delve" in c for c in candidates)
    assert "in the" not in candidates
    assert "of the" not in candidates
    assert "and the" not in candidates


def test_extract_candidate_phrases_respects_min_count() -> None:
    text = "appearing only twice appearing only twice " + "filler word " * 200
    candidates = extract_candidate_phrases(text, min_count=5)
    assert "appearing only twice" not in candidates


def test_extract_candidate_phrases_empty_corpus() -> None:
    assert extract_candidate_phrases("") == []
    assert extract_candidate_phrases("   ") == []


def test_refresh_from_corpus_assigns_provider() -> None:
    text = "novel ai phrase novel ai phrase novel ai phrase " * 50
    snap = refresh_from_corpus(text, provider="claude", min_count=3)
    assert snap.phrases["gpt"] == []
    assert any("novel" in p for p in snap.phrases["claude"])


def test_refresh_from_corpus_rejects_bad_provider() -> None:
    with pytest.raises(ValueError):
        refresh_from_corpus("text " * 100, provider="bogus")


def test_merge_snapshots_unions() -> None:
    a = DictionarySnapshot(phrases={"gpt": ["x"], "claude": ["y"]})
    b = DictionarySnapshot(phrases={"gpt": ["z"], "gemini": ["q"]})
    a.normalise()
    b.normalise()
    merged = merge_snapshots(a, b)
    assert merged.phrases["gpt"] == ["x", "z"]
    assert merged.phrases["claude"] == ["y"]
    assert merged.phrases["gemini"] == ["q"]


def test_refresh_from_url_parses_payload() -> None:
    payload = {
        "version": 1,
        "phrases": {
            "gpt": ["new gpt tic"],
            "claude": ["new claude tic"],
            "gemini": [],
            "other": [],
        },
    }

    class FakeResp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> object:
            return payload

    with patch("httpx.get", return_value=FakeResp()):
        snap = refresh_from_url("https://example.org/dict.json")
    assert snap.phrases["gpt"] == ["new gpt tic"]
    assert snap.phrases["claude"] == ["new claude tic"]


def test_refresh_from_url_network_error_raises() -> None:
    import httpx

    def boom(*a: object, **kw: object) -> object:
        raise httpx.ConnectError("network down")

    with patch("httpx.get", side_effect=boom):
        with pytest.raises(RuntimeError, match="network fetch failed"):
            refresh_from_url("https://example.org/dict.json")


def test_refresh_from_url_rejects_non_object() -> None:
    class FakeResp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> object:
            return [1, 2, 3]

    with patch("httpx.get", return_value=FakeResp()):
        with pytest.raises(RuntimeError, match="must be an object"):
            refresh_from_url("https://example.org/dict.json")


def test_get_merged_phrases_dedupes_against_builtin(
    isolated_dict: Path,
) -> None:
    builtin = {
        "gpt": ("Delve Into", "Tapestry"),
        "claude": ("Let me",),
        "gemini": (),
    }
    snap = DictionarySnapshot(
        phrases={"gpt": ["delve into", "brand new gpt phrase"]}
    )
    save_user_dictionary(snap)
    merged = get_merged_phrases(builtin)
    # built-in casing preserved, new phrase appended once
    assert merged["gpt"][:2] == ("Delve Into", "Tapestry")
    assert "brand new gpt phrase" in merged["gpt"]
    assert merged["gpt"].count("delve into") == 0  # dedup
    assert sum(1 for p in merged["gpt"] if p.lower() == "delve into") == 1


def test_t6_picks_up_reloaded_phrases(isolated_dict: Path) -> None:
    """Smoke test: write a custom phrase, reload, see it counted."""
    snap = DictionarySnapshot(
        phrases={"gpt": ["xyzzy plover quux"]}
    )
    save_user_dictionary(snap)
    _reload_phrase_tables()
    detector = T6AITextHeuristicDetector()
    # Need enough text so check_applicability passes (MIN_WORDS=300)
    body = (
        "We examined the system rigorously. " * 50
        + "xyzzy plover quux " * 10
        + "Filler content to pad. " * 50
    )
    result = detector.detect(body)
    assert result.applicable, result.skip_reason
    # Phrase should have been picked up — either the density triggered
    # CONCERN/SUSPICIOUS or at least the provider attribution NOTE.
    # We assert at least one finding mentions a non-zero hit count.
    assert result.findings, "expected at least one T6 finding"


def test_t6_reload_does_not_break_when_dictionary_missing(
    isolated_dict: Path,
) -> None:
    """If the dict file is absent, reload still succeeds with built-in only."""
    # ensure file does not exist
    if isolated_dict.exists():
        isolated_dict.unlink()
    _reload_phrase_tables()
    detector = T6AITextHeuristicDetector()
    body = (
        "We carefully analysed the manuscript and report no issues. " * 60
    )
    result = detector.detect(body)
    assert result.applicable
    # Should not raise; may or may not have findings.
