"""Tests for the `paperguard scan-industrial` CLI command."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from click.testing import CliRunner

from paperguard.cli import scan_industrial_cmd


def _wastewater_csv(tmp_path: Path) -> Path:
    """Build a synthetic wastewater CSV with a deliberate I5 repetition."""
    n = 30
    df = pd.DataFrame({
        "sample_time": pd.date_range("2026-01-01", periods=n, freq="1h"),
        "influent_COD_kg_day": [1000.0 + i * 5 for i in range(n)],
        "influent_BOD_kg_day": [500.0 + i * 2 for i in range(n)],
        "effluent_COD_kg_day": [200.0 + i * 1 for i in range(n)],
        "effluent_BOD_kg_day": [50.0 + i * 0.2 for i in range(n)],
        "sludge_COD_kg_day": [600.0 + i * 3 for i in range(n)],
        "co2_emitted_kg_day_C": [200.0 + i * 1 for i in range(n)],
        "operator_log": [
            (
                "Identical operator log narrative repeated across every "
                "sample. " * 8
            )
        ] * n,
        "report_date": [
            pd.Timestamp("2026-01-01") + pd.Timedelta(days=i // 24)
            for i in range(n)
        ],
    })
    p = tmp_path / "ww.csv"
    df.to_csv(p, index=False)
    return p


def test_scan_industrial_invalid_domain(tmp_path: Path) -> None:
    p = tmp_path / "x.csv"
    p.write_text("a,b\n1,2\n", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(scan_industrial_cmd, [str(p), "--domain", "bogus"])
    assert result.exit_code != 0
    assert "Invalid value for" in result.output or "not one of" in result.output


def test_scan_industrial_unknown_file_type(tmp_path: Path) -> None:
    p = tmp_path / "x.txt"
    p.write_text("anything", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(
        scan_industrial_cmd, [str(p), "--domain", "wastewater"]
    )
    assert result.exit_code != 0
    assert "Unsupported file type" in result.output


def test_scan_industrial_csv_end_to_end(tmp_path: Path) -> None:
    p = _wastewater_csv(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        scan_industrial_cmd,
        [str(p), "--domain", "wastewater"],
    )
    assert result.exit_code == 0, result.output
    assert "I1 — Mass / Energy Balance" in result.output
    assert "I2 — SCADA Timestamp Integrity" in result.output
    assert "I5 — Batch-Log Narrative Repetition" in result.output
    assert "Summary" in result.output


def test_scan_industrial_json_output(tmp_path: Path) -> None:
    p = _wastewater_csv(tmp_path)
    out = tmp_path / "report.json"
    runner = CliRunner()
    result = runner.invoke(
        scan_industrial_cmd,
        [
            str(p), "--domain", "wastewater",
            "--output-json", str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["domain"] == "wastewater"
    assert data["n_rows"] == 30
    assert isinstance(data["findings"], list)
    # I5 should fire because operator_log is identical across all 30 rows
    assert any(f["detector_id"] == "I5" for f in data["findings"])


def test_scan_industrial_overrides(tmp_path: Path) -> None:
    """--tolerance-pct override flows through to I1 (test via JSON)."""
    p = _wastewater_csv(tmp_path)
    out = tmp_path / "report.json"
    runner = CliRunner()
    # With 0.01% tolerance, even a 1% balance miss should fire.
    result = runner.invoke(
        scan_industrial_cmd,
        [
            str(p), "--domain", "wastewater",
            "--tolerance-pct", "0.01",
            "--output-json", str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(out.read_text(encoding="utf-8"))
    # I1 should fire because the synthetic data has ~5% closure with 0.01%
    # tolerance the violation will trip every row.
    i1_findings = [f for f in data["findings"] if f["detector_id"] == "I1"]
    assert i1_findings, "I1 with 0.01% tolerance should fire on the test data"


def test_scan_industrial_case_insensitive_domain(tmp_path: Path) -> None:
    p = _wastewater_csv(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        scan_industrial_cmd,
        [str(p), "--domain", "WASTEWATER"],
    )
    assert result.exit_code == 0


def test_scan_industrial_no_verdict_words(tmp_path: Path) -> None:
    """Privacy iron rule: CLI output must not use verdict words."""
    p = _wastewater_csv(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        scan_industrial_cmd, [str(p), "--domain", "wastewater"]
    )
    lower = result.output.lower()
    for word in ("fraud", "fabrication", "misconduct", "造假", "cheating"):
        assert word not in lower, f"forbidden {word!r} in CLI output"
