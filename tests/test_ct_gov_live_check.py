"""Smoke tests for the in-scan ClinicalTrials.gov NCT verification (2.0.8).

When ``paperguard scan`` extracts an NCT id from manuscript text, it
now hits the ClinicalTrials.gov v2 API to confirm the trial actually
exists. A 404 emits a SUSPICIOUS T2 finding (fabricated trial id is
a documented fraud pattern; see Goldacre 2019).

Tests mock the API client and verify both the existing-trial and
missing-trial code paths.
"""
from __future__ import annotations

from unittest.mock import patch

from paperguard.fetcher.clinicaltrials import ClinicalTrialsClient


def test_ct_client_returns_none_on_404() -> None:
    """The fetcher returns None on 404, not an exception."""
    import httpx

    class FakeResp:
        def __init__(self, status: int) -> None:
            self.status_code = status

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise httpx.HTTPStatusError(
                    "404",
                    request=None,  # type: ignore[arg-type]
                    response=httpx.Response(
                        status_code=self.status_code,
                        request=httpx.Request("GET", "https://x/"),
                    ),
                )

        def json(self) -> dict:
            return {}

    client = ClinicalTrialsClient(email="t@example.test")
    try:
        with patch.object(client.client, "get", return_value=FakeResp(404)):
            assert client.get_study("NCT99999999") is None
    finally:
        client.close()


def test_ct_client_rejects_non_nct_format() -> None:
    """``get_study`` returns None for non-NCT identifiers."""
    client = ClinicalTrialsClient(email="t@example.test")
    try:
        assert client.get_study("ISRCTN12345") is None
        assert client.get_study("not-an-nct") is None
    finally:
        client.close()


def test_ct_client_returns_record_on_200() -> None:
    """``get_study`` returns the parsed JSON on a 200."""

    class FakeResp:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "protocolSection": {
                    "outcomesModule": {
                        "primaryOutcomes": [
                            {"measure": "Reduction in HbA1c at 24 weeks"}
                        ]
                    }
                }
            }

    client = ClinicalTrialsClient(email="t@example.test")
    try:
        with patch.object(client.client, "get", return_value=FakeResp()):
            study = client.get_study("NCT01234567")
            assert study is not None
            outcomes = client.primary_outcomes("NCT01234567")
        with patch.object(client.client, "get", return_value=FakeResp()):
            outcomes = client.primary_outcomes("NCT01234567")
        assert "HbA1c" in outcomes[0]
    finally:
        client.close()
