"""Auto-extract clinical-trial registration IDs from manuscript text."""
from __future__ import annotations

import re

_PATTERNS = (
    re.compile(r"\bNCT\d{8}\b"),                    # ClinicalTrials.gov
    re.compile(r"\bISRCTN\d{8}\b"),                  # ISRCTN
    re.compile(r"\bChiCTR-?[\w\d-]+\b"),              # 中国临床试验注册
    re.compile(r"\bACTRN\d{14}\b"),                  # ANZCTR
    re.compile(r"\bEudraCT\s*\d{4}-\d{6}-\d{2}\b"),  # EU CTR
    re.compile(r"\bDRKS\d{8}\b"),                    # German trials
)


def extract_trial_ids(text: str) -> list[str]:
    """Return unique trial-registration IDs found in `text`.

    Order-preserving deduplication.
    """
    seen: set[str] = set()
    out: list[str] = []
    for pat in _PATTERNS:
        for m in pat.finditer(text or ""):
            tid = m.group(0).upper().strip()
            if tid not in seen:
                seen.add(tid)
                out.append(tid)
    return out


def find_nct_ids(text: str) -> list[str]:
    """Convenience wrapper for the most common case (ClinicalTrials.gov)."""
    return [t for t in extract_trial_ids(text) if t.startswith("NCT")]
