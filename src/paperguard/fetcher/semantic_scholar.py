"""Semantic Scholar API — Chinese & multilingual paper search.

Free public API with good Chinese journal coverage.
Rate limit: 100 requests / 5 minutes (no key), higher with API key.
Docs: https://api.semanticscholar.org/
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

_BASE = "https://api.semanticscholar.org/graph/v1"
_FIELDS = (
    "paperId,externalIds,title,authors,year,"
    "venue,citationCount,isOpenAccess"
)
_MAX_RESULTS = 20


@dataclass(frozen=True)
class ScholarPaper:
    """A single paper result from Semantic Scholar."""

    paper_id: str
    title: str
    doi: str = ""
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str = ""
    citation_count: int = 0
    is_open_access: bool = False


class SemanticScholarClient:
    """Lightweight Semantic Scholar API client for paper search."""

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        headers: dict[str, str] = {}
        if api_key:
            headers["x-api-key"] = api_key
        self._client = httpx.Client(timeout=timeout, headers=headers)

    def search(
        self,
        query: str,
        limit: int = _MAX_RESULTS,
        year: str | None = None,
    ) -> list[ScholarPaper]:
        """Search papers by title/keyword query.

        Args:
            query: Search string (Chinese or English).
            limit: Max results (1-100, default 20).
            year: Optional year filter, e.g. "2020" or "2018-2023".

        Returns:
            List of ScholarPaper results sorted by relevance.
        """
        params: dict[str, str] = {
            "query": query,
            "limit": str(min(limit, 100)),
            "fields": _FIELDS,
        }
        if year:
            params["year"] = year

        try:
            resp = self._client.get(
                f"{_BASE}/paper/search", params=params,
            )
            resp.raise_for_status()
        except httpx.HTTPError:
            return []

        data: dict[str, Any] = resp.json()
        raw_papers: list[dict[str, Any]] = data.get("data") or []
        return [self._parse(p) for p in raw_papers]

    def get_paper(self, doi: str) -> ScholarPaper | None:
        """Look up a single paper by DOI."""
        doi_clean = doi.strip().replace("https://doi.org/", "")
        try:
            resp = self._client.get(
                f"{_BASE}/paper/DOI:{doi_clean}",
                params={"fields": _FIELDS},
            )
            resp.raise_for_status()
        except httpx.HTTPError:
            return None
        return self._parse(resp.json())

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    @staticmethod
    def _parse(raw: dict[str, Any]) -> ScholarPaper:
        ext_ids = raw.get("externalIds") or {}
        authors_raw: list[dict[str, Any]] = raw.get("authors") or []
        return ScholarPaper(
            paper_id=raw.get("paperId") or "",
            title=raw.get("title") or "",
            doi=ext_ids.get("DOI") or "",
            authors=[a.get("name", "") for a in authors_raw],
            year=raw.get("year"),
            venue=raw.get("venue") or "",
            citation_count=raw.get("citationCount") or 0,
            is_open_access=bool(raw.get("isOpenAccess")),
        )
