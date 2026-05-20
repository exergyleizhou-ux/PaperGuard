"""Europe PMC full-text API client.

PubMed Central exposes full XML text of OA articles, plus structured
references and citation counts. PaperGuard uses this for:

- ``paperguard scan-pmc <DOI>`` — fetch full text + run LLM content
  review without ever downloading a PDF (faster, cleaner text)
- Author-history cross-reference (which of an author's papers have
  open full-text we can scan?)

Endpoints used:

  /search           — DOI → PMC ID lookup (already in oa_pdf.py)
  /article/PMC{id}/fullTextXML  — JATS-style XML body

JATS XML is parsed minimally: we strip the markup and pull the body
paragraphs, then optionally extract <sec> blocks (Methods / Results
/ Discussion) so the LLM reviewer can run section-targeted prompts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import httpx

EUROPE_PMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
USER_AGENT = (
    "PaperGuard/2.0.11 (PMC fetcher; "
    "https://github.com/exergyleizhou-ux/PaperGuard)"
)


@dataclass
class PMCArticle:
    pmcid: str
    doi: str
    title: str
    abstract: str
    full_text: str
    sections: dict[str, str] = field(default_factory=dict)


def lookup_pmcid(doi: str, timeout: float = 20.0) -> str | None:
    """Return the PMC ID for a DOI, or None if not in Europe PMC."""
    try:
        r = httpx.get(
            f"{EUROPE_PMC}/search",
            params={
                "query": f'DOI:"{doi}"',
                "format": "json",
                "resultType": "lite",
                "pageSize": 1,
            },
            timeout=timeout,
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


def fetch_full_text_xml(pmcid: str, timeout: float = 60.0) -> str | None:
    """Fetch JATS-style full-text XML. Returns None on any failure."""
    try:
        r = httpx.get(
            f"{EUROPE_PMC}/{pmcid}/fullTextXML",
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
        )
        r.raise_for_status()
        if not r.text.lstrip().startswith("<"):
            return None
        return r.text
    except httpx.HTTPError:
        return None


_TAG_RE = re.compile(r"<[^>]+>")
_SEC_RE = re.compile(
    r"<sec\b[^>]*>(.*?)</sec>", re.DOTALL | re.IGNORECASE
)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.DOTALL | re.IGNORECASE)
_ABSTRACT_RE = re.compile(
    r"<abstract\b[^>]*>(.*?)</abstract>", re.DOTALL | re.IGNORECASE
)
_BODY_RE = re.compile(r"<body\b[^>]*>(.*?)</body>", re.DOTALL | re.IGNORECASE)


def _strip_markup(s: str) -> str:
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", s)).strip()


def parse_jats(xml: str) -> dict[str, str]:
    """Pull title / abstract / body / per-section text out of JATS XML."""
    out: dict[str, str] = {}

    abs_match = _ABSTRACT_RE.search(xml)
    if abs_match:
        out["abstract"] = _strip_markup(abs_match.group(1))

    body_match = _BODY_RE.search(xml)
    body = body_match.group(1) if body_match else xml

    title_match = _TITLE_RE.search(xml)
    if title_match:
        out["title"] = _strip_markup(title_match.group(1))

    # Top-level sections keyed by their <title>
    for sec_match in _SEC_RE.finditer(body):
        sec_xml = sec_match.group(1)
        title_m = _TITLE_RE.search(sec_xml)
        title = (
            _strip_markup(title_m.group(1))[:80].lower()
            if title_m
            else "untitled"
        )
        text = _strip_markup(sec_xml)
        if not text:
            continue
        if title in out:
            out[title] += "\n\n" + text
        else:
            out[title] = text

    out["full_text"] = _strip_markup(body)
    return out


def fetch_article(doi: str) -> PMCArticle | None:
    """One-shot: DOI → PMC ID → fullTextXML → parsed PMCArticle.

    Returns None on any failure (not in PMC, no full text, etc.).
    """
    pmcid = lookup_pmcid(doi)
    if not pmcid:
        return None
    xml = fetch_full_text_xml(pmcid)
    if not xml:
        return None
    parsed = parse_jats(xml)
    return PMCArticle(
        pmcid=pmcid,
        doi=doi,
        title=parsed.get("title", ""),
        abstract=parsed.get("abstract", ""),
        full_text=parsed.get("full_text", ""),
        sections={
            k: v
            for k, v in parsed.items()
            if k not in {"title", "abstract", "full_text"}
        },
    )
