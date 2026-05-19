"""PDF 文本与表格提取。

策略：
- 用 pymupdf 提取整篇文本（快）
- 用 pdfplumber 提取嵌入式表格（准但慢）
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pdfplumber
import pymupdf


def extract_pdf_text(path: Path) -> str:
    """提取 PDF 全文。空 PDF 返回 ''。"""
    doc = pymupdf.open(path)  # type: ignore[no-untyped-call]
    try:
        parts: list[str] = []
        for i in range(doc.page_count):
            page = doc[i]
            text = page.get_text("text") or ""  # type: ignore[no-untyped-call]
            parts.append(text)
        return "\n".join(parts)
    finally:
        doc.close()  # type: ignore[no-untyped-call]


def extract_pdf_tables(path: Path) -> dict[str, pd.DataFrame]:
    """提取 PDF 嵌入表格 → {table_name: DataFrame}。

    使用 pdfplumber 的默认策略。每页可能有 0..N 张表。
    第一行视作 header；列若可数值化则数值化。
    """
    out: dict[str, pd.DataFrame] = {}
    with pdfplumber.open(path) as pdf:
        idx = 0
        for page_no, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables() or []
            for tbl in tables:
                if not tbl:
                    continue
                rows = [[(c or "").strip() for c in row] for row in tbl]
                if len(rows) < 2:
                    continue
                header = rows[0]
                seen: dict[str, int] = {}
                cols: list[str] = []
                for i, h in enumerate(header):
                    name = h or f"col_{i}"
                    if name in seen:
                        seen[name] += 1
                        name = f"{name}_{seen[name]}"
                    else:
                        seen[name] = 0
                    cols.append(name)
                df = pd.DataFrame(rows[1:], columns=cols)
                for c in df.columns:
                    coerced = pd.to_numeric(df[c], errors="coerce")
                    if coerced.notna().sum() >= max(1, len(df) // 2):
                        df[c] = coerced
                idx += 1
                out[f"p{page_no}_table_{idx}"] = df
    return out
