"""Excel/CSV 提取测试。"""
from __future__ import annotations

from pathlib import Path

from paperguard.extractor.excel import parse_data_file


def test_parse_csv(fixtures_dir: Path) -> None:
    csv_path = fixtures_dir / "fabricated_geng_style.csv"
    sheets = parse_data_file(csv_path)
    assert "sheet1" in sheets
    df = sheets["sheet1"]
    assert len(df) == 70
    assert "Control_OD" in df.columns


def test_parse_genuine_csv(fixtures_dir: Path) -> None:
    df = parse_data_file(fixtures_dir / "genuine_random.csv")["sheet1"]
    assert len(df) == 70
    assert {"Control_OD", "Treatment_OD", "Cell_Count"}.issubset(df.columns)
