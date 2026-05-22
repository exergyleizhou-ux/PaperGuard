"""I5 — Batch-log textual repetition (industrial scope).

Operators in pilot-scale and GMP environments are required to write
batch records — narrative observation logs documenting reactor
conditions, deviations, samples taken. A common manipulation
shortcut is **copy-pasting yesterday's narrative** into today's
batch log with minimal edits.

This detector quantifies that copy-pattern with a windowed
n-gram-overlap measure across the rows of a batch-log corpus.

Academic basis
--------------
- Plagiarism detection literature: Stein, Lipka, Prettenhofer (2011)
  *Intrinsic plagiarism analysis*, LREC.
- Industrial pharmacovigilance: FDA Warning Letter 2018-04 to a
  CMO that copy-pasted batch deviation narratives across 12 lots.

Algorithm
---------
1. For each batch's narrative ``text_column``, build a multiset of
   word 4-grams (lowercase, alphanum + space normalised).
2. Pairwise Jaccard similarity over the 4-gram sets.
3. Report any pair with Jaccard ≥ threshold:
   - ≥ 0.40 → NOTE (legitimate vocabulary overlap is common)
   - ≥ 0.60 → CONCERN (suspicious overlap)
   - ≥ 0.80 → SUSPICIOUS (very high overlap, likely copy-paste)
   - ≥ 0.95 → CRITICAL (effectively identical narrative)

Severity tiers are based on the **maximum** pairwise similarity
observed in the corpus. The detector also reports the top 5 most-
similar pairs as evidence.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, ClassVar

import pandas as pd

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity


@dataclass
class BatchRepetitionInput:
    df: pd.DataFrame
    text_column: str = "narrative"
    # Identifier column used for human-readable evidence (batch id, date)
    id_column: str | None = None
    n_gram: int = 4
    min_text_words: int = 30


_WORD_RE = re.compile(r"[a-z0-9]+")


def _ngram_set(text: str, n: int) -> frozenset[str]:
    words = _WORD_RE.findall((text or "").lower())
    if len(words) < n:
        return frozenset()
    return frozenset(" ".join(words[i : i + n]) for i in range(len(words) - n + 1))


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


class I5BatchRepetitionDetector(BaseDetector):
    """Copy-paste detection on batch-narrative columns."""

    id: ClassVar[str] = "I5"
    name: ClassVar[str] = "Batch-Log Narrative Repetition"
    description: ClassVar[str] = (
        "Quantifies pairwise n-gram overlap in batch-record narrative "
        "text. High overlap flags copy-pasted batch logs."
    )
    academic_basis: ClassVar[str] = (
        "Stein B, Lipka N, Prettenhofer P (2011) Intrinsic plagiarism "
        "analysis. LREC. FDA Warning Letters database documents "
        "copy-pasted batch deviation narratives as a recurring CMO "
        "issue (e.g., 2018-04)."
    )
    data_requirements: ClassVar[list[str]] = ["batch_log_input"]
    assumption_cluster: ClassVar[str] = "industrial_narrative_integrity"

    MIN_BATCHES: ClassVar[int] = 3

    def check_applicability(self, data: Any) -> tuple[bool, str]:
        if not isinstance(data, BatchRepetitionInput):
            return False, "Expected BatchRepetitionInput"
        df = data.df
        if df is None or len(df) < self.MIN_BATCHES:
            return False, f"Need ≥ {self.MIN_BATCHES} batches for comparison"
        if data.text_column not in df.columns:
            return False, f"Required column missing: {data.text_column!r}"
        return True, ""

    def _detect(self, data: BatchRepetitionInput, seed: int) -> list[Finding]:
        df = data.df
        col = data.text_column
        n = data.n_gram

        # Build n-gram sets per row.
        sets: list[tuple[int, str, frozenset[str]]] = []
        for idx, val in zip(df.index, df[col].astype(str), strict=False):
            words = _WORD_RE.findall(val.lower())
            if len(words) < data.min_text_words:
                continue
            ngrams = _ngram_set(val, n)
            if not ngrams:
                continue
            label = (
                str(df.at[idx, data.id_column])
                if data.id_column and data.id_column in df.columns
                else f"row[{idx}]"
            )
            sets.append((int(idx) if isinstance(idx, int) else 0, label, ngrams))

        if len(sets) < self.MIN_BATCHES:
            return []

        # Pairwise Jaccard.
        pairs: list[tuple[str, str, float]] = []
        for i in range(len(sets)):
            for j in range(i + 1, len(sets)):
                sim = _jaccard(sets[i][2], sets[j][2])
                if sim >= 0.40:
                    pairs.append((sets[i][1], sets[j][1], sim))

        if not pairs:
            return []

        pairs.sort(key=lambda p: -p[2])
        max_sim = pairs[0][2]
        n_critical = sum(1 for p in pairs if p[2] >= 0.95)
        n_suspicious = sum(1 for p in pairs if 0.80 <= p[2] < 0.95)
        n_concern = sum(1 for p in pairs if 0.60 <= p[2] < 0.80)
        n_note = sum(1 for p in pairs if 0.40 <= p[2] < 0.60)

        if n_critical > 0:
            severity = Severity.CRITICAL
        elif n_suspicious > 0:
            severity = Severity.SUSPICIOUS
        elif n_concern > 0:
            severity = Severity.CONCERN
        else:
            severity = Severity.NOTE

        return [
            Finding(
                detector_id=self.id,
                detector_name=self.name,
                severity=severity,
                summary=(
                    f"Max pairwise narrative similarity = "
                    f"{max_sim:.2%} across {len(pairs)} pairs "
                    f"(threshold ≥ 40%)"
                ),
                detail=(
                    f"Pairwise {n}-gram Jaccard similarity exceeds 40% "
                    f"on {len(pairs)} batch pairs. Most similar pair: "
                    f"{pairs[0][0]!r} vs {pairs[0][1]!r} = "
                    f"{pairs[0][2]:.2%}. Counts by severity tier: "
                    f"CRITICAL ≥ 95% = {n_critical}, SUSPICIOUS ≥ 80% "
                    f"= {n_suspicious}, CONCERN ≥ 60% = {n_concern}, "
                    f"NOTE ≥ 40% = {n_note}."
                ),
                test_statistic=max_sim,
                test_name=f"max pairwise {n}-gram Jaccard",
                evidence={
                    "n_pairs_above_threshold": len(pairs),
                    "max_similarity": max_sim,
                    "top_5_pairs": [
                        {"a": a, "b": b, "similarity": s}
                        for a, b, s in pairs[:5]
                    ],
                    "tier_counts": {
                        "critical_>=0.95": n_critical,
                        "suspicious_>=0.80": n_suspicious,
                        "concern_>=0.60": n_concern,
                        "note_>=0.40": n_note,
                    },
                    "n_batches_analysed": len(sets),
                },
                innocent_explanations=[
                    "Standard-operating-procedure boilerplate text is "
                    "intentionally repeated across all batch records "
                    "(e.g., regulatory headers, equipment descriptions). "
                    "Tighten the analysis to the deviation-narrative "
                    "field only.",
                    "Identical batches that genuinely had identical "
                    "outcomes — short narratives ('no deviations, "
                    "in-spec product') will register as duplicates.",
                    "Template-based narrative writing where operators "
                    "fill in numeric values into a fixed prose "
                    "template — legitimate practice in some GMP shops.",
                    "The text_column points to a metadata field "
                    "(equipment, recipe) instead of the narrative; "
                    "re-check column selection.",
                ],
                academic_reference=self.academic_basis,
            )
        ]
