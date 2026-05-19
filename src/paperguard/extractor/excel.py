"""Excel/CSV 提取 → pandas DataFrame。"""
from __future__ import annotations

from pathlib import Path

import pandas as pd


def parse_data_file(path: Path) -> dict[str, pd.DataFrame]:
    """解析任意支持的表格文件，返回 {sheet_name: DataFrame}。

    支持：
    - .xlsx / .xlsm: 所有工作表
    - .csv: 返回 {"sheet1": df}
    - .tsv: 返回 {"sheet1": df}
    """
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        sheets = pd.read_excel(path, sheet_name=None, engine="openpyxl")
        return sheets
    elif suffix == ".csv":
        return {"sheet1": pd.read_csv(path)}
    elif suffix == ".tsv":
        return {"sheet1": pd.read_csv(path, sep="\t")}
    else:
        raise ValueError(f"Unsupported file type: {suffix}")
