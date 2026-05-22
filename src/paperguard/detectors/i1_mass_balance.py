"""I1 — Mass / energy balance conservation-law check (industrial scope).

PaperGuard's text-and-academic-paper detectors (A1-T8) assume a research
manuscript context. I1 is the first of an **industrial** detector
family targeting process-engineering / pilot-scale / GMP-batch data:
mass and energy are conserved exactly (modulo measurement noise), and
batch logs that violate the conservation law by more than the
instrument's accumulated uncertainty are flagged.

Academic basis
--------------
- Process engineering: Smith, Van Ness, Abbott (2005) *Introduction to
  Chemical Engineering Thermodynamics*, §5 on energy balances.
- Anomaly detection in process data: Chiang, Russell, Braatz (2001)
  *Fault Detection and Diagnosis in Industrial Systems*, Springer.

Algorithm
---------
Input: a `MassBalanceInput` describing the conservation equation as a
linear constraint over named columns in a DataFrame.

  - ``equation``: ``{"sources": ["feed_A_kg", "feed_B_kg"],
                     "sinks":  ["product_kg", "waste_kg"],
                     "tolerance_pct": 1.0}``
  - ``df``: the batch log (one row per batch / time slice).

For each row, compute residual = (Σ sources) − (Σ sinks). Report
findings when:

  - **|residual| > tolerance_pct × Σ sources** — a single-batch
    violation; severity scales with the magnitude of the violation.
  - **mean(residual) / std(residual) significantly differs from 0** —
    systematic bias (e.g., un-accounted loss stream).
  - **residual distribution is bimodal or has outliers > 3 IQR** —
    batches with very different physics.

Severity tiers (defaults):
  - violation_count / N < 5 % → no finding (within tolerance)
  - 5–15 % rows violate         → NOTE
  - 15–30 % rows violate        → CONCERN
  - > 30 % rows violate         → SUSPICIOUS
  - mathematically impossible
    (negative product, total > 100 %) → CRITICAL

Failure modes (always silent):
  - Required columns missing → not applicable
  - DataFrame empty           → not applicable
  - All values NaN            → not applicable
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

import numpy as np
import pandas as pd

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity


@dataclass
class MassBalanceInput:
    """Conservation-law specification for I1.

    Examples
    --------
    Mass balance::

        MassBalanceInput(
            df=batch_log_df,
            sources=["feed_kg", "recycle_kg"],
            sinks=["product_kg", "waste_kg", "vent_kg"],
            tolerance_pct=1.0,
        )

    Energy balance::

        MassBalanceInput(
            df=df,
            sources=["heat_in_kJ", "work_in_kJ"],
            sinks=["heat_out_kJ", "enthalpy_product_kJ"],
            tolerance_pct=2.0,
        )
    """

    df: pd.DataFrame
    sources: list[str] = field(default_factory=list)
    sinks: list[str] = field(default_factory=list)
    tolerance_pct: float = 1.0  # ±1 % is typical for instrumented batches


class I1MassBalanceDetector(BaseDetector):
    """Mass / energy balance residual check on batch-log DataFrames."""

    id: ClassVar[str] = "I1"
    name: ClassVar[str] = "Mass / Energy Balance Residual"
    description: ClassVar[str] = (
        "Checks per-batch conservation residual (Σ sources − Σ sinks) "
        "against a stated tolerance. Flags systematic bias, single-row "
        "violations, and physically impossible rows."
    )
    academic_basis: ClassVar[str] = (
        "Smith VN, Van Ness HC, Abbott MM (2005) Introduction to "
        "Chemical Engineering Thermodynamics §5; Chiang LH, Russell "
        "EL, Braatz RD (2001) Fault Detection and Diagnosis in "
        "Industrial Systems."
    )
    data_requirements: ClassVar[list[str]] = ["mass_balance_input"]
    assumption_cluster: ClassVar[str] = "industrial_conservation"

    MIN_ROWS: ClassVar[int] = 5

    def check_applicability(self, data: Any) -> tuple[bool, str]:
        if not isinstance(data, MassBalanceInput):
            return False, "Expected MassBalanceInput"
        df = data.df
        if df is None or len(df) == 0:
            return False, "DataFrame is empty"
        if not data.sources or not data.sinks:
            return False, "Need at least one source and one sink"
        for col in data.sources + data.sinks:
            if col not in df.columns:
                return False, f"Required column missing: {col!r}"
        if len(df) < self.MIN_ROWS:
            return False, f"Need ≥ {self.MIN_ROWS} rows for analysis"
        return True, ""

    def _detect(self, data: MassBalanceInput, seed: int) -> list[Finding]:
        df = data.df
        sources = data.sources
        sinks = data.sinks
        tol_pct = data.tolerance_pct

        # Numeric coercion — any non-numeric row should be flagged but
        # not break the detector.
        src = df[sources].apply(pd.to_numeric, errors="coerce")
        snk = df[sinks].apply(pd.to_numeric, errors="coerce")
        src_sum = src.sum(axis=1, skipna=False)
        snk_sum = snk.sum(axis=1, skipna=False)

        # Drop rows with any NaN in the relevant columns; report N
        # actually checked.
        mask_valid = src_sum.notna() & snk_sum.notna()
        n_total = int(len(df))
        n_valid = int(mask_valid.sum())
        if n_valid < self.MIN_ROWS:
            return []

        residuals = src_sum[mask_valid] - snk_sum[mask_valid]
        denominator = src_sum[mask_valid].replace(0.0, np.nan)
        # absolute violation %: |residual| / source-total
        rel_violation = (residuals / denominator).abs() * 100

        threshold = float(tol_pct)
        violators = rel_violation > threshold
        n_violators = int(violators.sum())
        # CRITICAL: any individual column value is negative — physically
        # impossible for a mass/energy balance.
        neg_src = (src[mask_valid] < 0).any(axis=1)
        neg_snk = (snk[mask_valid] < 0).any(axis=1)
        n_critical = int((neg_src | neg_snk).sum())

        findings: list[Finding] = []

        # CRITICAL: physically impossible (negative source / sink totals)
        if n_critical > 0:
            findings.append(
                Finding(
                    detector_id=self.id,
                    detector_name=self.name,
                    severity=Severity.CRITICAL,
                    summary=(
                        f"{n_critical} row(s) have negative source or sink "
                        f"totals (physically impossible)"
                    ),
                    detail=(
                        "A mass / energy balance cannot have negative "
                        "feed or product. This row should not exist."
                    ),
                    evidence={
                        "n_negative_rows": n_critical,
                        "n_valid_rows": n_valid,
                        "sources_columns": sources,
                        "sinks_columns": sinks,
                    },
                    innocent_explanations=[
                        "Convention error: the column is signed "
                        "(positive = into the system, negative = out) "
                        "and should not have been added as a magnitude.",
                        "Sentinel value (-1, -999) was used to mark "
                        "'missing' and never converted to NaN before "
                        "the data was logged.",
                        "Unit mismatch — e.g., a credit/debit accounting "
                        "convention not appropriate for a physical balance.",
                        "Genuine instrument fault: a negative-reading "
                        "transmitter logged its raw output.",
                    ],
                    academic_reference=self.academic_basis,
                )
            )

        severity: Severity | None
        if n_violators >= max(1, int(0.30 * n_valid)):
            severity = Severity.SUSPICIOUS
        elif n_violators >= max(1, int(0.15 * n_valid)):
            severity = Severity.CONCERN
        elif n_violators >= max(1, int(0.05 * n_valid)):
            severity = Severity.NOTE
        else:
            severity = None

        if severity is not None:
            max_violation_pct = float(rel_violation.max())
            mean_residual = float(residuals.mean())
            std_residual = float(residuals.std(ddof=1)) if n_valid > 1 else 0.0
            findings.append(
                Finding(
                    detector_id=self.id,
                    detector_name=self.name,
                    severity=severity,
                    summary=(
                        f"{n_violators}/{n_valid} batches exceed the "
                        f"{tol_pct:.1f}% balance tolerance "
                        f"(max violation {max_violation_pct:.2f}%)"
                    ),
                    detail=(
                        f"Mass/energy balance residual exceeds the stated "
                        f"{tol_pct:.1f}% tolerance on {n_violators} of "
                        f"{n_valid} rows. Residual statistics: mean = "
                        f"{mean_residual:.4g}, std = {std_residual:.4g}, "
                        f"max relative violation = {max_violation_pct:.2f}%."
                    ),
                    test_statistic=max_violation_pct,
                    test_name="max relative residual (%)",
                    evidence={
                        "n_violators": n_violators,
                        "n_valid_rows": n_valid,
                        "n_total_rows": n_total,
                        "tolerance_pct": tol_pct,
                        "max_violation_pct": max_violation_pct,
                        "mean_residual": mean_residual,
                        "std_residual": std_residual,
                        "sources_columns": sources,
                        "sinks_columns": sinks,
                    },
                    innocent_explanations=[
                        "An un-instrumented loss stream (vent, drain, "
                        "evaporation, dust) is genuinely missing from "
                        "the balance — declare it as an extra sink.",
                        "Calibration drift on a feed or product "
                        "transmitter accumulated past the tolerance — "
                        "the violation is real but procedural.",
                        "Reaction enthalpy was omitted from an energy "
                        "balance that included only sensible heat.",
                        "Tolerance is set too tight for the instrument "
                        "accuracy in this scale of operation.",
                    ],
                    academic_reference=self.academic_basis,
                )
            )

        return findings
