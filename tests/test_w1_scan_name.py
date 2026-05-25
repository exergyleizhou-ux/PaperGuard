"""W1 — Author auto-fetch CLI tests (mocked, no network)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from click.testing import CliRunner

from paperguard.cli import main
from paperguard.core.types import AuditReport, Finding, Severity
from paperguard.fetcher.orcid import OrcidCandidate


@dataclass
class _FakeFetchResult:
    success: bool
    source: str = ""
    sha256: str = ""
    content_type: str = ""


_MOCK_CANDIDATES: list[OrcidCandidate] = [
    OrcidCandidate(
        orcid_id="0000-0001-2345-6789",
        name="Jane Doe",
        affiliations=["MIT"],
        works_count=42,
    ),
    OrcidCandidate(
        orcid_id="0000-0009-8765-4321",
        name="Jane Doe-Smith",
        affiliations=["Stanford"],
        works_count=10,
    ),
]

_MOCK_WORKS: list[dict[str, Any]] = [
    {
        "doi": "https://doi.org/10.1234/paper-a",
        "title": "Study Alpha",
        "best_oa_location": {"pdf_url": "https://example.com/a.pdf"},
    },
]


def _fake_report(file_path: Path, **_kw: Any) -> AuditReport:
    report = AuditReport(paper_identifier=str(file_path), seed=42)
    report.all_findings.append(
        Finding(
            detector_id="A1",
            detector_name="TerminalDigit",
            severity=Severity.NOTE,
            summary="Minor digit anomaly",
            detail="Detailed description for test",
            innocent_explanations=[
                "Rounding artefact",
                "Software truncation",
                "Transcription from source table",
            ],
        ),
    )
    return report


def test_scan_name_basic(tmp_path: Path) -> None:
    """scan-name disambiguates author then scans top candidate."""
    mock_disambiguate = AsyncMock(return_value=_MOCK_CANDIDATES)
    mock_oal = MagicMock()
    mock_oal.get_author_works.return_value = _MOCK_WORKS
    mock_oal.close = MagicMock()

    def fake_fetch(doi: str, dest: Path, **kw: Any) -> _FakeFetchResult:
        dest.write_text("x\n1\n2\n")
        return _FakeFetchResult(success=True, source="mock")

    with (
        patch("paperguard.cli.disambiguate_author", mock_disambiguate),
        patch("paperguard.cli.OpenAlexClient", return_value=mock_oal),
        patch("paperguard.cli.fetch_oa_pdf", side_effect=fake_fetch),
        patch("paperguard.cli._scan_single_file", side_effect=_fake_report),
    ):
        runner = CliRunner()
        out_json = tmp_path / "report.json"
        result = runner.invoke(
            main,
            ["scan-name", "Jane Doe", "--output-json", str(out_json)],
        )

    assert result.exit_code == 0
    assert "0000-0001-2345-6789" in result.output  # picked top candidate
    assert "Author scan complete" in result.output
    assert out_json.exists()
    data = json.loads(out_json.read_text())
    assert data["orcid_id"] == "0000-0001-2345-6789"


def test_scan_name_with_affiliation() -> None:
    """--affiliation is forwarded to disambiguate_author."""
    mock_disambiguate = AsyncMock(return_value=_MOCK_CANDIDATES[:1])
    mock_oal = MagicMock()
    mock_oal.get_author_works.return_value = []
    mock_oal.close = MagicMock()

    with (
        patch("paperguard.cli.disambiguate_author", mock_disambiguate),
        patch("paperguard.cli.OpenAlexClient", return_value=mock_oal),
    ):
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["scan-name", "Jane Doe", "--affiliation", "MIT"],
        )

    assert result.exit_code == 0
    mock_disambiguate.assert_called_once_with("Jane Doe", "MIT")


def test_scan_name_no_candidates() -> None:
    """When ORCID returns no candidates, exit gracefully."""
    mock_disambiguate = AsyncMock(return_value=[])

    with patch("paperguard.cli.disambiguate_author", mock_disambiguate):
        runner = CliRunner()
        result = runner.invoke(main, ["scan-name", "Nobody Real"])

    assert result.exit_code == 0
    assert "No ORCID candidates" in result.output


def test_scan_name_pick_option() -> None:
    """--pick N selects the Nth candidate instead of the top one."""
    mock_disambiguate = AsyncMock(return_value=_MOCK_CANDIDATES)
    mock_oal = MagicMock()
    mock_oal.get_author_works.return_value = []
    mock_oal.close = MagicMock()

    with (
        patch("paperguard.cli.disambiguate_author", mock_disambiguate),
        patch("paperguard.cli.OpenAlexClient", return_value=mock_oal),
    ):
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["scan-name", "Jane Doe", "--pick", "2"],
        )

    assert result.exit_code == 0
    assert "0000-0009-8765-4321" in result.output  # second candidate
