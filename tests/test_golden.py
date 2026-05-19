"""Golden tests — 固化对 fixture 数据的预期检测结果。

任何未来对检测器的改动一旦让 fabricated_geng_style.csv 检出 <
GOLDEN_FABRICATED_MIN_CRITICAL 个 CRITICAL，或让 genuine_random.csv
触发 ≥ 1 个 SUSPICIOUS+ → 测试失败。

这是召回率与误报率的"防退化"闸门。
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from paperguard.core.registry import DetectorRegistry
from paperguard.core.types import AuditReport, Severity
from paperguard.evidence.combiner import combine_evidence

# 黄金阈值 —— 来自 0.9.0 当前实际表现。改动检测器前请重新校准。
GOLDEN_FABRICATED_MIN_CRITICAL = 2
GOLDEN_FABRICATED_MIN_SUSPICIOUS = 2
GOLDEN_GENUINE_MAX_CONCERN_OR_HIGHER = 1


def _scan_csv_dataframe_only(path: Path) -> AuditReport:
    """只跑表格类检测器（不依赖文件路径检测器）。"""
    registry = DetectorRegistry().register_default(load_plugins=False)
    df = pd.read_csv(path)
    report = AuditReport(paper_identifier=str(path))
    for d_id in ("A1", "A2", "A3", "A5", "A6", "A7", "D1", "D2"):
        det = registry.get(d_id)
        if det is None:
            continue
        r = det.detect(df, seed=42)
        report.detector_results.append(r)
        report.all_findings.extend(r.findings)
    combine_evidence(report)
    return report


def test_golden_fabricated_is_critical(fixtures_dir: Path) -> None:
    report = _scan_csv_dataframe_only(fixtures_dir / "fabricated_geng_style.csv")
    assert report.overall_severity == Severity.CRITICAL, (
        f"fabricated fixture should be CRITICAL but is {report.overall_severity.label}"
    )

    n_crit = sum(1 for f in report.all_findings if f.severity == Severity.CRITICAL)
    n_susp = sum(1 for f in report.all_findings if f.severity == Severity.SUSPICIOUS)
    assert n_crit >= GOLDEN_FABRICATED_MIN_CRITICAL, (
        f"fabricated CRITICAL count regressed: {n_crit} < {GOLDEN_FABRICATED_MIN_CRITICAL}"
    )
    assert (n_crit + n_susp) >= GOLDEN_FABRICATED_MIN_SUSPICIOUS, (
        f"fabricated CRITICAL+SUSPICIOUS count regressed: {n_crit + n_susp}"
    )


def test_golden_genuine_is_clean(fixtures_dir: Path) -> None:
    report = _scan_csv_dataframe_only(fixtures_dir / "genuine_random.csv")
    n_high = sum(
        1 for f in report.all_findings if f.severity >= Severity.CONCERN
    )
    assert n_high <= GOLDEN_GENUINE_MAX_CONCERN_OR_HIGHER, (
        f"genuine fixture produces too many CONCERN+ findings: {n_high}"
    )
    assert report.overall_severity < Severity.SUSPICIOUS, (
        f"genuine fixture overall severity inflated to "
        f"{report.overall_severity.label}"
    )
