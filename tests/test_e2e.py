"""端到端测试 — 扫描造假/真实数据，确认报告正确生成。"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from click.testing import CliRunner

from paperguard.cli import main


def test_scan_fabricated_csv(fixtures_dir: Path) -> None:
    runner = CliRunner()
    csv = fixtures_dir / "fabricated_geng_style.csv"
    result = runner.invoke(main, ["scan", "-f", str(csv)])
    assert result.exit_code == 0, result.output
    assert "Overall: CRITICAL" in result.output or "Overall: SUSPICIOUS" in result.output


def test_scan_genuine_csv(tmp_path: Path) -> None:
    rng = np.random.default_rng(42)
    n = 70
    df = pd.DataFrame(
        {
            "Replicate": range(1, n + 1),
            "Control_OD": rng.normal(2.5, 0.3, size=n).round(3),
            "Treatment_OD": rng.normal(2.8, 0.3, size=n).round(3),
            "Cell_Count": rng.integers(3000, 6000, size=n),
        }
    )
    csv_path = tmp_path / "genuine.csv"
    df.to_csv(csv_path, index=False)

    runner = CliRunner()
    result = runner.invoke(main, ["scan", "-f", str(csv_path)])
    assert result.exit_code == 0, result.output
    assert "Overall: CRITICAL" not in result.output
    assert "Overall: SUSPICIOUS" not in result.output


def test_scan_existing_genuine_fixture(fixtures_dir: Path) -> None:
    """用 Section 3 生成的真实数据 CSV 跑一遍 CLI。"""
    runner = CliRunner()
    csv = fixtures_dir / "genuine_random.csv"
    result = runner.invoke(main, ["scan", "-f", str(csv)])
    assert result.exit_code == 0, result.output
    # 真实数据不应被定级为 CRITICAL/SUSPICIOUS
    assert "Overall: CRITICAL" not in result.output
    assert "Overall: SUSPICIOUS" not in result.output
