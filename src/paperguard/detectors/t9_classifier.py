"""T9 — TF-IDF + logistic-regression LLM-text classifier (opt-in).

A *learned* complement to the statistical T7 (perplexity) and T8 (DetectGPT)
detectors and the lexical T6 heuristic. A linear classifier (TF-IDF features +
logistic regression) is fitted on the public HC3 corpus (Guo et al., 2023) and
shipped as a small bundled artifact (``data/t9_classifier.npz``). Inference is
**pure NumPy** — no scikit-learn, torch, or network call at runtime — so the
core install stays lean and the detector runs in milliseconds on CPU.

Opt-in via ``PAPERGUARD_ML_CHECK=1`` (mirrors the T7/T8 gating), so enabling it
is an explicit choice and existing scans are unchanged by default.

**Empirical scope (honest).** The model is trained on HC3, whose "machine"
class is ChatGPT (gpt-3.5, 2023). It is an *in-distribution* signal: it is
strong on 2023-era ChatGPT prose and weaker / unreliable on newer models
(GPT-4o, Claude, Gemini), on non-English text, and on heavily copy-edited
manuscripts. It reports a *probability of LLM-style text*, never a verdict.

Iron rule: no verdict language; every ``Finding`` ships >= 3 innocent
explanations. The classifier emits a probability, never a confirmation.
"""
from __future__ import annotations

import logging
import math
import os
import re
from functools import lru_cache
from importlib.resources import files
from typing import Any, ClassVar

import numpy as np

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity

logger = logging.getLogger(__name__)

# Mirrors sklearn TfidfVectorizer's default token pattern.
_TOKEN_RE = re.compile(r"\b\w\w+\b", re.UNICODE)

MIN_WORDS = 150
_CONCERN_THRESHOLD = 0.70  # NOTE < 0.70 <= CONCERN < SUSPICIOUS
_NOTE_THRESHOLD = 0.50
_SEGMENT_CHARS = 1500  # ~ one HC3 answer; keeps inference in-distribution


def _opt_in_enabled() -> bool:
    """T9 is gated by an env var (set by the CLI flag), like T7/T8."""
    return os.environ.get("PAPERGUARD_ML_CHECK", "").lower() in {
        "1",
        "true",
        "yes",
    }


def _tokens(text: str) -> list[str]:
    """Lowercase + word-tokenize exactly as sklearn TfidfVectorizer does."""
    return _TOKEN_RE.findall(text.lower())


def _features(text: str, ngram_max: int) -> dict[str, int]:
    """Count unigram..ngram_max term frequencies (sklearn ngram semantics)."""
    toks = _tokens(text)
    counts: dict[str, int] = {}
    n = len(toks)
    for size in range(1, ngram_max + 1):
        for i in range(n - size + 1):
            gram = " ".join(toks[i : i + size])
            counts[gram] = counts.get(gram, 0) + 1
    return counts


class _Model:
    """Loaded TF-IDF + LR weights with a pure-NumPy scorer.

    Replicates ``TfidfVectorizer(sublinear_tf=True, norm="l2",
    smooth_idf=True) -> LogisticRegression`` decision_function so that
    ``predict_proba`` matches the trained sklearn pipeline (the trainer
    asserts this equivalence before shipping the artifact).
    """

    def __init__(self, npz: Any) -> None:
        self.vocab: dict[str, int] = {
            str(t): i for i, t in enumerate(npz["vocab"])
        }
        self.idf: np.ndarray = npz["idf"].astype(np.float64)
        self.coef: np.ndarray = npz["coef"].astype(np.float64)
        self.intercept: float = float(npz["intercept"])
        self.ngram_max: int = int(npz["ngram_max"])
        self.threshold: float = float(npz["threshold"])
        self.accuracy: float = float(npz["accuracy"])
        self.lr_plus: float = float(npz["lr_plus"])

    def prob_llm(self, text: str) -> float:
        """Return P(text is LLM-style) in [0, 1]."""
        counts = _features(text, self.ngram_max)
        idxs: list[int] = []
        tfidf: list[float] = []
        for gram, c in counts.items():
            j = self.vocab.get(gram)
            if j is None:
                continue
            tf = 1.0 + math.log(c)  # sublinear_tf
            idxs.append(j)
            tfidf.append(tf * self.idf[j])
        if not idxs:
            decision = self.intercept  # empty doc -> only the bias term
        else:
            vec = np.asarray(tfidf, dtype=np.float64)
            norm = float(np.sqrt(np.dot(vec, vec)))  # L2 normalize
            if norm > 0.0:
                vec = vec / norm
            decision = float(np.dot(vec, self.coef[idxs])) + self.intercept
        return 1.0 / (1.0 + math.exp(-decision))


