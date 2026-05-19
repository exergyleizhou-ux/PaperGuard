"""OpenAlex 集成测试。需要联网，默认跳过。"""
from __future__ import annotations

import pytest

from paperguard.fetcher.openalex import OpenAlexClient


@pytest.mark.network
def test_openalex_get_work_by_doi() -> None:
    """通过稳定的 DOI（Watson & Crick 1953）取单篇论文。"""
    client = OpenAlexClient(email="test@example.com")
    try:
        work = client.get_work_by_doi("10.1038/171737a0")
        assert work is not None
        assert "title" in work or "display_name" in work
    finally:
        client.close()


@pytest.mark.network
def test_openalex_search_works() -> None:
    client = OpenAlexClient(email="test@example.com")
    try:
        results = client.search_works(query="DNA structure", per_page=3)
        assert len(results) > 0
        assert "title" in results[0] or "display_name" in results[0]
    finally:
        client.close()
