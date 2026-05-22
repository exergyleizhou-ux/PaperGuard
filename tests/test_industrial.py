"""Tests for the 2.2.0 industrial detector pack (I1 / I2 / I5)."""
from __future__ import annotations

import pandas as pd

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
    _jaccard,
    _ngram_set,
)

# ---------------------------------------------------------------------------
# I1 — Mass balance
# ---------------------------------------------------------------------------


def _balance_df(violations: int = 0, n: int = 20) -> pd.DataFrame:
    """Build a synthetic batch log where sources ≈ sinks ± noise."""
    import numpy as np

    rng = np.random.default_rng(42)
    feed_a = rng.uniform(50, 100, n)
    feed_b = rng.uniform(10, 30, n)
    sources_total = feed_a + feed_b
    # 0.3% noise on sinks (within 1% tolerance)
    sinks_total = sources_total * (1 + rng.normal(0, 0.003, n))
    product = sinks_total * 0.8
    waste = sinks_total - product
    df = pd.DataFrame({
        "feed_A_kg": feed_a,
        "feed_B_kg": feed_b,
        "product_kg": product,
        "waste_kg": waste,
    })
    # Force a few rows to violate the balance hard
    for i in range(violations):
        df.at[i, "product_kg"] *= 0.5  # cut product by half — big violation
    return df


def test_i1_clean_data_no_finding() -> None:
    det = I1MassBalanceDetector()
    inp = MassBalanceInput(
        df=_balance_df(violations=0),
        sources=["feed_A_kg", "feed_B_kg"],
        sinks=["product_kg", "waste_kg"],
        tolerance_pct=1.0,
    )
    result = det.detect(inp)
    assert result.applicable
    assert result.findings == []


def test_i1_many_violations_fires_suspicious() -> None:
    det = I1MassBalanceDetector()
    inp = MassBalanceInput(
        df=_balance_df(violations=8, n=20),  # 40 % violators
        sources=["feed_A_kg", "feed_B_kg"],
        sinks=["product_kg", "waste_kg"],
        tolerance_pct=1.0,
    )
    result = det.detect(inp)
    assert result.applicable
    assert result.findings
    assert result.findings[0].severity.name in {"SUSPICIOUS", "CONCERN"}


def test_i1_negative_value_fires_critical() -> None:
    df = _balance_df(violations=0, n=20)
    df.at[0, "product_kg"] = -1.0   # physically impossible
    det = I1MassBalanceDetector()
    inp = MassBalanceInput(
        df=df,
        sources=["feed_A_kg", "feed_B_kg"],
        sinks=["product_kg", "waste_kg"],
        tolerance_pct=1.0,
    )
    result = det.detect(inp)
    assert result.findings
    severities = {f.severity.name for f in result.findings}
    assert "CRITICAL" in severities


def test_i1_missing_column_not_applicable() -> None:
    det = I1MassBalanceDetector()
    df = _balance_df(0)
    inp = MassBalanceInput(
        df=df,
        sources=["feed_A_kg", "NOT_THERE"],
        sinks=["product_kg"],
    )
    ok, reason = det.check_applicability(inp)
    assert ok is False
    assert "missing" in reason


def test_i1_innocent_explanations_count() -> None:
    det = I1MassBalanceDetector()
    inp = MassBalanceInput(
        df=_balance_df(violations=8),
        sources=["feed_A_kg", "feed_B_kg"],
        sinks=["product_kg", "waste_kg"],
        tolerance_pct=1.0,
    )
    result = det.detect(inp)
    for f in result.findings:
        assert len(f.innocent_explanations) >= 4


# ---------------------------------------------------------------------------
# I2 — Timestamp integrity
# ---------------------------------------------------------------------------


def _good_ts_df(n: int = 100, dt_s: float = 1.0) -> pd.DataFrame:
    base = pd.Timestamp("2026-05-22 09:00:00.123")
    return pd.DataFrame(
        {"timestamp": [base + pd.Timedelta(seconds=i * dt_s) for i in range(n)]}
    )


def test_i2_clean_data_no_finding() -> None:
    det = I2TimestampIntegrityDetector()
    inp = TimestampIntegrityInput(df=_good_ts_df(100, 1.0))
    result = det.detect(inp)
    assert result.applicable
    assert result.findings == []


def test_i2_backwards_jump_fires_suspicious() -> None:
    df = _good_ts_df(50, 1.0)
    df.at[25, "timestamp"] = df.at[10, "timestamp"]   # back-dated row
    det = I2TimestampIntegrityDetector()
    result = det.detect(TimestampIntegrityInput(df=df))
    assert result.findings
    assert any(f.severity.name == "SUSPICIOUS" for f in result.findings)


def test_i2_round_minute_clustering_fires() -> None:
    """Hand-entered batch log with HH:MM:00 timestamps."""
    base = pd.Timestamp("2026-05-22 09:00:00")
    df = pd.DataFrame(
        {"timestamp": [base + pd.Timedelta(seconds=i * 30) for i in range(40)]}
    )
    # Force every other row to land on exact minute (no fractional second)
    for i in range(0, 40, 2):
        df.at[i, "timestamp"] = df.at[i, "timestamp"].replace(second=0)
    inp = TimestampIntegrityInput(df=df, expected_dt_seconds=30.0)
    result = I2TimestampIntegrityDetector().detect(inp)
    # 50%+ round-minute → SUSPICIOUS
    severities = {f.severity.name for f in result.findings}
    assert "SUSPICIOUS" in severities or "CONCERN" in severities


