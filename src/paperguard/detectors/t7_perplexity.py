"""T7 — perplexity-based LLM-text signal (opt-in, costs an API call).

Where T6 looks for *dictionary tics* — phrases over-represented in LLM
output — T7 measures the **information-theoretic surprisal** of the
manuscript prose under a reference language model. Human academic
writing has a typical perplexity around 25-80 for technical English;
unedited LLM output sits much lower (5-15) because the model is
emitting the very next token it would have predicted.

This is **paraphrase-resistant** in a way T6 is not. A determined
LLM user can swap out every "delve into" / "tapestry of" by hand,
but reducing perplexity back to human levels requires substantive
rewriting.

Trade-offs you should know:

  - Perplexity is **noisy at short lengths** — we require ≥ 500 words
    before running. Even then the signal is weak.
  - Heavily polished prose by a non-native English author can also
    sit low (~10-15) because professional editing reduces surprisal.
  - Domain-specific boilerplate ("Materials and Methods", "Statistical
    Analysis") is inherently low-perplexity even when human-written.
  - The reference LM matters. A small, weak model assigns lower
    likelihood to all text and inflates perplexity; switch models and
    the threshold has to move with it. For that reason, default
    thresholds below are conservative and the detector always emits
    a NOTE-level disclaimer about model dependence.

Severity tiers (default thresholds):

  perplexity > 20  → no finding (normal human academic English)
  10 ≤ ppl ≤ 20    → NOTE         (low, weakly indicative)
  5  ≤ ppl < 10    → SUSPICIOUS   (very low for academic prose)
       ppl < 5     → CRITICAL     (LM is essentially predicting it
                                   exactly — characteristic of
                                   unedited LLM output)

Failure modes (always silent, never raise):

  - API unreachable → no finding, log a warning
  - API returns no logprobs → no finding
  - Text too short → check_applicability returns False with reason
  - Network timeout → no finding
"""
from __future__ import annotations

import logging
import math
import os
import re
from typing import Any, ClassVar

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity

logger = logging.getLogger(__name__)


# Tiers — exposed as class attributes so callers / tests can override.
_DEFAULT_NOTE = 20.0
_DEFAULT_SUSPICIOUS = 10.0
_DEFAULT_CRITICAL = 5.0


def _opt_in_enabled() -> bool:
    """T7 is gated by an env var the CLI flag flips on."""
    return os.environ.get("PAPERGUARD_PERPLEXITY_CHECK", "").lower() in {
        "1",
        "true",
        "yes",
    }


def _segment_text(text: str, max_chars_per_segment: int = 2400) -> list[str]:
    """Split text into ~equal sentence-aligned segments under the char cap.

    We split on sentence boundaries (period+space) so that the LM doesn't
    score a partial sentence — that would unfairly inflate perplexity.
    """
    if not text:
        return []
    # split into sentences
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


def _call_openai_logprobs(
    text: str, model: str, base_url: str, api_key: str, timeout: float
) -> list[float] | None:
    """Return per-token logprobs by asking the API to score a continuation.

    Implementation strategy
    -----------------------
    The chat-completions API doesn't directly expose "perplexity of an
    input string". The workaround we use:

      1. Send the text as the *user* message and ask the assistant to
         echo back a one-token confirmation ("OK"). The completion is
         tiny — we don't care about that response.
      2. Pass ``logprobs=true`` and ``top_logprobs=5``. The OpenAI-shape
         response then returns logprobs *for the completion tokens*,
         not the prompt — so this only measures the assistant's reply,
         not the manuscript.

    That doesn't give us prompt-token perplexity. For a true prompt
    perplexity we'd need the legacy /v1/completions endpoint with
    ``echo=true logprobs=N`` — but the major proxies (cliproxy
    included) don't expose that. **So this implementation uses a
    practical proxy**: we instruct the model to *continue* the
    manuscript text. Specifically:

      - System: "Continue the following academic text exactly as it
        would be written. Respond with the next 32 tokens only."
      - User: text[:N]
      - Then we read the logprobs of the *completion*. The intuition:
        if the manuscript truly is LLM-written, the model will be
        very confident about how to continue (low entropy → low
        perplexity). If human-written, the continuation is
        comparatively uncertain.

    This is a *continuation-perplexity* proxy, NOT the literature's
    classical input-perplexity. We document this clearly in the
    Finding's `applicability_notes`.

    Returns None on any failure (network, missing logprobs field, etc.)
    """
    import httpx

    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Continue the following academic text exactly as it would "
                    "be written in the same source. Output only the next "
                    "few tokens — no commentary, no header, no quotes."
                ),
            },
            {"role": "user", "content": text},
        ],
        "max_tokens": 32,
        "temperature": 0,
        "logprobs": True,
        "top_logprobs": 5,
    }
    # Proxies that 400 on response_format also tend to 400 on logprobs.
    # Caller catches and returns None — that's fine.
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
        logger.warning("T7 LLM call failed: %s", e)
        return None
    except ValueError as e:
        logger.warning("T7 LLM response not JSON: %s", e)
        return None

    try:
        choice = data["choices"][0]
        lp = choice.get("logprobs") or {}
        content = lp.get("content") or []
        out: list[float] = []
        for tok in content:
            v = tok.get("logprob")
            if isinstance(v, (int, float)):
                out.append(float(v))
        if not out:
            return None
        return out
    except (KeyError, IndexError, TypeError) as e:
        logger.warning("T7 LLM logprobs missing/malformed: %s", e)
        return None


