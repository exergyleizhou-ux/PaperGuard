"""selfcheck / diff / W8+W9 CLI 测试。"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from click.testing import CliRunner

from paperguard.cli import main


def test_selfcheck_runs() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["selfcheck"])
    assert result.exit_code == 0
    assert "A1:" in result.output
    assert "OK" in result.output or "installation" in result.output.lower()


def test_selfcheck_specific_detector() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["selfcheck", "--detector", "A3"])
    assert result.exit_code == 0
    assert "A3" in result.output


def test_diff_no_changes(tmp_path: Path) -> None:
    payload = {
        "overall_severity": 0,
        "all_findings": [
            {"detector_id": "A1", "summary": "x", "severity": 2}
        ],
    }
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text(json.dumps(payload))
    b.write_text(json.dumps(payload))
    runner = CliRunner()
    r = runner.invoke(main, ["diff", str(a), str(b)])
    assert r.exit_code == 0
    assert "No changes" in r.output


def test_diff_added(tmp_path: Path) -> None:
    a_payload = {"overall_severity": 0, "all_findings": []}
    b_payload = {
        "overall_severity": 2,
        "all_findings": [
            {"detector_id": "A1", "summary": "new-thing", "severity": 2}
        ],
    }
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text(json.dumps(a_payload))
    b.write_text(json.dumps(b_payload))
    runner = CliRunner()
    r = runner.invoke(main, ["diff", str(a), str(b)])
    assert r.exit_code == 0
    assert "new-thing" in r.output
    assert "1 new finding" in r.output


def test_explain_disabled_without_provider(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("PAPERGUARD_LLM_PROVIDER", raising=False)
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"overall_severity": 0, "all_findings": []}))
    runner = CliRunner()
    r = runner.invoke(main, ["explain", "--json", str(p)])
    # Aborted -> exit code 1
    assert r.exit_code != 0
    assert "LLM" in r.output or "PAPERGUARD_LLM_PROVIDER" in r.output


# --- W8: Windows GBK fix ---------------------------------------------------


def test_w8_gbk_reconfigure_on_win32(monkeypatch: Any) -> None:
    """On win32, stdout/stderr should be reconfigured to utf-8."""
    import importlib

    import paperguard.cli as cli_mod

    mock_stdout = MagicMock(spec=["reconfigure"])
    mock_stderr = MagicMock(spec=["reconfigure"])
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "stdout", mock_stdout)
    monkeypatch.setattr(sys, "stderr", mock_stderr)
    monkeypatch.delenv("PYTHONIOENCODING", raising=False)

    # Re-run the module-level guard by reloading
    importlib.reload(cli_mod)

    mock_stdout.reconfigure.assert_called_once_with(
        encoding="utf-8", errors="replace"
    )
    mock_stderr.reconfigure.assert_called_once_with(
        encoding="utf-8", errors="replace"
    )

    # Restore original platform to avoid side-effects
    importlib.reload(cli_mod)


# --- W9: Multi-file CLI support --------------------------------------------


def test_scan_multiple_files_positional(tmp_path: Path) -> None:
    """paperguard scan a.csv b.csv should process both files."""
    a = tmp_path / "a.csv"
    b = tmp_path / "b.csv"
    a.write_text("x,y\n1,2\n3,4\n")
    b.write_text("x,y\n5,6\n7,8\n")
    runner = CliRunner()
    r = runner.invoke(main, ["scan", str(a), str(b)])
    assert r.exit_code == 0
    assert "a.csv" in r.output
    assert "b.csv" in r.output


def test_scan_multiple_files_flag(tmp_path: Path) -> None:
    """paperguard scan -f a.csv -f b.csv should process both files."""
    a = tmp_path / "a.csv"
    b = tmp_path / "b.csv"
    a.write_text("x,y\n1,2\n3,4\n")
    b.write_text("x,y\n5,6\n7,8\n")
    runner = CliRunner()
    r = runner.invoke(main, ["scan", "-f", str(a), "-f", str(b)])
    assert r.exit_code == 0
    assert "a.csv" in r.output
    assert "b.csv" in r.output


def test_scan_single_file_backward_compat(tmp_path: Path) -> None:
    """Single-file scan still works (backward compatibility)."""
    f = tmp_path / "solo.csv"
    f.write_text("x,y\n1,2\n")
    runner = CliRunner()
    r = runner.invoke(main, ["scan", str(f)])
    assert r.exit_code == 0
    assert "solo.csv" in r.output
