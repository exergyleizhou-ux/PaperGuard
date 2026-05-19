"""从 .docx 文件提取 Word 表格 → pandas DataFrame。

实现策略：
- .docx 是 zip 包，正文在 word/document.xml
- 表格用 <w:tbl>，行 <w:tr>，单元格 <w:tc>，文本在 <w:t>
- 数值列尝试 pd.to_numeric 转换，转不动就保留为字符串
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pandas as pd

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_NS = {"w": W_NS}


def _cell_text(tc: ET.Element) -> str:
    """把一个 <w:tc> 里所有 <w:t> 文本拼起来。"""
    parts: list[str] = []
    for t in tc.iter(f"{{{W_NS}}}t"):
        if t.text:
            parts.append(t.text)
    return "".join(parts).strip()


def _row_cells(tr: ET.Element) -> list[str]:
    return [_cell_text(tc) for tc in tr.findall(f"{{{W_NS}}}tc")]


def _try_numerify(series: pd.Series) -> pd.Series:
    """如果整列能转成数值就转，否则保留原样。"""
    cleaned = series.astype(str).str.strip()
    coerced = pd.to_numeric(cleaned, errors="coerce")
    # 至少一半能转才认作数值列
    if coerced.notna().sum() >= max(1, len(coerced) // 2):
        return coerced
    return series


def parse_docx_tables(path: Path) -> dict[str, pd.DataFrame]:
    """提取 .docx 中的所有表格。

    Returns:
        {"table_1": DataFrame, "table_2": DataFrame, ...}
        每个 DataFrame 把第一行当 header。无表格时返回空 dict。
    """
    out: dict[str, pd.DataFrame] = {}
    with zipfile.ZipFile(path) as z:
        if "word/document.xml" not in z.namelist():
            return out
        with z.open("word/document.xml") as f:
            root = ET.parse(f).getroot()

    tables = root.iter(f"{{{W_NS}}}tbl")
    for idx, tbl in enumerate(tables, start=1):
        rows = [_row_cells(tr) for tr in tbl.findall(f"{{{W_NS}}}tr")]
        if not rows:
            continue
        # 对齐列数（pad 到 max width）
        max_cols = max(len(r) for r in rows)
        for r in rows:
            while len(r) < max_cols:
                r.append("")

        if len(rows) < 2:
            df = pd.DataFrame(rows)
        else:
            header = rows[0]
            # 列名去重 + 空串补名
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
            # 数值化尝试
            for c in df.columns:
                df[c] = _try_numerify(df[c])

        out[f"table_{idx}"] = df
    return out
