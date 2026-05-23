"""G5 — reagent / equipment temporal consistency.

This detector flags one specific failure mode: the paper's Methods or
Materials section mentions a four-digit year that **postdates the
paper's own submission date**, in close proximity to a reagent /
equipment / catalog-number context. The paper cannot have used a
reagent released after the experiments it describes.

Inspired by the "试剂/设备型号是否存在" check from external
academic-integrity prompt skills (e.g. the geng-academic-fraud
checklist). Implemented as a precise textual signal rather than a
prompt because PaperGuard's design constraint is that every Finding
must point to specific bytes in the input — prompts cannot.

Scope (v1 — what this detector does)
-------------------------------------
- Input: paper text + paper publication / submission year.
- Output: NOTE-level Findings for each future-year mention that
  appears within a 60-character window of one of the configured
  reagent / equipment / catalog-context keywords.

What this detector **does not** do
----------------------------------
- It does **not** look up whether a given catalog number is real.
  That requires a vendor-catalog database (Sigma, Cell Signaling,
  ThermoFisher, etc.) and is out of scope for v1.
- It does **not** flag mentions of future years in non-reagent
  contexts (Introduction citations, Discussion of follow-up work).
- It does **not** claim a future-year mention is fraud. The Finding
  ships with four innocent explanations covering the most common
  benign causes.

Severity is intentionally capped at NOTE. A future-year reagent
citation is informative for a reviewer's attention; it is not by
itself evidence of misconduct. The intended use is multi-detector
co-firing — when G5 fires alongside G1 EXIF temporal, G4 file
metadata, or A3 inter-column arithmetic, the joint signal becomes
worth a closer look.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, ClassVar

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity

_REAGENT_CONTEXT_KEYWORDS: tuple[str, ...] = (
    # Catalog identifiers
    "catalog", "catalogue", "cat. no", "cat no", "cat#", "cat.#",
    "lot no", "lot#", "lot.#", "reorder",
    "part no", "part#",
    "manufacturer", "vendor", "supplier",
    # Reagent / antibody / equipment keywords
    "antibody", "antibodies", "monoclonal", "polyclonal", "clone",
    "primer", "primers",
    "reagent", "kit", "assay kit",
    "purchased from", "obtained from", "sourced from",
    "from sigma", "from millipore", "from invitrogen",
    "from thermo", "from thermofisher", "from cell signaling",
    "from abcam", "from biorad", "from bio-rad",
    "from agilent", "from qiagen", "from roche", "from idt",
    "from new england biolabs", "from neb",
    # Equipment vendor lines
    "instrument", "spectrometer", "microscope", "cytometer",
    "sequencer", "thermocycler", "imager", "centrifuge",
)


_YEAR_RE = re.compile(r"\b(19[0-9]{2}|20[0-9]{2}|21[0-9]{2})\b")
_WINDOW = 60  # characters on either side of the year mention


@dataclass
class ReagentTemporalInput:
    """Input contract: paper text + the paper's own year.

    ``paper_year`` is the paper's submission or publication year.
    Years strictly greater than this are flagged.
    """

    text: str
    paper_year: int


def _context_around(text: str, idx: int, length: int) -> str:
    """Return up to WINDOW chars before and after the year span."""
    start = max(0, idx - _WINDOW)
    end = min(len(text), idx + length + _WINDOW)
    return text[start:end]


class G5ReagentTemporalDetector(BaseDetector):
    """G5 — reagent/equipment cited with a year postdating the paper."""

    id: ClassVar[str] = "G5"
    name: ClassVar[str] = "Reagent / Equipment Temporal Consistency"
    description: ClassVar[str] = (
        "Flag reagent or equipment context near a four-digit year that "
        "is later than the paper's own submission / publication year."
    )
    academic_basis: ClassVar[str] = (
        "Folk-forensics check used by post-publication reviewers (see "
        "e.g. PubPeer threads on retracted Methods sections). No "
        "single canonical reference; the principle is physical "
        "impossibility — a paper cannot cite a reagent that did not "
        "exist when the experiments were run."
    )
    data_requirements: ClassVar[list[str]] = [
        "paper_text",
        "paper_year",
    ]
    assumption_cluster: ClassVar[str] = "metadata_forensics"

    def check_applicability(self, data: Any) -> tuple[bool, str]:
        if not isinstance(data, ReagentTemporalInput):
            return False, "Expected ReagentTemporalInput"
        if not data.text or not data.text.strip():
            return False, "Empty paper text"
        if data.paper_year < 1900 or data.paper_year > 2200:
            return False, f"Implausible paper_year={data.paper_year}"
        return True, ""

    def _detect(self, data: ReagentTemporalInput, seed: int) -> list[Finding]:
        findings: list[Finding] = []

        for m in _YEAR_RE.finditer(data.text):
            year = int(m.group(1))
            if year <= data.paper_year:
                continue
            ctx = _context_around(data.text, m.start(), len(m.group(1)))
            ctx_lower = ctx.lower()
            hit_keyword: str | None = next(
                (kw for kw in _REAGENT_CONTEXT_KEYWORDS if kw in ctx_lower),
                None,
            )
            if hit_keyword is None:
                continue
            findings.append(
                Finding(
                    detector_id=self.id,
                    detector_name=self.name,
                    severity=Severity.NOTE,
                    summary=(
                        f"Year {year} cited near reagent/equipment "
                        f"context, postdating paper_year={data.paper_year}."
                    ),
                    detail=(
                        f"Found year {year} (offset {m.start()} in text) "
                        f"within {_WINDOW} chars of the keyword "
                        f"{hit_keyword!r}. The paper itself is dated "
                        f"{data.paper_year}; a reagent or instrument "
                        f"released in {year} cannot have been used in "
                        f"experiments described by an earlier paper. "
                        f"Context excerpt: {ctx.strip()[:240]}..."
                    ),
                    evidence={
                        "year_cited": year,
                        "paper_year": data.paper_year,
                        "offset": m.start(),
                        "keyword": hit_keyword,
                        "context": ctx.strip()[:240],
                    },
                    innocent_explanations=[
                        "Reference list entry (review article published "
                        "after the paper) is being quoted by ID in a "
                        "Methods sentence, not the reagent itself.",
                        "The paper was revised after initial submission "
                        "and a newly-cited reagent was added in revision.",
                        "Year refers to an updated catalog version of an "
                        "older product whose original release predates the paper.",
                        "OCR / PDF text extraction error introduced a wrong digit.",
                    ],
                    academic_reference=self.academic_basis,
                )
            )

        return findings
