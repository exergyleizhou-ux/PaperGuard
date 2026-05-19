"""Unit tests for the PMC-first OA PDF fetcher.

Network calls are mocked. The integration paths (real PMC lookup,
real Unpaywall lookup) live under ``-m network`` and are
deliberately not run in CI.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx

from paperguard.fetcher.oa_pdf import (
    _pmc_id_for_doi,
    _try_download,
    _unpaywall_pdf_url,
    fetch_oa_pdf,
)

# --------------------------------------------------------------------------
# %PDF- header validation
# --------------------------------------------------------------------------


class _FakeStreamResponse:
    def __init__(self, chunks: list[bytes], status: int = 200, ctype: str = "application/pdf"):
        self._chunks = chunks
        self.status_code = status
        self.headers = {"content-type": ctype}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"status {self.status_code}",
                request=None,  # type: ignore[arg-type]
                response=None,  # type: ignore[arg-type]
            )

    def iter_bytes(self, chunk_size: int = 8192):
        yield from self._chunks


def test_try_download_accepts_pdf_header(tmp_path: Path) -> None:
    pdf_bytes = b"%PDF-1.4\n%hello world body\n%%EOF"
    fake = _FakeStreamResponse([pdf_bytes])
    with patch("paperguard.fetcher.oa_pdf.httpx.stream", return_value=fake):
        ok, sha_or_err, ctype = _try_download(
            "https://example.test/x.pdf", tmp_path / "out.pdf"
        )
    assert ok is True
    assert len(sha_or_err) == 64  # sha256 hex
    assert (tmp_path / "out.pdf").read_bytes() == pdf_bytes


def test_try_download_rejects_html(tmp_path: Path) -> None:
    html = b"<!DOCTYPE html><html><body>404</body></html>"
    fake = _FakeStreamResponse([html], ctype="text/html")
    with patch("paperguard.fetcher.oa_pdf.httpx.stream", return_value=fake):
        ok, sha_or_err, ctype = _try_download(
            "https://example.test/x.pdf", tmp_path / "out.pdf"
        )
    assert ok is False
    assert "not a PDF" in sha_or_err


def test_try_download_rejects_empty(tmp_path: Path) -> None:
    fake = _FakeStreamResponse([])
    with patch("paperguard.fetcher.oa_pdf.httpx.stream", return_value=fake):
        ok, _, _ = _try_download(
            "https://example.test/x.pdf", tmp_path / "out.pdf"
        )
    assert ok is False


# --------------------------------------------------------------------------
# PMC ID lookup
# --------------------------------------------------------------------------


def _mock_get(json_payload: dict, status: int = 200):
    m = MagicMock()
    m.status_code = status
    m.json.return_value = json_payload
    m.raise_for_status.return_value = None
    return m


def test_pmc_id_for_doi_hit() -> None:
    payload = {
        "resultList": {"result": [{"id": "12345", "pmcid": "PMC1234567"}]}
    }
    with patch("paperguard.fetcher.oa_pdf.httpx.get", return_value=_mock_get(payload)):
        assert _pmc_id_for_doi("10.1000/test") == "PMC1234567"


def test_pmc_id_for_doi_miss() -> None:
    payload = {"resultList": {"result": []}}
    with patch("paperguard.fetcher.oa_pdf.httpx.get", return_value=_mock_get(payload)):
        assert _pmc_id_for_doi("10.1000/notinpmc") is None


def test_pmc_id_for_doi_network_error() -> None:
    with patch(
        "paperguard.fetcher.oa_pdf.httpx.get",
        side_effect=httpx.ConnectError("dns fail"),
    ):
        assert _pmc_id_for_doi("10.1000/any") is None


# --------------------------------------------------------------------------
# Unpaywall lookup
# --------------------------------------------------------------------------


def test_unpaywall_pdf_url_hit() -> None:
    payload = {
        "best_oa_location": {
            "url_for_pdf": "https://publisher.test/article.pdf",
            "url_for_landing_page": "https://publisher.test/article",
        }
    }
    with patch("paperguard.fetcher.oa_pdf.httpx.get", return_value=_mock_get(payload)):
        assert (
            _unpaywall_pdf_url("10.1000/test")
            == "https://publisher.test/article.pdf"
        )


def test_unpaywall_pdf_url_no_pdf() -> None:
    payload = {"best_oa_location": {"url_for_landing_page": "x"}}
    with patch("paperguard.fetcher.oa_pdf.httpx.get", return_value=_mock_get(payload)):
        assert _unpaywall_pdf_url("10.1000/test") is None


def test_unpaywall_pdf_url_no_oa() -> None:
    payload = {"best_oa_location": None}
    with patch("paperguard.fetcher.oa_pdf.httpx.get", return_value=_mock_get(payload)):
        assert _unpaywall_pdf_url("10.1000/test") is None


# --------------------------------------------------------------------------
# Fallback chain — PMC → Unpaywall → OpenAlex
# --------------------------------------------------------------------------


def _fake_pdf_stream():
    return _FakeStreamResponse([b"%PDF-1.4\nfake\n"])


def test_fetch_oa_pdf_pmc_wins(tmp_path: Path) -> None:
    with patch(
        "paperguard.fetcher.oa_pdf._pmc_id_for_doi", return_value="PMC1"
    ), patch(
        "paperguard.fetcher.oa_pdf.httpx.stream", return_value=_fake_pdf_stream()
    ):
        res = fetch_oa_pdf("10.1/x", tmp_path / "out.pdf")
    assert res.success is True
    assert res.source == "pmc"
    assert (tmp_path / "out.pdf").exists()


def test_fetch_oa_pdf_pmc_miss_unpaywall_wins(tmp_path: Path) -> None:
    with patch(
        "paperguard.fetcher.oa_pdf._pmc_id_for_doi", return_value=None
    ), patch(
        "paperguard.fetcher.oa_pdf._unpaywall_pdf_url",
        return_value="https://up.test/x.pdf",
    ), patch(
        "paperguard.fetcher.oa_pdf.httpx.stream", return_value=_fake_pdf_stream()
    ):
        res = fetch_oa_pdf("10.1/x", tmp_path / "out.pdf")
    assert res.success is True
    assert res.source == "unpaywall"


def test_fetch_oa_pdf_falls_through_to_openalex(tmp_path: Path) -> None:
    with patch(
        "paperguard.fetcher.oa_pdf._pmc_id_for_doi", return_value=None
    ), patch(
        "paperguard.fetcher.oa_pdf._unpaywall_pdf_url", return_value=None
    ), patch(
        "paperguard.fetcher.oa_pdf.httpx.stream", return_value=_fake_pdf_stream()
    ):
        res = fetch_oa_pdf(
            "10.1/x",
            tmp_path / "out.pdf",
            openalex_oa_url="https://oa.test/x.pdf",
        )
    assert res.success is True
    assert res.source == "openalex"


def test_fetch_oa_pdf_all_sources_fail(tmp_path: Path) -> None:
    with patch(
        "paperguard.fetcher.oa_pdf._pmc_id_for_doi", return_value=None
    ), patch(
        "paperguard.fetcher.oa_pdf._unpaywall_pdf_url", return_value=None
    ):
        res = fetch_oa_pdf("10.1/x", tmp_path / "out.pdf", openalex_oa_url=None)
    assert res.success is False
    assert res.source == ""
    assert "all failed" in res.error
