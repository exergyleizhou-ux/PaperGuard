# T9 specificity calibration on real Open-Access papers (2026-05-29)

**Question.** T9 (TF-IDF/LR LLM-text classifier) is trained on HC3 — English
Q&A, ChatGPT-2023. Does its high-specificity operating point hold on
*out-of-domain* real human-led research text? A detector that flags genuine
papers is worse than useless, so we bound its **false-positive rate** before
relying on it.

## Method

- **Corpus.** 400 Open-Access works (last 12 months) affiliated with one
  university (Zhejiang A&F University, OpenAlex `I1284762954`), fetched via the
  free OpenAlex API. Predominantly materials-science / environmental-science
  abstracts — a domain and author population very different from HC3.
- **Open-Access only.** Abstracts come from OpenAlex's `abstract_inverted_index`
  (no paywalled full texts downloaded or stored).
- **Scoring.** Each abstract is scored offline by the shipped T9 artifact
  (`prob_llm`). No network, no API key, no LLM calls.
- **Reproduce:** `python scripts/calibrate_t9_oa.py --institution I1284762954 --max 400`

## Results

| Metric | All (N=400) | Detector-eligible, ≥150 words (N=365) |
|---|---|---|
| mean p(LLM) | 0.141 | 0.145 |
| median p(LLM) | 0.070 | 0.073 |
| 90th percentile | 0.401 | 0.414 |
| ≥ NOTE (0.50) | 6.5 % | 6.8 % |
| ≥ CONCERN (0.70) | 3.0 % | 3.3 % |
| **≥ SUSPICIOUS (0.90, report threshold)** | **0.0 % (0/400)** | **0.0 % (0/365)** |

## Interpretation

- **False-positive rate at the ship threshold (p ≥ 0.90) is 0 % on 400 real
  papers**, and this holds out-of-domain (Chinese-authored materials /
  environmental abstracts vs HC3 English Q&A). The conservative 0.90 cut-point
  is validated: T9 does not flag genuine research at its reporting threshold.
- The bulk of real abstracts sit low (median p ≈ 0.07), as desired.
- The ~3–7 % that cross the softer NOTE/CONCERN tiers are **not** evidence of
  error or of misconduct. In 2025 it is common — and increasingly
  permitted when disclosed — to polish English abstracts with an LLM, so these
  softer flags plausibly mix genuine out-of-domain false positives **and** real
  LLM-assisted writing. This study **bounds specificity; it does not accuse any
  author or paper.** No per-paper or per-author results are produced.
- **No domain retraining needed.** Because specificity already holds at the ship
  threshold, T9 does not require fine-tuning on this domain to be safe to use.

## Ethics

Aggregate statistics only. Open-Access sources only. The institution is a
*data source* for a specificity check, not a target — the calibration script
accepts any institution id and reports only distributions. Consistent with the
project iron rule: T9 reports a probability, never a verdict.
