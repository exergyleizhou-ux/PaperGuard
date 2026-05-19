# Quickstart — 5 minutes from install to first scan

This walk-through assumes you already use Python 3.11+ and can run
shell commands. You will:

1. Install PaperGuard from PyPI.
2. Scan a deliberately fabricated CSV that ships with the project (the
   "high-finding" case).
3. Scan a real, publicly available retracted paper — the 2015 Wansink
   BMC Nutrition study (the "real-world, modest-finding" case).
4. Learn how to read the report.

The two cases on opposite ends teach the **most important lesson about
PaperGuard**: how much it finds depends almost entirely on **what you
feed it**. Raw data files (`.csv`/`.xlsx`) light up every numeric
forensics detector. Published PDFs hide most data behind narrative and
typically yield 0–3 findings even on cases now known to be problematic.

---

## 1. Install

```bash
python -m venv pg
# Linux / macOS
source pg/bin/activate
# Windows PowerShell
.\pg\Scripts\Activate.ps1

pip install paperguard
paperguard --version            # should print 2.0.2 or newer
paperguard list-detectors        # should list 30 detectors
```

To also enable the multi-tenant Web UI:

```bash
pip install "paperguard[webui]"
```

For now we stay on the CLI.

---

## 2. The high-finding case: a fabricated CSV

The repository ships two paired fixtures in `tests/fixtures/`. Grab the
fabricated one:

```bash
curl -O https://raw.githubusercontent.com/exergyleizhou-ux/PaperGuard/main/tests/fixtures/fabricated_geng_style.csv
```

Run a scan:

```bash
paperguard scan -f fabricated_geng_style.csv --lang en
```

You should see something like:

```text
╭────────────── PaperGuard Audit Report ──────────────╮
│ Overall: CRITICAL                                   │
│ File:    fabricated_geng_style.csv                  │
╰─────────────────────────────────────────────────────╯

Total findings: 7 | CRITICAL: 2, SUSPICIOUS: 3, CONCERN: 1
Independent evidence clusters: 2

  [CRITICAL]   A1   Terminal-digit non-uniform on Cell_Count …
  [CRITICAL]   A7   Last-digit 0/5 preference: 52.9% (expected 20%)
  [SUSPICIOUS] A3   Control_OD - Treatment_OD constant -0.3000 …
  [SUSPICIOUS] B1   GRIM violation: mean*N not integer for …
  [SUSPICIOUS] A5   Decimal-fraction repetition rate 87% …
  [CONCERN]    A2   Benford applicability gate not met
  …
```

Two things to notice:

- **Multiple detectors fire on the same row of evidence.** A1 catches
  the χ² non-uniformity; A7 catches that 52.9% of last digits are
  0 or 5; A5 catches the decimal-fraction repetition. They overlap on
  purpose — three independent angles on the same fabrication pattern
  give you stronger evidence than one.
- **Each finding lists possible innocent explanations.** Don't skip
  them. Instrument quantisation, manual rounding, and cultural digit
  preference are all real causes of A1-style patterns in honest data.

For comparison, scan the genuine fixture:

```bash
curl -O https://raw.githubusercontent.com/exergyleizhou-ux/PaperGuard/main/tests/fixtures/genuine_random.csv
paperguard scan -f genuine_random.csv --lang en
```

You should see `Overall: PASS — 0 findings`. This is what real i.i.d.
data looks like.

---

## 3. The real-world case: a retracted Wansink PDF

Brian Wansink's "all-you-can-eat" papers were among the most scrutinised
retractions of the late 2010s. The underlying problems — selective
reporting, p-hacking, contradictions across multiple papers from the
same dataset — were eventually exposed not by computational forensics
but by leaked email exchanges. Nevertheless one of the retracted papers
is openly available, with full CC-BY licensing, and we can run
PaperGuard on it:

```bash
curl -L -o wansink_2015.pdf \
  "https://bmcnutr.biomedcentral.com/counter/pdf/10.1186/s40795-015-0030-x"
paperguard scan -f wansink_2015.pdf --lang en
```

Expected output:

```text
Overall: SUSPICIOUS
Total findings: 2 | SUSPICIOUS: 1, CONCERN: 1

  [SUSPICIOUS] T3   No Data Availability statement detected
  [CONCERN]    T5   Stylometric outlier: adjective density 0.0309
                    (ref ≈ 0.10) — possible Stapel-fraud-style
                    flatness; explore further
```

**Two findings. That's it.** Not because the paper was fine — it was
retracted — but because:

1. **The PDF contains narrative + summary statistics, not raw data.**
   The numeric-forensics detectors (A1 / A2 / A3 / A5 / A6 / A7) only
   fire on data tables of ≥ 50 rows. A typical results section has
   ~5 summary numbers per table.
2. **The actually-damning evidence was in the leaked spreadsheets**
   (Wansink's "email cache" with co-authors), not in the published
   text. PaperGuard would have lit up like a Christmas tree on those
   spreadsheets. It cannot light up on what isn't in the file.
3. **Statcheck (B4) recomputes any reported t/F/χ²/r/z p-values it
   finds in prose.** This paper does not report enough inline
   statistics to give it material.

This is the **expected behaviour** of PaperGuard on a PDF-only scan,
and is **exactly why** the documentation repeatedly says:

> A flag is an invitation to look more carefully, not a conclusion.
> Missing flags are not a vindication.

The honest reading of the two findings:

- **T3 SUSPICIOUS — no Data Availability statement.** In 2015 this was
  not universal; in 2026 it is an ICMJE expectation for primary
  research. Worth asking the corresponding author if the dataset is
  available on request.
- **T5 CONCERN — low adjective density.** Stylometric heuristic from
  Markowitz & Hancock (2014). Calibrated on English psychology prose,
  so the signal is weak on nutrition papers, and the detector clearly
  labels itself as **exploratory**. By itself, this is a curiosity,
  not a verdict.

To get the full power of PaperGuard on the Wansink case you would need
the original spreadsheets. The lesson generalises: when you investigate
a paper, ask for its supplementary data files; scan those alongside the
PDF.

---

## 4. Read the report

The terminal output is the human view. For programmatic work you want
the JSON:

```bash
paperguard scan -f fabricated_geng_style.csv \
                --output-json report.json --lang en
```

Each finding is a self-contained record:

```json
{
  "detector_id": "A1",
  "detector_name": "Terminal Digit Distribution Analysis",
  "severity": 3,
  "summary": "Column 'Cell_Count' last-digit distribution is non-uniform …",
  "p_value": 0.0,
  "p_value_adjusted": 0.0,
  "test_name": "χ²(9) goodness-of-fit",
  "test_statistic": 148.29,
  "effect_size": 0.485,
  "evidence": { "column": "Cell_Count", "n": 70, "frequency_table": { … } },
  "innocent_explanations": [
    "Instrument quantisation (e.g. balance with 0.05 step display)",
    "Manual rounding to a specific precision at data entry time",
    "Cultural digit preference in self-reported data",
    "Derived values where the formula constrains the last digit"
  ],
  "academic_reference": "Mosimann et al. (1995). …"
}
```

Severity is an integer:

| Code | Label | Meaning |
|---|---|---|
| `3` | CRITICAL | Multiple independent strong-effect detectors agreeing |
| `2` | SUSPICIOUS | Strong single-detector signal worth investigating |
| `1` | CONCERN | Mild signal, often dominated by innocent explanations |
| `0` | NOTE | Exploratory observation, not a flag |

The `p_value_adjusted` column applies BH–FDR correction across **all**
findings in the report, not just within one detector. This keeps
batch-of-many-papers scans from drowning you in false discoveries.

---

## 5. HTML report (optional)

For sharing with a non-CLI audience:

```bash
paperguard scan -f fabricated_geng_style.csv \
                --output-html report.html --lang en
```

The HTML is self-contained (no external assets), WCAG 2.1 AA compliant,
and supports `en` / `zh-CN` / `es` / `ja` / `de` via `--lang`.

---

## What to do next

- Read [`docs/fraud_case_studies.md`](fraud_case_studies.md) to see how
  9 real-world cases (Stapel, Fujii, Hwang, Schön, Macchiarini, Wansink,
  Masliah, the Geng-style 2025 patterns, and Bik et al. 2016) map to
  PaperGuard's specific detectors. Each entry honestly distinguishes
  "would catch" from "cannot catch".
- Browse [`docs/detectors/`](detectors/) for a one-page deep-dive per
  detector (assumptions, applicability gates, false-positive sources,
  references).
- If you operate a team and want persistent reports + sharing controls,
  see [`docs/webui_multitenant.md`](webui_multitenant.md).
- To add a custom detector via the plugin entry-point group, see
  [`examples/plugin_example/`](../examples/plugin_example/).

## Disclaimer

PaperGuard flags **statistical anomalies, not fraud**. Every finding
includes possible innocent explanations. Use the output as a starting
point for further inquiry, never as a conclusion. Any concern about
authorship integrity must be raised through journal editors or
institutional investigation channels, not on the basis of this tool's
output alone.
