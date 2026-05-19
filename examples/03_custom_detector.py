"""Example 3 — Write a custom detector.

Shows the minimal scaffold for adding a new detector. Here we implement
a toy "all-equal column" detector that flags any numeric column where all
N values are byte-identical (a degenerate case GRIM doesn't cover).

Run from the project root:

    python examples/03_custom_detector.py
"""
from __future__ import annotations

from typing import ClassVar

import numpy as np
import pandas as pd

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity


class AllEqualColumnDetector(BaseDetector):
    """Toy detector — a column whose every entry is identical is suspicious."""

    id: ClassVar[str] = "X1"
    name: ClassVar[str] = "All-Equal Column"
    description: ClassVar[str] = "Flags any numeric column with zero variance."
    academic_basis: ClassVar[str] = "Trivial; included for tutorial purposes."
    data_requirements: ClassVar[list[str]] = ["raw_numeric_values"]
    assumption_cluster: ClassVar[str] = "column_degeneracy"

    def check_applicability(self, data: pd.DataFrame) -> tuple[bool, str]:
        if not isinstance(data, pd.DataFrame):
            return False, "Expected DataFrame"
        if not len(data.select_dtypes(include=[np.number]).columns):
            return False, "No numeric columns"
        return True, ""

    def _detect(self, data: pd.DataFrame, seed: int) -> list[Finding]:
        findings: list[Finding] = []
        for col in data.select_dtypes(include=[np.number]).columns:
            values = data[col].dropna()
            if len(values) < 3:
                continue
            if values.nunique() == 1:
                findings.append(
                    Finding(
                        detector_id=self.id,
                        detector_name=self.name,
                        severity=Severity.CONCERN,
                        summary=f"Column '{col}' has zero variance",
                        detail=(
                            f"All {len(values)} rows of column '{col}' carry the "
                            f"same value {values.iloc[0]}. This may be intentional "
                            "(a fixed parameter) or may reflect a copy-paste error "
                            "in data entry."
                        ),
                        evidence={"column": str(col), "value": float(values.iloc[0])},
                        innocent_explanations=[
                            "The column is a fixed experimental parameter (e.g., dose).",
                            "Data entry copy-paste; can be confirmed against raw files.",
                            "All samples truly produced an identical reading (rare but possible).",
                        ],
                        academic_reference=self.academic_basis,
                    )
                )
        return findings


def main() -> None:
    df = pd.DataFrame(
        {
            "treatment_dose_mg": [5.0] * 10,  # fixed parameter
            "outcome": [1.2, 1.5, 1.4, 1.6, 1.3, 1.5, 1.4, 1.6, 1.5, 1.4],
        }
    )
    result = AllEqualColumnDetector().detect(df, seed=42)
    print(f"Applicable: {result.applicable}")
    for f in result.findings:
        print(f"  [{f.severity.label}] {f.summary}")
        for ie in f.innocent_explanations:
            print(f"    - {ie}")


if __name__ == "__main__":
    main()
