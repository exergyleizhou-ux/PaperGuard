"""T8 — DetectGPT-style perturbation detector (opt-in, costs API calls).

**Empirical scope (2.2.7).** T8 requires a **non-reasoning** paraphraser
whose rewrites drift *off* the LLM-likelihood manifold — this is the
core assumption of Mitchell et al.'s probability-curvature method.
**Reasoning models (OpenAI o-series, DeepSeek-v4, Qwen3-thinking,
GPT-5-class) are structurally incompatible**: their paraphrases stay
on-manifold and the detection score collapses or reverses. Measured
LR+ on DeepSeek-v4-flash was 0.25 (N=20) — worse than coin flip — for
exactly this reason. Recommended endpoints: OpenAI `gpt-4o`
(non-reasoning), or self-hosted Llama-3.3-70B. See
`docs/llm_detection_real_endpoints.md` for the full matrix and
`docs/t8_endpoint_limitation.md` for the original cliproxy diagnosis.

T7 needs token logprobs, which many chat-completion proxies (cliproxy,
some team pools) silently drop. T8 is the **alternative statistical
signal that needs only plain-text completions**.

Method
------
Adapted from Mitchell et al. (2023) "DetectGPT: Zero-Shot Machine-
Generated Text Detection using Probability Curvature":

  1. Take the manuscript passage `x`.
  2. Build `K` perturbations `x_1 ... x_K` by asking the reference LM
     to rewrite the passage with light paraphrasing (≈15% of content
     words swapped, preserving meaning).
  3. Ask the LM to **rate naturalness** of each of `{x, x_1, ..., x_K}`
     on a 1-10 scale. We *parse* the score from the response text — no
     logprobs needed.
  4. Compute detection_score = (mean(score_perturbed) - score_original)
                                 / std(score_perturbed)
  5. Interpretation:
       - LLM-authored text: the LM consistently rates `x` as more
         natural than its own paraphrases (because `x` was on the
         likelihood manifold to begin with). detection_score < 0,
         and < -0.5 is suspicious.
       - Human-authored text: `x` is *not* on the LM's manifold;
         paraphrases are about as natural or even more so.
         detection_score ≥ 0.

Cost: 1 (original score) + K (perturbations) + K (perturbation scores)
       = 2K + 1 calls per segment. We default to K = 3 and 2 segments,
       so 14 API calls per paper. Heavier than T7 but works on every
       chat-completion endpoint.

Severity tiers (defaults, override via class attributes):

  detection_score ≥ 0       → no finding (human-like)
  -0.5 ≤ score < 0          → NOTE       (marginal)
  -1.5 ≤ score < -0.5       → SUSPICIOUS (LLM thinks original is much
                                          better than its paraphrases)
       score < -1.5         → CRITICAL   (very strong signal)

Failure modes (always silent, never raise):

  - LM refuses to rate / returns non-numeric → segment dropped
  - Network error → segment dropped
  - Fewer than 2 successful perturbations for a segment → segment dropped
  - All segments drop → detect() emits NOTE "inconclusive"
"""
from __future__ import annotations

import logging
import math
import os
import random
import re
import statistics
from typing import Any, ClassVar

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity

logger = logging.getLogger(__name__)

_DEFAULT_NOTE = 0.0
_DEFAULT_SUSPICIOUS = -0.5
_DEFAULT_CRITICAL = -1.5

_RATING_RE = re.compile(r"\b(10|[1-9])(?:\s*/\s*10)?\b")


def _opt_in_enabled() -> bool:
    """T8 is gated by an env var the CLI flag flips on."""
    return os.environ.get("PAPERGUARD_DETECTGPT_CHECK", "").lower() in {
        "1",
        "true",
        "yes",
    }


