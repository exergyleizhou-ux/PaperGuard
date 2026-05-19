"""selfcheck / diff CLI 测试。"""
from __future__ import annotations

import json
from pathlib import Path

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
