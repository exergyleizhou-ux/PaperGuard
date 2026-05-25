"""Tests for ORCID disambiguation helper (W10)."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from paperguard.fetcher.orcid import OrcidCandidate, disambiguate_author


def _expanded(entries: list[dict[str, Any]]) -> dict[str, Any]:
    return {"expanded-result": entries, "num-found": len(entries)}


def _works(count: int) -> dict[str, Any]:
    return {"group": [{"work-summary": [{}]} for _ in range(count)]}


def _resp(json_data: dict[str, Any]) -> MagicMock:
    r = MagicMock()
    r.json.return_value = json_data
    r.raise_for_status = MagicMock()
    return r


def _patch_client(side_effect: list[MagicMock]) -> Any:
    """Context manager that patches httpx.AsyncClient + asyncio.sleep."""
    patcher_sleep = patch(
        "paperguard.fetcher.orcid.asyncio.sleep", new_callable=AsyncMock
    )
    patcher_client = patch("paperguard.fetcher.orcid.httpx.AsyncClient")

    class _Ctx:
        def __enter__(self) -> AsyncMock:
            self._sleep = patcher_sleep.__enter__()
            mock_cls = patcher_client.__enter__()
            self._mock = AsyncMock()
            mock_cls.return_value.__aenter__.return_value = self._mock
            mock_cls.return_value.__aexit__.return_value = False
            self._mock.get = AsyncMock(side_effect=side_effect)
            return self._mock

        def __exit__(self, *args: object) -> None:
            patcher_client.__exit__(*args)
            patcher_sleep.__exit__(*args)

    return _Ctx()


@pytest.mark.asyncio
async def test_disambiguate_basic() -> None:
    search_resp = _resp(
        _expanded(
            [
                {
                    "orcid-id": "0000-0001-1234-5678",
                    "given-names": "John",
                    "family-names": "Smith",
                    "institution-name": ["MIT"],
                },
                {
                    "orcid-id": "0000-0002-8765-4321",
                    "given-names": "John",
                    "family-names": "Smith",
                    "institution-name": ["Oxford"],
                },
            ]
        )
    )
    with _patch_client([search_resp, _resp(_works(15)), _resp(_works(8))]):
        candidates = await disambiguate_author("John Smith")

    assert len(candidates) == 2
    assert candidates[0].works_count == 15
    assert candidates[0].orcid_id == "0000-0001-1234-5678"
    assert candidates[1].works_count == 8


@pytest.mark.asyncio
async def test_disambiguate_with_affiliation() -> None:
    search_resp = _resp(
        _expanded(
            [
                {
                    "orcid-id": "0000-0001-1111-2222",
                    "given-names": "Jane",
                    "family-names": "Doe",
                    "institution-name": ["Stanford University"],
                },
            ]
        )
    )
    with _patch_client([search_resp, _resp(_works(20))]) as mock:
        candidates = await disambiguate_author("Jane Doe", affiliation="Stanford")

    assert len(candidates) == 1
    assert candidates[0].affiliations == ["Stanford University"]
    search_call = mock.get.call_args_list[0]
    assert "affiliation-org-name" in str(search_call)


@pytest.mark.asyncio
async def test_disambiguate_no_results() -> None:
    with _patch_client([_resp(_expanded([]))]):
        candidates = await disambiguate_author("Nonexistent Author")

    assert candidates == []


def test_who_cli() -> None:
    from paperguard.cli import main

    mock_candidates = [
        OrcidCandidate(
            orcid_id="0000-0001-1234-5678",
            name="John Smith",
            affiliations=["MIT"],
            works_count=10,
        ),
    ]
    with patch(
        "paperguard.cli.disambiguate_author", new_callable=AsyncMock
    ) as mock_da:
        mock_da.return_value = mock_candidates
        runner = CliRunner()
        result = runner.invoke(main, ["who", "John Smith"])

    assert result.exit_code == 0
    assert "0000-0001-1234-5678" in result.output
    assert "John Smith" in result.output
