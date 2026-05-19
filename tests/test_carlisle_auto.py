"""Tests for Carlisle automation: multi-arm + auto-NCT + table parsing."""
from __future__ import annotations

from paperguard.detectors.c1_carlisle import (
    BaselineVariable,
    C1CarlisleDetector,
    CarlisleInput,
    _multi_arm_ps,
    _welch_pair,
)
from paperguard.extractor.baseline_tables import (
    _identify_arm_columns,
    _parse_categorical_row,
    _parse_continuous_row,
)
from paperguard.extractor.trial_ids import extract_trial_ids, find_nct_ids

# === Multi-arm C1 ===

def test_welch_pair_smoke() -> None:
    p = _welch_pair((30, 10.0, 2.0), (30, 12.0, 2.0))
    assert 0.0 < p < 1.0


def test_multi_arm_3_pairs() -> None:
    """3 arms → C(3,2) = 3 pairwise p-values."""
    v = BaselineVariable(
        name="x",
        arms=[
            (30, 10.0, 2.0),
            (30, 10.1, 2.0),
            (30, 9.9, 2.0),
        ],
    )
    ps = _multi_arm_ps(v)
    assert len(ps) == 3


def test_c1_multi_arm_overly_balanced() -> None:
    """3-arm with near-identical means → 应触发"""
    vars_ = [
        BaselineVariable(
            name=f"v{i}",
            arms=[(50, 10.0, 2.0), (50, 10.005, 2.0), (50, 9.998, 2.0)],
        )
        for i in range(8)
    ]
    inp = CarlisleInput(trial_id="T1", variables=vars_)
    result = C1CarlisleDetector().detect(inp, seed=42)
    assert result.applicable
    assert len(result.findings) >= 1


def test_c1_2_arm_still_works() -> None:
    """Backward compat: 旧 2-arm 字段方式仍可用。"""
    vars_ = [
        BaselineVariable(
            name=f"v{i}",
            n1=50, mean1=10.0, sd1=2.0,
            n2=50, mean2=10.01, sd2=2.0,
        )
        for i in range(8)
    ]
    inp = CarlisleInput(trial_id="T1", variables=vars_)
    result = C1CarlisleDetector().detect(inp, seed=42)
    assert result.applicable


# === Trial ID extraction ===

def test_extract_nct() -> None:
    text = "This trial is registered at ClinicalTrials.gov (NCT04123456)."
    ids = find_nct_ids(text)
    assert "NCT04123456" in ids


def test_extract_multiple_registries() -> None:
    text = (
        "Registered: NCT04123456, ISRCTN12345678, ChiCTR-INR-17012345, "
        "EudraCT 2020-001234-56, DRKS00012345."
    )
    ids = extract_trial_ids(text)
    assert any(t.startswith("NCT") for t in ids)
    assert any(t.startswith("ISRCTN") for t in ids)
    assert any(t.startswith("CHICTR") for t in ids)
    assert any(t.startswith("EUDRACT") for t in ids)
    assert any(t.startswith("DRKS") for t in ids)


def test_extract_dedup() -> None:
    text = "NCT04123456 appears twice in NCT04123456."
    ids = extract_trial_ids(text)
    assert ids.count("NCT04123456") == 1


def test_extract_no_match() -> None:
    assert extract_trial_ids("No trial IDs here.") == []


# === Baseline table parsing helpers ===

def test_identify_arm_columns_typical() -> None:
    header = ["Characteristic", "Treatment (n=50)", "Placebo (n=49)"]
    cols = _identify_arm_columns(header)
    assert cols == [1, 2]


def test_identify_arm_columns_three_arm() -> None:
    header = ["Variable", "Drug A", "Drug B", "Placebo"]
    cols = _identify_arm_columns(header)
    assert cols == [1, 2, 3]


def test_parse_continuous_row() -> None:
    row = ["Age (yrs)", "45.2 ± 12.3", "44.8 ± 11.9"]
    flat = _parse_continuous_row(row, arm_cols=[1, 2])
    assert flat == (45.2, 12.3, 44.8, 11.9)


def test_parse_continuous_row_paren() -> None:
    row = ["BMI", "27.1 (4.8)", "27.3 (5.1)"]
    flat = _parse_continuous_row(row, arm_cols=[1, 2])
    assert flat == (27.1, 4.8, 27.3, 5.1)


def test_parse_continuous_row_missing_returns_none() -> None:
    row = ["Sex", "Male", "Female"]
    flat = _parse_continuous_row(row, arm_cols=[1, 2])
    assert flat is None


def test_parse_categorical_row() -> None:
    row = ["Male", "25 (50.0%)", "23 (47.0%)"]
    cat = _parse_categorical_row(row, arm_cols=[1, 2])
    assert cat == [(25, 50.0), (23, 47.0)]
