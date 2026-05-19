"""B4 Statcheck 测试。"""
from __future__ import annotations

from scipy import stats

from paperguard.core.types import Severity
from paperguard.detectors.b4_statcheck import B4StatcheckDetector, _extract_matches


def test_t_test_consistent() -> None:
    """t(38)=2.03, p=0.049 → 双尾 p≈0.0494（一致，应不报告）。"""
    expected_p = 2 * (1 - stats.t.cdf(2.03, df=38))  # ≈ 0.0494
    text = f"In condition A, t(38) = 2.03, p = {expected_p:.3f}, results were significant."
    result = B4StatcheckDetector().detect(text, seed=42)
    assert result.applicable
    # 报告 p 与计算 p 在精度上应一致 → 不报告
    findings = [f for f in result.findings if "t(38)" in f.evidence.get("raw_match", "")]
    assert len(findings) == 0


def test_t_test_inconsistent() -> None:
    """t(38)=2.03 真实 p≈0.05，报告 p=0.01 → CONCERN。"""
    text = "Replicate result: t(38) = 2.03, p = 0.01, large effect observed."
    result = B4StatcheckDetector().detect(text, seed=42)
    assert any(f.detector_id == "B4" for f in result.findings)


def test_t_decision_reversal() -> None:
    """t(20)=1.5, 真实 p≈0.15, 报告 p<0.05 → SUSPICIOUS（决策反转）。"""
    text = "Group difference: t(20) = 1.5, p < 0.05, significant."
    result = B4StatcheckDetector().detect(text, seed=42)
    findings = [f for f in result.findings if f.severity == Severity.SUSPICIOUS]
    assert len(findings) >= 1
    assert findings[0].evidence["decision_reversal"] is True


def test_f_test_extraction() -> None:
    text = "ANOVA: F(2, 47) = 4.12, p = 0.022, significant main effect."
    matches = _extract_matches(text)
    assert len(matches) == 1
    assert matches[0].test_type == "F"
    assert matches[0].df1 == 2
    assert matches[0].df2 == 47


def test_chi2_extraction() -> None:
    text = "Cross-tabulation: χ²(3) = 12.5, p = 0.006."
    matches = _extract_matches(text)
    assert len(matches) == 1
    assert matches[0].test_type == "chi2"
    assert matches[0].df1 == 3


def test_z_extraction() -> None:
    text = "Effect size: z = 2.58, p = 0.010, two-tailed."
    matches = _extract_matches(text)
    assert any(m.test_type == "z" for m in matches)


def test_inapplicable_short_text() -> None:
    result = B4StatcheckDetector().detect("x", seed=42)
    assert not result.applicable
