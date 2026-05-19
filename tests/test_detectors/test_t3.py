"""T3 data availability + ethics 测试。"""
from __future__ import annotations

from paperguard.core.types import Severity
from paperguard.detectors.t3_data_availability import (
    DataAvailabilityInput,
    T3DataAvailabilityDetector,
)


def test_t3_flags_missing_data_statement() -> None:
    text = (
        "We measured tree biomass at 50 sites. Statistical models were "
        "fitted using lme4 in R. Results are reported in Tables 1-3. "
        "Acknowledgements: thanks to all collaborators. " * 5
    )
    result = T3DataAvailabilityDetector().detect(text, seed=42)
    assert result.applicable
    # 至少有"缺数据声明"或"缺COI"
    assert len(result.findings) >= 1


def test_t3_passes_complete_statement() -> None:
    text = (
        "Data availability. All data are deposited at Zenodo "
        "(https://doi.org/10.5281/zenodo.1234567) and code is at "
        "https://github.com/example/repo. "
        "Ethics: this study was approved by the institutional review board "
        "(IRB) of the University, approval number 2023-001. "
        "Competing interests: the authors declare no competing interests. "
        + "lorem ipsum " * 30
    )
    result = T3DataAvailabilityDetector().detect(text, seed=42)
    assert result.applicable
    # 不应有 CONCERN+
    assert all(f.severity < Severity.CONCERN for f in result.findings)


def test_t3_flags_vague_availability() -> None:
    text = (
        "Data availability: data are available from the corresponding author "
        "upon reasonable request. " + "lorem ipsum " * 50
    )
    result = T3DataAvailabilityDetector().detect(text, seed=42)
    findings = [
        f
        for f in result.findings
        if "request" in f.detail.lower() or "托辞" in f.summary
    ]
    assert len(findings) >= 1


def test_t3_flags_missing_trial_registration() -> None:
    text = "We conducted a randomized controlled trial on 200 patients. " * 5
    inp = DataAvailabilityInput(text=text, is_clinical_trial=True)
    result = T3DataAvailabilityDetector().detect(inp, seed=42)
    findings = [f for f in result.findings if "注册" in f.summary or "trial" in f.summary.lower()]
    assert len(findings) >= 1


def test_t3_finds_nct_id() -> None:
    text = (
        "This trial is registered at ClinicalTrials.gov (NCT04123456). "
        "Data availability: data are at Zenodo doi.org/10.5281/zenodo.999. "
        "IRB approved by ethics committee number 2022-Med-007. "
        "Competing interests: none. " + "lorem " * 50
    )
    inp = DataAvailabilityInput(
        text=text, is_clinical_trial=True, is_human_subjects=True
    )
    result = T3DataAvailabilityDetector().detect(inp, seed=42)
    # 应该完全 clean
    severe = [f for f in result.findings if f.severity >= Severity.CONCERN]
    assert len(severe) == 0
