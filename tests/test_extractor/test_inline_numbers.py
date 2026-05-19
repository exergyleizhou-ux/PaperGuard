"""inline 数字分类测试。"""
from __future__ import annotations

from paperguard.extractor.inline_numbers import classify_numbers


def test_p_values() -> None:
    text = "Reaction was significant (p=0.034) but post-hoc p < 0.001 and P=2.1e-4."
    out = classify_numbers(text)
    assert 0.034 in out["p_values"]
    assert 0.001 in out["p_values"]
    assert any(abs(v - 2.1e-4) < 1e-9 for v in out["p_values"])


def test_percentages() -> None:
    text = "Conversion improved by 23.5% (range 18% to 31.2 %)."
    out = classify_numbers(text)
    assert 23.5 in out["percentages"]
    assert 18.0 in out["percentages"]
    assert 31.2 in out["percentages"]


def test_mean_sd() -> None:
    text = "Mean OD was 2.31 ± 0.12 in treated samples and 1.87 ± 0.08 in controls."
    out = classify_numbers(text)
    assert 2.31 in out["mean_centers"]
    assert 0.12 in out["mean_sds"]
    assert 1.87 in out["mean_centers"]
    assert 0.08 in out["mean_sds"]


def test_general_decimals_avoid_double_classification() -> None:
    text = "Found 23.5% improvement, p=0.03, with mean 4.20 ± 0.15."
    out = classify_numbers(text)
    # 4.20 should be in mean_centers, not general_decimals
    assert 4.20 in out["mean_centers"]
    assert 4.20 not in out["general_decimals"]
    # 23.5 should be in percentages
    assert 23.5 in out["percentages"]
    assert 23.5 not in out["general_decimals"]
    # 0.03 should be in p_values
    assert 0.03 in out["p_values"]
    assert 0.03 not in out["general_decimals"]


def test_empty_text() -> None:
    out = classify_numbers("")
    for k in ("p_values", "percentages", "mean_centers", "mean_sds", "general_decimals"):
        assert out[k] == []
