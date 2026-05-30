# Full-text recall validation on retracted papers (2026-05-29)

First test that exercises detectors on **full text** (via Europe PMC OA), not
just abstracts. This is a diagnostic for the "firepower" roadmap: it locates
exactly where recall is missing.

## Method
- 40 retracted (`PUB_TYPE:"Retracted Publication"`, OA, in-EPMC) + 40 control
  (OA research-articles, in-EPMC, not retracted, 2018–2023).
- Detectors run on full text, flag = severity ≥ CONCERN: B4 statcheck,
  T4 tortured phrases, T6 lexical, T9 classifier.
- Reproduce: `python scripts/validate_recall_fulltext.py --n 40`

## Results

| Detector | recall % (retracted) | FP % (control) | LR+ |
|---|---|---|---|
| **T4 tortured phrases** | 10.0 | 5.0 | **2.00** |
| B4 statcheck | 0.0 | 2.5 | 0.00 |
| T6 lexical | 0.0 | 0.0 | — |
| T9 classifier | 50.0 | 52.5 | 0.95 |
| any | 50.0 | 60.0 | 0.83 |

## Diagnosis — where the firepower is missing
1. **T4 is the only discriminating detector (LR+ 2.0).** The paper-mill
   tortured-phrase signal is real but modest; worth strengthening.
2. **B4 statcheck recall = 0** — caught no retracted paper. Either statistic
   extraction from JATS-stripped full text is failing, or this retraction
   sample is not "statistical-error" type. **Highest-priority gap to fix:**
   statcheck should be a primary fabrication catcher.
3. **T9 is non-discriminative on full text (50 % vs 52 %).** Root cause: T9
   takes the *max* segment probability; over a many-segment full paper the max
   is almost always high (a multiple-comparisons artifact). T9 was calibrated
   for abstract-length text. **Fix: density/fraction-based aggregation for long
   documents, not max.**
4. **The strongest anti-fabrication families were not exercised here:** numeric
   recompute (GRIM/GRIMMER/SPRITE/Carlisle on reported means/SDs/tables) and
   image forensics (F1–F7 on figures). These need table/figure extraction, the
   next pipeline to build.

## Firepower roadmap priorities (from this diagnostic)
1. Fix T9 full-text aggregation (density, not max) → restore discrimination.
2. Investigate + strengthen statcheck recall on full text.
3. Build figure/data extraction so image + numeric detectors can run on full
   papers (where real data fabrication lives).

## Post-fix confirmation — T9 density tiering (commit 4893c8b)

After changing T9 from max-segment to density-based tiering (a tier needs
≥25 % of segments LLM-like), the full-text re-run shows:

| | T9 control false-positive rate (full text) |
|---|---|
| before fix (max-segment) | 52.5 % (N=40) |
| **after fix (density)** | **10.0 % (N=30)** |

A ~5× reduction — the long-document false-positive artifact is fixed. T9's
recall on the retracted cohort is ~0 %, which is **correct**: most retractions
are not AI-written text, so T9 should rarely fire on them; the point of the fix
is that it no longer fires on *normal* papers either. Abstract-level behaviour
(single segment → fraction 1.0) is unchanged, so the HC3 golden tests and the
OA calibration (0 % FP at the ship threshold) still hold.

Note: overall text-layer discrimination remains modest (T4 LR+ ≈ 1.5). The
decisive anti-fabrication families (numeric recompute + image forensics) still
need full-text table/figure extraction — the next firepower milestone.

Aggregate only; no per-paper or per-author verdicts.

## P1 follow-up — statcheck (B4) extraction fix + honest recall finding (2026-05-30)

### What was fixed (commit 2a86a7e)
The JATS parser (`fetcher/europepmc.py: _strip_markup`) stripped tags but never
**decoded XML entities**. In JATS, `<` is mandatorily escaped as `&lt;`, so the
dominant reporting form `p < .05` arrived downstream as `p &lt; .05` and every
inequality-form statistic was invisible to B4's regexes. Fix: `html.unescape`
after tag-stripping (so a decoded `<` cannot be re-read as markup), plus
`<sup>/<sub>` dropped without padding (`R<sup>2</sup>` → `R2`,
`χ<sup>2</sup>` → `χ2`) and chi-square regexes tolerant of one space left when
italic+superscript markup splits the symbol. Benefits T4/T6/T9 too.

Correctness is proven deterministically: on a representative JATS snippet the
extractor went from **1 → 5** matches (t, F, r, χ²-in-parens, χ²-separated).
On the live full-text cohort, B4 control FP moved 0 → 2.5 % — i.e. B4 now fires
where it parses, confirming the path is live.

### Honest recall finding — it is a COHORT mismatch, not an extraction bug
Re-running `validate_recall_fulltext.py --n 40` after the fix:

| Detector | recall % (retracted) | FP % (control) | LR+ |
|---|---|---|---|
| B4 statcheck | 0.0 | 2.5 | 0.00 |
| T4 tortured phrases | 7.5 | 5.0 | 1.50 |
| T6 lexical | 0.0 | 0.0 | — |
| T9 classifier | 0.0 | 10.0 | 0.00 |

An extraction-coverage diagnostic on the same 40 retracted papers explains the 0:

- **0/40 retracted papers contain *any* statcheck-extractable statistic.**
- 16/40 do report p-values (`p < .05`-style), but the test statistic + df + p
  almost never appear in the inline adjacency statcheck recomputes:
  `t(` 3/40, `F(` 1/40, `r(` 0/40, chi-related 9/40.

**Conclusion:** statcheck (a psychology-NHST recomputation tool) cannot score a
generic `PUB_TYPE:"Retracted Publication"` OA cohort, which is dominated by
biology / medicine / materials retractions (image manipulation, plagiarism,
paper-mill) that do not report inline NHST. B4 recall = 0 here is **expected and
correct**, not a detector failure. The extraction fix was still necessary: it is
what lets B4 work at all on the disciplines where it *does* apply.

### Next steps for B4 (carried to the network-validation batch)
1. Measure B4 on a **psychology/neuroscience-filtered** retracted cohort (where
   inline NHST is actually reported) to obtain a meaningful recall number.
2. Optionally add **table-aware / proximity extraction** so a statistic split
   across a sentence or table cell (`t = 2.1 … df = 28 … p = .01`) is recovered.
3. Treat B4 as a high-precision convergent signal for specific disciplines, not
   a primary recall driver across all retractions.

Aggregate only; no per-paper or per-author verdicts.
