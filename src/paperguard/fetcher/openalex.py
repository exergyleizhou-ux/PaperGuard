"""OpenAlex API 客户端 — 论文元数据 + 作者搜索。

API 文档: https://docs.openalex.org/
礼貌池: 在 URL 中加 ?mailto=your@email.com 获得更快响应。
速率限制: 100,000 calls/day, ~10 calls/second。
"""
from __future__ import annotations

from typing import Any

import httpx

from paperguard.config import get_settings
from paperguard.fetcher.cache import cached_call


class OpenAlexClient:
    """OpenAlex REST API 的轻量封装。"""

    def __init__(self, email: str | None = None, timeout: float = 30.0) -> None:
        self.email = email or get_settings().email
        self.base = get_settings().openalex_base
        self.client = httpx.Client(timeout=timeout)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        params["mailto"] = self.email
        url = f"{self.base}{path}"
        r = self.client.get(url, params=params)
        r.raise_for_status()
        data: dict[str, Any] = r.json()
        return data

    @cached_call("openalex.work", ttl=7 * 24 * 3600)
    def get_work_by_doi(self, doi: str) -> dict[str, Any] | None:
        """按 DOI 获取单篇论文元数据。结果缓存 7 天。"""
        doi_clean = doi.strip().lower().replace("https://doi.org/", "")
        try:
            return self._get(f"/works/doi:{doi_clean}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    def search_works(
        self,
        query: str = "",
        author: str = "",
        institution: str = "",
        year_from: int | None = None,
        year_to: int | None = None,
        per_page: int = 25,
    ) -> list[dict[str, Any]]:
        """搜索论文。"""
        filters: list[str] = []
        if year_from:
            filters.append(f"from_publication_date:{year_from}-01-01")
        if year_to:
            filters.append(f"to_publication_date:{year_to}-12-31")
        if institution:
            filters.append(
                f"authorships.institutions.display_name.search:{institution}"
            )

        params: dict[str, Any] = {"per_page": per_page}
        if query:
            params["search"] = query
        if author:
            params["filter"] = f"author.display_name.search:{author}"
            if filters:
                params["filter"] += "," + ",".join(filters)
        elif filters:
            params["filter"] = ",".join(filters)

        data = self._get("/works", params=params)
        results: list[dict[str, Any]] = data.get("results", [])
        return results

    def search_authors(self, name: str, per_page: int = 10) -> list[dict[str, Any]]:
        """搜索作者。"""
        data = self._get(
            "/authors",
            params={"search": name, "per_page": per_page},
        )
        results: list[dict[str, Any]] = data.get("results", [])
        return results

    def get_author_works(
        self, author_id: str, per_page: int = 100
    ) -> list[dict[str, Any]]:
        """获取某作者的所有论文。author_id 可以是 ORCID 或 OpenAlex ID。"""
        params: dict[str, Any] = {
            "filter": f"author.id:{author_id}",
            "per_page": per_page,
        }
        data = self._get("/works", params=params)
        results: list[dict[str, Any]] = data.get("results", [])
        return results

    def get_author_retraction_rate(
        self, author_id: str, max_works: int = 200
    ) -> dict[str, Any]:
        """估算某作者的历史撤稿率。

        OpenAlex 的 `is_retracted` 标志由其同步 Retraction Watch 维护。
        本方法拉取作者最近 ≤ max_works 篇论文，统计 is_retracted 比例。
        """
        params: dict[str, Any] = {
            "filter": f"author.id:{author_id}",
            "per_page": min(max_works, 200),
            "select": "id,is_retracted,publication_year",
        }
        data = self._get("/works", params=params)
        results: list[dict[str, Any]] = data.get("results", [])
        n_total = len(results)
        n_retracted = sum(1 for w in results if w.get("is_retracted"))
        retracted_dois: list[str] = [
            w.get("id", "") for w in results if w.get("is_retracted")
        ]
        return {
            "author_id": author_id,
            "n_works_sampled": n_total,
            "n_retracted": n_retracted,
            "retraction_rate": (n_retracted / n_total) if n_total else 0.0,
            "retracted_work_ids": retracted_dois,
        }

    def close(self) -> None:
        self.client.close()
