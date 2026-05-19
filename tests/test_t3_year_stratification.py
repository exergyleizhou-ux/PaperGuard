"""T3 year-stratification regression tests (2.0.7).

The v5 recall study (docs/recall_test_v5.md, N=200) showed T3 fired
at 89% on the matched-control arm — driven mostly by older biomedical
papers that legitimately predate ICMJE's data-availability mandate
(2018) and pre-existed NCT registration (2005). 2.0.7 stratifies T3
severity by publication year so pre-policy papers don't get penalised
for not meeting policies that didn't exist yet.

Rules tested below:

- Data Availability statement missing:
    * year < 2018 → no finding (pre-mandate)
    * year >= 2018 OR year is None → CONCERN

- Clinical-trial paper missing trial registration:
    * year < 2005 → no finding (pre-NCT era)
    * 2005 <= year < 2010 → CONCERN (early ICMJE adoption period)
    * year >= 2010 OR year is None → SUSPICIOUS (strict period)
"""
from __future__ import annotations

import pytest

from paperguard.core.types import Severity
from paperguard.detectors.t3_data_availability import (
    DataAvailabilityInput,
    T3DataAvailabilityDetector,
)

_BARE_TEXT = (
    "Introduction. In this study we measured the response of "
    "cells to a treatment over multiple time points and quantified "
    "the resulting changes against a control. The results section "
    "reports each replicate and the discussion compares the findings "
    "to the existing literature. Methods. Standard protocols were "
    "applied throughout. We collected samples following the kit "
    "manufacturer's instructions. "
)


def _make_input(**kwargs):  # type: ignore[no-untyped-def]
    return DataAvailabilityInput(text=_BARE_TEXT, **kwargs)


def test_t3_das_pre_2018_silent() -> None:
    d = T3DataAvailabilityDetector()
    result = d.detect(_make_input(paper_year=2010), seed=42)
    das_findings = [
        f for f in result.findings if "Data Availability" in f.summary
    ]
    assert das_findings == []


def test_t3_das_2018_plus_concerns() -> None:
    d = T3DataAvailabilityDetector()
    result = d.detect(_make_input(paper_year=2020), seed=42)
    das_findings = [
        f for f in result.findings if "Data Availability" in f.summary
    ]
    assert len(das_findings) == 1
    assert das_findings[0].severity == Severity.CONCERN


def test_t3_das_year_unknown_concerns() -> None:
    d = T3DataAvailabilityDetector()
    result = d.detect(_make_input(paper_year=None), seed=42)
    das_findings = [
        f for f in result.findings if "Data Availability" in f.summary
    ]
    assert len(das_findings) == 1


def test_t3_trial_pre_2005_silent() -> None:
    d = T3DataAvailabilityDetector()
    result = d.detect(
        _make_input(is_clinical_trial=True, paper_year=2002), seed=42
    )
    trial_findings = [f for f in result.findings if "临床试验" in f.summary]
    assert trial_findings == []


def test_t3_trial_2005_to_2009_concerns() -> None:
    d = T3DataAvailabilityDetector()
    result = d.detect(
        _make_input(is_clinical_trial=True, paper_year=2007), seed=42
    )
    trial_findings = [f for f in result.findings if "临床试验" in f.summary]
    assert len(trial_findings) == 1
    assert trial_findings[0].severity == Severity.CONCERN
    assert trial_findings[0].evidence.get("severity_tier") == "early"


def test_t3_trial_2010_plus_suspicious() -> None:
    d = T3DataAvailabilityDetector()
    result = d.detect(
        _make_input(is_clinical_trial=True, paper_year=2018), seed=42
    )
    trial_findings = [f for f in result.findings if "临床试验" in f.summary]
    assert len(trial_findings) == 1
    assert trial_findings[0].severity == Severity.SUSPICIOUS
    assert trial_findings[0].evidence.get("severity_tier") == "strict"


def test_t3_trial_year_unknown_suspicious() -> None:
    d = T3DataAvailabilityDetector()
    result = d.detect(
        _make_input(is_clinical_trial=True, paper_year=None), seed=42
    )
    trial_findings = [f for f in result.findings if "临床试验" in f.summary]
    assert len(trial_findings) == 1
    assert trial_findings[0].severity == Severity.SUSPICIOUS


@pytest.mark.parametrize("year", [1995, 1999, 2004])
def test_t3_pre_policy_papers_silent_on_year_rules(year: int) -> None:
    """Pre-2005 papers should emit zero year-gated findings (DAS + trial).

    A NOTE-level "no COI" finding may still fire — that's not year-gated
    and is intentionally always-on regardless of publication year.
    """
    d = T3DataAvailabilityDetector()
    result = d.detect(
        _make_input(is_clinical_trial=True, paper_year=year), seed=42
    )
    year_gated = [
        f
        for f in result.findings
        if "Data Availability" in f.summary or "临床试验" in f.summary
    ]
    assert year_gated == []


def test_t3_2017_paper_das_silent_but_trial_strict() -> None:
    d = T3DataAvailabilityDetector()
    result = d.detect(
        _make_input(is_clinical_trial=True, paper_year=2017), seed=42
    )
    das = [f for f in result.findings if "Data Availability" in f.summary]
    trial = [f for f in result.findings if "临床试验" in f.summary]
    assert das == []
    assert len(trial) == 1
    assert trial[0].severity == Severity.SUSPICIOUS
