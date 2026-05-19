"""Web UI 测试 — 用 FastAPI TestClient。"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from paperguard.webui.app import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_index_returns_html(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "PaperGuard" in r.text
    assert "<form" in r.text


def test_detectors_endpoint(client: TestClient) -> None:
    r = client.get("/detectors")
    assert r.status_code == 200
    data = r.json()
    assert data["version"]
    ids = [d["id"] for d in data["detectors"]]
    assert "A1" in ids
    assert "B4" in ids
    assert "G3" in ids


def test_scan_fabricated_csv(client: TestClient, fixtures_dir: Path) -> None:
    csv = fixtures_dir / "fabricated_geng_style.csv"
    with csv.open("rb") as f:
        r = client.post(
            "/scan",
            files={"file": (csv.name, f, "text/csv")},
            data={"lang": "en"},
        )
    assert r.status_code == 200
    assert "CRITICAL" in r.text
    assert "Disclaimer" in r.text


def test_scan_json_endpoint(client: TestClient, fixtures_dir: Path) -> None:
    csv = fixtures_dir / "genuine_random.csv"
    with csv.open("rb") as f:
        r = client.post(
            "/scan.json",
            files={"file": (csv.name, f, "text/csv")},
        )
    assert r.status_code == 200
    data = r.json()
    assert "overall_severity" in data
    assert "all_findings" in data


def test_scan_rejects_unsupported_type(client: TestClient, tmp_path: Path) -> None:
    p = tmp_path / "evil.exe"
    p.write_bytes(b"\x00\x01\x02")
    with p.open("rb") as f:
        r = client.post(
            "/scan",
            files={"file": (p.name, f, "application/octet-stream")},
            data={"lang": "en"},
        )
    assert r.status_code == 415


def test_scan_chinese_lang(client: TestClient, fixtures_dir: Path) -> None:
    csv = fixtures_dir / "fabricated_geng_style.csv"
    with csv.open("rb") as f:
        r = client.post(
            "/scan",
            files={"file": (csv.name, f, "text/csv")},
            data={"lang": "zh-CN"},
        )
    assert r.status_code == 200
    assert "免责声明" in r.text or "审查报告" in r.text