def _segment_text(text: str, max_chars_per_segment: int = 1600) -> list[str]:
    """Split text into sentence-aligned segments under the char cap."""
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    segments: list[str] = []
    buf = ""
    for s in sentences:
        if not s:
            continue
        if len(buf) + len(s) + 1 > max_chars_per_segment and buf:
            segments.append(buf.strip())
            buf = s
        else:
            buf = (buf + " " + s) if buf else s
    if buf:
        segments.append(buf.strip())
    return segments


def _call_chat(
    system: str,
    user: str,
    *,
    model: str,
    base_url: str,
    api_key: str,
    timeout: float = 60.0,
    max_tokens: int = 400,
    temperature: float = 0.0,
) -> str | None:
    """Minimal chat-completion call. Returns assistant text or None."""
    import httpx

    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    try:
        r = httpx.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPError as e:
        logger.warning("T8 LLM call failed: %s", e)
        return None
    except ValueError as e:
        logger.warning("T8 LLM response not JSON: %s", e)
        return None
    try:
        content = data["choices"][0]["message"]["content"]
        if isinstance(content, str) and content.strip():
            return content
    except (KeyError, IndexError, TypeError) as e:
        logger.warning("T8 malformed response: %s", e)
    return None


def _generate_perturbation(
    text: str,
    *,
    model: str,
    base_url: str,
    api_key: str,
    timeout: float,
    seed_hint: int,
) -> str | None:
    """Ask the LM to paraphrase ~15% of content words while preserving meaning."""
    system = (
        "You are an academic copy editor. Lightly paraphrase the user's "
        "passage by replacing roughly 15% of content words (nouns, verbs, "
        "adjectives) with close synonyms. PRESERVE the meaning exactly. "
        "Do not add, remove, or reorder sentences. Output ONLY the rewritten "
        "passage, no preamble, no commentary, no quotation marks."
    )
    user = f"Variant seed: {seed_hint}\n\nPassage:\n{text}"
    # Budget for reasoning models: paraphrasing a 600-char input on
    # DeepSeek-v4 / Qwen3 / o1-class models burns ~300-600 hidden
    # reasoning tokens BEFORE emitting the actual paraphrase (~150
    # tokens). Total ≈ 800-1200. Non-reasoning models ignore the extra
    # budget. We try at 2× input length first, then retry at 4× with a
    # less reasoning-heavy prompt if the first attempt returns empty.
    budget_pass1 = max(1200, min(2500, len(text) * 2 + 800))
    out = _call_chat(
        system, user,
        model=model, base_url=base_url, api_key=api_key,
        timeout=timeout,
        max_tokens=budget_pass1,
        temperature=0.7,
    )
    # Retry pass: if reasoning model exhausted budget on hidden thinking
    # (content="" but call returned 200), try again with a much higher
    # ceiling. This is the single biggest failure mode in real T8 runs.
    if out is None:
        budget_pass2 = max(3000, len(text) * 4 + 1500)
        retry_system = system + (
            " Skip all reasoning steps. Output the paraphrase directly "
            "without any chain-of-thought."
        )
        out = _call_chat(
            retry_system, user,
            model=model, base_url=base_url, api_key=api_key,
            timeout=timeout,
            max_tokens=budget_pass2,
            temperature=0.7,
        )
    if out is None:
        return None
    # Sanity: if the LM returns the same string verbatim or something
    # absurdly short, drop it.
    if out.strip() == text.strip():
        return None
    if len(out) < 0.5 * len(text):
        return None
    return out.strip()


