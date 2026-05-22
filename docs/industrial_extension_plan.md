# PaperGuard industrial extension — design, scope, and roadmap

> **Status (2.2.0):** initial 3 detectors + HDF5 extractor shipped.
> Sufficient for pilot-scale and GMP batch-record screening; full
> industrial coverage takes 3 more detectors documented below.

## Why an industrial layer

PaperGuard 1.x and 2.0/2.1 were built for **academic-paper data
integrity**: detect terminal-digit anomalies in tables, p-value
mis-reports, image splicing, paper-mill phrase signatures, LLM-text
markers. The methodological core (statistical residual checking +
disclaimer-first reporting + multi-detector concordance) applies just
as well to **industrial process data**, where the failure modes
differ but the analysis pattern is the same.

Industrial scenarios PaperGuard addresses:

- **Pilot-scale runs**: are the published yields actually achievable
  given the energy balance the company published?
- **GMP / FDA 21 CFR Part 11**: batch records and electronic
  audit trails are required to be tamper-evident; PaperGuard's
  timestamp + repetition + balance checks formalize that.
- **Industrial QC**: a multi-site CMO's batch reports — are they
  copied from each other? Do they violate mass balance more often
  at certain plants?
- **Patent / dossier auditing**: does the supporting data submitted
  to a regulator actually demonstrate the claims the dossier text
  makes?
- **Internal whistle-blower screening**: editor-side triage before
  expensive forensic engineering.

## Three-detector starting pack (shipped in 2.2.0)

| Detector | What it detects | Input |
|---|---|---|
| **I1** Mass / Energy Balance | per-batch conservation residual, systematic bias, negative source/sink values | `MassBalanceInput(df, sources=[...], sinks=[...], tolerance_pct=1.0)` |
| **I2** SCADA Timestamp Integrity | back-filled timestamps, round-minute clustering, timezone-shift jumps, non-monotone insertions | `TimestampIntegrityInput(df, timestamp_column="ts", expected_dt_seconds=...)` |
| **I5** Batch-Log Narrative Repetition | copy-pasted narrative text across batch records (FDA Warning-Letter pattern) | `BatchRepetitionInput(df, text_column="narrative", id_column="batch_id")` |

All three live in `src/paperguard/detectors/i{1,2,5}_*.py`, register
through `register_default()`, share the same `Finding` API (≥4
`innocent_explanations`, no verdict language), participate in the
BH-FDR combiner.

## Data-extraction layer addition

| Format | Status | Module |
|---|---|---|
| .csv / .tsv | ✅ shipped (1.x) | `extractor.excel` |
| .xlsx / .xlsm | ✅ shipped (1.x) | `extractor.excel` |
| .docx / .doc / .docb | ✅ shipped (2.1.17) | `extractor.legacy_doc` |
| .pdf | ✅ shipped (1.x) | `extractor.pdf_text` |
| **.h5 / .hdf5** | ✅ **NEW (2.2.0)** | `extractor.hdf5_io` |
| .parquet / .arrow | ⏳ 2.3 | (planned) |
| OPC UA streaming | ⏳ 3.0 | (planned, needs `asyncua`) |
| OSIsoft PI Web API | ⏳ 3.0 | (planned, REST adapter) |
| HYSYS / Aspen .bkp | 🚫 not free | (closed-source format) |

For HDF5 in particular:

```python
from paperguard.extractor.hdf5_io import extract_hdf5_tables

tables = extract_hdf5_tables(Path("plant_archive_2026Q1.h5"))
# {"PI/Reactor1/Temperature": DataFrame(...), ...}
# Each table can feed A1, A2, A3, A5, A6, A7, D1, D2, I1, I2, I5
```

## What's NOT yet implemented (3.x targets)

| Planned | Domain | Why deferred |
|---|---|---|
| **I3** Calibration drift reverse-recovery | Pharma QA, semiconductor metrology | needs state-space modelling + Kalman filter; needs domain test data |
| **I4** Multi-scale (lab → pilot → production) dimensionless-number consistency | Chemical engineering | needs domain dimensionless-number library; needs expert ground truth |
| **I6** DCS trend over-smoothness paradox | Process control | D1 already covers a closely related signal; I6 would add the explicit "Excel beautification" rule |
| **OPC UA / PI streaming** | Real-time control | needs continuous-process adapter, not the current batch-oriented design |

## Calibration position (matches the academic layer)

I1-I5 follow the same conservative philosophy as A1-T8:

- Every finding carries **≥ 4 innocent explanations**.
- No verdict language anywhere in output.
- Severity tiers are deliberately wide; the tool surfaces, the human
  decides.
- The tool runs on tabular / time-series / narrative data — it does
  **not** ingest live SCADA streams or alter control loops.

## Empirical validation (future v3.x)

The 2.2.0 release ships I1/I2/I5 with **unit tests on synthetic
data**. A future industrial recall study will need:

- a public corpus of pilot-scale / GMP batch records with
  ground-truth annotations
- one such corpus exists (FDA Warning Letters database has
  documented batch-record tampering cases); building a usable
  benchmark from it is N=20-50 papers' worth of work

The same empirical-calibration discipline that produced
`recall_test_v10.md` (T6) and `recall_image_v3.md` (F1/F4/F6)
should produce `recall_industrial_v1.md` (I1/I2/I5) before the
detectors are claimed to have measured precision-recall on
real-world data.

Until that study lands, **treat the industrial layer as
hypothesis-class detectors with sound math but unmeasured
operating characteristics on real data**. That is honest, and it's
the same position the LLM-text layer (T7/T8) holds today.

## Use cases this enables

1. **Pre-publication pilot-scale audit (academic + industrial cross-over).**
   Run PaperGuard against a manuscript + its supporting pilot data
   spreadsheet. If the spreadsheet's balance doesn't close to the
   tolerance the methods section claims, the editor sees it before
   acceptance.

2. **CMO QA across sites.** Feed in 6 months of batch records from
   3 sites. I5 flags any pair of sites that share narrative text;
   I1 flags any plant with a systematic balance bias; I2 flags any
   site whose timestamps look hand-entered.

3. **Regulatory dossier consistency.** Cross-check the data tables
   submitted to FDA / EMA against the narrative claims in the
   dossier — does the claimed yield match the balance? Is the
   batch genealogy in the timestamps consistent?

4. **Internal whistle-blower triage.** Anonymous tip says "we
   never actually ran batch 124". PaperGuard tests: does batch
   124's narrative repeat batch 123's? Does batch 124 violate the
   mass balance? Did the timestamps for batch 124 cluster on
   round minutes typical of hand entry?

## Install

```bash
# Base PaperGuard (academic-only)
pip install paperguard

# Plus industrial extension
pip install "paperguard[industrial]"   # adds h5py for .h5 ingest

# Plus webui multi-tenant production
pip install "paperguard[webui]"        # adds redis for rate-limit + scan cache

# Plus everything (recommended for editorial offices)
pip install "paperguard[industrial,webui,legacy-doc]"
```

The 3 industrial detectors are **registered by default** — they're
applicable only when the user supplies the right input type
(`MassBalanceInput` / `TimestampIntegrityInput` /
`BatchRepetitionInput`), so they will not fire on academic
manuscript inputs.

## Commercial-license position

PaperGuard is MIT-licensed. The industrial detectors are MIT too.
There is **no paid tier** — the project's funding model is
academic-citation-driven, not subscription-driven.

Editorial offices, CMOs, and regulators are encouraged to vendor
the source, run it on-prem, and contribute back fixes. The same
disclaimer architecture applies: any finding is a triage signal,
not a verdict, and any compliance action remains the institutional
decision of the user.