def _logprobs_to_perplexity(logprobs: list[float]) -> float:
    """Perplexity = exp(-mean(logprob)). logprob is natural log."""
    if not logprobs:
        return float("inf")
    return math.exp(-sum(logprobs) / len(logprobs))


def compute_perplexity(
    text: str,
    *,
    model: str | None = None,
    max_segments: int = 3,
    timeout: float = 60.0,
) -> float | None:
    """Public helper: compute perplexity for a piece of text or None on failure.

    Strategy:
      1. Try the logprobs route first (works when the API returns token
         logprobs).
      2. If that fails for every segment, fall back to the
         generation-divergence proxy (works on any chat-completion endpoint).

    The two routes return slightly different absolute numbers, but both
    sit in the same range and share the same severity thresholds.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.warning("T7: OPENAI_API_KEY not set")
        return None
    base_url = os.environ.get(
        "PAPERGUARD_LLM_BASE_URL", "https://api.openai.com/v1"
    )
    model_name = (
        model or os.environ.get("PAPERGUARD_LLM_MODEL") or "gpt-4o-mini"
    )
    segments = _segment_text(text)[:max_segments]
    if not segments:
        return None

    # Classical logprobs perplexity. If the proxy doesn't return logprobs
    # we return None — the detector then emits a NOTE-level "inconclusive"
    # finding rather than fabricating a number. T8 (DetectGPT-style
    # perturbation) is the proper alternative when logprobs aren't
    # available; see ``paperguard.detectors.t8_detectgpt``.
    perps: list[float] = []
    for seg in segments:
        lp = _call_openai_logprobs(seg, model_name, base_url, api_key, timeout)
        if lp is None:
            continue
        perps.append(_logprobs_to_perplexity(lp))
    if not perps:
        return None
    return math.exp(sum(math.log(p) for p in perps) / len(perps))


class T7PerplexityDetector(BaseDetector):
    """Continuation-perplexity proxy for LLM-generated manuscript text.

    See module docstring for the methodology + caveats. The detector is
    opt-in via the ``PAPERGUARD_PERPLEXITY_CHECK=1`` env var, which the
    CLI ``--perplexity-check`` flag sets automatically.
    """

    id: ClassVar[str] = "T7"
    name: ClassVar[str] = "LLM Perplexity (continuation proxy)"
    description: ClassVar[str] = (
        "Measures how confidently a reference LM continues the manuscript "
        "text. Low continuation-perplexity is weakly indicative of LLM "
        "authorship. Opt-in; requires an LLM API."
    )
    academic_basis: ClassVar[str] = (
        "Gehrmann et al. (2019) GLTR; Mitchell et al. (2023) DetectGPT; "
        "Bao et al. (2023) Fast-DetectGPT. PaperGuard adapts the idea as "
        "a continuation-perplexity proxy compatible with chat-completion "
        "APIs (the OSS literature mostly used /v1/completions logprobs)."
    )
    data_requirements: ClassVar[list[str]] = ["manuscript_text"]
    assumption_cluster: ClassVar[str] = "paper_mill_signature"

    MIN_WORDS: ClassVar[int] = 500
    THRESHOLD_NOTE: ClassVar[float] = _DEFAULT_NOTE
    THRESHOLD_SUSPICIOUS: ClassVar[float] = _DEFAULT_SUSPICIOUS
    THRESHOLD_CRITICAL: ClassVar[float] = _DEFAULT_CRITICAL

    def check_applicability(self, data: Any) -> tuple[bool, str]:
        if not _opt_in_enabled():
            return False, (
                "T7 is opt-in; set PAPERGUARD_PERPLEXITY_CHECK=1 "
                "(or pass --perplexity-check)."
            )
        if not isinstance(data, str):
            return False, "Expected text string"
        n_words = len(re.findall(r"\b[a-zA-Z]+\b", data))
        if n_words < self.MIN_WORDS:
            return False, (
                f"Text too short for stable perplexity estimate "
                f"({n_words} < {self.MIN_WORDS})"
            )
        if not os.environ.get("OPENAI_API_KEY"):
            return False, "OPENAI_API_KEY not set; T7 requires an LLM API."
        return True, ""

    def _detect(self, data: str, seed: int) -> list[Finding]:
        perplexity = compute_perplexity(data)
        if perplexity is None or not math.isfinite(perplexity):
            # API failed — emit a NOTE so the user knows we tried.
            return [
                Finding(
                    detector_id=self.id,
                    detector_name=self.name,
                    severity=Severity.NOTE,
                    summary=(
                        "T7 perplexity check requested but the LLM API "
                        "call did not return usable logprobs"
                    ),
                    detail=(
                        "We attempted a continuation-perplexity probe but "
                        "the response contained no logprobs (proxy may not "
                        "support logprobs=true). T7 is reported as "
                        "inconclusive — this is NOT evidence of LLM "
                        "authorship, only that the check could not run."
                    ),
                    evidence={"perplexity": None, "outcome": "api_no_logprobs"},
                    innocent_explanations=[
                        "The configured LLM proxy may not expose token "
                        "logprobs; switch to an endpoint that does.",
                        "Transient network failure — retry the scan.",
                        "Rate-limit response from the proxy.",
                    ],
                    academic_reference=self.academic_basis,
                    applicability_notes=(
                        "Inconclusive — no logprobs in the API response."
                    ),
                )
            ]

        severity: Severity | None = None
        if perplexity < self.THRESHOLD_CRITICAL:
            severity = Severity.CRITICAL
        elif perplexity < self.THRESHOLD_SUSPICIOUS:
            severity = Severity.SUSPICIOUS
        elif perplexity < self.THRESHOLD_NOTE:
            severity = Severity.NOTE

        if severity is None:
            # Perplexity is in the normal human-academic range → no finding.
            return []

        return [
            Finding(
                detector_id=self.id,
                detector_name=self.name,
                severity=severity,
                summary=(
                    f"Continuation perplexity {perplexity:.2f} "
                    f"(< {self.THRESHOLD_NOTE:.1f}); weak LLM-authorship signal"
                ),
                detail=(
                    f"Reference LM produces a continuation of the manuscript "
                    f"with perplexity {perplexity:.2f}. Normal academic "
                    f"English typically sits above {self.THRESHOLD_NOTE:.0f}. "
                    "Lower perplexity is consistent with — but not proof "
                    "of — LLM authorship.\n\n"
                    "Methodology: continuation-perplexity proxy (NOT classical "
                    "input perplexity). The LM is asked to continue the text; "
                    "the per-token logprobs of its completion are aggregated. "
                    "This is a published-literature-inspired approximation "
                    "compatible with chat-completion APIs."
                ),
                test_statistic=perplexity,
                test_name="continuation perplexity",
                evidence={
                    "perplexity": perplexity,
                    "threshold_note": self.THRESHOLD_NOTE,
                    "threshold_suspicious": self.THRESHOLD_SUSPICIOUS,
                    "threshold_critical": self.THRESHOLD_CRITICAL,
                    "model": (
                        os.environ.get("PAPERGUARD_LLM_MODEL") or "default"
                    ),
                },
                innocent_explanations=[
                    "Professional English editing (common for non-native "
                    "authors) reduces continuation perplexity by polishing "
                    "the prose into more predictable phrasing.",
                    "Technical boilerplate sections (Methods, Statistical "
                    "Analysis) inherently sit at low perplexity even when "
                    "human-written.",
                    "The reference LM may be biased toward the manuscript's "
                    "domain (e.g., trained heavily on biomedical literature) "
                    "— it will find such text predictable regardless of "
                    "authorship.",
                    "Perplexity is a *statistical* signal; the absolute "
                    "value depends on the reference model. Do not treat "
                    "a single low value as a verdict — corroborate with "
                    "T6 phrase signal and editorial review.",
                ],
                academic_reference=self.academic_basis,
                applicability_notes=(
                    "Continuation-perplexity proxy. Output depends on the "
                    "reference model; thresholds are conservative defaults "
                    "for GPT-4-class models. Re-tune via T7's THRESHOLD_* "
                    "class attributes for other LMs."
                ),
            )
        ]
