# PaperGuard's Epistemic Position

PaperGuard exists in a politically dangerous space. Calling out academic
misconduct ruins careers, generates lawsuits, and is sometimes wrong. This
document is the public commitment about what this tool will and will not say.

## The vocabulary rule

The words **"fraud", "fabrication", "misconduct", "造假"** do not appear in
any PaperGuard report, ever. They appear in academic citations and in this
documentation, but never in the analytical output the tool produces about a
specific paper.

Instead, every finding uses neutral terms:
- "statistical anomaly"
- "inconsistency"
- "unexplained pattern"
- "signal warranting review"

This is a hard guarantee enforced by code review, not a stylistic preference.

## The innocent-explanation rule

Every `Finding` has a `innocent_explanations: list[str]` field with at
least **three** entries listing plausible non-misconduct causes. A
`Finding` without innocent explanations is a code-level bug.

This forces the tool — and through it, the reader — to think Bayesian:
P(misconduct | observed signal) is **not** the same as P(signal | misconduct).
False positives are real, and we want them visible.

## The disclaimer rule

Every report (terminal, HTML, JSON) ends with the same disclaimer:

> This report flags **statistical anomalies, not fraud**. Anomalies can
> arise from instrument behavior, data-cleaning choices, legitimate
> experimental constraints, or honest error. Any concern about authorship
> integrity should be raised through journal editors or institutional
> investigation channels, not on the basis of this tool's output alone.

In all 5 supported languages (en, zh-CN, es, ja, de).

## What PaperGuard is for

1. **Personal screening before submission** — catch your own mistakes
   (wrong N, mis-typed p, image accidentally reused).
2. **Pre-review screening by journal editors** — surface signals that
   warrant deeper human review.
3. **Post-publication concerns by readers** — find specific anomalies
   to ask the authors about politely, **before** considering raising
   it with the journal.
4. **Education** — show students what real statistical-integrity checks
   look like, and what their limits are.

## What PaperGuard is **not** for

1. ❌ **Public accusations.** Output of this tool is not evidence of
   misconduct. Saying "PaperGuard CRITICAL means the paper is fraudulent"
   is a misuse and the maintainers reject responsibility for that misuse.
2. ❌ **Automated retraction recommendations.** No automated system has
   the contextual understanding to recommend retraction.
3. ❌ **Reviewer-of-record substitute.** PaperGuard supplements; it does
   not replace careful human review.
4. ❌ **Author-intent inference.** Statistical anomalies can have many
   causes; intent is not one PaperGuard claims to discern.

## Why the disclaimer matters

A 2023 case in psychology had a senior researcher's career publicly
destroyed by a high-profile claim of fabrication based partly on
GRIM/GRIMMER outputs. The institutional investigation later found that
**most of the flagged numbers were typos and rounding errors, not
fabrication** — but the public claim was made before that investigation
finished, and the reputational damage was not reversed.

This is the failure mode PaperGuard is designed to make harder. Anomalies
should produce investigations, not verdicts.

## Reporting concerns the right way

If PaperGuard surfaces something on a paper you read:

1. **Verify the signal yourself.** Open the paper, find the actual values,
   re-run the check by hand.
2. **Read the `innocent_explanations`.** Sometimes one of them obviously
   applies (e.g., the paper's Methods explicitly states stratified
   randomization → C1 over-balance is expected).
3. **Contact the corresponding author.** A polite, specific question
   ("Could you clarify how the SD in Table 2 row 3 was computed?") is
   strictly better than going to social media.
4. **If author response is unsatisfactory:** Raise with the journal's
   editorial office. Use COPE flowcharts. Include the report.
5. **Only after journal channels exhaust:** Consider PubPeer for public
   transparency.

## Reporting bugs in PaperGuard

If PaperGuard flagged something innocent, **that's a bug in PaperGuard**.
Please file an issue with:
- The redacted minimal example that triggers it
- Which detector misfired
- Why you believe the signal is a false positive

We will adjust thresholds, add `innocent_explanations`, or document the
limitation.
