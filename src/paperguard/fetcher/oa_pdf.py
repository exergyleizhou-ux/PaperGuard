"""PMC-first open-access PDF fetcher.

Resolves a DOI to a downloadable PDF by trying sources in increasing
order of historical 403-friendliness:

1. **Europe PMC / PubMed Central** — for any DOI that has a PMC ID,
   `https://europepmc.org/articles/PMCxxxx?pdf=render` reliably
   serves a real PDF to anonymous clients. This is the cleanest
   source for biomedical retractions.
2. **Unpaywall** — `best_oa_location.url_for_pdf` is more accurate
   than the OpenAlex-denormalised `oa_url`.
3. **OpenAlex** — last-resort fallback.

After download, the first 8 bytes are checked for the ``%PDF-``
magic header. Anything else (typically HTML landing pages or PDF
viewers) is rejected so downstream extractors don't choke on
non-PDF input.

Used by ``scripts/recall_test_v3.py`` and beyond; designed to be
importable from any caller that has a DOI and wants raw PDF bytes.
"""
from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx

USER_AGENT = (
    "PaperGuard/2.0.5 (PDF fetcher; https://github.com/exergyleizhou-ux/PaperGuard)"
)
EUROPE_PMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
UNPAYWALL = "https://api.unpaywall.org/v2"

_last_request_per_host: dict[str, float] = {}


def _contact_email() -> str:
    return os.environ.get(
        "PAPERGUARD_CONTACT_EMAIL", "research@example.org"
    )


def _rate_limit(url: str, min_interval: float = 1.0) -> None:
    host = urlparse(url).netloc
    now = time.time()
    last = _last_request_per_host.get(host, 0.0)
    wait = (last + min_interval) - now
    if wait > 0:
        time.sleep(wait)
    _last_request_per_host[host] = time.time()


@dataclass(frozen=True)
class FetchResult:
    success: bool
    source: str  # "pmc", "unpaywall", "openalex", or ""
    sha256: str
    content_type: str
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.success


def _pmc_id_for_doi(doi: str) -> str | None:
    """Query Europe PMC for the PMC ID matching a DOI. None if not in PMC."""
    try:
        _rate_limit(EUROPE_PMC, min_interval=0.4)
        r = httpx.get(
            f"{EUROPE_PMC}/search",
            params={
                "query": f'DOI:"{doi}"',
                "format": "json",
                "resultType": "lite",
                "pageSize": 1,
            },
            timeout=20,
            headers={"User-Agent": USER_AGENT},
        )
        r.raise_for_status()
        data = r.json()
        results = data.get("resultList", {}).get("result", [])
        if not results:
            return None
        pmcid = results[0].get("pmcid")
        if not pmcid or not pmcid.startswith("PMC"):
            return None
        return str(pmcid)
    except (httpx.HTTPError, KeyError, ValueError):
        return None


def _pmc_pdf_url(pmcid: str) -> str:
    return f"https://europepmc.org/articles/{pmcid}?pdf=render"


def _unpaywall_pdf_url(doi: str) -> str | None:
    try:
        _rate_limit(UNPAYWALL, min_interval=0.4)
        r = httpx.get(
            f"{UNPAYWALL}/{doi}",
            params={"email": _contact_email()},
            timeout=20,
            headers={"User-Agent": USER_AGENT},
        )
        r.raise_for_status()
        data = r.json()
        best = data.get("best_oa_location") or {}
        url = best.get("url_for_pdf")
        return str(url) if url else None
    except (httpx.HTTPError, KeyError, ValueError):
        return None


def _try_download(url: str, dest: Path) -> tuple[bool, str, str]:
    """Stream-download with %PDF- header check. Returns (ok, sha_or_err, ctype)."""
    try:
        _rate_limit(url, min_interval=1.0)
        with httpx.stream(
            "GET",
            url,
            timeout=60,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        ) as r:
            r.raise_for_status()
            ctype = (r.headers.get("content-type") or "").lower()
            first_chunk = b""
            chunks_iter = r.iter_bytes(chunk_size=8192)
            try:
                first_chunk = next(chunks_iter)
            except StopIteration:
                return False, "empty response body", ctype
            if not first_chunk.startswith(b"%PDF-"):
                return False, "not a PDF (first bytes != %PDF-)", ctype
            h = hashlib.sha256()
            h.update(first_chunk)
            with dest.open("wb") as f:
                f.write(first_chunk)
                for chunk in chunks_iter:
                    h.update(chunk)
                    f.write(chunk)
        return True, h.hexdigest(), ctype
    except httpx.HTTPError as e:
        return False, f"{type(e).__name__}: {e}", ""


def fetch_oa_pdf(
    doi: str, dest: Path, openalex_oa_url: str | None = None
) -> FetchResult:
    """Try PMC → Unpaywall → OpenAlex in order. First successful PDF wins.

    Parameters
    ----------
    doi:
        Normalised DOI string, without ``https://doi.org/`` prefix.
    dest:
        Local path the PDF should be written to.
    openalex_oa_url:
        Fallback URL from a prior OpenAlex query. Optional. When None
        the openalex stage is skipped.

    Returns
    -------
    FetchResult
        ``success`` is True iff a real PDF was written to ``dest``.
        ``source`` indicates which provider succeeded; ``""`` when none.
    """
    # 1) PMC
    pmcid = _pmc_id_for_doi(doi)
    if pmcid:
        ok, sha_or_err, ctype = _try_download(_pmc_pdf_url(pmcid), dest)
        if ok:
            return FetchResult(True, "pmc", sha_or_err, ctype)
    # 2) Unpaywall
    upw_url = _unpaywall_pdf_url(doi)
    if upw_url:
        ok, sha_or_err, ctype = _try_download(upw_url, dest)
        if ok:
            return FetchResult(True, "unpaywall", sha_or_err, ctype)
    # 3) OpenAlex (caller-supplied)
    if openalex_oa_url:
        ok, sha_or_err, ctype = _try_download(openalex_oa_url, dest)
        if ok:
            return FetchResult(True, "openalex", sha_or_err, ctype)
    return FetchResult(
        False,
        "",
        "",
        "",
        error="no source returned a valid PDF (pmc/unpaywall/openalex all failed)",
    )
