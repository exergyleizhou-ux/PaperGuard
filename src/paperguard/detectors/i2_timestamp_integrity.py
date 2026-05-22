"""I2 — SCADA / DCS timestamp integrity (industrial scope).

Industrial control systems (Honeywell DCS, Yokogawa CENTUM,
Rockwell PlantPAx, OSIsoft PI System) generate timestamped trend
data at a deterministic sample rate. Honest data shows:

  - **Roughly uniform sample interval Δt** (jitter << configured rate)
  - **No back-dated insertions** (timestamp strictly monotone)
  - **No "round-number" timestamps** (operators handwriting times
    over-prefer XX:00:00 / XX:15:00 etc.)

Tampering signatures
--------------------
- **Back-fill**: an operator writes a value at the end of the shift
  with a fabricated timestamp inside the shift; Δt distribution
  becomes bimodal or has a single large outlier.
- **Hand-written batch log**: timestamps cluster on round minutes,
  unlike SCADA which would have second-precision timestamps.
- **Time-zone shift**: silent UTC↔local-time switch leaves a
  ~3600s or ~28800s discontinuity.

Algorithm
---------
1. Parse the timestamp column to ``pandas.Timestamp``.
2. Compute Δt between consecutive rows.
3. Robust outlier test on Δt: median ± 3 × MAD.
4. Round-minute clustering: % of Δt values whose second component
   is exactly 0; compare against an expected ≤ 5%.
5. Monotonicity: count rows where t[i+1] < t[i].

Severity tiers (defaults):
  - all clean → no finding
  - 1-2 outliers / no monotone violation → NOTE
  - ≥ 3 outliers OR round-clustering > 15 % → CONCERN
  - any monotone violation OR clustering > 50 % → SUSPICIOUS
  - timezone-shift discontinuity (Δt ≈ ±3600s or ±28800s with N>5 jumps) → CRITICAL
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

import numpy as np
import pandas as pd

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity


@dataclass
class TimestampIntegrityInput:
    df: pd.DataFrame
    timestamp_column: str = "timestamp"
    # Expected nominal sample period in seconds. If unset, we infer
    # from the median Δt.
    expected_dt_seconds: float | None = None


class I2TimestampIntegrityDetector(BaseDetector):
    """SCADA / DCS timestamp integrity check."""

    id: ClassVar[str] = "I2"
    name: ClassVar[str] = "SCADA Timestamp Integrity"
    description: ClassVar[str] = (
        "Detects back-filled SCADA timestamps via Δt outliers, "
        "round-minute clustering, monotonicity violations, and "
        "timezone-shift discontinuities."
    )
    academic_basis: ClassVar[str] = (
        "Chiang LH, Russell EL, Braatz RD (2001) Fault Detection and "
        "Diagnosis in Industrial Systems §3. Industrial-data "
        "tampering signatures are documented in NIST SP 800-82r3 "
        "(Guide to Operational Technology Security)."
    )
    data_requirements: ClassVar[list[str]] = ["timestamp_input"]
    assumption_cluster: ClassVar[str] = "industrial_temporal_integrity"

    MIN_ROWS: ClassVar[int] = 20

    def check_applicability(self, data: Any) -> tuple[bool, str]:
        if not isinstance(data, TimestampIntegrityInput):
            return False, "Expected TimestampIntegrityInput"
        df = data.df
        if df is None or len(df) < self.MIN_ROWS:
            return False, f"Need ≥ {self.MIN_ROWS} rows"
        if data.timestamp_column not in df.columns:
            return False, (
                f"Required column missing: {data.timestamp_column!r}"
            )
        return True, ""

    def _detect(
        self, data: TimestampIntegrityInput, seed: int
    ) -> list[Finding]:
        df = data.df
        col = data.timestamp_column

        try:
            ts = pd.to_datetime(df[col], errors="coerce")
        except Exception:  # noqa: BLE001
            return []

        valid = ts.dropna()
        if len(valid) < self.MIN_ROWS:
            return []

        # Sort by original index (assume rows are in capture order).
        # Cast to a typed ndarray so mypy doesn't see ExtensionArray.
        ts_arr: np.ndarray = np.asarray(valid.values, dtype="datetime64[ns]")
        dt_seconds: np.ndarray = (
            np.diff(ts_arr).astype("timedelta64[s]").astype(float)
        )

        if len(dt_seconds) == 0:
            return []

        median_dt = float(np.median(dt_seconds))
        mad = float(np.median(np.abs(dt_seconds - median_dt))) or 1e-9
        expected_dt = data.expected_dt_seconds or median_dt

        findings: list[Finding] = []

        # 1) Monotonicity violations
        n_back = int((dt_seconds < 0).sum())
        if n_back > 0:
            findings.append(
                Finding(
                    detector_id=self.id,
                    detector_name=self.name,
                    severity=Severity.SUSPICIOUS,
                    summary=(
                        f"{n_back} row(s) where timestamp is earlier "
                        f"than the previous row (non-monotone)"
                    ),
                    detail=(
                        "SCADA / DCS systems write timestamps in order. "
                        "A back-dated row strongly suggests post-hoc "
                        "data insertion or a serious clock fault."
                    ),
                    evidence={
                        "n_backwards_jumps": n_back,
                        "n_intervals": int(len(dt_seconds)),
                    },
                    innocent_explanations=[
                        "Daylight-saving fall-back created one "
                        "hour-long backwards jump (one event per year).",
                        "NTP clock-skew correction stepped the system "
                        "clock backwards once.",
                        "Multiple data sources were merged out of order; "
                        "consider sorting before analysis.",
                        "The CSV was loaded with the wrong column "
                        "as the timestamp.",
                    ],
                    academic_reference=self.academic_basis,
                )
            )

        # 2) Δt outliers (robust z-score >= 4)
        z = (dt_seconds - median_dt) / (1.4826 * mad)
        n_outliers = int((np.abs(z) >= 4.0).sum())
        max_outlier_dt = (
            float(dt_seconds[np.argmax(np.abs(z))])
            if len(dt_seconds) > 0
            else 0.0
        )

        if n_outliers >= 3:
            severity = (
                Severity.CONCERN if n_outliers < 10 else Severity.SUSPICIOUS
            )
            findings.append(
                Finding(
                    detector_id=self.id,
                    detector_name=self.name,
                    severity=severity,
                    summary=(
                        f"{n_outliers} Δt outliers (median {median_dt:.1f}s, "
                        f"max single Δt {max_outlier_dt:.1f}s)"
                    ),
                    detail=(
                        f"Sample period varies more than expected. Median "
                        f"Δt = {median_dt:.1f}s, MAD = {mad:.1f}s. The "
                        f"largest outlier had Δt = {max_outlier_dt:.1f}s — "
                        f"a back-filled or duplicated timestamp typically "
                        f"shows up here."
                    ),
                    test_statistic=float(np.max(np.abs(z))),
                    test_name="max robust-z of Δt",
                    evidence={
                        "n_outliers": n_outliers,
                        "median_dt_s": median_dt,
                        "mad_s": mad,
                        "max_dt_s": max_outlier_dt,
                    },
                    innocent_explanations=[
                        "Scheduled maintenance windows insert a gap "
                        "in the recording schedule.",
                        "A logger restart created one or two missing "
                        "intervals.",
                        "The configured sample period changed mid-trial; "
                        "expected_dt_seconds should be parameterised.",
                        "Network outage between SCADA and historian "
                        "caused buffered batch-write of multiple rows.",
                    ],
                    academic_reference=self.academic_basis,
                )
            )

        # 3) Round-minute clustering
        sec = np.asarray(valid.dt.second.values, dtype=float)
        usec = np.asarray(valid.dt.microsecond.values, dtype=float)
        seconds_component: np.ndarray = sec + usec / 1e6
        n_round = int((seconds_component == 0).sum())
        pct_round = 100.0 * n_round / len(valid)
        # SCADA at 1-Hz: rounds-on-zero proportion = 1/60 ≈ 1.67 %.
        # Anything > ~10 % is suspicious for hand-entry.
        sev: Severity | None
        if pct_round > 50:
            sev = Severity.SUSPICIOUS
        elif pct_round > 15:
            sev = Severity.CONCERN
        else:
            sev = None
        if sev is not None and expected_dt < 60:
            # Only flag round-minute clustering when sub-minute
            # sampling is expected. At Δt ≥ 60s round-on-zero is the
            # norm.
            findings.append(
                Finding(
                    detector_id=self.id,
                    detector_name=self.name,
                    severity=sev,
                    summary=(
                        f"{pct_round:.1f}% of timestamps land on the "
                        f"exact minute (expected ≤ 5 % at "
                        f"Δt={expected_dt:.1f}s)"
                    ),
                    detail=(
                        "SCADA / DCS at sub-minute sample rate should "
                        "have second / sub-second timestamp precision. "
                        "An over-representation of HH:MM:00 timestamps "
                        "is characteristic of hand-written batch logs "
                        "or post-hoc rounding."
                    ),
                    test_statistic=pct_round,
                    test_name="percent timestamps on exact minute",
                    evidence={
                        "n_round_zero": n_round,
                        "n_total": int(len(valid)),
                        "pct_round": pct_round,
                        "expected_dt_s": expected_dt,
                    },
                    innocent_explanations=[
                        "The historian intentionally aligns reporting "
                        "intervals to clock minutes; sub-second precision "
                        "was discarded at archive time.",
                        "The CSV writer formatted timestamps with %M:%S "
                        "= 00:00 truncation.",
                        "Timestamps were generated by a scheduler that "
                        "fires on the minute boundary.",
                    ],
                    academic_reference=self.academic_basis,
                )
            )

        # 4) Timezone-shift jumps (Δt ≈ ±3600 or ±28800 multiple)
        tz_jumps = int(
            np.sum(
                np.isclose(np.abs(dt_seconds), 3600, atol=10)
                | np.isclose(np.abs(dt_seconds), 28800, atol=10)
            )
        )
        if tz_jumps >= 5:
            findings.append(
                Finding(
                    detector_id=self.id,
                    detector_name=self.name,
                    severity=Severity.CRITICAL,
                    summary=(
                        f"{tz_jumps} Δt jumps look like timezone-shift "
                        f"discontinuities (±3600s or ±28800s)"
                    ),
                    detail=(
                        "Multiple intervals match common timezone "
                        "offsets (1 h or 8 h). This is consistent with "
                        "a silent UTC ↔ local-time switch during data "
                        "merge — values in the affected segment may "
                        "be displaced from their true clock time."
                    ),
                    evidence={
                        "n_tz_shift_jumps": tz_jumps,
                        "expected_dt_s": expected_dt,
                    },
                    innocent_explanations=[
                        "Daylight-saving transitions in long-running "
                        "data sets — one to two per year is normal.",
                        "Operators across two sites in different "
                        "timezones submitted reports merged without "
                        "explicit TZ awareness.",
                        "A reformat tool dropped the TZ designator "
                        "leaving the consumer to guess the offset.",
                    ],
                    academic_reference=self.academic_basis,
                )
            )

        return findings
