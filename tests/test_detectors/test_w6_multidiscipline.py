"""W6 — B4 statcheck multi-discipline format tests."""
from __future__ import annotations

from scipy import stats

from paperguard.detectors.b4_statcheck import B4StatcheckDetector, _extract_matches

# --- R² / r² regression format (chemistry / materials) ---


def test_r2_extraction_basic() -> None:
    """r² = 0.85, n = 30, p = 0.001 should be extracted as r2 type."""
    text = "The correlation was r² = 0.85, n = 30, p = 0.001."
    matches = _extract_matches(text)
    r2_matches = [m for m in matches if m.test_type == "r2"]
    assert len(r2_matches) == 1
    assert r2_matches[0].reported_stat == 0.85
    assert r2_matches[0].df1 == 30  # n stored in df1


def test_r2_uppercase() -> None:
    """R² = 0.72, N = 45, P < 0.05 (uppercase) should also match."""
    text = "Model fit: R² = 0.72, N = 45, P < 0.05."
    matches = _extract_matches(text)
    r2_matches = [m for m in matches if m.test_type == "r2"]
    assert len(r2_matches) == 1
    assert r2_matches[0].reported_stat == 0.72


def test_r2_consistent() -> None:
    """r² = 0.50, n = 22 → F(1,20) = 20.0 → p ≈ 0.000258; report consistent."""
    f_stat = (0.5 / 1.0) / ((1.0 - 0.5) / (22 - 2))
    true_p = 1 - stats.f.cdf(f_stat, 1, 20)
    text = f"Regression: r² = 0.50, n = 22, p = {true_p:.4f}."
    result = B4StatcheckDetector().detect(text, seed=42)
    r2_findings = [
        f for f in result.findings
        if f.evidence.get("test_type") == "r2"
    ]
    assert len(r2_findings) == 0  # consistent → no finding


def test_r2_inconsistent() -> None:
    """r² = 0.10, n = 20 → true p ≈ 0.175; reported p = 0.001 → flagged."""
    text = "Linear regression: r² = 0.10, n = 20, p = 0.001."
    result = B4StatcheckDetector().detect(text, seed=42)
    r2_findings = [
        f for f in result.findings
        if f.evidence.get("test_type") == "r2"
    ]
    assert len(r2_findings) >= 1


def test_r2_caret_notation() -> None:
    """R^2 = 0.65, n = 40 should match the caret notation."""
    text = "Model R^2 = 0.65, n = 40, p = 0.001."
    matches = _extract_matches(text)
    r2_matches = [m for m in matches if m.test_type == "r2"]
    assert len(r2_matches) == 1


# --- Separated-df chi-square (ecology / biology) ---


def test_chi2_separated_df() -> None:
    """χ² = 15.3, df = 4, p = 0.004 (separated df format)."""
    text = "Association test: χ² = 15.3, df = 4, p = 0.004."
    matches = _extract_matches(text)
    chi2_matches = [m for m in matches if m.test_type == "chi2"]
    assert len(chi2_matches) >= 1
    sep = [m for m in chi2_matches if "df = 4" in m.raw]
    assert len(sep) >= 1
    assert sep[0].df1 == 4


def test_chi2_separated_consistent() -> None:
    """chi2 = 11.00, df = 4 → true p ≈ 0.0266; report consistent."""
    true_p = 1 - stats.chi2.cdf(11.00, df=4)
    text = f"Goodness of fit: χ² = 11.00, df = 4, p = {true_p:.3f}."
    result = B4StatcheckDetector().detect(text, seed=42)
    chi2_findings = [
        f for f in result.findings
        if f.evidence.get("test_type") == "chi2"
        and "df = 4" in f.evidence.get("raw_match", "")
    ]
    assert len(chi2_findings) == 0


def test_chi2_separated_inconsistent() -> None:
    """chi2 = 3.00, df = 4, p = 0.001 → true p ≈ 0.558; flagged."""
    text = "Species distribution: χ² = 3.00, df = 4, p = 0.001."
    result = B4StatcheckDetector().detect(text, seed=42)
    findings = [f for f in result.findings if f.detector_id == "B4"]
    assert len(findings) >= 1


def test_chi2_separated_df_notation() -> None:
    """Also matches 'DF = 3' and 'd.f. = 5' variants."""
    text1 = "Test: χ² = 12.50, DF = 3, p = 0.006."
    text2 = "Test: chi2 = 8.20, d.f. = 2, p = 0.016."
    m1 = [m for m in _extract_matches(text1) if m.test_type == "chi2"]
    m2 = [m for m in _extract_matches(text2) if m.test_type == "chi2"]
    assert len(m1) >= 1
    assert len(m2) >= 1


# --- Kruskal-Wallis H test (biology / ecology nonparametric) ---


def test_h_test_extraction() -> None:
    """H(2) = 8.50, p = 0.014 should be extracted as H type."""
    text = "Kruskal-Wallis test: H(2) = 8.50, p = 0.014."
    matches = _extract_matches(text)
    h_matches = [m for m in matches if m.test_type == "H"]
    assert len(h_matches) == 1
    assert h_matches[0].df1 == 2
    assert h_matches[0].reported_stat == 8.50


def test_h_test_consistent() -> None:
    """H(3) = 7.81, true p ≈ 0.050; report consistent."""
    true_p = 1 - stats.chi2.cdf(7.81, df=3)
    text = f"Non-parametric ANOVA: H(3) = 7.81, p = {true_p:.3f}."
    result = B4StatcheckDetector().detect(text, seed=42)
    h_findings = [
        f for f in result.findings
        if f.evidence.get("test_type") == "H"
    ]
    assert len(h_findings) == 0


def test_h_test_inconsistent() -> None:
    """H(2) = 2.00, true p ≈ 0.368; reported p = 0.01 → flagged."""
    text = "Kruskal-Wallis: H(2) = 2.00, p = 0.01."
    result = B4StatcheckDetector().detect(text, seed=42)
    findings = [
        f for f in result.findings
        if f.evidence.get("test_type") == "H"
    ]
    assert len(findings) >= 1


# --- Existing patterns still work (regression guard) ---


def test_existing_t_still_works() -> None:
    """Original t-test pattern must not break."""
    text = "Group diff: t(38) = 2.03, p = 0.01."
    result = B4StatcheckDetector().detect(text, seed=42)
    assert any(f.detector_id == "B4" for f in result.findings)


def test_existing_chi2_parens_still_works() -> None:
    """Original χ²(df) parenthesised pattern must not break."""
    text = "Cross-tab: χ²(3) = 12.50, p = 0.006."
    matches = _extract_matches(text)
    assert any(m.test_type == "chi2" for m in matches)
