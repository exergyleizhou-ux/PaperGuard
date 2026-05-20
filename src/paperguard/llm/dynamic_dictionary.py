"""T6 dynamic dictionary — refresh + merge AI-style phrase lists from sources
outside the hardcoded built-in lists.

Motivation
----------
The T6 detector ships a hardcoded snapshot of LLM-overused phrases (Kobak
2025, Cabanac 2024, our own observations). That snapshot ages: GPT-5 and
Claude 4.x add new tics every quarter. This module lets a user refresh
the dictionary without waiting for a PaperGuard release.

Design
------
- A user dictionary lives at ``~/.paperguard/ai_dictionary.json``.
- It is keyed by provider ("gpt" / "claude" / "gemini" / "other"); the
  T6 detector merges built-in + user phrases at load time.
- Refresh sources:
    1. ``--source URL``: a JSON file shaped
       ``{"gpt": [...], "claude": [...], ...}``. Trivial to host.
    2. ``--corpus PATH``: a local text file presumed to be LLM output.
       Extracts 2- to 4-grams that appear above a baseline frequency.
- On every refresh we compute the set diff vs the current state and
  log what was added / removed.
- All network operations have short timeouts; failures fall back to the
  built-in list silently (the detector never breaks).

The user dictionary is **additive** — it never deletes built-in
phrases. That keeps test fixtures and recall numbers reproducible.
"""
from __future__ import annotations

import json
import logging
import os
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DICTIONARY_VERSION = 1
PROVIDERS = ("gpt", "claude", "gemini", "other")

# Baseline N-gram frequencies from a corpus of N=200 human-written
# Nature/Science abstracts (2010-2018, pre-LLM era). These are used
# to filter "common English" out of corpus-derived candidates. The
# numbers are per-million-tokens. Values below are conservative
# upper bounds — anything appearing more frequently than this in
# normal academic English is filtered out as not a useful LLM signal.
_HUMAN_BASELINE_PER_MILLION: dict[str, float] = {
    # very common phrases — filter aggressively
    "in the": 8000.0,
    "of the": 9000.0,
    "to the": 4000.0,
    "and the": 3500.0,
    "for the": 2500.0,
    "with the": 2000.0,
    "on the": 2000.0,
    "is the": 1500.0,
    "by the": 1500.0,
    "from the": 1500.0,
    "of a": 1500.0,
    "to be": 1000.0,
    "we have": 600.0,
    "we used": 400.0,
    "in this": 800.0,
    "this study": 300.0,
    "in our": 200.0,
}


def _default_dictionary_path() -> Path:
    base = os.environ.get("PAPERGUARD_HOME")
    if base:
        return Path(base) / "ai_dictionary.json"
    return Path.home() / ".paperguard" / "ai_dictionary.json"


@dataclass
class DictionarySnapshot:
    """On-disk shape of the user dictionary."""

    version: int = DICTIONARY_VERSION
    generated_at: str = ""
    source: str = ""
    phrases: dict[str, list[str]] = field(default_factory=dict)

    def normalise(self) -> None:
        """Ensure every provider key exists and phrases are deduped + sorted."""
        for provider in PROVIDERS:
            raw = self.phrases.get(provider, []) or []
            cleaned = sorted({p.strip().lower() for p in raw if p and p.strip()})
            self.phrases[provider] = cleaned

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class DictionaryDiff:
    """Set diff between two snapshots, per provider."""

    added: dict[str, list[str]] = field(default_factory=dict)
    removed: dict[str, list[str]] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not any(self.added.values()) and not any(self.removed.values())

    def summary_lines(self) -> list[str]:
        out: list[str] = []
        for provider in PROVIDERS:
            a = self.added.get(provider, [])
            r = self.removed.get(provider, [])
            if not a and not r:
                continue
            out.append(f"  {provider}: +{len(a)} new, -{len(r)} removed")
            for phrase in a[:8]:
                out.append(f"    + {phrase!r}")
            for phrase in r[:8]:
                out.append(f"    - {phrase!r}")
        if not out:
            out.append("  (no changes)")
        return out


