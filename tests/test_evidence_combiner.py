"""证据组合器 smoke test。"""
from __future__ import annotations

import pandas as pd

from paperguard.core.registry import DetectorRegistry
from paperguard.core.types import AuditReport, Finding, Severity
from paperguard.evidence.combiner import (
    _convergence_statement,
    benjamini_hochberg,
    combine_evidence,
)


def test_bh_monotonic_zero_input() -> None:
    assert benjamini_hochberg([]) == []


def test_bh_single_pvalue() -> None:
    qs = benjamini_hochberg([0.04])
    assert qs == [0.04]


def test_bh_orders_preserved() -> None:
    qs = benjamini_hochberg([0.001, 0.5, 0.04])
    assert len(qs) == 3
    # 输入第 0 个最小 → q 也应是最小
    assert qs[0] == min(qs)


def test_combiner_fabricated(fabricated_data: pd.DataFrame) -> None:
    registry = DetectorRegistry().register_default()
    report = AuditReport(paper_identifier="tests/fixtures/fabricated_geng_style.csv")
    for d in registry.all():
        # G4 需要文件路径，跳过它
        if d.id == "G4":
            continue
        # B1 需要 GRIMInput 列表，跳过
        if d.id == "B1":
            continue
        r = d.detect(fabricated_data, seed=42)
        report.detector_results.append(r)
        report.all_findings.extend(r.findings)

    combine_evidence(report)
    assert report.overall_severity == Severity.CRITICAL
    assert "CRITICAL" in report.combined_evidence_strength


def test_convergence_statement_empty_below_two() -> None:
    """A single line of evidence is not 'convergent' — no narrative."""
    assert _convergence_statement(0, []) == ""
    assert _convergence_statement(1, ["paper_mill_signature"]) == ""


def test_convergence_statement_investigate_framing_not_verdict() -> None:
    """>=2 clusters → convergence stated, framed as INVESTIGATE not guilt."""
    msg = _convergence_statement(2, ["benford", "paper_mill_signature"])
    assert "CONVERGENCE" in msg
    assert "INVESTIGATION" in msg
    low = msg.lower()
    # IRON RULE: never a verdict about a person
    for banned in ("guilty", "fraud", "fabricated by", "misconduct occurred"):
        assert banned not in low
    # names are listed so the convergence is concrete
    assert "benford" in low and "paper_mill_signature" in low


def test_convergence_strong_at_three_clusters() -> None:
    msg = _convergence_statement(3, ["a", "b", "c"])
    assert "strong" in msg
    assert "3 independent" in msg


def test_convergence_surfaced_in_report_two_clusters() -> None:
    """End-to-end: two findings from different clusters → convergence text."""
    registry = DetectorRegistry().register_default()
    seen: dict[str, str] = {}
    for d in registry.all():
        c = d.assumption_cluster
        if c and c not in seen:
            seen[c] = d.id
        if len(seen) >= 2:
            break
    ids = list(seen.values())[:2]
    assert len(ids) == 2, "need two distinct clusters for this test"

    report = AuditReport(paper_identifier="tests/convergence")
    for did in ids:
        report.all_findings.append(
            Finding(
                detector_id=did,
                detector_name=did,
                severity=Severity.CONCERN,
                summary="anomaly signal",
                detail="d",
            )
        )
    combine_evidence(report)
    assert "CONVERGENCE" in report.combined_evidence_strength
    assert "INVESTIGATION" in report.combined_evidence_strength
    low = report.combined_evidence_strength.lower()
    assert "guilty" not in low and "fraud" not in low
