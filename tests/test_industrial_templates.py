"""Tests for the 12 industrial-domain templates."""
from __future__ import annotations

import pandas as pd
import pytest

from paperguard.detectors.i1_mass_balance import (
    I1MassBalanceDetector,
    MassBalanceInput,
)
from paperguard.detectors.i2_timestamp_integrity import (
    I2TimestampIntegrityDetector,
    TimestampIntegrityInput,
)
from paperguard.detectors.i5_batch_repetition import (
    BatchRepetitionInput,
    I5BatchRepetitionDetector,
)
from paperguard.industrial import (
    AGRICULTURE,
    BIOCOMPUTATION,
    BIOPHARMA,
    CHEMICAL,
    DISTILLERS_GRAIN,
    ENVIRONMENT,
    FOOD,
    MEDICAL,
    PHARMA,
    SEMICONDUCTOR,
    WASTE_GAS,
    WASTEWATER,
    DomainTemplate,
    get_template,
    list_domains,
)

ALL_TEMPLATES = [
    AGRICULTURE,
    BIOCOMPUTATION,
    BIOPHARMA,
    CHEMICAL,
    DISTILLERS_GRAIN,
    ENVIRONMENT,
    FOOD,
    MEDICAL,
    PHARMA,
    SEMICONDUCTOR,
    WASTE_GAS,
    WASTEWATER,
]


def test_12_domains_present() -> None:
    assert len(ALL_TEMPLATES) == 12
    names = list_domains()
    assert len(names) == 12
    for t in ALL_TEMPLATES:
        assert t.name in names


def test_get_template_known() -> None:
    t = get_template("pharma")
    assert t.name == "pharma"
    assert t.tolerance_pct == 0.5  # GMP is strictest


def test_get_template_unknown_raises() -> None:
    with pytest.raises(KeyError, match="Unknown industrial domain"):
        get_template("not_a_real_sector")


@pytest.mark.parametrize("template", ALL_TEMPLATES)
def test_each_template_has_required_fields(template: DomainTemplate) -> None:
    assert template.name
    assert template.description
    assert template.regulatory_frame
    assert template.sources, "every template needs ≥1 source"
    assert template.sinks, "every template needs ≥1 sink"
    assert template.tolerance_pct >= 0
    assert template.timestamp_column
    assert template.expected_dt_seconds > 0
    assert template.narrative_column
    assert template.id_column
    assert template.falsification_modes, "every template needs documented modes"


@pytest.mark.parametrize("template", ALL_TEMPLATES)
def test_each_template_builds_valid_inputs(
    template: DomainTemplate,
) -> None:
    # I1: a DataFrame with the template's expected columns
    cols = list(template.sources) + list(template.sinks)
    df = pd.DataFrame({c: [1.0] * 10 for c in cols})
    inp1 = template.mass_balance(df)
    assert isinstance(inp1, MassBalanceInput)
    det1 = I1MassBalanceDetector()
    ok, _ = det1.check_applicability(inp1)
    assert ok

    # I2: timestamp column
    df_ts = pd.DataFrame(
        {
            template.timestamp_column: pd.date_range(
                "2026-01-01",
                periods=50,
                freq=f"{int(template.expected_dt_seconds)}s",
            )
        }
    )
    inp2 = template.timestamp_integrity(df_ts)
    assert isinstance(inp2, TimestampIntegrityInput)
    det2 = I2TimestampIntegrityDetector()
    ok2, _ = det2.check_applicability(inp2)
    assert ok2

    # I5: narrative column + id column
    df_n = pd.DataFrame(
        {
            template.id_column: ["A", "B", "C"],
            template.narrative_column: [
                "Distinct narrative " + ("alpha " * 30),
                "Distinct narrative " + ("beta " * 30),
                "Distinct narrative " + ("gamma " * 30),
            ],
        }
    )
    inp3 = template.batch_repetition(df_n)
    assert isinstance(inp3, BatchRepetitionInput)
    det3 = I5BatchRepetitionDetector()
    ok3, _ = det3.check_applicability(inp3)
    assert ok3


def test_overrides_work() -> None:
    df = pd.DataFrame({
        "my_in": [10, 20, 30, 40, 50, 60],
        "my_out": [10, 20, 30, 40, 50, 60],
    })
    inp = WASTEWATER.mass_balance(
        df, sources=["my_in"], sinks=["my_out"], tolerance_pct=5.0
    )
    assert inp.sources == ["my_in"]
    assert inp.sinks == ["my_out"]
    assert inp.tolerance_pct == 5.0


def test_pharma_is_strictest() -> None:
    """GMP biopharma is structurally strictest."""
    assert PHARMA.tolerance_pct <= 0.5
    assert BIOPHARMA.tolerance_pct <= 0.5
    # Environment is loosest (annual reporting)
    assert ENVIRONMENT.tolerance_pct >= 5.0


def test_semiconductor_high_resolution() -> None:
    """1-Hz timestamp expectation for fab MFC logging."""
    assert SEMICONDUCTOR.expected_dt_seconds <= 5.0


def test_environment_long_period() -> None:
    """Environmental inventories tend to be annual."""
    assert ENVIRONMENT.expected_dt_seconds >= 86400.0


def test_distillers_grain_template_makes_sense() -> None:
    """User's own paper uses this domain; check the template
    captures the relevant streams."""
    assert "wet_grain_in_kg" in DISTILLERS_GRAIN.sources
    assert "dried_DDGS_kg" in DISTILLERS_GRAIN.sinks
    # tolerance is moderate (not GMP, not loose env)
    assert 1.0 <= DISTILLERS_GRAIN.tolerance_pct <= 5.0


def test_smoke_end_to_end_wastewater() -> None:
    """E2E: synthesize a tiny wastewater dataset, run the 3 detectors."""
    df = pd.DataFrame({
        "influent_COD_kg_day": [1000.0] * 20,
        "influent_BOD_kg_day": [500.0] * 20,
        "effluent_COD_kg_day": [200.0] * 20,
        "effluent_BOD_kg_day": [50.0] * 20,
        "sludge_COD_kg_day": [600.0] * 20,
        "co2_emitted_kg_day_C": [200.0] * 20,
    })
    result = I1MassBalanceDetector().detect(WASTEWATER.mass_balance(df))
    assert result.applicable
    # Balance: 1500 in vs 1050 out → 30% violation > 5% tolerance
    assert result.findings
    assert result.findings[0].severity.name in {
        "NOTE", "CONCERN", "SUSPICIOUS"
    }


def test_no_template_uses_verdict_words() -> None:
    """Privacy iron rule: even template metadata avoids verdict words."""
    forbidden = ("fraud", "fabrication", "misconduct", "造假", "cheating")
    for t in ALL_TEMPLATES:
        bag = (
            t.description + " "
            + t.regulatory_frame + " "
            + " ".join(t.falsification_modes)
        ).lower()
        for w in forbidden:
            assert w not in bag, (
                f"forbidden word {w!r} in template {t.name!r}"
            )
