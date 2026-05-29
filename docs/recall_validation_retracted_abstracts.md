# Text-layer recall validation on retracted papers — abstract level (2026-05-29)

**Honest negative result.** Recorded for transparency (negative results matter).

## Method
- 200 retracted (`is_retracted:true`) + 200 non-retracted control Open-Access
  works from OpenAlex; **abstracts only** (`abstract_inverted_index`).
- Ran the abstract-applicable text detectors T4 (tortured phrases), T6 (lexical
  AI/paper-mill), T9 (learned classifier).
- Reproduce: `python scripts/validate_recall_retracted.py --n 200`

## Results

| Detector | recall % (retracted) | FP % (control) | LR+ |
|---|---|---|---|
| T4 tortured phrases | 0.5 | 0.0 | ∞ (only 1/200; rarely fires) |
| T6 lexical | 4.0 | 7.5 | 0.53 |
| T9 classifier | 5.0 | 6.0 | 0.83 |
| any | 9.0 | 11.5 | 0.78 |

(LR+ ≈ 1 means no discrimination; the text detectors do **not** separate
retracted from normal papers at the abstract level.)

## Honest interpretation — why this is a NULL, and what it does/doesn't mean
1. **Abstracts only.** PaperGuard's strongest families — numeric/statistical
   (GRIM, statcheck, Benford, GRIMMER, SPRITE, TIVA, Carlisle) and image
   forensics (F1–F7) — **cannot run on an abstract**. They need full-text
   tables, reported statistics, and figures. The high-yield detectors were
   never exercised here.
2. **Most retractions are not text-detectable.** Data fabrication, image
   duplication, ethics breaches, duplicate publication leave **no trace in the
   abstract prose**. Low text-layer recall on a mixed-cause retraction set is
   expected, not a defect.
3. **Wrong altitude.** This bounds the *abstract text layer*, not the tool.
   The proper recall test must run the full detector suite on **full text +
   data files + figures** (e.g. via Europe PMC OA full text), and is the
   subject of follow-up work.

This result is kept deliberately: it documents that abstract-only text
screening is near-chance and should not be relied on. It is a guardrail
against over-claiming, consistent with the project's iron rule.