def load_user_dictionary(path: Path | None = None) -> DictionarySnapshot:
    """Read the user dictionary from disk. Returns an empty snapshot
    if the file does not exist or is malformed.
    """
    p = path or _default_dictionary_path()
    if not p.exists():
        return DictionarySnapshot()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("user dictionary at %s unreadable: %s", p, e)
        return DictionarySnapshot()
    if not isinstance(raw, dict):
        return DictionarySnapshot()
    phrases_raw = raw.get("phrases", {})
    if not isinstance(phrases_raw, dict):
        phrases_raw = {}
    phrases: dict[str, list[str]] = {}
    for provider in PROVIDERS:
        v = phrases_raw.get(provider, [])
        if isinstance(v, list):
            phrases[provider] = [str(x) for x in v if isinstance(x, str)]
        else:
            phrases[provider] = []
    snap = DictionarySnapshot(
        version=int(raw.get("version", DICTIONARY_VERSION)),
        generated_at=str(raw.get("generated_at", "")),
        source=str(raw.get("source", "")),
        phrases=phrases,
    )
    snap.normalise()
    return snap


def save_user_dictionary(snap: DictionarySnapshot, path: Path | None = None) -> Path:
    """Write the snapshot to disk, creating parent directories as needed."""
    p = path or _default_dictionary_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    snap.normalise()
    if not snap.generated_at:
        snap.generated_at = datetime.now(UTC).isoformat()
    p.write_text(json.dumps(snap.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def diff_snapshots(
    old: DictionarySnapshot, new: DictionarySnapshot
) -> DictionaryDiff:
    diff = DictionaryDiff()
    for provider in PROVIDERS:
        old_set = set(old.phrases.get(provider, []))
        new_set = set(new.phrases.get(provider, []))
        added = sorted(new_set - old_set)
        removed = sorted(old_set - new_set)
        if added:
            diff.added[provider] = added
        if removed:
            diff.removed[provider] = removed
    return diff


# ---------------------------------------------------------------------------
# Refresh sources
# ---------------------------------------------------------------------------


def refresh_from_url(
    url: str, timeout: float = 30.0
) -> DictionarySnapshot:
    """Fetch a JSON document at *url* shaped like a DictionarySnapshot.

    Expected JSON:
        {"phrases": {"gpt": [...], "claude": [...], "gemini": [...], "other": [...]}}

    Top-level keys ``version`` / ``generated_at`` / ``source`` are optional.

    Raises:
        RuntimeError on network failure or non-JSON response.
    """
    import httpx

    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True)
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPError as e:
        raise RuntimeError(f"network fetch failed: {e}") from e
    except json.JSONDecodeError as e:
        raise RuntimeError(f"response was not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise RuntimeError("dictionary JSON must be an object at top level")

    phrases_raw = data.get("phrases", {})
    if not isinstance(phrases_raw, dict):
        raise RuntimeError("'phrases' must be an object keyed by provider")

    phrases: dict[str, list[str]] = {}
    for provider in PROVIDERS:
        v = phrases_raw.get(provider, [])
        if isinstance(v, list):
            phrases[provider] = [str(x) for x in v if isinstance(x, str)]
        else:
            phrases[provider] = []

    snap = DictionarySnapshot(
        version=int(data.get("version", DICTIONARY_VERSION)),
        generated_at=str(data.get("generated_at", datetime.now(UTC).isoformat())),
        source=str(data.get("source", url)),
        phrases=phrases,
    )
    snap.normalise()
    return snap


_TOKEN_RE = re.compile(r"\b[a-zA-Z]{2,}\b")


def _ngrams(words: list[str], n: int) -> Iterable[str]:
    for i in range(len(words) - n + 1):
        yield " ".join(words[i : i + n])


def extract_candidate_phrases(
    corpus_text: str,
    *,
    n_range: tuple[int, int] = (2, 4),
    min_count: int = 3,
    min_per_million: float = 200.0,
) -> list[str]:
    """Extract N-gram candidates from a corpus of suspected LLM output.

    Heuristic:
      - Lowercase, tokenize on word boundaries.
      - For each n in n_range, count n-gram frequency.
      - Keep phrases that:
          * appear >= min_count times
          * are above min_per_million tokens/million in the corpus
          * are NOT in the human-baseline list at higher freq
      - Strip stopword-only sequences ("of the", "in the", ...).
    """
    words = [w.lower() for w in _TOKEN_RE.findall(corpus_text or "")]
    if not words:
        return []
    total = len(words)
    candidates: dict[str, int] = {}
    for n in range(n_range[0], n_range[1] + 1):
        counter = Counter(_ngrams(words, n))
        for phrase, count in counter.items():
            if count < min_count:
                continue
            per_million = count / total * 1_000_000
            if per_million < min_per_million:
                continue
            # filter dominantly-stopword phrases
            human_base = _HUMAN_BASELINE_PER_MILLION.get(phrase)
            if human_base and per_million < human_base * 2:
                continue
            # crude stopword check — at least one token must be content-bearing
            content_tokens = [
                t
                for t in phrase.split()
                if t not in _STOPWORDS
            ]
            if not content_tokens:
                continue
            candidates[phrase] = max(candidates.get(phrase, 0), count)

    return sorted(candidates.keys())


_STOPWORDS: set[str] = {
    "a", "an", "the", "of", "in", "on", "at", "to", "by", "for", "from",
    "is", "are", "was", "were", "be", "been", "being",
    "and", "or", "but", "if", "as", "with", "without",
    "this", "that", "these", "those",
    "we", "our", "us", "you", "your", "i", "me",
    "it", "its", "their", "they",
    "have", "has", "had",
}


def refresh_from_corpus(
    corpus_text: str,
    *,
    provider: str = "other",
    min_count: int = 3,
    min_per_million: float = 200.0,
) -> DictionarySnapshot:
    """Build a snapshot from a single corpus, assigning all candidates to
    one provider bucket (default ``"other"``).
    """
    if provider not in PROVIDERS:
        raise ValueError(f"provider must be one of {PROVIDERS}, got {provider!r}")
    phrases = extract_candidate_phrases(
        corpus_text, min_count=min_count, min_per_million=min_per_million
    )
    snap = DictionarySnapshot(
        version=DICTIONARY_VERSION,
        generated_at=datetime.now(UTC).isoformat(),
        source="corpus",
        phrases={p: [] for p in PROVIDERS},
    )
    snap.phrases[provider] = phrases
    snap.normalise()
    return snap


def merge_snapshots(
    base: DictionarySnapshot, *others: DictionarySnapshot
) -> DictionarySnapshot:
    """Union-merge snapshots. The *base* metadata is preserved."""
    merged = DictionarySnapshot(
        version=base.version,
        generated_at=base.generated_at or datetime.now(UTC).isoformat(),
        source=base.source,
        phrases={p: list(base.phrases.get(p, [])) for p in PROVIDERS},
    )
    for other in others:
        for provider in PROVIDERS:
            merged.phrases[provider].extend(other.phrases.get(provider, []))
    merged.normalise()
    return merged


# ---------------------------------------------------------------------------
# T6 integration: merged-phrase loader
# ---------------------------------------------------------------------------


def get_merged_phrases(
    builtin: dict[str, tuple[str, ...]],
    path: Path | None = None,
) -> dict[str, tuple[str, ...]]:
    """Return ``{provider: tuple-of-phrases}`` with built-in + user phrases.

    The detector calls this once per process. Built-in phrases retain
    their original casing; user phrases are appended lowercase. The T6
    regex is case-insensitive, so casing differences are inert.
    """
    snap = load_user_dictionary(path)
    out: dict[str, tuple[str, ...]] = {}
    for provider, base_list in builtin.items():
        user_extra = snap.phrases.get(provider, [])
        # dedupe case-insensitively while preserving original built-in order
        seen_lower = {p.lower() for p in base_list}
        extras = [p for p in user_extra if p.lower() not in seen_lower]
        out[provider] = tuple(base_list) + tuple(extras)
    return out
