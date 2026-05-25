"""W10 — ORCID disambiguation helper tests (mocked, no network)."""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from click.testing import CliRunner

from paperguard.cli import main
from paperguard.fetcher.orcid import (
    OrcidCandidate,
    _build_query,
    disambiguate_author,
)

# --- Unit: _build_query ---


def test_build_query_full_name() -> None:
    q = _build_query("Lei Zhou", None)
    assert "family-name:Zhou" in q
    assert "given-names:Lei" in q


def test_build_query_with_affiliation() -> None:
    q = _build_query("Lei Zhou", "MIT")
    assert "affiliation-org-name:MIT" in q


def test_build_query_single_name() -> None:
    q = _build_query("Zhou", None)
    assert "family-name:Zhou" in q


# --- Unit: disambiguate_author (mocked HTTP) ---


_MOCK_SEARCH_RESPONSE: dict[str, Any] = {
    "expanded-result": [
        {
            "orcid-id": "0000-0001-2345-6789",
            "given-names": "Lei",
            "family-names": "Zhou",
            "institution-name": ["MIT", "Stanford"],
        },
        {
            "orcid-id": "0000-0009-8765-4321",
            "given-names": "Lei",
            "family-names": "Zhou",
            "institution-name": ["Tsinghua"],
        },
    ]
}

_MOCK_WORKS_RESPONSE: dict[str, Any] = {
    "group": [{"work-summary": []}] * 15
}


def test_disambiguate_returns_candidates() -> None:
    mock_client = AsyncMock()
    search_resp = MagicMock()
    search_resp.json.return_value = _MOCK_SEARCH_RESPONSE
    search_resp.raise_for_status = MagicMock()

    works_resp = MagicMock()
    works_resp.json.return_value = _MOCK_WORKS_RESPONSE
    works_resp.raise_for_status = MagicMock()

    mock_client.get = AsyncMock(side_effect=[search_resp, works_resp, works_resp])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    # monotonic calls: initial last_ts=0, then check elapsed before each works fetch
    # Entry 1: last_ts=monotonic()→0, elapsed=mono()→0 - 0=0 < 1 → sleep, last_ts=mono()→2
    # Entry 2: elapsed=mono()→2 - 2=0 < 1 → sleep, last_ts=mono()→4
    mono_values = [0.0] + [float(i) for i in range(0, 20)]
    with patch("paperguard.fetcher.orcid.httpx.AsyncClient", return_value=mock_client):
        with patch("paperguard.fetcher.orcid.time.monotonic", side_effect=mono_values):
            candidates = asyncio.run(disambiguate_author("Lei Zhou"))

    assert len(candidates) == 2
    assert all(isinstance(c, OrcidCandidate) for c in candidates)
    assert candidates[0].works_count == 15


def test_disambiguate_empty_result() -> None:
    mock_client = AsyncMock()
    search_resp = MagicMock()
    search_resp.json.return_value = {"expanded-result": []}
    search_resp.raise_for_status = MagicMock()

    mock_client.get = AsyncMock(return_value=search_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("paperguard.fetcher.orcid.httpx.AsyncClient", return_value=mock_client):
        candidates = asyncio.run(disambiguate_author("Nonexistent Person"))

    assert candidates == []


# --- CLI: `paperguard who` (mocked) ---


def test_who_cli_shows_table() -> None:
    mock_cands = [
        OrcidCandidate(
            orcid_id="0000-0001-2345-6789",
            name="Lei Zhou",
            affiliations=["MIT"],
            works_count=42,
        ),
    ]

    async def _fake(*a: Any, **kw: Any) -> list[OrcidCandidate]:
        return mock_cands

    with patch("paperguard.cli.disambiguate_author", side_effect=_fake):
        runner = CliRunner()
        result = runner.invoke(main, ["who", "Lei Zhou"])

    assert result.exit_code == 0
    assert "0000-0001-2345-6789" in result.output


def test_who_cli_no_results() -> None:
    async def _empty(*a: Any, **kw: Any) -> list[OrcidCandidate]:
        return []

    with patch("paperguard.cli.disambiguate_author", side_effect=_empty):
        runner = CliRunner()
        result = runner.invoke(main, ["who", "Nobody"])

    assert result.exit_code == 0
    assert "No candidates" in result.output


def test_who_cli_with_affiliation() -> None:
    mock_cands = [
        OrcidCandidate(
            orcid_id="0000-0009-8765-4321",
            name="Lei Zhou",
            affiliations=["Tsinghua"],
            works_count=10,
        ),
    ]

    async def _fake(*a: Any, **kw: Any) -> list[OrcidCandidate]:
        return mock_cands

    with patch("paperguard.cli.disambiguate_author", side_effect=_fake):
        runner = CliRunner()
        result = runner.invoke(main, ["who", "Lei Zhou", "--affiliation", "Tsinghua"])

    assert result.exit_code == 0
    assert "Tsinghua" in result.output
