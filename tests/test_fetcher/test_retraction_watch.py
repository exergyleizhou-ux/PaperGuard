"""Retraction Watch CSV loader 测试。"""
from __future__ import annotations

from pathlib import Path

from paperguard.fetcher.retraction_watch import lookup_retraction, reset_cache


def _make_minimal_csv(path: Path) -> None:
    path.write_text(
        "OriginalPaperDOI,RetractionDOI,RetractionDate,Reason,Journal,Author\n"
        "10.1234/test.001,10.1234/retr.001,2020-01-15,+Fabrication,Nature,Smith J\n"
        "10.5555/other.999,10.5555/retr.999,2021-06-30,+Error,Cell,Doe A\n",
        encoding="utf-8",
    )


def test_lookup_hit(tmp_path: Path) -> None:
    reset_cache()
    csv = tmp_path / "rw.csv"
    _make_minimal_csv(csv)
    row = lookup_retraction("10.1234/test.001", csv)
    assert row is not None
    assert row["Reason"] == "+Fabrication"


def test_lookup_miss(tmp_path: Path) -> None:
    reset_cache()
    csv = tmp_path / "rw.csv"
    _make_minimal_csv(csv)
    assert lookup_retraction("10.9999/notfound", csv) is None


def test_lookup_missing_csv(tmp_path: Path) -> None:
    reset_cache()
    csv = tmp_path / "does_not_exist.csv"
    assert lookup_retraction("10.1234/test.001", csv) is None


def test_lookup_case_insensitive(tmp_path: Path) -> None:
    reset_cache()
    csv = tmp_path / "rw.csv"
    _make_minimal_csv(csv)
    row = lookup_retraction("HTTPS://DOI.ORG/10.1234/TEST.001", csv)
    assert row is not None