def _score_naturalness(
    text: str,
    *,
    model: str,
    base_url: str,
    api_key: str,
    timeout: float,
) -> float | None:
    """Ask the LM to estimate how likely the passage came from an LLM.

    Naming kept as `_score_naturalness` for backward compat with tests,
    but the prompt is the LLM-likeness scale described below. Direction:
    HIGH score = LLM-like, LOW score = human-like.

    DetectGPT theory works the same way under this reformulation:
      - LM-generated text: LM rates ORIGINAL as MORE LLM-like than
        paraphrases (because original is precisely on the LM manifold,
        paraphrases drift off).
      - Human-generated text: LM cannot tell original from paraphrases.

    Detection score sign convention:
        score = (mean(scores_perturbed) - score_original) / std(...)
      LM text  → score_original is HIGH  → score is NEGATIVE → suspicious
      Human    → score_original ≈ scores_perturbed → score ≈ 0
    """
    system = (
        "You are a forensics expert detecting AI-generated academic prose. "
        "On a 1-10 scale, rate how likely the passage was generated by a "
        "large language model (ChatGPT/Claude/Gemini) rather than written "
        "by a human researcher. 10 = almost certainly LLM-generated "
        "(uses LLM phrases like 'delve into', 'meticulously', 'tapestry', "
        "'pivotal role', sounds polished but generic). 1 = clearly "
        "human-written (specific technical detail, idiosyncratic phrasing, "
        "or rough edges typical of researcher drafts). Respond with ONLY "
        "the integer score on its own line. No explanation."
    )
    # max_tokens must be high enough for reasoning models (DeepSeek-v4,
    # o1/o3, GPT-5) to spend their hidden reasoning budget AND still emit
    # a final number. Empirically 500 covers DeepSeek-v4-flash's ~150
    # reasoning tokens per scoring call. Non-reasoning models ignore the
    # extra budget.
    out = _call_chat(
        system, text,
        model=model, base_url=base_url, api_key=api_key,
        timeout=timeout,
        max_tokens=500,
        temperature=0.0,
    )
    if out is None:
        return None
    m = _RATING_RE.search(out)
    if not m:
        logger.info("T8 naturalness score unparseable: %r", out[:80])
        return None
    try:
        score = float(m.group(1))
    except ValueError:
        return None
    if not 1 <= score <= 10:
        return None
    return score


def _detection_score_for_segment(
    text: str,
    *,
    model: str,
    base_url: str,
    api_key: str,
    timeout: float,
    k_perturbations: int,
    rng: random.Random,
) -> tuple[float | None, dict[str, Any]]:
    """Run one segment through the DetectGPT pipeline."""
    diagnostics: dict[str, Any] = {
        "n_perturbations_requested": k_perturbations,
        "n_perturbations_returned": 0,
        "n_scores_parsed": 0,
        "score_original": None,
        "scores_perturbed": [],
    }
    score_original = _score_naturalness(
        text, model=model, base_url=base_url, api_key=api_key, timeout=timeout
    )
    if score_original is None:
        return None, diagnostics
    diagnostics["score_original"] = score_original

    perturbed_scores: list[float] = []
    for _ in range(k_perturbations):
        p = _generate_perturbation(
            text,
            model=model,
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            seed_hint=rng.randint(1, 999_999),
        )
        if p is None:
            continue
        diagnostics["n_perturbations_returned"] += 1
        s = _score_naturalness(
            p, model=model, base_url=base_url, api_key=api_key, timeout=timeout
        )
        if s is None:
            continue
        perturbed_scores.append(s)
        diagnostics["scores_perturbed"].append(s)
    diagnostics["n_scores_parsed"] = len(perturbed_scores)

    if len(perturbed_scores) < 2:
        return None, diagnostics

    # Detection score: how many SDs below the perturbed mean the original
    # naturalness sits. A NEGATIVE value means "original was rated MORE
    # natural than its paraphrases" — the LM thinks `x` is the local
    # likelihood maximum, which is what we expect for LM-authored text.
    # We adopt the opposite sign convention from the DetectGPT paper here
    # so that "more suspicious" is "more negative" — consistent with
    # other PaperGuard z-style severity scaling.
    mean_p = statistics.mean(perturbed_scores)
    std_p = statistics.pstdev(perturbed_scores) or 0.5  # avoid div/0
    score = (mean_p - score_original) / std_p
    return score, diagnostics


