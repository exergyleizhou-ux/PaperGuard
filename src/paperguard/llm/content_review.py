"""LLM-assisted manuscript content review (**opt-in**).

Where ``llm/explainer.py`` translates a detector Finding into lay
language *after the fact*, this module does the opposite: it reads
the manuscript text and asks the LLM to **flag passages that look
suspicious for documented reasons**.

The output is fed back as low-severity (NOTE / CONCERN) Findings.
The system prompt strictly limits the model to objective categories:

  - **arithmetic**: numbers in the text that obviously do not add up
  - **contradiction**: two passages saying directly opposite things
  - **missing**: claimed methodology / statistic / ethics statement
    that is referenced but not described
  - **implausible_precision**: numbers reported with more precision
    than the instrument or sample size could plausibly support
  - **stat_misuse**: a statistical test applied to the wrong kind of
    data (e.g. paired t-test on unpaired samples)

Things the LLM is **forbidden** from outputting:

  - "fraud", "fabrication", "misconduct" or any verdict word
  - opinions about author intent
  - new categories outside the list above
  - speculation without a quoted passage as evidence

The output is parsed as JSON. Any malformed response is dropped.
Failures are silent — main flow always continues.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

from paperguard.core.types import Finding, Severity

logger = logging.getLogger(__name__)

_CATEGORIES = {
    "arithmetic",
    "contradiction",
    "missing",
    "implausible_precision",
    "stat_misuse",
}

_SYSTEM_PROMPT = """You are a careful scientific-integrity reviewer.

You will receive a section of a manuscript. Your job is to identify
**at most 5** specific passages that fall into ONE of these categories:

- "arithmetic": numbers in the text that obviously do not add up
- "contradiction": two passages within this section saying directly
   opposite things
- "missing": a claimed methodology / statistic / ethics statement
   that is referenced but not described
- "implausible_precision": numbers reported with more precision than
   the instrument or sample size could plausibly support
- "stat_misuse": a statistical test applied to the wrong kind of
   data (e.g. paired t-test on independent samples)

You MUST:
- Return JSON with a single key "issues" whose value is a list (may
  be empty) of objects {"category": str, "passage": str, "explanation": str}
- Quote each "passage" verbatim from the input (≤ 200 characters)
- Keep "explanation" objective, ≤ 80 words
- Use only the 5 categories above
- Return {"issues": []} when nothing matches

