"""W4 — Chinese database integration tests (mocked, no network)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from paperguard.cli import main
from paperguard.fetcher.semantic_scholar import (
    ScholarPaper,
    SemanticScholarClient,
)

# ---- mock data -------------------------------------------------------------

_MOCK_API_RESPONSE: dict[str, Any] = {
    "total": 2,
    "data": [
        {
            "paperId": "abc123",
            "externalIds": {"DOI": "10.1000/test-cn-1"},
            "title": "基于深度学习的图像分类研究",
            "authors": [
                {"name": "张三"},
                {"name": "李四"},
            ],
            "year": 2023,
            "venue": "计算机学报",
            "citationCount": 15,
            "isOpenAccess": True,
        },
        {
            "paperId": "def456",
            "externalIds": {},
            "title": "A Study on Neural Networks",
            "authors": [{"name": "Wang Wu"}],
            "year": 2022,
            "venue": "IEEE Access",
            "citationCount": 8,
            "isOpenAccess": False,
        },
    ],
}


# ---- unit tests: SemanticScholarClient -------------------------------------

def test_parse_paper() -> None:
    """_parse converts raw API dict to ScholarPaper."""
    raw = _MOCK_API_RESPONSE["data"][0]
    paper = SemanticScholarClient._parse(raw)
    assert paper.paper_id == "abc123"
    assert paper.doi == "10.1000/test-cn-1"
    assert paper.title == "基于深度学习的图像分类研究"
    assert paper.authors == ["张三", "李四"]
    assert paper.year == 2023
    assert paper.venue == "计算机学报"
    assert paper.citation_count == 15
    assert paper.is_open_access is True


def test_parse_paper_missing_doi() -> None:
    """Papers without DOI get empty string."""
    raw = _MOCK_API_RESPONSE["data"][1]
    paper = SemanticScholarClient._parse(raw)
    assert paper.doi == ""
    assert paper.is_open_access is False


def test_search_returns_papers() -> None:
    """search() parses API response into ScholarPaper list."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = _MOCK_API_RESPONSE
    mock_resp.raise_for_status = MagicMock()

    client = SemanticScholarClient()
    with patch.object(client._client, "get", return_value=mock_resp):
        results = client.search("深度学习")
    client.close()

    assert len(results) == 2
    assert results[0].title == "基于深度学习的图像分类研究"
    assert results[1].title == "A Study on Neural Networks"


def test_search_empty_response() -> None:
    """search() returns empty list when no results."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"total": 0, "data": []}
    mock_resp.raise_for_status = MagicMock()

    client = SemanticScholarClient()
    with patch.object(client._client, "get", return_value=mock_resp):
        results = client.search("nonexistent query xyz")
    client.close()

    assert results == []


def test_search_http_error_returns_empty() -> None:
    """search() returns empty list on HTTP error."""
    import httpx

    client = SemanticScholarClient()
    with patch.object(
        client._client,
        "get",
        side_effect=httpx.ConnectError("network error"),
    ):
        results = client.search("test")
    client.close()

    assert results == []


def test_get_paper_by_doi() -> None:
    """get_paper() looks up a single paper by DOI."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = _MOCK_API_RESPONSE["data"][0]
    mock_resp.raise_for_status = MagicMock()

    client = SemanticScholarClient()
    with patch.object(client._client, "get", return_value=mock_resp):
        paper = client.get_paper("10.1000/test-cn-1")
    client.close()

    assert paper is not None
    assert paper.doi == "10.1000/test-cn-1"


# ---- CLI tests: search-cn -------------------------------------------------

def test_search_cn_basic() -> None:
    """search-cn prints a table of results."""
    mock_client = MagicMock()
    mock_client.search.return_value = [
        ScholarPaper(
            paper_id="abc123",
            title="基于深度学习的图像分类研究",
            doi="10.1000/test-cn-1",
            authors=["张三", "李四"],
            year=2023,
            venue="计算机学报",
            citation_count=15,
            is_open_access=True,
        ),
    ]

    with patch(
        "paperguard.cli.SemanticScholarClient",
        return_value=mock_client,
    ):
        runner = CliRunner()
        result = runner.invoke(main, ["search-cn", "深度学习"])

    assert result.exit_code == 0
    assert "1 results" in result.output


def test_search_cn_no_results() -> None:
    """search-cn shows message when no papers found."""
    mock_client = MagicMock()
    mock_client.search.return_value = []

    with patch(
        "paperguard.cli.SemanticScholarClient",
        return_value=mock_client,
    ):
        runner = CliRunner()
        result = runner.invoke(main, ["search-cn", "zzzznothing"])

    assert result.exit_code == 0
    assert "No papers found" in result.output


def test_search_cn_output_json(tmp_path: Path) -> None:
    """search-cn --output-json writes structured JSON."""
    mock_client = MagicMock()
    mock_client.search.return_value = [
        ScholarPaper(
            paper_id="abc123",
            title="Test Paper",
            doi="10.1000/x",
            authors=["Author A"],
            year=2024,
            venue="Test Journal",
            citation_count=5,
            is_open_access=False,
        ),
    ]

    out = tmp_path / "results.json"
    with patch(
        "paperguard.cli.SemanticScholarClient",
        return_value=mock_client,
    ):
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["search-cn", "test", "--output-json", str(out)],
        )

    assert result.exit_code == 0
    assert out.exists()
    data = json.loads(out.read_text())
    assert len(data) == 1
    assert data[0]["doi"] == "10.1000/x"
    assert data[0]["title"] == "Test Paper"


def test_search_cn_year_filter() -> None:
    """--year option is forwarded to the client."""
    mock_client = MagicMock()
    mock_client.search.return_value = []

    with patch(
        "paperguard.cli.SemanticScholarClient",
        return_value=mock_client,
    ):
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["search-cn", "neural", "--year", "2020-2023"],
        )

    assert result.exit_code == 0
    mock_client.search.assert_called_once_with(
        "neural", limit=20, year="2020-2023",
    )
