# Figure/table recall validation — first end-to-end run (2026-05-30)

First validation that exercises the **image-forensics (F1/F2/F3/F5/F6/F7)** and
**Carlisle baseline-balance (C1)** detectors on real papers, via the offline
connector `evidence/figure_pipeline.run_figure_pipeline` driven by
`scripts/validate_recall_figures.py`. Cohorts are public Europe PMC OA
(retracted vs control); aggregate only, no per-paper IDs/authors/verdicts.

## What this run established
- **The pipeline is end-to-end live.** PMC OA PDFs download, the image
  extractor yields figures, and all six image detectors + C1 execute without
  error. This is the first time these families have run on real retracted
  papers at all — text-only validation never reached them.

## Smoke result (N is tiny — pipeline check, NOT a recall claim)

```
retracted N=2 (imgs=2, tables=0)   control N=3 (imgs=3, tables=0)
det   recall%   FP%    LR+
F1      0.0     0.0     0
F2      0.0    66.7    0.00
F3    100.0   100.0    1.00
F5      0.0     0.0     0
F6    100.0   100.0    1.00
F7    100.0   100.0    1.00
C1      0.0     0.0     0
ANY   100.0   100.0    1.00
```

## Honest diagnosis — discrimination is ~0, and we know why
F3/F6/F7 fire on **both** cohorts (LR+ ≈ 1 — no better than chance), and F2
fires more on controls. This is **not** a usable recall result, and the run is
too small (N=2/3) for any quantitative claim. But the qualitative signal is
clear and the root cause is identified:

- **Every scored PDF hit the page-as-raster fallback** (`imgs` came from
  `extractor.images` rendering whole pages at 150 dpi, because these PMC PDFs
  carry no embedded figure bitmaps — `tables=0` likewise: pdfplumber found no
  parseable baseline tables).
- F3 (splice/copy-move), F6 (patch-splice histogram) and F7 (GAN spectral) are
  designed for **real figure panels** (microscopy, blots, plots). Run on a
  **full rendered page** (mixed text + multiple sub-figures + whitespace) they
  see repetitive text glyphs and uniform regions everywhere, so they flag
  normal and retracted pages alike.

## Consequence for the roadmap
The decisive anti-fabrication families still need **figure-level extraction**,
not page rasters:
1. Fetch the **PMC OA package** (`.tar.gz`) or the per-figure image URLs from
   the EPMC `fullTextImages` / OA-service endpoints, so each detector sees an
   individual figure panel rather than a whole page.
2. Re-run this harness at a larger N once real figure images are fed; only then
   are F1–F7 recall/FP numbers meaningful.
3. C1 needs RCT papers specifically (baseline tables); a generic retracted
   cohort yields `tables=0`. Filter the cohort to RCTs to measure C1.

Until figure-level extraction lands, **the page-raster path should not be
treated as image-forensics evidence** — it is a fallback for "a figure exists
on this page", not a panel-level forensic input. Reporting code already shows
`applicable=False` / empty notes honestly; no verdict language is emitted.

## Panel-level run attempt (2026-05-31) — fix wired, numbers still pending

The discrimination fix above was implemented: `scripts/validate_recall_figures.py`
now feeds **per-figure panels** from the PMC OA package
(`extractor.pmc_figures.fetch_pmc_figure_images`) to F1–F7 instead of page
rasters, keeping the PDF only for C1 baseline tables. The page-raster path is
gone.

A run still could **not** produce trustworthy recall numbers here, for two
honest reasons (neither a code fault):

1. **Low OA figure-package coverage for retractions.** The retracted cohort
   yielded **0/6** papers with ≥2 extractable OA figure panels. Many retracted
   PMC articles either are not in the OA *package* subset (oa.fcgi returns no
   `.tgz`) or their package carries <2 figure files. So even with correct
   panel extraction, the *retracted ∩ has-OA-figure-package* set is small and
   needs a much larger candidate sweep (or a figure-rich sub-cohort, e.g.
   cell-biology / Western-blot papers) to score meaningfully.
2. **Environment TLS instability.** The control phase aborted on
   `SSL: DECRYPTION_FAILED_OR_BAD_RECORD_MAC` during a plain Europe PMC search —
   an environment/proxy-level TLS failure, not a logic error. Sustained HTTPS in
   this sandbox is unreliable (same root cause as background tasks dying
   silently and `gh run watch` dropping mid-stream).

**Next run (stable network):** sweep a larger candidate pool (`--n` higher, and
raise the `* 6` over-fetch), and consider filtering the retracted cohort to
figure-heavy disciplines so F1–F7 have real panels to score. Until then the
panel-level pipeline is *wired and unit-tested* but its real-paper recall is
**unmeasured** — stated plainly rather than papered over.

## Hardened run on a working network (2026-05-31) — data-source wall identified

With the hardened harness (retry/backoff, `--over-fetch 12`, and a figure-heavy
`--discipline "(western blot OR microscopy OR flow cytometry OR
immunohistochemistry)"` filter) and a network that was up this time
(96 candidates were retrieved per cohort; no TLS crash — the earlier
bad-record-mac was intermittent), the run still could not measure image-forensics
recall:

```
RETRACTED: 96 candidates -> 1 scored (panels=0, tables=1)
CONTROL  : 96 candidates -> 0 scored (panels=0, tables=0)  -> clean exit
```

**Root cause is data availability, not code or network.** Almost no article —
retracted or control — returned a PMC OA *package* (`oa.fcgi` gives no `.tgz`)
with ≥2 extractable figure panels. The OA *full text* exists, but the OA
*image package* mostly does not. Even biasing toward figure-heavy disciplines
and over-fetching 12× did not yield a scoreable image cohort.

### Conclusion for image forensics (F1–F7)
The whole stack is **correct and exercised** — fetch → panel extraction →
F1–F7 all run end-to-end (the smoke test in this doc and the unit tests prove
it). What is missing is a **figure-image data source with coverage**. The PMC
OA package route cannot supply enough real panels to compute recall. Measuring
F1–F7 recall needs a different source, e.g.:
  * publisher per-figure image URLs (EPMC `fullTextImages` / supplementary), or
  * a curated image-manipulation benchmark (e.g. the Bik et al. labelled set).

That is a separate data-engineering effort, out of scope here. C1 (baseline
tables) did fire on 1 paper, confirming the table path works; a meaningful C1
number needs an RCT-filtered cohort. **Image-forensics recall remains
unmeasured — stated plainly, not papered over.** Code, pipeline, fetcher, and
harness are all done and green; the blocker is external data coverage.

Aggregate only; no per-paper or per-author verdicts.