def compute_detection_score(
    text: str,
    *,
    model: str | None = None,
    max_segments: int = 2,
    k_perturbations: int = 3,
    timeout: float = 60.0,
    seed: int = 42,
) -> tuple[float | None, list[dict[str, Any]]]:
    """Public helper: compute the aggregated detection score for the text.

    Returns (score, per_segment_diagnostics). score is None on total
    failure (no segments produced a score).
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None, []
    base_url = os.environ.get(
        "PAPERGUARD_LLM_BASE_URL", "https://api.openai.com/v1"
    )
    model_name = (
        model or os.environ.get("PAPERGUARD_LLM_MODEL") or "gpt-4o-mini"
    )
    segments = _segment_text(text)[:max_segments]
    if not segments:
        return None, []

    rng = random.Random(seed)
    seg_scores: list[float] = []
    diagnostics: list[dict[str, Any]] = []
    for seg in segments:
        s, diag = _detection_score_for_segment(
            seg,
            model=model_name,
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            k_perturbations=k_perturbations,
            rng=rng,
        )
        diagnostics.append(diag)
        if s is not None and math.isfinite(s):
            seg_scores.append(s)
    if not seg_scores:
        return None, diagnostics
    return statistics.mean(seg_scores), diagnostics


class T8DetectGPTDetector(BaseDetector):
    """Probability-curvature detector for LLM-generated manuscript text.

    Works on any chat-completion endpoint (no logprobs required). Opt-in
    via ``PAPERGUARD_DETECTGPT_CHECK=1`` or the CLI ``--detectgpt-check``
    flag. See module docstring for methodology + caveats.
    """

    id: ClassVar[str] = "T8"
    name: ClassVar[str] = "DetectGPT-style Perturbation"
    description: ClassVar[str] = (
        "Measures whether the LM rates the manuscript text as more natural "
        "than its own paraphrases (a likelihood-curvature signal). Strongly "
        "indicative of LLM authorship without needing token logprobs. "
        "Opt-in; requires an LLM API."
    )
    academic_basis: ClassVar[str] = (
        "Mitchell et al. (2023) DetectGPT: Zero-Shot Machine-Generated "
        "Text Detection using Probability Curvature, ICML. PaperGuard "
        "adapts the score-curvature idea to chat-completion APIs (the "
        "original paper assumes access to white-box token probabilities)."
    )
    data_requirements: ClassVar[list[str]] = ["manuscript_text"]
    assumption_cluster: ClassVar[str] = "paper_mill_signature"

    MIN_WORDS: ClassVar[int] = 400
    THRESHOLD_NOTE: ClassVar[float] = _DEFAULT_NOTE
    THRESHOLD_SUSPICIOUS: ClassVar[float] = _DEFAULT_SUSPICIOUS
    THRESHOLD_CRITICAL: ClassVar[float] = _DEFAULT_CRITICAL

    K_PERTURBATIONS: ClassVar[int] = 3
    MAX_SEGMENTS: ClassVar[int] = 2

    def check_applicability(self, data: Any) -> tuple[bool, str]:
        if not _opt_in_enabled():
            return False, (
                "T8 is opt-in; set PAPERGUARD_DETECTGPT_CHECK=1 "
                "(or pass --detectgpt-check)."
            )
        if not isinstance(data, str):
            return False, "Expected text string"
        n_words = len(re.findall(r"\b[a-zA-Z]+\b", data))
        if n_words < self.MIN_WORDS:
            return False, (
                f"Text too short for stable DetectGPT estimate "
                f"({n_words} < {self.MIN_WORDS})"
            )
        if not os.environ.get("OPENAI_API_KEY"):
            return False, "OPENAI_API_KEY not set; T8 requires an LLM API."
        return True, ""

    def _detect(self, data: str, seed: int) -> list[Finding]:
        score, diagnostics = compute_detection_score(
            data,
            max_segments=self.MAX_SEGMENTS,
            k_perturbations=self.K_PERTURBATIONS,
            seed=seed,
        )
        if score is None:
            return [
                Finding(
                    detector_id=self.id,
                    detector_name=self.name,
                    severity=Severity.NOTE,
                    summary=(
                        "T8 DetectGPT check requested but no segment "
                        "produced a usable score"
                    ),
                    detail=(
                        "The LLM either could not paraphrase the text or "
                        "refused to rate naturalness on a numeric scale. "
                        "T8 is reported as inconclusive — this is NOT "
                        "evidence of LLM authorship, only that the check "
                        "could not run on this manuscript."
                    ),
                    evidence={
                        "score": None,
                        "outcome": "no_scores",
                        "diagnostics": diagnostics,
                    },
                    innocent_explanations=[
                        "The proxy may rate-limit or filter the "
                        "paraphrase prompt; switch providers.",
                        "Transient network failure — retry the scan.",
                        "Manuscript text contains characters that confuse "
                        "the rating prompt.",
                    ],
                    academic_reference=self.academic_basis,
                    applicability_notes=(
                        "Inconclusive — no segment scored successfully."
                    ),
                )
            ]

        severity: Severity | None = None
        if score < self.THRESHOLD_CRITICAL:
            severity = Severity.CRITICAL
        elif score < self.THRESHOLD_SUSPICIOUS:
            severity = Severity.SUSPICIOUS
        elif score < self.THRESHOLD_NOTE:
            severity = Severity.NOTE

        if severity is None:
            return []

        return [
            Finding(
                detector_id=self.id,
                detector_name=self.name,
                severity=severity,
                summary=(
                    f"DetectGPT detection score {score:+.2f}; weak LLM-"
                    f"authorship signal"
                ),
                detail=(
                    f"Across {len(diagnostics)} segment(s), the reference LM "
                    f"rated the manuscript text on average {score:+.2f} "
                    "standard deviations relative to its own paraphrases. "
                    "Negative scores mean the LM rated the original as more "
                    "natural than the paraphrases — consistent with the "
                    "original sitting at a local likelihood maximum, which "
                    "is what LM-generated text does.\n\n"
                    "Methodology: DetectGPT-style probability-curvature "
                    "adapted to chat-completion APIs. Naturalness ratings "
                    "are parsed from plain-text completions; no token "
                    "logprobs required."
                ),
                test_statistic=score,
                test_name="DetectGPT curvature (chat-API variant)",
                evidence={
                    "score": score,
                    "threshold_note": self.THRESHOLD_NOTE,
                    "threshold_suspicious": self.THRESHOLD_SUSPICIOUS,
                    "threshold_critical": self.THRESHOLD_CRITICAL,
                    "n_segments": len(diagnostics),
                    "k_perturbations": self.K_PERTURBATIONS,
                    "model": (
                        os.environ.get("PAPERGUARD_LLM_MODEL") or "default"
                    ),
                    "diagnostics": diagnostics,
                },
                innocent_explanations=[
                    "Professional English editing (common for non-native "
                    "authors) can place text close to LM-likelihood maxima "
                    "even when human-written.",
                    "Highly formulaic sections (Methods, Statistical "
                    "Analysis) sit near the manifold inherently.",
                    "The reference LM may be biased toward the manuscript's "
                    "domain — it will rate domain-typical text as natural "
                    "regardless of authorship.",
                    "DetectGPT is a *statistical* signal. The score depends "
                    "on the LM choice and the perturbation quality. Treat "
                    "as triage, not verdict — corroborate with T6 phrase "
                    "signal and editorial review.",
                ],
                academic_reference=self.academic_basis,
                applicability_notes=(
                    "Chat-API variant of the original white-box DetectGPT. "
                    "Output depends on the reference LM and the paraphraser; "
                    "thresholds are conservative defaults for GPT-4-class "
                    "models. Re-tune via T8DetectGPTDetector.THRESHOLD_* "
                    "for other LMs."
                ),
            )
        ]
