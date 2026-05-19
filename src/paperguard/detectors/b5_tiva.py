"""B5 — Test of Insufficient Variance (TIVA)。

学术依据：
Schimmack (2014) "The Test of Insufficient Variance (TIVA): A new tool for
the detection of questionable research practices." Replicability-Index.

原理：在 H0 + 真实研究下，一组实验得到的 z 值方差应 ≥ 1。
若 N 个研究报告的 p 值转换为 z 值后方差远低于 1，可能存在：
- p-hacking
- 选择性报告（不发表 null result）
- 不报告失败的复制
- 完全编造数据

检验：χ²(k-1) = OV × (k-1)，其中 OV 是 z 值的样本方差，k 是研究数。

输入：一组 p 值（最好来自不同实验/研究，而非同一研究的多个 outcome）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from scipy import stats

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity


@dataclass
class TIVAInput:
    p_values: list[float]
    label: str = ""
    one_tailed_alpha: float = 0.05


def _p_to_z(p: float, one_tailed: bool = False) -> float:
    """p → z（H1 方向假设为正）。"""
    eps = 1e-12
    p_clamped = min(max(p, eps), 1 - eps)
    if one_tailed:
        return float(stats.norm.ppf(1 - p_clamped))
    # 双尾：p/2 转成 z
    return float(stats.norm.ppf(1 - p_clamped / 2))


class B5TIVADetector(BaseDetector):
    """Schimmack 2014 z-variance 检验。"""

    id: ClassVar[str] = "B5"
    name: ClassVar[str] = "Test of Insufficient Variance (TIVA)"
    description: ClassVar[str] = (
        "对一组研究的 p 值转 z 后做方差检验；σ²(z) ≪ 1 提示 p-hacking。"
    )
    academic_basis: ClassVar[str] = (
        "Schimmack (2014). The Test of Insufficient Variance (TIVA). "
        "Replicability-Index blog."
    )
    data_requirements: ClassVar[list[str]] = ["multi_study_p_values"]
    assumption_cluster: ClassVar[str] = "summary_statistic_consistency"

    def check_applicability(self, data: Any) -> tuple[bool, str]:
        if not isinstance(data, TIVAInput):
            return False, "Expected TIVAInput"
        if len(data.p_values) < 4:
            return False, "TIVA 需要至少 4 个独立 p 值"
        return True, ""

    def _detect(self, data: TIVAInput, seed: int) -> list[Finding]:
        zs = [_p_to_z(p) for p in data.p_values if 0 < p < 1]
        k = len(zs)
        if k < 4:
            return []

        # 样本方差
        mean_z = sum(zs) / k
        ov = sum((z - mean_z) ** 2 for z in zs) / (k - 1)
        chi2 = ov * (k - 1)
        p_combined = float(stats.chi2.cdf(chi2, df=k - 1))  # 左尾：方差太小

        if p_combined > 0.10:
            return []
        if p_combined < 0.001:
            severity = Severity.SUSPICIOUS
        elif p_combined < 0.01:
            severity = Severity.CONCERN
        else:
            severity = Severity.NOTE

        return [
            Finding(
                detector_id=self.id,
                detector_name=self.name,
                severity=severity,
                summary=(
                    f"{data.label or 'A set of'} {k} studies have"
                    f" z-score variance = {ov:.3f}（期望 ≥ 1, p={p_combined:.2e}）"
                ),
                detail=(
                    f"对 {k} 个 p 值转 z 计算方差 = {ov:.4f}。"
                    f"χ²({k - 1}) = {chi2:.3f}, 左尾 p = {p_combined:.4e}。"
                    "z 方差远低于 1 意味着所有研究的 z 值过于聚集，"
                    "提示 p-hacking、selective reporting 或 outright fabrication。"
                ),
                p_value=p_combined,
                test_statistic=chi2,
                test_name=f"TIVA χ²({k - 1})",
                evidence={
                    "label": data.label,
                    "n_studies": k,
                    "z_values": zs,
                    "observed_variance": ov,
                    "chi2": chi2,
                },
                innocent_explanations=[
                    "所有研究共享同一稳定真实效应（罕见且应有强先验）",
                    "Meta-analytic 漏报：本工具假设所有研究都独立同分布",
                    "数据来自高度相关的子样本（不应作为独立 z 喂入 TIVA）",
                    "样本量极大，效应量极稳定，z 值自然集中（说明会反驳）",
                ],
                academic_reference=self.academic_basis,
            )
        ]