You MUST NOT:
- Use the words "fraud", "fabrication", "misconduct", "造假"
- Make judgements about author intent
- Add categories outside the 5 above
- Quote passages not present in the input
- Output anything other than the JSON object
"""


@dataclass
class ContentIssue:
    category: str
    passage: str
    explanation: str


class LLMContentReviewer:
    """Opt-in LLM content reviewer. Returns ``None`` when not configured."""

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.provider = provider or os.environ.get("PAPERGUARD_LLM_PROVIDER")
        self.model = model or os.environ.get("PAPERGUARD_LLM_MODEL")
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self.provider)

    def review(self, text: str, max_chars: int = 8000) -> list[ContentIssue] | None:
        if not self.enabled:
            return None
        if not text or len(text) < 200:
            return []
        # Keep prompt bounded; LLM cost scales with length.
        text_excerpt = text[:max_chars]
        try:
            raw = self._call_provider(text_excerpt)
        except Exception as e:  # noqa: BLE001
            logger.warning("LLM content review failed: %s", e)
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        issues_raw = data.get("issues") if isinstance(data, dict) else None
        if not isinstance(issues_raw, list):
            return []
        out: list[ContentIssue] = []
        for item in issues_raw[:5]:
            if not isinstance(item, dict):
                continue
            cat = item.get("category", "")
            passage = item.get("passage", "")
            explanation = item.get("explanation", "")
            if cat not in _CATEGORIES:
                continue
            if not isinstance(passage, str) or not isinstance(explanation, str):
                continue
            if not passage or not explanation:
                continue
            # Guard rail: passage must actually appear in the text we
            # sent. Drops hallucinated quotes.
            if passage[:60] not in text_excerpt:
                continue
            out.append(
                ContentIssue(
                    category=cat,
                    passage=passage[:300],
                    explanation=explanation[:400],
                )
            )
        return out

    def _call_provider(self, text: str) -> str:
        if self.provider == "openai":
            return self._call_openai(text)
        if self.provider == "anthropic":
            return self._call_anthropic(text)
        if self.provider == "ollama":
            return self._call_ollama(text)
        raise ValueError(f"Unknown LLM provider: {self.provider}")

    def _call_openai(self, text: str) -> str:
        import httpx

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        # Custom base URL for proxy / team pool support. Defaults to
        # api.openai.com. Override with PAPERGUARD_LLM_BASE_URL.
        base_url = os.environ.get(
            "PAPERGUARD_LLM_BASE_URL", "https://api.openai.com/v1"
        ).rstrip("/")
        model = self.model or "gpt-4o-mini"
        payload: dict[str, object] = {
            "model": model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            "temperature": 0,
        }
        # Many proxies (CLI pools, OpenRouter, etc.) accept the
        # response_format field but the official API requires the
        # model to support it. Keep it on by default; drop it via
        # PAPERGUARD_LLM_NO_JSON_MODE for proxies that 400 on it.
        if os.environ.get("PAPERGUARD_LLM_NO_JSON_MODE", "").lower() not in {
            "1",
            "true",
            "yes",
        }:
            payload["response_format"] = {"type": "json_object"}
        r = httpx.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=self.timeout,
        )
        r.raise_for_status()
        content: str = r.json()["choices"][0]["message"]["content"]
        return content

    def _call_anthropic(self, text: str) -> str:
        import httpx

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        model = self.model or "claude-sonnet-4-6"
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 1500,
                "system": _SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": text}],
            },
            timeout=self.timeout,
        )
        r.raise_for_status()
        content: str = r.json()["content"][0]["text"]
        return content

    def _call_ollama(self, text: str) -> str:
        import httpx

        base = os.environ.get("OLLAMA_BASE", "http://localhost:11434")
        model = self.model or "llama3"
        r = httpx.post(
            f"{base}/api/chat",
            json={
                "model": model,
                "stream": False,
                "format": "json",
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
            },
            timeout=self.timeout,
        )
        r.raise_for_status()
        content: str = r.json()["message"]["content"]
        return content


def issues_to_findings(issues: list[ContentIssue]) -> list[Finding]:
    """Convert ContentIssue list to PaperGuard Finding list."""
    sev_map = {
        "arithmetic": Severity.SUSPICIOUS,
        "contradiction": Severity.SUSPICIOUS,
        "implausible_precision": Severity.CONCERN,
        "stat_misuse": Severity.CONCERN,
        "missing": Severity.CONCERN,
    }
    out: list[Finding] = []
    for issue in issues:
        sev = sev_map.get(issue.category, Severity.NOTE)
        out.append(
            Finding(
                detector_id="LLM_REVIEW",
                detector_name="LLM-Assisted Content Review",
                severity=sev,
                summary=(
                    f"LLM flagged a "
                    f"{issue.category.replace('_', ' ')} issue"
                ),
                detail=(
                    f"Category: {issue.category}\n"
                    f"Quoted passage: \"{issue.passage}\"\n\n"
                    f"LLM explanation:\n{issue.explanation}"
                ),
                evidence={
                    "category": issue.category,
                    "passage": issue.passage,
                    "llm_explanation": issue.explanation,
                    "review_source": "LLM (opt-in, PAPERGUARD_LLM_PROVIDER)",
                },
                innocent_explanations=[
                    "LLM judgement is not authoritative; verify the "
                    "quoted passage against the full context before "
                    "acting",
                    "Apparent contradictions may resolve under domain "
                    "knowledge the LLM lacks",
                    "Apparent precision issues may be appropriate for "
                    "the specific instrument or model used",
                    "Stat-misuse heuristics fail on study designs the "
                    "LLM hasn't seen many examples of",
                ],
                academic_reference=(
                    "Opt-in LLM review (PAPERGUARD_LLM_PROVIDER). System "
                    "prompt restricts the model to 5 objective issue "
                    "categories and forbids verdict language. Treat "
                    "findings as triage hints, not conclusions."
                ),
            )
        )
    return out
