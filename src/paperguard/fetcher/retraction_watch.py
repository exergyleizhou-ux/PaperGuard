"""Retraction Watch 完整数据库查询。

CrossRef 的 update-to 字段只覆盖一小部分撤稿。Retraction Watch (RW) 是更完整的库。
RW 提供 CSV 数据集（学术免费使用）：
    https://gitlab.com/crossref/retraction-watch-data

本模块预期用户已下载 retraction_watch.csv 到本地（如 cache_dir）；
不内置下载，避免网络依赖与许可问题。

CSV 关键列（按 RW 官方 schema）：
- "OriginalPaperDOI"   原文 DOI
- "RetractionDOI"      撤稿声明 DOI
- "RetractionDate"     撤稿日期
- "Reason"             撤稿理由（含 fabrication / falsification / error / etc）
- "Journal"            期刊
- "Author"             作者
"""
from __future__ import annotations

import csv
from pathlib import Path


def _load_index(csv_path: Path) -> dict[str, dict[str, str]]:
    """惰性加载 + 缓存到模块全局。"""
    index: dict[str, dict[str, str]] = {}
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            doi = (row.get("OriginalPaperDOI") or "").strip().lower()
            if not doi or doi == "unavailable":
                continue
            index[doi] = row
    return index


_CACHE: dict[str, dict[str, dict[str, str]]] = {}


def lookup_retraction(doi: str, csv_path: Path) -> dict[str, str] | None:
    """在 RW CSV 中查询 DOI。"""
    if not csv_path.exists():
        return None

    key = str(csv_path.resolve())
    if key not in _CACHE:
        _CACHE[key] = _load_index(csv_path)

    doi_clean = doi.strip().lower().replace("https://doi.org/", "")
    return _CACHE[key].get(doi_clean)


def reset_cache() -> None:
    """测试用：清空全局缓存。"""
    _CACHE.clear()
