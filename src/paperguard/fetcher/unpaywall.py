"""Unpaywall — 查找 DOI 对应的 OA PDF。"""
from __future__ import annotations

from pathlib import Path

import httpx

from paperguard.config import get_settings


class UnpaywallClient:
    """Unpaywall REST API 客户端。"""

    def __init__(self, email: str | None = None, timeout: float = 30.0) -> None:
        self.email = email or get_settings().email
        self.base = get_settings().unpaywall_base
        self.client = httpx.Client(timeout=timeout)

    def get_oa_url(self, doi: str) -> str | None:
        """返回 best OA PDF URL，没有则 None。"""
        doi_clean = doi.strip().lower().replace("https://doi.org/", "")
        try:
            r = self.client.get(
                f"{self.base}/{doi_clean}",
                params={"email": self.email},
            )
            r.raise_for_status()
            data = r.json()
            best = data.get("best_oa_location")
            if best:
                url = best.get("url_for_pdf") or best.get("url")
                return str(url) if url else None
            return None
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    def download_oa_pdf(self, doi: str, dst_path: Path) -> Path | None:
        """下载 best OA PDF 到 dst_path。返回 Path 或 None。"""
        url = self.get_oa_url(doi)
        if not url:
            return None
        try:
            r = self.client.get(url, follow_redirects=True)
            r.raise_for_status()
        except httpx.HTTPError:
            return None
        # 简单 PDF 头检查
        body = r.content
        if not body.startswith(b"%PDF"):
            return None
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        dst_path.write_bytes(body)
        return dst_path

    def close(self) -> None:
        self.client.close()
