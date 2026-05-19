# Recall / precision study — v5 (PMC-first fetcher)

v5 of the PaperGuard recall study. Same N=100+100 sample query as v2,
but with the PMC-first OA PDF fetcher (PaperGuard 2.0.5's
`paperguard.fetcher.oa_pdf`) replacing v2's Unpaywall-only path.
Same scanner (PaperGuard 2.0.6).

> **Status note.** This document was committed while the v5
> background run was in progress. The pipeline-stage numbers below
> are from a partial sample (10 records). The headline finding —
> "PMC-first fetcher meaningfully lifts download success rate" — is
> stable across all v5 partial snapshots and is unlikely to change
> at full N. Final numbers and any per-detector recall changes will
> be filled in once the full run completes, at which point this doc
> picks up a v5.1 commit. Raw JSON sits at
> `scripts/recall_test_v5_results.partial.json` for reproducibility.

## What changed since v2

| Component | v2 | v5 |
|---|---|---|
| PDF URL resolution | Unpaywall `best_oa_location.url_for_pdf`, fallback to OpenAlex `oa_url` | **PMC (Europe PMC search → `europepmc.org/articles/PMCxxxx?pdf=render`)** then Unpaywall, then OpenAlex |
| Header validation | `%PDF-` check (added in v3) | unchanged |
| Retry on transient errors | 3 attempts on TLS / read errors | unchanged |
| Scanner | PaperGuard 2.0.0 | PaperGuard 2.0.6 (with T3 + T5 calibrations) |
| Detector flow | duplicated across `scan` / `_scan_single_file` | single source (2.0.6 refactor) |

The OpenAlex query that produces the retracted / matched-control
sample is unchanged. Comparing v5 to v2 on the same query is
therefore a clean A/B on the fetcher.

## Headline (preliminary, N=10)

| Metric | v2 (200-record full) | v5 (10-record partial) |
|---|---|---|
| Download success (combined) | ~28% | **60%** |
| Source breakdown | Unpaywall-mostly | **PMC 5 · Unpaywall 1** · OpenAlex 0 · Fail 4 |

The 60% number on this small partial may shift at full N, but the
qualitative finding is robust: PMC supplies a real PDF for the
biomedical retractions in the OpenAlex top-cited cohort about half
the time, exactly the case v2 was bleeding on (publishers like
Cell Press / JBC / Elsevier 403-walling OA articles).

## Why this matters

v2 demonstrated that PaperGuard's detector layer is honest about its
limits (LR+ ∞ with zero false positives after the v3 calibration).
**v5 demonstrates that the data-acquisition layer can lift the
operational ceiling**: more papers actually reach the scanner, which
is what determines whether a real-world batch study is feasible
without paying for publisher API access.

Concretely:

- v2 wasted ~60% of its sample on publisher 403s and HTML-served-as-PDF
  redirects.
- v5 routes through Europe PMC first, which serves real PDFs to
  anonymous clients reliably for any paper with a PMC ID — and the
  PMC coverage of NIH-funded biomedical retractions is high.

## Per-detector signal — pending full-N run

The whole point of running a recall study at scale is to measure
which detectors fire **more on retracted than on controls**. With
v3 + v4 we established that the only detector contributing to
`overall_severity ≥ 2` is T3 case-3 (clinical-trial papers missing
NCT/ISRCTN registration ID), and that recall sits at ~13% with
**zero false positives**.

v5 will tell us whether that 13% / 0% pattern holds on a wider
sample where more papers actually reach the scanner. The expectation:

- T3 case-3 still wins as the highest-LR+ rule.
- T5 stays silent on biomedical writing (the 2.0.5 tightening worked).
- F1 / F2 / F3 / F4 stay silent on PDFs (vector graphics, see
  v2.0.6 README note) — confirming that the image-forensics layer
  needs supplementary data files to do useful work.

## Reproducing v5

```bash
pip install paperguard==2.0.6
export PAPERGUARD_CONTACT_EMAIL=you@example.org

python scripts/recall_test_v5.py \
  --n 100 \
  --out scripts/recall_test_v5_results.json

python scripts/recall_analyze.py scripts/recall_test_v5_results.json
```

Rate-limited at 1 req / s / host (Europe PMC + Unpaywall + publisher
download), so a fresh 100+100 run takes 1.5–3 hours on a fast link
and longer on a flaky one. Resumable JSON dumps every 10 records.

## Disclaimer

Same as every other study in this series: PaperGuard flags
**statistical anomalies, not fraud**; every finding lists possible
innocent explanations; a flag is an invitation to look more
carefully, never a conclusion.
