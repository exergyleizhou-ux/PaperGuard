# Industrial domain templates — 12-sector cheatsheet

PaperGuard 2.2.0 shipped 3 industrial detectors (I1 mass/energy
balance, I2 SCADA timestamp integrity, I5 batch-log repetition).
PaperGuard 2.2.1 adds **12 domain templates** that pre-configure
those detectors for concrete sectors.

A template is a frozen dataclass declaring:
- which DataFrame columns are sources vs sinks
- what mass-balance tolerance is realistic
- what SCADA sample period is expected
- what field carries the operator narrative
- a documentation of typical units + falsification modes
- the relevant regulatory frame (FDA / EPA / EU / China)

The same I1/I2/I5 detector code runs against every sector — only
the **input configuration** changes.

## The 12 domains

| Domain | Tolerance | Δt expected | Regulatory frame |
|---|---|---|---|
| `wastewater` | 5 % | 1 hr | EPA NPDES / EU UWWTD / GB 18918 |
| `waste_gas` | 3 % | 1 s | EPA CEMS / EU IED / GB 13223 |
| `distillers_grain` | 2 % | 1 day | FDA 21 CFR 507 / EC 183/2005 |
| `chemical` | 1 % | 30 s | EPA TSCA+RCRA / REACH |
| `pharma` | **0.5 %** | 5 min | **FDA 21 CFR 211+11 / EU GMP** |
| `food` | 2 % | 15 min | FDA FSMA+HACCP / EC 852/2004 |
| `semiconductor` | **0.1 %** | 1 s | SEMI E10 / ITRS |
| `environment` | 10 % | 1 mo | EPA CERCLA / E-PRTR |
| `medical` | 0 % | 1 min | HIPAA / CMS / MDR — de-identified only |
| `agriculture` | 15 % | 1 day | USDA NOP / CAP IACS |
| `biopharma` | **0.5 %** | 1 min | FDA cGMP biologic / ICH Q5 / USP |
| `biocomputation` | 2 % | 1 min | CLIA + CAP / IVDR / MIQE / MINSEQE |

The tolerance ladder is real: pharma + biopharma sit at 0.5 % because
GMP requires near-exact reconciliation, semiconductor at 0.1 %
because MFC gas-flow control is that precise, and environment at
10 % because annual inventories accept that much measurement
uncertainty.

## Usage

```python
from paperguard.industrial import WASTEWATER
from paperguard.detectors.i1_mass_balance import I1MassBalanceDetector
import pandas as pd

df = pd.read_csv("wastewater_2026Q1.csv")
# Auto-fills sources=("influent_COD_kg_day", "influent_BOD_kg_day"),
# sinks=("effluent_COD_kg_day", ...), tolerance_pct=5.0
result = I1MassBalanceDetector().detect(WASTEWATER.mass_balance(df))
print(result.findings)
```

Column-name overrides if your CSV uses different names:

```python
result = I1MassBalanceDetector().detect(
    WASTEWATER.mass_balance(
        df,
        sources=["COD_in_kg_per_day", "BOD_in_kg_per_day"],
        sinks=["COD_out_kg_per_day", "sludge_COD_kg_per_day"],
        tolerance_pct=3.0,
    )
)
```

## Per-domain falsification modes catalogued

Each template ships a ``falsification_modes`` tuple documenting the
**actually-observed** integrity-failure patterns in that sector. Some
highlights:

| Domain | Documented failure mode |
|---|---|
| wastewater | Removal-efficiency padding to meet permit; sample-time backfill |
| waste_gas | CEMS data substitution during exceedance windows |
| distillers_grain | Moisture-adjusted yield padding (dry weight inflated) |
| chemical | Yield padding via un-recovered material recorded as product |
| pharma | Deviation backdating; lot-record narrative cloned (FDA WL 2018-04) |
| food | CCP temperature back-filled within tolerance after deviation |
| semiconductor | Yield padding (rejected wafers reclassified as good) |
| environment | Annual emission inventory narrative cloned across years |
| medical | Phantom-billing; Cerner "copy-forward" of progress notes |
| agriculture | Yield over-reporting for subsidy claims |
| biopharma | Titre back-calculation from claimed yield |
| biocomputation | Failed reads silently re-included in pipeline output |

This list is for **detector calibration** — knowing which patterns
exist tells you which thresholds matter. It is **not** a
"how-to-detect-fraud" guide; PaperGuard's output remains structurally
non-verdict (≥4 innocent explanations per finding, no verdict
language anywhere).

## Adding a new domain

```python
from paperguard.industrial import DomainTemplate

MY_DOMAIN = DomainTemplate(
    name="my_sector",
    description="...",
    regulatory_frame="...",
    sources=("...", "..."),
    sinks=("...", "..."),
    tolerance_pct=1.5,
    timestamp_column="ts",
    expected_dt_seconds=300.0,
    narrative_column="log_text",
    id_column="batch_id",
    typical_units={...},
    falsification_modes=(...,),
)
```

Then either:
- Use it locally: `MY_DOMAIN.mass_balance(df)` → `MassBalanceInput`
- Or open a PR to add it to `paperguard/industrial/templates.py`

## Calibration position (matches the academic layer)

The same conservative philosophy as A1-T8 applies:

- Every finding carries **≥ 4 innocent explanations**.
- No verdict language anywhere.
- Severity tiers are deliberately wide.
- Domain templates document falsification modes for **detector
  design**, not as accusations against any organization or person.

Real-world deployment requires the user to handle PHI / PII / trade
secrets according to their applicable regulatory frame. PaperGuard
does not phone home, does not transmit data, and runs entirely on
the user's machine (or their own webui deployment).

## Empirical validation

Templates are **unit-tested on synthetic data** (`tests/test_industrial_templates.py`,
34 tests). Each template's columns / tolerance / Δt have been
sanity-checked but **no real-world recall study against an
industrial corpus has been run**. The same calibrated-honesty
discipline that produced `recall_test_v10.md` (T6 on N=200) and
`recall_image_v3.md` (F1/F4/F6 on N=85) should produce
`recall_industrial_<domain>_v1.md` per domain before any LR+ number
is claimed.

Until that lands, treat each template as a **hypothesis-class
configuration with sound math but unmeasured real-data operating
characteristics**. That is the same honesty position the LLM-text
layer (T7/T8) holds today.
