"""PubMed via Biopython Entrez。

直接复用成熟的 `biopython.Entrez` 模块。比手写 E-utils HTTP 抓取
节省精力 + 处理 XML 边界情况。

Entrez 礼貌池要求：在调用前设置 `Entrez.email`；可选 `Entrez.api_key`。
"""
# mypy: ignore-errors
from __future__ import annotations

import os
from typing import Any

from paperguard.config import get_settings


def _ensure_entrez_configured() -> None:
    from Bio import Entrez  # type: ignore[import-untyped]

    if not getattr(Entrez, "email", None):
        Entrez.email = get_settings().email
    api_key = os.environ.get("NCBI_API_KEY")
    if api_key and not getattr(Entrez, "api_key", None):
        Entrez.api_key = api_key


def fetch_pubmed_record(pmid: str) -> dict[str, Any] | None:
    """通过 PMID 取 PubMed 记录摘要。"""
    _ensure_entrez_configured()
    from Bio import Entrez  # type: ignore[import-untyped]

    pmid = pmid.strip()
    if not pmid.isdigit():
        return None
    try:
        with Entrez.efetch(
            db="pubmed", id=pmid, rettype="abstract", retmode="xml"
        ) as h:
            records = Entrez.read(h)
    except Exception:  # noqa: BLE001
        return None
    articles = (
        records.get("PubmedArticle", []) if isinstance(records, dict) else []
    )
    if not articles:
        return None
    art = articles[0]
    medline = art.get("MedlineCitation", {})
    article = medline.get("Article", {})
    title = str(article.get("ArticleTitle", ""))
    journal = str(article.get("Journal", {}).get("Title", ""))
    pub_date = (
        article.get("Journal", {})
        .get("JournalIssue", {})
        .get("PubDate", {})
    )
    year = pub_date.get("Year") if isinstance(pub_date, dict) else None
    return {
        "pmid": pmid,
        "title": title,
        "journal": journal,
        "year": str(year) if year else None,
        "raw": dict(art),
    }


def lookup_pmid_from_doi(doi: str) -> str | None:
    """DOI → PMID 反查（用 Entrez esearch）。"""
    _ensure_entrez_configured()
    from Bio import Entrez  # type: ignore[import-untyped]

    doi_clean = doi.strip().lower().replace("https://doi.org/", "")
    try:
        with Entrez.esearch(db="pubmed", term=f"{doi_clean}[doi]") as h:
            res = Entrez.read(h)
    except Exception:  # noqa: BLE001
        return None
    ids = res.get("IdList", []) if isinstance(res, dict) else []
    return str(ids[0]) if ids else None
