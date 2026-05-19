"""ORI Administrative Actions（学术不端制裁名单）本地查询。

ORI 官网公布历年制裁案例（https://ori.hhs.gov/case-summaries）。
本模块走"用户本地维护 CSV"模式：

预期 CSV 列：
  Name, Institution, ActionDate, ActionEnd, Findings, URL

CSV 由用户自己从 ORI 网页爬取/整理并保存到 cache_dir，
本模块不内置爬虫（HTML 结构易变；引入爬取代码会增加维护成本与合规风险）。

查询语义：按姓名模糊匹配（不区分大小写），返回所有匹配的制裁记录。
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Any

_CACHE: dict[str, list[dict[str, str]]] = {}


def _load_index(csv_path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not (row.get("Name") or "").strip():
                continue
            rows.append({k: (v or "").strip() for k, v in row.items()})
    return rows


def reset_cache() -> None:
    """测试用：清空全局缓存。"""
    _CACHE.clear()


def lookup_author(
    name: str,
    csv_path: Path,
    as_of: date | None = None,
) -> list[dict[str, Any]]:
    """返回与 name 模糊匹配的 ORI 制裁记录。

    Args:
        name: 作者姓名。
        csv_path: 用户维护的 ORI 名单 CSV。
        as_of: 仅返回在该日期当时仍处于制裁期内的记录。None = 全历史。
    """
    if not csv_path.exists():
        return []

    key = str(csv_path.resolve())
    if key not in _CACHE:
        _CACHE[key] = _load_index(csv_path)

    qname = name.strip().lower()
    if not qname:
        return []

    out: list[dict[str, Any]] = []
    for row in _CACHE[key]:
        full = row.get("Name", "").lower()
        if qname in full or full in qname:
            if as_of is not None:
                end = row.get("ActionEnd", "")
                if end:
                    try:
                        end_date = date.fromisoformat(end)
                        if end_date < as_of:
                            continue
                    except ValueError:
                        pass
            out.append(dict(row))
    return out
