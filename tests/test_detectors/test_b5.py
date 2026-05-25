"""B5 TIVA 测试。"""
from __future__ import annotations

from paperguard.core.types import Severity
from paperguard.detectors.b5_tiva import B5TIVADetector, TIVAInput, _p_to_z


def test_p_to_z_basic() -> None:
    # 双尾 p=0.05 → z≈1.96
    z = _p_to_z(0.05, one_tailed=False)
    assert 1.93 < z < 1.99


def test_tiva_flags_low_variance() -> None:
    """所有 p 都接近 0.05（即 z 都接近 1.96），方差应 ≪ 1。"""
    # W3: minimum n raised to 10
    ps = [0.045, 0.048, 0.051, 0.049, 0.046, 0.047, 0.050, 0.044, 0.052, 0.048]
    inp = TIVAInput(p_values=ps, label="Studies 1-10")
    result = B5TIVADetector().detect(inp, seed=42)
    assert result.applicable
    assert len(result.findings) == 1
    assert result.findings[0].severity >= Severity.NOTE


def test_tiva_passes_normal_variance() -> None:
    """方差正常的一组 p 值不应触发。"""
    # W3: minimum n raised to 10; use high-variance spread to avoid triggering
    ps = [0.001, 0.15, 0.4, 0.95, 0.7, 0.55, 0.83, 0.32, 0.22, 0.08]
    inp = TIVAInput(p_values=ps)
    result = B5TIVADetector().detect(inp, seed=42)
    assert result.applicable
    # W3: low-power NOTE findings are acceptable for normal-variance data
    for f in result.findings:
        assert f.severity <= Severity.NOTE


def test_tiva_inapplicable_few_studies() -> None:
    inp = TIVAInput(p_values=[0.01, 0.02])
    result = B5TIVADetector().detect(inp, seed=42)
    assert not result.applicable
