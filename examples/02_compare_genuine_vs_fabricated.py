"""Example 2 — Run the full registry on both paired fixtures, print summaries.

Demonstrates that the same detector pipeline yields:
  - CRITICAL on the fabricated CSV (constant Δ between OD columns, biased digits)
  - PASS on the genuine CSV (gaussian noise, no inter-column determinism)

Run from the project root:

    python examples/02_compare_genuine_vs_fabricated.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from paperguard.core.registry import DetectorRegistry
from paperguard.core.types import AuditReport
from paperguard.evidence.combiner import combine_evidence


def scan_csv(path: Path) -> AuditReport:
    df = pd.read_csv(path)
    registry = DetectorRegistry().register_default()
    report = AuditReport(paper_identifier=str(path))
    for d_id in ("A1", "A3", "A5"):
        det = registry.get(d_id)
        if det is None:
            continue
        result = det.detect(df, seed=42)
        report.detector_results.append(result)
        report.all_findings.extend(result.findings)
    combine_evidence(report)
    return report


def main() -> None:
    fixtures = Path(__file__).parent.parent / "tests" / "fixtures"
    for name in ("fabricated_geng_style.csv", "genuine_random.csv"):
        report = scan_csv(fixtures / name)
        print(f"=== {name} ===")
        print(f"  Overall: {report.overall_severity.label}")
        print(f"  {report.combined_evidence_strength}")
        for f in report.all_findings:
            print(f"    [{f.severity.label}] {f.detector_id}: {f.summary}")
        print()


if __name__ == "__main__":
    main()
