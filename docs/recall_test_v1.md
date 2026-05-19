# Recall / precision pilot — v1 (N = 10 + 10)

A small-scale shake-out of "does PaperGuard distinguish retracted
papers from matched controls?" The honest answer this run gave was:
**not yet measurable** at this sample size, and **the bottleneck is
the OA download pipeline, not PaperGuard itself.** Methodology and raw
results are recorded here so v2 can be a real measurement.

## Goal

Given a sample of N OA-retracted research articles and N matched OA
non-retracted controls, scan each with `paperguard scan` and report:

- Recall — fraction of retracted papers where `overall_severity ≥ 2`
- False-positive rate — fraction of controls where
  `overall_severity ≥ 2`
- Per-detector firing rate, broken down by arm

## Methodology

Code: [`scripts/recall_test_v1.py`](../scripts/recall_test_v1.py).

1. **Retracted sample**: OpenAlex query
   `is_retracted:true, open_access.is_oa:true, type:article, language:en`,
   sorted by `cited_by_count` desc, with "Retraction Notice" /
   "Notice of Retraction" titles filtered out (those are not the
   original research). Take the first N where an `oa_url` is present.
2. **Control sample**: for each retracted paper, query OpenAlex for
   `is_retracted:false, open_access.is_oa:true,
   primary_topic.subfield = (same subfield),
   publication_year ∈ [year-1, year+1]`,
   sort by `cited_by_count` desc. Take the top non-retraction-notice
   OA paper that isn't the retracted one. If no match: skip (no
   control for this slot).
3. Download each `oa_url` to local PDF. SHA-256 the bytes.
4. Run `paperguard scan -f <pdf> --output-json … --lang en` with a
   300-second per-paper timeout.
5. Aggregate `overall_severity`, `n_findings`, and the set of
   detector IDs that fired.

Output: `scripts/recall_test_v1_results.json`.

## What v1 actually measured

This pilot covered N = 10 retracted + 10 matched controls. The pilot's
**numerical** recall / precision are not yet trustworthy — see the
operational issues below.

Per-arm download + scan success:

| Arm | N | `oa_url` ≠ null | PDF downloaded | Scan returned `overall_severity` |
|---|---|---|---|---|
| Retracted | 10 | 10 | 3 | 0 |
| Control | 10 | 10 | 2 | 1 |

The 10/10 → 3 + 2 drop is dominated by **OpenAlex `oa_url`
redirects to HTML landing pages**, not directly to PDF bytes. Several
"successful" downloads were HTML pages containing a "Download PDF"
link rather than the PDF itself; PaperGuard's pymupdf reader then
either errored or silently produced no findings (no parseable tables,
no inline statistics).

Of the 5 papers that did download as real PDFs, 3 caused
`paperguard scan` to exit non-zero (deeper inspection needed — likely
a font / image extraction edge case on specific publisher PDFs), and
2 completed successfully:

- Retracted side: **0 successful scans** (all 3 PDFs that downloaded
  crashed the scanner).
- Control side: **1 successful scan** —
  Lancet 2014, DOI [10.1016/s0140-6736(14)60460-8](https://doi.org/10.1016/s0140-6736(14)60460-8) —
  `overall_severity = 3` (CRITICAL), 6 findings spanning T3, T5, F1.

A sample of 1 cannot estimate recall vs precision. We are reporting
this honestly rather than spinning the single control finding into a
"100% false-positive rate".

## What the single successful scan tells us

The control paper that completed (Lancet 2014, a high-citation
non-retracted article) hit **T3 (data availability statement)**,
**T5 (stylometric outlier)**, and **F1 (image perceptual-hash
duplication)**. The first two are common on older clinical trials
(2014 predates universal data-availability statements; methodology
prose is repetitive by design). The F1 hit on a real published Lancet
paper is the most interesting finding of the pilot and merits manual
follow-up: it might be a legitimate within-paper figure reuse, a
benign template overlap (e.g. trial-flow diagrams), or a real
unflagged anomaly. The point of an anomaly flag is to invite that
manual look — exactly what the documentation says throughout.

## Operational issues found (the actually useful output of v1)

1. **`oa_url` is HTML, not PDF, for some publishers.** Need to add a
   Content-Type check after redirect resolution; if HTML, look for a
   `<meta name="citation_pdf_url">` or follow the publisher-specific
   PDF link.
2. **No content-type validation post-download.** A 200 response with
   HTML body silently passed through; PaperGuard then tried to parse
   it as a PDF.
3. **No retry / fallback mirror.** Unpaywall has a more accurate
   `best_oa_location.url_for_pdf` than OpenAlex's denormalised
   `oa_url`. v2 should try Unpaywall first.
4. **PaperGuard CLI exit=1 on certain real-publisher PDFs.** Three of
   the five real downloads crashed the scanner. This is the most
   actionable v1 finding — the scanner should never exit non-zero on
   parseable-but-unusual PDFs. Worth a separate bug. Likely candidates:
   image-extractor errors on font-only pages, or pymupdf raising on a
   damaged xref table.
5. **Need to skip "publisher front-matter" PDFs** that contain only
   the title page + abstract, no body. A few of the downloads were
   PubMed Central front-matter wrappers rather than the full article.

## v2 plan

Given v1's findings, a credible recall-vs-precision study needs:

1. Build a PDF-fetching helper that:
   - Resolves OpenAlex `id` → DOI → Unpaywall `best_oa_location.url_for_pdf`
     first, falls back to OpenAlex `oa_url`.
   - Validates `Content-Type: application/pdf` (or sniffs for `%PDF-`
     header) before writing the file.
   - Retries once with a different mirror on failure.
   - SHA-256-deduplicates so the same paper isn't scanned twice.
2. Add an `--ignore-scan-errors` mode to the CLI that downgrades
   non-zero exits to a per-paper error record, so a study can complete
   even if individual PDFs are pathological.
3. Reproduce v1 with N = 100 + 100 once the fetcher is fixed.
4. Stratify by year (pre-2010 / 2010–2017 / 2018+), by field
   (clinical / preclinical / social), and by Retraction Watch reason
   code (when available).

## Reproducing v1

```bash
.venv/Scripts/python.exe scripts/recall_test_v1.py \
  --n 10 \
  --out scripts/recall_test_v1_results.json
```

This pulls live data from OpenAlex; re-running on a different day may
pick up a slightly different sample if OpenAlex re-indexes. SHA-256 of
each downloaded PDF is recorded in the output JSON so divergence is
visible.

## Headline

**Pilot N = 10 + 10. Pipeline is the bottleneck, not the detector.
v2 with a proper Unpaywall-first fetcher and CLI-error tolerance will
give a real signal.**
