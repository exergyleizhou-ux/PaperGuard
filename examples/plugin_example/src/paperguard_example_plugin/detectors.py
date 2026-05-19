"""Example plugin detector: flag numeric columns with zero variance.

Loaded automatically by `paperguard.core.registry.DetectorRegistry`
via the `paperguard.detectors` entry-point group.
"""
from __future__ import annotations

from typing import ClassVar

import numpy as np
import pandas as pd

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity


class ZeroVarianceDetector(BaseDetector):
    """Flag any numeric column whose values are all identical."""

    id: ClassVar[str] = "X1_ZERO_VARIANCE"
    name: ClassVar[str] = "Zero-Variance Column (example plugin)"
    description: ClassVar[str] = (
        "Numeric columns with zero variance — either a constant parameter "
        "or a copy-paste artifact."
    )
    academic_basis: ClassVar[str] = "Trivial; provided as plugin tutorial."
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
                        severity=Severity.NOTE,
                        summary=f"Column '{col}' has zero variance",
                        detail=(
                            f"All {len(values)} entries are {values.iloc[0]}. "
                            "Either a fixed experimental parameter or a "
                            "data-entry copy-paste."
                        ),
                        evidence={
                            "column": str(col),
                            "n": int(len(values)),
                            "constant_value": float(values.iloc[0]),
                        },
                        innocent_explanations=[
                            "Column is a fixed experimental parameter "
                            "(e.g., a treatment dose).",
                            "All samples truly produced an identical reading.",
                            "Column intentionally constant for reference.",
                        ],
                        academic_reference=self.academic_basis,
                    )
                )
        return findings
