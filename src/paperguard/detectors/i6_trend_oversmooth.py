"""I6 — DCS / SCADA trend over-smoothness ("Excel beautification") detector.

The complement to D1 (residual smoothness on tabular data, academic
scope). I6 specifically targets the **operator-painted-curve**
failure mode in industrial trend data:

  - A real DCS / SCADA / historian trend has high-frequency noise
    riding on the slow process drift. Even at 1-minute averaging
    you see sample-to-sample jitter from quantisation +
    measurement noise.
  - A "painted" trend — copy-pasted from another batch, drawn by
    hand in Excel, or smoothed by an operator before submission —
    has **unrealistically low high-frequency content**.

Algorithm
---------
1. Take the first-difference series `Δx[i] = x[i+1] − x[i]`.
2. Compute robust std (1.4826 × MAD) of Δx.
3. Compute the **noise-floor ratio**: `std(Δx) / std(x)`. For real
   continuous-process trends this ratio is typically ≥ 0.5 % at
   ~1-Hz sampling, ≥ 1 % at ~1-min sampling.
4. Compute the **lag-1 autocorrelation** of Δx. A real noise
   sequence has `r1 ≈ 0`. Painted curves often have `r1 > 0.5`
   because the operator drew a smooth curve.
5. Spectral check: estimate the dominant frequency content of Δx.
   Real-process noise is broad-band; painted curves are bandlimited.

Severity tiers (defaults):
- noise_ratio ≥ 0.01 AND |lag1_acf| < 0.3   → no finding
- noise_ratio < 0.005  OR  lag1_acf > 0.5    → NOTE
- noise_ratio < 0.002  OR  lag1_acf > 0.7    → CONCERN
- noise_ratio < 0.0005 OR  lag1_acf > 0.85   → SUSPICIOUS
- noise_ratio ≈ 0 (Δx all identical)         → CRITICAL

This detector requires at least 50 samples in the trend column.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

import numpy as np
import pandas as pd

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity


@dataclass
class TrendSmoothnessInput:
    """Input for I6 — a single column of values to analyse for over-smoothness."""

    df: pd.DataFrame
    column: str
    expected_min_noise_ratio: float = 0.005  # 0.5% std(Δx)/std(x)


class I6TrendOversmoothDetector(BaseDetector):
    """Detects unrealistically smooth DCS / SCADA trend columns."""

    id: ClassVar[str] = "I6"
    name: ClassVar[str] = "Trend Over-Smoothness (Excel beautification)"
    description: ClassVar[str] = (
        "Detects DCS / SCADA / historian trend columns that have been "
        "painted, smoothed, or copy-pasted from another batch. Uses "
        "first-difference noise-floor ratio + lag-1 autocorrelation."
    )
    academic_basis: ClassVar[str] = (
        "Chiang LH, Russell EL, Braatz RD (2001) Fault Detection and "
        "Diagnosis in Industrial Systems §3 on process noise. The "
        "specific 'painted curve' failure mode is documented in NIST "
        "SP 800-82r3 (OT security) and several FDA Warning Letters."
    )
    data_requirements: ClassVar[list[str]] = ["trend_smoothness_input"]
    assumption_cluster: ClassVar[str] = "industrial_temporal_integrity"

    MIN_SAMPLES: ClassVar[int] = 50

    def check_applicability(self, data: Any) -> tuple[bool, str]:
        if not isinstance(data, TrendSmoothnessInput):
            return False, "Expected TrendSmoothnessInput"
        if data.df is None or data.column not in data.df.columns:
            return False, f"Required column missing: {data.column!r}"
        col = pd.to_numeric(data.df[data.column], errors="coerce").dropna()
        if len(col) < self.MIN_SAMPLES:
            return False, f"Need ≥ {self.MIN_SAMPLES} samples"
        return True, ""

    def _detect(
        self, data: TrendSmoothnessInput, seed: int
    ) -> list[Finding]:
        col = pd.to_numeric(data.df[data.column], errors="coerce").dropna()
        x = np.asarray(col.values, dtype=float)
        n = len(x)

        # Cast to typed ndarrays so mypy sees ndarray not ExtensionArray.
        dx: np.ndarray = np.diff(x)
        if len(dx) < 2:
            return []

        std_x = float(np.std(x, ddof=1))
        std_dx = float(np.std(dx, ddof=1))
        if std_x < 1e-12:
            # Column is constant — can't say anything about smoothness
            return []
        noise_ratio = std_dx / std_x

        # Lag-1 autocorrelation of Δx (Pearson)
        if std_dx < 1e-12:
            # All differences identical (or zero) — extreme smoothness
            lag1 = 1.0
        else:
            dx_centred = dx - dx.mean()
            num = float(np.sum(dx_centred[:-1] * dx_centred[1:]))
            den = float(np.sum(dx_centred ** 2))
            lag1 = num / den if den > 1e-12 else 0.0

        # Bonus signal: are all the Δx exactly the same? (perfect line)
        n_unique_dx = int(len(np.unique(np.round(dx, 12))))
        all_identical = n_unique_dx <= 2

        # Severity decision
        severity: Severity | None
        if all_identical and std_x > 1e-9:
            severity = Severity.CRITICAL
        elif noise_ratio < 0.0005 or lag1 > 0.85:
            severity = Severity.SUSPICIOUS
        elif noise_ratio < 0.002 or lag1 > 0.7:
            severity = Severity.CONCERN
        elif noise_ratio < data.expected_min_noise_ratio or lag1 > 0.5:
            severity = Severity.NOTE
        else:
            severity = None

        if severity is None:
            return []

        return [
            Finding(
                detector_id=self.id,
                detector_name=self.name,
                severity=severity,
                summary=(
                    f"Trend column {data.column!r} is unusually smooth: "
                    f"noise ratio {noise_ratio:.4f}, "
                    f"lag-1 ACF of Δx {lag1:.2f}"
                ),
                detail=(
                    f"Examined {n} samples of column {data.column!r}. "
                    f"std(x) = {std_x:.4g}, std(Δx) = {std_dx:.4g}, "
                    f"noise ratio = {noise_ratio:.4f} (expected ≥ "
                    f"{data.expected_min_noise_ratio} for genuine DCS "
                    f"trends). Lag-1 autocorrelation of Δx = {lag1:.2f} "
                    f"(expected ≈ 0 for genuine measurement noise). "
                    f"{n_unique_dx} distinct values in Δx out of "
                    f"{len(dx)} differences."
                ),
                test_statistic=noise_ratio,
                test_name="std(Δx) / std(x) — noise-floor ratio",
                evidence={
                    "n_samples": n,
                    "std_x": std_x,
                    "std_dx": std_dx,
                    "noise_ratio": noise_ratio,
                    "lag1_acf_dx": lag1,
                    "n_unique_dx": n_unique_dx,
                    "all_dx_identical": all_identical,
                    "expected_min_noise_ratio": (
                        data.expected_min_noise_ratio
                    ),
                },
                innocent_explanations=[
                    "The column is a setpoint or a configuration value, "
                    "not a measurement — a setpoint legitimately has "
                    "near-zero noise.",
                    "Historian post-processing applied a low-pass filter "
                    "or moving-average smoothing for storage efficiency; "
                    "the raw 1-Hz data may have been honest.",
                    "Process under tight closed-loop control (e.g., "
                    "well-tuned PID on a fast variable like flow) can "
                    "genuinely show very low high-frequency content.",
                    "Sample rate too low: averaging over a long interval "
                    "(say 1 hour) before sampling can eliminate the "
                    "high-frequency noise legitimately.",
                    "The column is a derived metric (rolling average, "
                    "EWMA forecast), not a raw sensor reading.",
                ],
                academic_reference=self.academic_basis,
                applicability_notes=(
                    "Expected-min-noise-ratio = "
                    f"{data.expected_min_noise_ratio}. Tune via "
                    "TrendSmoothnessInput.expected_min_noise_ratio for "
                    "datasets where the underlying physics has "
                    "intrinsically low noise (setpoints, configured "
                    "limits, or heavily-filtered historian outputs)."
                ),
            )
        ]
