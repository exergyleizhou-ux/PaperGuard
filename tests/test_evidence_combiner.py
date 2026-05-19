"""证据组合器 smoke test。"""
from __future__ import annotations

import pandas as pd

from paperguard.core.registry import DetectorRegistry
from paperguard.core.types import AuditReport, Severity
from paperguard.evidence.combiner import benjamini_hochberg, combine_evidence


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
