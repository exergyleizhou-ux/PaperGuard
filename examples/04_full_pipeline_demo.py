"""Example 4 — Full-pipeline demo, exercising every detector.

This script:
- Creates synthetic inputs for each detector type
- Runs them through the registry
- Renders a single combined report
- Shows how to programmatically inspect findings before serializing

Run from the project root:

    python examples/04_full_pipeline_demo.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from paperguard.core.registry import DetectorRegistry
from paperguard.core.types import AuditReport
from paperguard.detectors.b1_grim import GRIMInput
from paperguard.detectors.b5_tiva import TIVAInput
from paperguard.detectors.b6_grimmer import GRIMMERInput
from paperguard.detectors.c1_carlisle import BaselineVariable, CarlisleInput
from paperguard.detectors.t1_text_similarity import TextSimilarityInput
from paperguard.evidence.combiner import combine_evidence
from paperguard.reporter.terminal import print_report


def main() -> None:
    registry = DetectorRegistry().register_default(load_plugins=False)
    report = AuditReport(paper_identifier="examples/04_demo")

    # --- Numeric forensics on a fabricated DataFrame
    fixtures = Path(__file__).parent.parent / "tests" / "fixtures"
    df = pd.read_csv(fixtures / "fabricated_geng_style.csv")
    for d_id in ("A1", "A2", "A3", "A5"):
        det = registry.get(d_id)
        if det is None:
            continue
        r = det.detect(df, seed=42)
        report.detector_results.append(r)
        report.all_findings.extend(r.findings)

    # --- B1 GRIM: Likert-scale impossible mean
    b1 = registry.get("B1")
    if b1 is not None:
        r = b1.detect([GRIMInput(mean=3.15, n=10, decimal_places=2, label="Q1")], seed=42)
        report.detector_results.append(r)
        report.all_findings.extend(r.findings)

    # --- B4 Statcheck: a synthetic inconsistent t-test
    b4 = registry.get("B4")
    if b4 is not None:
        text = (
            "We compared treatment vs control. "
            "A significant effect was observed, t(38) = 2.03, p = 0.001. "
            "Replication: t(20) = 1.5, p < 0.05. "
            "ANOVA: F(2, 47) = 4.12, p = 0.022."
        )
        r = b4.detect(text, seed=42)
        report.detector_results.append(r)
        report.all_findings.extend(r.findings)

    # --- B5 TIVA: low-variance z values
    b5 = registry.get("B5")
    if b5 is not None:
        r = b5.detect(
            TIVAInput(
                p_values=[0.045, 0.047, 0.049, 0.046, 0.048, 0.05, 0.044],
                label="Suspicious lab",
            ),
            seed=42,
        )
        report.detector_results.append(r)
        report.all_findings.extend(r.findings)

    # --- B6 GRIMMER: impossible mean/SD pair
    b6 = registry.get("B6")
    if b6 is not None:
        r = b6.detect(
            [GRIMMERInput(mean=3.15, sd=1.0, n=10, label="Likert Q1")], seed=42
        )
        report.detector_results.append(r)
        report.all_findings.extend(r.findings)

    # --- C1 Carlisle: overly balanced RCT baseline
    c1 = registry.get("C1")
    if c1 is not None:
        vars_ = [
            BaselineVariable(f"var{i}", n1=50, mean1=10.0, sd1=2.0,
                              n2=50, mean2=10.01, sd2=2.0)
            for i in range(8)
        ]
        r = c1.detect(CarlisleInput(trial_id="DEMO-TRIAL", variables=vars_), seed=42)
        report.detector_results.append(r)
        report.all_findings.extend(r.findings)

    # --- T1 Text similarity vs a single corpus entry
    t1 = registry.get("T1")
    if t1 is not None:
        common = (
            "Mitochondria are the powerhouse of the cell, generating ATP through "
            "oxidative phosphorylation in eukaryotic cells."
        )
        r = t1.detect(
            TextSimilarityInput(
                query_text=common, corpus={"prior_draft": common + " Extra text here."}
            ),
            seed=42,
        )
        report.detector_results.append(r)
        report.all_findings.extend(r.findings)

    # --- T3 + T4: data availability + tortured-phrase audit on the same blob
    t3 = registry.get("T3")
    t4 = registry.get("T4")
    sample_text = (
        "We trained a profound neural organization on colossal information. "
        "Statistical analysis used arbitrary backwoods classifiers. "
        "Data are available from the corresponding author upon reasonable request. "
        + ("lorem ipsum " * 30)
    )
    if t3 is not None:
        r = t3.detect(sample_text, seed=42)
        report.detector_results.append(r)
        report.all_findings.extend(r.findings)
    if t4 is not None:
        r = t4.detect(sample_text, seed=42)
        report.detector_results.append(r)
        report.all_findings.extend(r.findings)

    # --- Aggregate + render
    combine_evidence(report)
    print_report(report, lang="en")


if __name__ == "__main__":
    main()


# Suppress F401: np kept for users who extend with numpy-using detectors
_ = np
