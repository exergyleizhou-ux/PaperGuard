"""End-to-end industrial demo — synthetic wastewater treatment plant scan.

Builds a 30-day mock plant log with three deliberate integrity
issues, then runs I1 + I2 + I5 with the WASTEWATER domain template.

Run::

    python examples/industrial_wastewater_demo.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from paperguard.detectors.i1_mass_balance import I1MassBalanceDetector
from paperguard.detectors.i2_timestamp_integrity import (
    I2TimestampIntegrityDetector,
)
from paperguard.detectors.i5_batch_repetition import I5BatchRepetitionDetector
from paperguard.industrial import WASTEWATER


def build_demo_dataset() -> pd.DataFrame:
    """30 days of hourly samples with 3 intentional issues."""
    rng = np.random.default_rng(42)
    n_hours = 30 * 24
    base_time = pd.Timestamp("2026-04-01 00:00:00")

    # Honest balance: ~1500 kg/day COD in, removal ~85 %, sludge takes most
    in_cod = rng.normal(1500, 150, n_hours) / 24  # kg/hr
    in_bod = in_cod * 0.6
    eff_cod = in_cod * 0.15
    eff_bod = eff_cod * 0.30
    sludge = in_cod * 0.78
    # Honest residual stream — about 5% balance closure
    co2 = in_cod - eff_cod - sludge

    df = pd.DataFrame({
        "sample_time": [
            base_time + pd.Timedelta(hours=i) for i in range(n_hours)
        ],
        "influent_COD_kg_day": in_cod,
        "influent_BOD_kg_day": in_bod,
        "effluent_COD_kg_day": eff_cod,
        "effluent_BOD_kg_day": eff_bod,
        "sludge_COD_kg_day": sludge,
        "co2_emitted_kg_day_C": co2,
        "operator_log": [
            f"Shift {i // 8} normal operation. Influent within spec, "
            f"effluent below permit. Sludge wasting on schedule. "
            f"DO 2.4 mg/L, MLSS 3200 mg/L. No deviations." * 2
            for i in range(n_hours)
        ],
        "report_date": [base_time + pd.Timedelta(days=i // 24) for i in range(n_hours)],
    })

    # === Inject 3 integrity issues ===

    # Issue 1 (I1): on a few days the effluent was actually higher than reported.
    # Operator wrote the permit-compliant number → balance won't close.
    for i in range(72, 96):  # 24 hours mid-month
        df.at[i, "effluent_COD_kg_day"] *= 0.3  # under-report by ~70%

    # Issue 2 (I2): 12 timestamps were backfilled (sample taken late, written
    # at end of shift) — all on round 15-minute marks.
    for i in range(200, 212):
        df.at[i, "sample_time"] = (
            df.at[i, "sample_time"].replace(minute=0, second=0)
        )

    # Issue 3 (I5): the same operator log got copied across 100 hours of a
    # weekend when nobody was really there.
    weekend_template = (
        "Sat-Sun shift coverage. Influent within spec, effluent "
        "within permit. Sludge wasting on schedule. DO 2.4 mg/L, "
        "MLSS 3200 mg/L. No deviations noted." * 4
    )
    for i in range(400, 500):
        df.at[i, "operator_log"] = weekend_template

    return df


def main() -> None:
    df = build_demo_dataset()
    print(f"Built demo dataset: {len(df)} hourly samples across 30 days.")
    print(f"Columns: {list(df.columns)}\n")

    # --- I1 Mass balance ---
    print("=" * 60)
    print("I1 — Mass Balance")
    print("=" * 60)
    result_i1 = I1MassBalanceDetector().detect(WASTEWATER.mass_balance(df))
    if result_i1.findings:
        for f in result_i1.findings:
            print(f"[{f.severity.name}] {f.summary}")
            print(f"  {f.detail[:200]}...")
    else:
        print("  (no balance violations)")

    # --- I2 Timestamp integrity ---
    print("\n" + "=" * 60)
    print("I2 — SCADA Timestamp Integrity")
    print("=" * 60)
    result_i2 = I2TimestampIntegrityDetector().detect(
        WASTEWATER.timestamp_integrity(df)
    )
    if result_i2.findings:
        for f in result_i2.findings:
            print(f"[{f.severity.name}] {f.summary}")
    else:
        print("  (no timestamp anomalies)")

    # --- I5 Batch-log repetition ---
    print("\n" + "=" * 60)
    print("I5 — Batch-Log Narrative Repetition")
    print("=" * 60)
    # Use the same template, but tell I5 to use report_date as ID and
    # operator_log as narrative. (template defaults are already these,
    # but show the override pattern.)
    result_i5 = I5BatchRepetitionDetector().detect(
        WASTEWATER.batch_repetition(df)
    )
    if result_i5.findings:
        for f in result_i5.findings:
            print(f"[{f.severity.name}] {f.summary}")
            print(f"  top pairs: {f.evidence.get('top_5_pairs', [])[:2]}")
    else:
        print("  (no repetition flagged)")

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    total = len(result_i1.findings) + len(result_i2.findings) + len(result_i5.findings)
    print(
        f"  Total findings across I1+I2+I5: {total}\n"
        f"  Every finding ships with ≥3 innocent explanations.\n"
        f"  PaperGuard does NOT call these 'fraud' or 'misconduct'.\n"
        f"  A trained human reviewer decides what each finding means."
    )


if __name__ == "__main__":
    main()
