"""ClinicalTrials.gov v2 API 客户端。

提供按 NCT ID 取注册记录的接口。用于 T2 检测器比对"注册的 primary
outcome"与"论文报告的 primary outcome"，识别 outcome switching。
"""
from __future__ import annotations

from typing import Any

import httpx

from paperguard.config import get_settings

BASE_URL = "https://clinicaltrials.gov/api/v2"


class ClinicalTrialsClient:
    """ClinicalTrials.gov v2 API。"""

    def __init__(self, email: str | None = None, timeout: float = 30.0) -> None:
        self.email = email or get_settings().email
        self.client = httpx.Client(
            timeout=timeout,
            headers={
                "User-Agent": f"PaperGuard/0.5.0 (mailto:{self.email})",
                "Accept": "application/json",
            },
        )

    def get_study(self, nct_id: str) -> dict[str, Any] | None:
        """通过 NCT ID 取完整研究记录。404 返回 None。"""
        nct = nct_id.strip().upper()
        if not nct.startswith("NCT"):
            return None
        try:
            r = self.client.get(f"{BASE_URL}/studies/{nct}")
            r.raise_for_status()
            data: dict[str, Any] = r.json()
            return data
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    def primary_outcomes(self, nct_id: str) -> list[str]:
        """便捷方法：返回注册的 primary outcome 字符串列表。"""
        study = self.get_study(nct_id)
        if not study:
            return []
        outcomes_module = (
            study.get("protocolSection", {}).get("outcomesModule", {})
        )
        return [
            o.get("measure", "")
            for o in outcomes_module.get("primaryOutcomes", [])
            if o.get("measure")
        ]

    def close(self) -> None:
        self.client.close()