def test_i2_short_input_not_applicable() -> None:
    det = I2TimestampIntegrityDetector()
    df = _good_ts_df(5, 1.0)
    ok, _ = det.check_applicability(TimestampIntegrityInput(df=df))
    assert ok is False


def test_i2_innocent_explanations_count() -> None:
    df = _good_ts_df(50, 1.0)
    df.at[25, "timestamp"] = df.at[10, "timestamp"]
    det = I2TimestampIntegrityDetector()
    result = det.detect(TimestampIntegrityInput(df=df))
    for f in result.findings:
        assert len(f.innocent_explanations) >= 3


# ---------------------------------------------------------------------------
# I5 — Batch-log repetition
# ---------------------------------------------------------------------------


def test_i5_jaccard_identical() -> None:
    a = _ngram_set("the quick brown fox jumps over the lazy dog", 4)
    assert _jaccard(a, a) == 1.0


def test_i5_jaccard_disjoint() -> None:
    a = _ngram_set("alpha beta gamma delta epsilon zeta", 4)
    b = _ngram_set("xenon yarrow zeppelin orange purple lemon", 4)
    assert _jaccard(a, b) == 0.0


def test_i5_copy_paste_fires() -> None:
    narr_template = (
        "Batch reactor charged at 9 AM. Heated to 70 C with continuous "
        "stirring at 300 rpm. Catalyst added after temperature stabilised. "
        "Reaction proceeded for 4 hours without deviation. Product was "
        "transferred to the storage tank and sampled for QC analysis. "
        "All readings within spec, no further action required."
    )
    df = pd.DataFrame({
        "batch_id": ["B-001", "B-002", "B-003"],
        "narrative": [narr_template] * 3,
    })
    inp = BatchRepetitionInput(
        df=df, text_column="narrative", id_column="batch_id"
    )
    result = I5BatchRepetitionDetector().detect(inp)
    assert result.findings
    assert result.findings[0].severity.name == "CRITICAL"


def test_i5_distinct_narratives_no_finding() -> None:
    df = pd.DataFrame({
        "batch_id": ["B-001", "B-002", "B-003"],
        "narrative": [
            "Batch reactor A. Charged 50 kg phenol and 22 kg catalyst. "
            "Reaction temperature climbed to 78 C peak. Sampled at hour 3. "
            "QC shows 97 % conversion. Transferred to tank T-12 at 14:30. "
            "Operator J. Patel, supervisor M. Chen.",
            "Reactor B operation. Initial charge 60 kg salicylic acid "
            "with 18 kg propionic anhydride. Heated to 82 C and held "
            "for 5 hours. Cooled to 25 C and crystallised in vessel V-3. "
            "Filter cake 41 kg, mother liquor recycled. Operator R. Singh.",
            "Distillation column run on stream 04A. Feed rate 120 kg/h "
            "at 90 C and 1.2 bar reflux. Top product purity 99.4 % by GC, "
            "bottom waste 0.6 % impurity. Energy 14.5 GJ. Operator C. Lee, "
            "no deviation reported. Run terminated at 22:30.",
        ],
    })
    inp = BatchRepetitionInput(
        df=df, text_column="narrative", id_column="batch_id"
    )
    result = I5BatchRepetitionDetector().detect(inp)
    assert result.findings == []


def test_i5_innocent_explanations_count() -> None:
    df = pd.DataFrame({
        "batch_id": ["B-001", "B-002", "B-003"],
        "narrative": ["Identical narrative pasted across batch records " * 10] * 3,
    })
    inp = BatchRepetitionInput(df=df, text_column="narrative", id_column="batch_id")
    result = I5BatchRepetitionDetector().detect(inp)
    for f in result.findings:
        assert len(f.innocent_explanations) >= 4


def test_i5_short_narrative_excluded() -> None:
    df = pd.DataFrame({
        "batch_id": ["B-001", "B-002"],
        "narrative": ["short", "also short"],
    })
    inp = BatchRepetitionInput(df=df, text_column="narrative")
    result = I5BatchRepetitionDetector().detect(inp)
    assert result.findings == []


# ---------------------------------------------------------------------------
# Privacy iron rule (cross-detector)
# ---------------------------------------------------------------------------


def test_industrial_no_verdict_words() -> None:
    forbidden = ("fraud", "fabrication", "misconduct", "造假", "cheating")

    # I1
    inp1 = MassBalanceInput(
        df=_balance_df(violations=8),
        sources=["feed_A_kg", "feed_B_kg"],
        sinks=["product_kg", "waste_kg"],
    )
    r1 = I1MassBalanceDetector().detect(inp1)

    # I2
    df_ts = _good_ts_df(50, 1.0)
    df_ts.at[25, "timestamp"] = df_ts.at[10, "timestamp"]
    r2 = I2TimestampIntegrityDetector().detect(TimestampIntegrityInput(df=df_ts))

    # I5
    df_n = pd.DataFrame({
        "batch_id": ["A", "B"],
        "narrative": ["Identical narrative " * 30, "Identical narrative " * 30],
    })
    r5 = I5BatchRepetitionDetector().detect(
        BatchRepetitionInput(df=df_n, text_column="narrative", id_column="batch_id")
    )

    for r in (r1, r2, r5):
        for f in r.findings:
            bag = (
                f.summary + " " + f.detail + " " + " ".join(f.innocent_explanations)
            ).lower()
            for w in forbidden:
                assert w not in bag, (
                    f"forbidden word {w!r} in {f.detector_id}: {bag[:100]}"
                )