@lru_cache(maxsize=1)
def _load_model() -> _Model | None:
    """Load the bundled artifact once. Returns None if it is absent."""
    try:
        res = files("paperguard.data").joinpath("t9_classifier.npz")
        with res.open("rb") as fh:
            npz = np.load(fh, allow_pickle=False)
            return _Model(npz)
    except (FileNotFoundError, ModuleNotFoundError, KeyError, OSError) as e:
        logger.warning("T9 model artifact not loadable: %s", e)
        return None


class T9ClassifierDetector(BaseDetector):
    id: ClassVar[str] = "T9"
    name: ClassVar[str] = "TF-IDF/LR LLM-text classifier"
    description: ClassVar[str] = (
        "Learned linear classifier (TF-IDF + logistic regression, trained on "
        "HC3) estimating the probability that a passage reads as ChatGPT-style "
        "text. Pure-NumPy inference; opt-in via PAPERGUARD_ML_CHECK."
    )
    academic_basis: ClassVar[str] = (
        "Guo et al. (2023) 'How Close is ChatGPT to Human Experts? "
        "Comparison Corpus and Detection' (HC3 dataset)."
    )
    data_requirements: ClassVar[list[str]] = ["manuscript_text"]
    # Shares the LLM-text assumption cluster with T6/T7/T8 — NOT independent
    # evidence; the combiner must not double-count these.
    assumption_cluster: ClassVar[str] = "llm_text_signature"

    def check_applicability(self, data: Any) -> tuple[bool, str]:
        if not _opt_in_enabled():
            return False, "T9 is opt-in (set PAPERGUARD_ML_CHECK=1)"
        if not isinstance(data, str):
            return False, "Expected text string"
        if len(re.findall(r"\b[a-zA-Z]+\b", data)) < MIN_WORDS:
            return False, "Text too short"
        if _load_model() is None:
            return False, "T9 model artifact not available"
        return True, ""

    def _segment(self, text: str) -> list[str]:
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        segs: list[str] = []
        buf = ""
        for s in sentences:
            if not s:
                continue
            if len(buf) + len(s) + 1 > _SEGMENT_CHARS and buf:
                segs.append(buf.strip())
                buf = s
            else:
                buf = (buf + " " + s) if buf else s
        if buf:
            segs.append(buf.strip())
        return segs

    def _detect(self, data: str, seed: int) -> list[Finding]:
        model = _load_model()
        if model is None:  # defensive; check_applicability already guards
            return []
        segments = self._segment(data) or [data]
        probs = [model.prob_llm(seg) for seg in segments]
        p_max = max(probs)
        p_mean = sum(probs) / len(probs)

        if p_max >= model.threshold:
            severity = Severity.SUSPICIOUS
        elif p_max >= _CONCERN_THRESHOLD:
            severity = Severity.CONCERN
        elif p_max >= _NOTE_THRESHOLD:
            severity = Severity.NOTE
        else:
            return []  # reads human-like; emit nothing

        n_flagged = sum(1 for p in probs if p >= _CONCERN_THRESHOLD)
        return [
            Finding(
                detector_id=self.id,
                detector_name=self.name,
                severity=severity,
                summary=(
                    f"A passage scores p(LLM-style)={p_max:.2f} on the learned "
                    "TF-IDF/LR classifier"
                ),
                detail=(
                    "A logistic-regression classifier trained on the HC3 "
                    "human-vs-ChatGPT corpus assigns a high LLM-style "
                    f"probability to {n_flagged} of {len(segments)} text "
                    "segment(s). This is a stylistic similarity signal against "
                    "2023-era ChatGPT prose, not a determination of authorship."
                ),
                test_statistic=round(p_max, 4),
                test_name="tfidf_lr_prob_llm",
                evidence={
                    "p_llm_max": round(p_max, 4),
                    "p_llm_mean": round(p_mean, 4),
                    "n_segments": len(segments),
                    "n_flagged": n_flagged,
                    "threshold": model.threshold,
                    "model_holdout_accuracy": model.accuracy,
                    "model_lr_plus_at_threshold": model.lr_plus,
                },
                innocent_explanations=[
                    "The author is a non-native English writer whose phrasing "
                    "overlaps with the model's training distribution.",
                    "The passage was legitimately polished with an LLM writing "
                    "assistant, which many journals now permit when disclosed.",
                    "Formulaic sections (background, standard methods) read "
                    "'LLM-like' simply because the genre is highly conventional.",
                    "HC3 captures ChatGPT circa 2023; domain or model drift can "
                    "inflate the score on perfectly human modern text.",
                ],
                academic_reference=self.academic_basis,
                applicability_notes=(
                    "In-distribution signal trained on HC3 (ChatGPT, 2023; "
                    f"held-out accuracy {model.accuracy:.3f}). Treat as a "
                    "screening prior and corroborate with T6/T7/T8 before "
                    "acting. Unreliable on newer models and non-English text."
                ),
            )
        ]
