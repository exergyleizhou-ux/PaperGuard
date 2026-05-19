"""Example 1 — Scan the fabricated fixture and inspect the report.

Run from the project root:

    python examples/01_scan_fabricated.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from paperguard.core.registry import DetectorRegistry
from paperguard.core.types import AuditReport
from paperguard.detectors.g4_metadata_forensics import MetadataForensicsInput
from paperguard.evidence.combiner import combine_evidence
from paperguard.reporter.terminal import print_report


def main() -> None:
    fixture = Path(__file__).parent.parent / "tests" / "fixtures" / "fabricated_geng_style.csv"
    df = pd.read_csv(fixture)

    registry = DetectorRegistry().register_default()
    report = AuditReport(paper_identifier=str(fixture))

    for d_id in ("A1", "A3", "A5"):
        detector = registry.get(d_id)
        if detector is None:
            continue
        result = detector.detect(df, seed=42)
        report.detector_results.append(result)
        report.all_findings.extend(result.findings)

    # G4 needs a file path, not a DataFrame
    g4 = registry.get("G4")
    if g4 is not None:
        result = g4.detect(MetadataForensicsInput(file_path=fixture), seed=42)
        report.detector_results.append(result)
        report.all_findings.extend(result.findings)

    combine_evidence(report)
    print_report(report)


if __name__ == "__main__":
    main()
