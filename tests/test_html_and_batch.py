"""HTML 报告 + batch 命令测试。"""
from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from paperguard.cli import main
from paperguard.core.types import AuditReport, Finding, Severity
from paperguard.reporter.html_export import export_html, render_html


def test_html_render_empty_report() -> None:
    r = AuditReport(paper_identifier="x.csv", overall_severity=Severity.PASS)
    html = render_html(r)
    assert "<html" in html
    assert "PASS" in html
    assert "No anomalies detected" in html
    assert "Disclaimer" in html  # 免责声明必须有


def test_html_render_with_finding() -> None:
    r = AuditReport(paper_identifier="x.csv", overall_severity=Severity.CRITICAL)
    r.combined_evidence_strength = "Total findings: 1 | CRITICAL: 1"
    r.all_findings = [
        Finding(
            detector_id="A1",
            detector_name="Test Detector",
            severity=Severity.CRITICAL,
            summary="Test summary",
            detail="Test detail",
            p_value=1e-9,
            p_value_adjusted=2e-9,
            evidence={"key": "value"},
            innocent_explanations=["Reason 1", "Reason 2"],
            academic_reference="Some Author (2020)",
        )
    ]
    html = render_html(r)
    assert "Test summary" in html
    assert "Test detail" in html
    assert "Reason 1" in html
    assert "Some Author" in html
    assert "1.0000e-09" in html or "1e-09" in html.lower()


def test_html_escapes_html_chars() -> None:
    r = AuditReport(
        paper_identifier="<script>alert('x')</script>",
        overall_severity=Severity.PASS,
    )
    html = render_html(r)
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html


def test_export_html_writes_file(tmp_path: Path) -> None:
    r = AuditReport(paper_identifier="x", overall_severity=Severity.PASS)
    p = tmp_path / "report.html"
    export_html(r, p)
    assert p.exists()
    assert "<html" in p.read_text(encoding="utf-8")


def test_batch_command_csv_glob(tmp_path: Path) -> None:
    """batch 在两个 fixture CSV 上跑，应生成 summary + per-file 报告。"""
    runner = CliRunner()
    # 用 fixtures 目录的绝对 glob
    fixtures = Path(__file__).parent / "fixtures"
    glob_pattern = str(fixtures / "*.csv")
    out_dir = tmp_path / "batch_out"
    result = runner.invoke(
        main, ["batch", "--glob", glob_pattern, "--out-dir", str(out_dir)]
    )
    assert result.exit_code == 0, result.output
    assert (out_dir / "summary.json").exists()
    # 2 个 fixture → 2 个 json + 2 个 html
    jsons = list(out_dir.glob("*.json"))
    htmls = list(out_dir.glob("*.html"))
    assert len(jsons) == 3  # 2 fixtures + summary
    assert len(htmls) == 2
