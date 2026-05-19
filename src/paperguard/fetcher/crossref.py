"""CrossRef API — DOI 元数据 + Retraction Watch 集成。

API 文档: https://api.crossref.org
礼貌池: 在 User-Agent 中加 mailto:your@email.com。
Retraction 数据通过 update-to 字段透出。
"""
from __future__ import annotations

from typing import Any

import httpx

from paperguard.config import get_settings


class CrossRefClient:
    """CrossRef REST API 客户端。"""

    def __init__(self, email: str | None = None, timeout: float = 30.0) -> None:
        self.email = email or get_settings().email
        self.base = get_settings().crossref_base
        self.client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": f"PaperGuard/0.1.0 (mailto:{self.email})"},
        )

    def get_work(self, doi: str) -> dict[str, Any] | None:
        """按 DOI 取 CrossRef message。"""
        doi_clean = doi.strip().lower().replace("https://doi.org/", "")
        try:
            r = self.client.get(f"{self.base}/works/{doi_clean}")
            r.raise_for_status()
            msg = r.json().get("message")
            return msg if isinstance(msg, dict) else None
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    def check_retraction(self, doi: str) -> dict[str, Any] | None:
        """检查 DOI 是否被撤稿（通过 update-to 字段）。

        Returns:
            None: 未撤稿或未找到。
            dict: 含撤稿记录。
        """
        work = self.get_work(doi)
        if not work:
            return None
        updates = work.get("update-to", [])
        retraction_updates = [
            u
            for u in updates
            if u.get("type", "").lower() in {"retraction", "retract", "withdrawal"}
        ]
        if not retraction_updates:
            return None
        return {
            "doi": doi,
            "is_retracted": True,
            "retraction_records": retraction_updates,
        }

    def close(self) -> None:
        self.client.close()
