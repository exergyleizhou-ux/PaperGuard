"""W7 — Batch author audit CLI tests (mocked, no network)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from paperguard.cli import main
from paperguard.core.types import AuditReport, Finding, Severity


@dataclass
class _FakeFetchResult:
    success: bool
    source: str = ""
    sha256: str = ""
    content_type: str = ""


_MOCK_WORKS: list[dict[str, Any]] = [
    {
        "doi": "https://doi.org/10.1234/test-paper-1",
        "title": "A Study on Something",
        "best_oa_location": {"pdf_url": "https://example.com/1.pdf"},
    },
    {
        "doi": "https://doi.org/10.1234/test-paper-2",
        "title": "Another Study",
        "best_oa_location": {"pdf_url": "https://example.com/2.pdf"},
    },
    {
        "doi": None,
        "title": "No DOI Paper",
        "best_oa_location": None,
    },
]


def _make_fake_pdf(dest: Path) -> None:
    """Write a minimal file so fetch_oa_pdf side_effect has something."""
    dest.write_text("x,y\n1.23,4.56\n7.89,0.12\n")


def _fake_report(file_path: Path, **_kw: Any) -> AuditReport:
    """Return a minimal AuditReport with one dummy finding."""
    report = AuditReport(paper_identifier=str(file_path), seed=42)
    report.all_findings.append(
        Finding(
            detector_id="B4",
            detector_name="StatCheck",
            severity=Severity.NOTE,
            summary="Dummy finding for test",
            detail="Detailed description of finding",
            innocent_explanations=[
                "Rounding in source data",
                "Software version difference",
                "Transcription from original table",
            ],
        ),
    )
    return report


def test_scan_author_basic(tmp_path: Path) -> None:
    """scan-author fetches works, downloads PDFs, scans them."""
    mock_oal = MagicMock()
    mock_oal.get_author_works.return_value = _MOCK_WORKS
    mock_oal.close = MagicMock()

    def fake_fetch(doi: str, dest: Path, **kw: Any) -> _FakeFetchResult:
        _make_fake_pdf(dest)
        return _FakeFetchResult(success=True, source="mock")

    with (
        patch("paperguard.cli.OpenAlexClient", return_value=mock_oal),
        patch("paperguard.cli.fetch_oa_pdf", side_effect=fake_fetch),
        patch("paperguard.cli._scan_single_file", side_effect=_fake_report),
    ):
        runner = CliRunner()
        out_json = tmp_path / "report.json"
        result = runner.invoke(
            main,
            ["scan-author", "0009-0000-9073-1349", "--output-json", str(out_json)],
        )

    assert result.exit_code == 0
    assert "Author scan complete" in result.output
    assert "2 scanned" in result.output
    assert out_json.exists()
    data = json.loads(out_json.read_text())
    assert data["orcid_id"] == "0009-0000-9073-1349"
    assert data["papers_scanned"] == 2


def test_scan_author_no_works() -> None:
    """When no works found, print message and exit 0."""
    mock_oal = MagicMock()
    mock_oal.get_author_works.return_value = []
    mock_oal.close = MagicMock()

    with patch("paperguard.cli.OpenAlexClient", return_value=mock_oal):
        runner = CliRunner()
        result = runner.invoke(main, ["scan-author", "0000-0000-0000-0000"])

    assert result.exit_code == 0
    assert "No works found" in result.output


def test_scan_author_pdf_fetch_fails() -> None:
    """When PDF fetch fails, skip the paper gracefully."""
    mock_oal = MagicMock()
    mock_oal.get_author_works.return_value = _MOCK_WORKS[:1]
    mock_oal.close = MagicMock()

    def fail_fetch(doi: str, dest: Path, **kw: Any) -> _FakeFetchResult:
        return _FakeFetchResult(success=False)

    with (
        patch("paperguard.cli.OpenAlexClient", return_value=mock_oal),
        patch("paperguard.cli.fetch_oa_pdf", side_effect=fail_fetch),
    ):
        runner = CliRunner()
        result = runner.invoke(main, ["scan-author", "0000-0001-2345-6789"])

    assert result.exit_code == 0
    assert "0 scanned" in result.output
    assert "1 skipped" in result.output


def test_scan_author_no_anomalies(tmp_path: Path) -> None:
    """When scan finds nothing, show completion message."""
    mock_oal = MagicMock()
    mock_oal.get_author_works.return_value = [
        {
            "doi": "https://doi.org/10.9999/clean",
            "title": "Clean Paper",
            "best_oa_location": {"pdf_url": "https://example.com/c.pdf"},
        },
    ]
    mock_oal.close = MagicMock()

    def fake_fetch(doi: str, dest: Path, **kw: Any) -> _FakeFetchResult:
        dest.write_text("x\n1\n2\n3\n")
        return _FakeFetchResult(success=True, source="mock")

    def clean_report(file_path: Path, **_kw: Any) -> AuditReport:
        return AuditReport(paper_identifier=str(file_path), seed=42)

    with (
        patch("paperguard.cli.OpenAlexClient", return_value=mock_oal),
        patch("paperguard.cli.fetch_oa_pdf", side_effect=fake_fetch),
        patch("paperguard.cli._scan_single_file", side_effect=clean_report),
    ):
        runner = CliRunner()
        result = runner.invoke(main, ["scan-author", "0000-0001-0000-0000"])

    assert result.exit_code == 0
    assert "Author scan complete" in result.output
