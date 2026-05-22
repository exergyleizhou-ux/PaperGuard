"""Industrial-detector synthetic recall study (v1, N=50 clean + 50 tampered
per domain). Two domains: wastewater + pharma.

Each domain we generate:
  - 50 honest batch/sample datasets (realistic noise, narratives vary)
  - 50 tampered datasets: each has ≥1 of {I1 violation, I2 backfill,
    I5 narrative copy-paste} injected with realistic magnitude

We then run I1+I2+I5 with the matching DomainTemplate and compute:
  - per-detector recall (TPR among tampered) and FPR (TPR among clean)
  - LR+ at the default detector threshold
  - joint LR+ for "ANY of I1/I2/I5 fires"

The study is **synthetic-ground-truth**: we know exactly which datasets
were tampered. This validates that the templates' default tolerances
are calibrated correctly for each domain.

Outputs:
  - scripts/recall_industrial_v1_results.json
  - docs/recall_industrial_v1.md (separate analyser)
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from paperguard.detectors.i1_mass_balance import I1MassBalanceDetector
from paperguard.detectors.i2_timestamp_integrity import (
    I2TimestampIntegrityDetector,
)
from paperguard.detectors.i5_batch_repetition import (
    I5BatchRepetitionDetector,
)
from paperguard.industrial import PHARMA, WASTEWATER, DomainTemplate

RNG = np.random.default_rng(20260522)
NARRATIVES_BANK = [
    "Operator A normal shift. Influent within spec, effluent below permit. "
    "DO 2.4 mg/L, MLSS 3200 mg/L, F/M ratio nominal. No deviations.",
    "Storm event 15:00; flow spiked to 1.8x nominal for 90 min. "
    "Equalisation basin held; effluent permit unchanged.",
    "Aerobic basin DO dropped to 1.1 mg/L for 22 minutes. Blower "
    "VFD reset; recovered. No effluent excursion.",
    "Sludge wasting 8% above target due to high MLSS. Will reduce "
    "tomorrow. Effluent within spec throughout.",
    "Influent COD spike to 1850 mg/L 08:00-11:00 — looks like "
    "industrial discharge. Effluent permit maintained.",
    "Routine shift. All parameters nominal. UV bank #2 lamp 11 "
    "replaced; transmittance now 92%.",
    "DO sensor #3 reading drift +0.3 mg/L; recalibrated 14:00. "
    "Trend back to baseline within 2 h.",
    "Polymer dosing pump P-205 stalled 05:30, restored 06:10. "
    "Effluent turbidity unchanged.",
    "Visitor tour 13:30-15:00; lab and headworks. No process impact.",
    "Reseeded RBC #4 with sludge from RBC #1. Recovery expected "
    "in 3-5 days.",
]


@dataclass
class CaseResult:
    arm: str  # "clean" or "tampered"
    case_id: str
    tamper_modes: list[str]
    i1_fired: bool
    i1_severity: str
    i2_fired: bool
    i2_severity: str
    i5_fired: bool
    i5_severity: str


def _wastewater_clean(case_id: str) -> pd.DataFrame:
    n = 24 * 14  # 14 days hourly
    base = pd.Timestamp("2026-04-01") + pd.Timedelta(days=int(case_id.rstrip("T")) * 14)
    influent_cod = RNG.normal(1500, 120, n) / 24  # kg/hr
    sludge = influent_cod * RNG.uniform(0.72, 0.78, n)
    effluent = influent_cod * RNG.uniform(0.12, 0.18, n)
    co2 = influent_cod - sludge - effluent
    return pd.DataFrame({
        "sample_time": [base + pd.Timedelta(hours=i) for i in range(n)],
        "influent_COD_kg_day": influent_cod,
        "influent_BOD_kg_day": influent_cod * 0.6,
        "effluent_COD_kg_day": effluent,
        "effluent_BOD_kg_day": effluent * 0.30,
        "sludge_COD_kg_day": sludge,
        "co2_emitted_kg_day_C": co2,
        "operator_log": [
            NARRATIVES_BANK[i % len(NARRATIVES_BANK)] + f" [shift_{i // 8}]"
            for i in range(n)
        ],
        "report_date": [base + pd.Timedelta(days=i // 24) for i in range(n)],
    })


def _wastewater_tampered(case_id: str) -> tuple[pd.DataFrame, list[str]]:
    df = _wastewater_clean(case_id)
    modes: list[str] = []
    # Pick at least 1 of 3 tamper modes randomly, biased toward all 3
    tamper_flags = RNG.random(3) < 0.6
    if not tamper_flags.any():
        tamper_flags[RNG.integers(3)] = True

    if tamper_flags[0]:
        # I1: drop reported effluent by 40% on 30% of rows
        rows = RNG.choice(len(df), int(0.3 * len(df)), replace=False)
        df.loc[rows, "effluent_COD_kg_day"] *= 0.6
        modes.append("i1_effluent_padded")

    if tamper_flags[1]:
        # I2: round 25 timestamps to exact hour
        rows = RNG.choice(len(df), 25, replace=False)
        for r in rows:
            df.at[r, "sample_time"] = df.at[r, "sample_time"].replace(
                minute=0, second=0
            )
        # Also one backwards jump
        df.at[100, "sample_time"] = df.at[80, "sample_time"]
        modes.append("i2_round_minute_and_backfill")

    if tamper_flags[2]:
        # I5: copy one narrative across 40 hours
        template = NARRATIVES_BANK[3] * 4
        start = int(RNG.integers(50, len(df) - 50))
        for r in range(start, start + 40):
            df.at[r, "operator_log"] = template
        modes.append("i5_narrative_repetition")

    return df, modes


def _pharma_clean(case_id: str) -> pd.DataFrame:
    n = 30  # 30 lots
    base = pd.Timestamp("2026-04-01") + pd.Timedelta(days=int(case_id.rstrip("T")) * 30)
    api = RNG.normal(50, 2, n)
    excipient = RNG.normal(450, 10, n)
    lubricant = RNG.normal(2.5, 0.1, n)
    total_in = api + excipient + lubricant
    # Honest yield ~98 %, reject ~1.5 %, loss ~0.5 %
    yield_pct = RNG.normal(0.98, 0.005, n)
    reject_pct = RNG.normal(0.015, 0.003, n)
    loss_pct = 1 - yield_pct - reject_pct
    finished = total_in * yield_pct
    reject = total_in * reject_pct
    loss = total_in * loss_pct
    return pd.DataFrame({
        "batch_record_ts": [
            base + pd.Timedelta(hours=i * 8) for i in range(n)
        ],
        "API_kg": api,
        "excipient_kg": excipient,
        "lubricant_kg": lubricant,
        "finished_tablets_kg": finished,
        "reject_kg": reject,
        "in_process_loss_kg": loss,
        "deviation_log": [
            NARRATIVES_BANK[i % len(NARRATIVES_BANK)] + f" Lot {case_id}-{i:03d}"
            for i in range(n)
        ],
        "lot_number": [f"L{case_id}-{i:03d}" for i in range(n)],
    })


def _pharma_tampered(case_id: str) -> tuple[pd.DataFrame, list[str]]:
    df = _pharma_clean(case_id)
    modes: list[str] = []
    tamper_flags = RNG.random(3) < 0.6
    if not tamper_flags.any():
        tamper_flags[RNG.integers(3)] = True

    if tamper_flags[0]:
        # I1: shave 1-2% off in_process_loss on most rows (yield padding)
        df["in_process_loss_kg"] *= 0.3
        modes.append("i1_loss_under_reported")

    if tamper_flags[1]:
        # I2: backdate 8 batch records to round 8-hour boundaries
        for r in RNG.choice(len(df), 8, replace=False):
            df.at[r, "batch_record_ts"] = df.at[r, "batch_record_ts"].replace(
                minute=0, second=0
            )
        modes.append("i2_round_timestamps")

    if tamper_flags[2]:
        # I5: copy lot 0 narrative across 6 consecutive lots
        if len(df) > 8:
            template_text = NARRATIVES_BANK[2] * 6
            for r in range(2, 8):
                df.at[r, "deviation_log"] = template_text
            modes.append("i5_deviation_copied")

    return df, modes


def _run_one(
    df: pd.DataFrame,
    template: DomainTemplate,
    arm: str,
    case_id: str,
    modes: list[str],
) -> CaseResult:
    res = CaseResult(
        arm=arm,
        case_id=case_id,
        tamper_modes=modes,
        i1_fired=False, i1_severity="none",
        i2_fired=False, i2_severity="none",
        i5_fired=False, i5_severity="none",
    )

    r1 = I1MassBalanceDetector().detect(template.mass_balance(df))
    if r1.findings:
        sev = max((f.severity for f in r1.findings), key=lambda s: s.value)
        res.i1_fired = sev.name in {"NOTE", "CONCERN", "SUSPICIOUS", "CRITICAL"}
        res.i1_severity = sev.name

    r2 = I2TimestampIntegrityDetector().detect(
        template.timestamp_integrity(df)
    )
    if r2.findings:
        sev = max((f.severity for f in r2.findings), key=lambda s: s.value)
        res.i2_fired = sev.name in {"NOTE", "CONCERN", "SUSPICIOUS", "CRITICAL"}
        res.i2_severity = sev.name

    r5 = I5BatchRepetitionDetector().detect(template.batch_repetition(df))
    if r5.findings:
        sev = max((f.severity for f in r5.findings), key=lambda s: s.value)
        res.i5_fired = sev.name in {"NOTE", "CONCERN", "SUSPICIOUS", "CRITICAL"}
        res.i5_severity = sev.name

    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--out", default="scripts/recall_industrial_v1_results.json")
    args = ap.parse_args()
    n = args.n

    domains = [
        ("wastewater", WASTEWATER, _wastewater_clean, _wastewater_tampered),
        ("pharma", PHARMA, _pharma_clean, _pharma_tampered),
    ]
    all_results: dict[str, Any] = {}
    for dom_name, tmpl, clean_fn, tamper_fn in domains:
        print(f"=== {dom_name} ===", file=sys.stderr)
        results: list[dict[str, Any]] = []
        for i in range(n):
            cid = f"{i:03d}"
            results.append(
                {
                    **_run_one(
                        clean_fn(cid), tmpl, "clean", cid, modes=[]
                    ).__dict__
                }
            )
        for i in range(n):
            cid = f"{i:03d}T"
            df_tampered, modes = tamper_fn(cid)
            results.append({**_run_one(df_tampered, tmpl, "tampered", cid, modes).__dict__})
        all_results[dom_name] = results
        # Summary
        clean = [r for r in results if r["arm"] == "clean"]
        tamp = [r for r in results if r["arm"] == "tampered"]
        for det in ("i1", "i2", "i5"):
            tp = sum(1 for r in tamp if r[f"{det}_fired"])
            fp = sum(1 for r in clean if r[f"{det}_fired"])
            tpr = tp / max(len(tamp), 1)
            fpr = fp / max(len(clean), 1)
            lr = tpr / fpr if fpr > 0 else float("inf") if tpr > 0 else 0
            print(
                f"  {det.upper()}: TP={tp}/{len(tamp)} FP={fp}/{len(clean)} "
                f"TPR={tpr:.2%} FPR={fpr:.2%} LR+={lr}",
                file=sys.stderr,
            )
        # Joint
        tp_j = sum(
            1 for r in tamp
            if r["i1_fired"] or r["i2_fired"] or r["i5_fired"]
        )
        fp_j = sum(
            1 for r in clean
            if r["i1_fired"] or r["i2_fired"] or r["i5_fired"]
        )
        tpr_j = tp_j / max(len(tamp), 1)
        fpr_j = fp_j / max(len(clean), 1)
        lr_j = (
            tpr_j / fpr_j
            if fpr_j > 0
            else float("inf") if tpr_j > 0 else 0
        )
        print(
            f"  JOINT (any of I1/I2/I5): TP={tp_j}/{len(tamp)} "
            f"FP={fp_j}/{len(clean)} TPR={tpr_j:.2%} FPR={fpr_j:.2%} "
            f"LR+={lr_j}",
            file=sys.stderr,
        )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {"n_per_arm": n, "domains": all_results},
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"\nWrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
