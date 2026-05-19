"""ORI sanctions 测试。"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from paperguard.fetcher.ori_sanctions import lookup_author, reset_cache


def _make_csv(path: Path) -> None:
    path.write_text(
        "Name,Institution,ActionDate,ActionEnd,Findings,URL\n"
        "Smith John,Example U,2020-01-15,2023-01-15,Falsification of data,http://ex.com/1\n"
        "Doe Jane,Other Inst,2018-06-30,2021-06-30,Fabrication of results,http://ex.com/2\n",
        encoding="utf-8",
    )


def test_lookup_hit(tmp_path: Path) -> None:
    reset_cache()
    csv = tmp_path / "ori.csv"
    _make_csv(csv)
    hits = lookup_author("Smith John", csv)
    assert len(hits) == 1
    assert hits[0]["Institution"] == "Example U"


def test_lookup_partial_match(tmp_path: Path) -> None:
    reset_cache()
    csv = tmp_path / "ori.csv"
    _make_csv(csv)
    hits = lookup_author("smith", csv)
    assert len(hits) == 1


def test_lookup_as_of_filters_expired(tmp_path: Path) -> None:
    """Smith 制裁 2023-01-15 结束；查询 2025-01-01 应过滤掉。"""
    reset_cache()
    csv = tmp_path / "ori.csv"
    _make_csv(csv)
    hits = lookup_author("Smith John", csv, as_of=date(2025, 1, 1))
    assert len(hits) == 0


def test_missing_csv(tmp_path: Path) -> None:
    reset_cache()
    csv = tmp_path / "nope.csv"
    assert lookup_author("Smith", csv) == []
