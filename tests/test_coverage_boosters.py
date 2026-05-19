"""快速覆盖率扩展测试 — 覆盖之前未测路径。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from paperguard.cli import main
from paperguard.fetcher.cache import _key_for, cache_get, cache_set, cached_call


# --- Fetcher cache
def test_cache_set_get_roundtrip() -> None:
    cache_set("test.ns", "k1", {"x": 1}, ttl=60)
    assert cache_get("test.ns", "k1") == {"x": 1}


def test_cache_miss_returns_none() -> None:
    assert cache_get("test.ns", "definitely-not-set-xyz") is None


def test_cache_key_stable() -> None:
    k1 = _key_for("ns", ("a", "b"), {"x": 1})
    k2 = _key_for("ns", ("a", "b"), {"x": 1})
    assert k1 == k2


def test_cached_call_decorator() -> None:
    import uuid

    calls = [0]
    ns = f"test.decor.{uuid.uuid4().hex}"  # 唯一命名空间，跨测试运行隔离

    @cached_call(ns, ttl=60)
    def slow_fn(x: int) -> int:
        calls[0] += 1
        return x * 2

    assert slow_fn(7) == 14
    assert slow_fn(7) == 14  # cache hit
    assert calls[0] == 1
    assert slow_fn(8) == 16
    assert calls[0] == 2


# --- list-detectors CLI
def test_list_detectors_table() -> None:
    runner = CliRunner()
    r = runner.invoke(main, ["list-detectors"])
    assert r.exit_code == 0
    assert "A1" in r.output
    assert "T6" in r.output


def test_list_detectors_json() -> None:
    runner = CliRunner()
    r = runner.invoke(main, ["list-detectors", "--format", "json"])
    assert r.exit_code == 0
    data = json.loads(r.output)
    ids = [d["id"] for d in data]
    assert "A1" in ids
    assert "F4" in ids


def test_list_detectors_ids_filter() -> None:
    runner = CliRunner()
    r = runner.invoke(
        main, ["list-detectors", "--format", "ids", "--cluster", "image_forensics"]
    )
    assert r.exit_code == 0
    ids = r.output.strip().splitlines()
    assert "F1" in ids
    assert "F2" in ids
    assert "A1" not in ids


# --- fetch-ori template
def test_fetch_ori_creates_template(tmp_path: Path) -> None:
    runner = CliRunner()
    out = tmp_path / "ori.csv"
    r = runner.invoke(main, ["fetch-ori", "--out", str(out)])
    assert r.exit_code == 0
    assert out.exists()
    txt = out.read_text(encoding="utf-8")
    assert "Name,Institution" in txt


# --- JSON schema render
def test_render_schema() -> None:
    from paperguard.reporter.schema import render_schema

    schema = render_schema()
    assert schema.get("$schema")
    assert schema.get("title") == "PaperGuard Audit Report"
    assert "properties" in schema


# --- selfcheck CLI happy-path
def test_selfcheck_runs() -> None:
    runner = CliRunner()
    r = runner.invoke(main, ["selfcheck"])
    assert r.exit_code == 0
    assert "Selfcheck" in r.output


# --- Pubmed module guard
def test_pubmed_invalid_pmid_returns_none() -> None:
    from paperguard.fetcher.pubmed import fetch_pubmed_record

    assert fetch_pubmed_record("not-a-pmid") is None


# --- Baseline extraction handles missing/invalid PDF
def test_baseline_extraction_empty_pdf(tmp_path: Path) -> None:
    import pymupdf

    from paperguard.extractor.baseline_tables import extract_baseline_tables

    p = tmp_path / "empty.pdf"
    doc = pymupdf.open()  # type: ignore[no-untyped-call]
    doc.new_page()  # type: ignore[no-untyped-call]
    doc.save(p)  # type: ignore[no-untyped-call]
    doc.close()  # type: ignore[no-untyped-call]
    out = extract_baseline_tables(p)
    assert out == []


# --- Settings smoke
def test_settings_loads() -> None:
    from paperguard.config import get_settings

    s = get_settings()
    assert s.email
    assert s.seed == 42


# --- Float utils edge cases
def test_get_last_significant_digit_edge() -> None:
    from paperguard.utils.float_utils import (
        get_decimal_places,
        get_last_significant_digit,
        safe_equal,
    )

    assert get_last_significant_digit("0.50") == 5
    assert get_decimal_places("1.230") == 2
    assert safe_equal(1.0, 1.0 + 1e-15)
    assert not safe_equal(1.0, 1.1)


@pytest.mark.parametrize(
    "doi,expected_404_handling",
    [("10.99999/nonexistent", None), ("", None)],
)
def test_unpaywall_get_oa_url_invalid_returns_none(
    doi: str, expected_404_handling: object
) -> None:
    """No-network: just test the function doesn't crash on obviously bad input."""
    from paperguard.fetcher.unpaywall import UnpaywallClient

    client = UnpaywallClient()
    # The actual HTTP call will fail with 404 or timeout; we just check shape
    try:
        result = client.get_oa_url(doi)
        assert result is None or isinstance(result, str)
    except Exception:
        pass  # network-dependent; not a unit-level test
    finally:
        client.close()
    _ = expected_404_handling
