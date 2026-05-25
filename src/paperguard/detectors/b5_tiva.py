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

    # W3: raised minimum from 4 to 10 for small-n graceful degradation
    SMALL_N: ClassVar[int] = 10

    def check_applicability(self, data: Any) -> tuple[bool, str]:
        if not isinstance(data, TIVAInput):
            return False, "Expected TIVAInput"
        if len(data.p_values) < self.SMALL_N:
            return False, f"TIVA needs at least {self.SMALL_N} independent p-values"
        return True, ""

    def _detect(self, data: TIVAInput, seed: int) -> list[Finding]:
        import math

        zs = [_p_to_z(p) for p in data.p_values if 0 < p < 1]
        k = len(zs)
        if k < self.SMALL_N:
            return []

        # W3: small-n graceful degradation
        low_power = k < 50

        # 样本方差 (TIVA)
        mean_z = sum(zs) / k
        ov = sum((z - mean_z) ** 2 for z in zs) / (k - 1)
        chi2 = ov * (k - 1)
        p_combined = float(stats.chi2.cdf(chi2, df=k - 1))  # 左尾：方差太小

        # --- 2.0.14: meta-analytic z (Stouffer + R-index + I²) ---
        # Stouffer's Z = sum(z) / sqrt(k); two-sided p
        stouffer_z = sum(zs) / math.sqrt(k)
        stouffer_p = 2.0 * (1.0 - stats.norm.cdf(abs(stouffer_z)))

        # Schimmack's R-index = observed success rate - estimated power
        # (Schimmack 2016). Approximated as:
        #   success_rate = fraction of p < 0.05
        #   median_power = average of (z > 1.645) post-hoc power proxy
        #   R = success_rate - median_power
        success_rate = sum(1 for p in data.p_values if p < 0.05) / k
        # Post-hoc power ≈ Φ(|z| - z_α) using one-tailed α=0.05
        z_alpha = 1.645
        post_hoc_powers = [
            float(stats.norm.cdf(abs(z) - z_alpha)) for z in zs
        ]
        median_power = (
            sorted(post_hoc_powers)[len(post_hoc_powers) // 2]
            if post_hoc_powers
            else 0.0
        )
        r_index = success_rate - median_power

        # Cochran Q + I²: cross-study heterogeneity
        # Q = sum((z_i - mean_z)^2). Under H_0 of homogeneity, Q ~ χ²(k-1).
        # I² = max(0, (Q - df) / Q) gives % of variance due to heterogeneity.
        q_stat = sum((z - mean_z) ** 2 for z in zs)
        df = k - 1
        if q_stat > 0:
            i_sq = max(0.0, (q_stat - df) / q_stat)
        else:
            i_sq = 0.0
        q_p = float(1.0 - stats.chi2.cdf(q_stat, df=df))

        # --- decide if any of the three meta-signals fires ---
        # Thresholds tightened so the meta layer does not fire on small
        # noisy samples — these are diagnostic-grade signals, not
        # screening signals.
        meta_signals: list[str] = []
        if r_index < -0.35 and k >= 6:
            meta_signals.append(
                f"R-index = {r_index:.3f} (< -0.35 with k≥6: success "
                "rate much higher than median power, classic p-hacking "
                "signature)"
            )
        if i_sq < 0.02 and k >= 10:
            meta_signals.append(
                f"I² = {i_sq:.3f} (< 0.02 with k≥10: essentially no "
                "heterogeneity, all studies suspiciously consistent; "
                f"Cochran Q p = {q_p:.3e})"
            )
        if p_combined > 0.10 and not meta_signals:
            return []

        # Original TIVA finding (preserved)
        if p_combined < 0.001:
            severity = Severity.SUSPICIOUS
        elif p_combined < 0.01:
            severity = Severity.CONCERN
        elif p_combined < 0.10:
            severity = Severity.NOTE
        else:
            severity = Severity.NOTE
        # Elevate if both TIVA AND a meta signal fire
        if p_combined < 0.01 and meta_signals:
            severity = Severity.SUSPICIOUS

        # W3: cap severity for low-power samples (10 <= k < 50)
        if low_power and severity > Severity.NOTE:
            severity = Severity.NOTE

        return [
            Finding(
                detector_id=self.id,
                detector_name=self.name,
                severity=severity,
                summary=(
                    f"{data.label or 'A set of'} {k} studies: "
                    f"z-var={ov:.3f}, Stouffer p={stouffer_p:.2e}, "
                    f"R-index={r_index:.3f}, I²={i_sq:.3f}"
                ),
                detail=(
                    f"Meta-analytic check on {k} p-values:\n"
                    f"  TIVA (Schimmack 2014): variance = {ov:.4f}, "
                    f"χ²({df}) = {chi2:.3f}, left-tail p = {p_combined:.4e}\n"
                    f"  Stouffer's combined Z = {stouffer_z:.3f}, "
                    f"two-sided p = {stouffer_p:.4e}\n"
                    f"  R-index (Schimmack 2016) = success rate "
                    f"{success_rate:.2f} - median power "
                    f"{median_power:.2f} = {r_index:.3f}\n"
                    f"  Cochran Q = {q_stat:.3f}, p = {q_p:.4e}; "
                    f"I² (heterogeneity) = {i_sq:.3f}\n"
                    + (
                        f"  Triggered meta-signals: {'; '.join(meta_signals)}\n"
                        if meta_signals
                        else ""
                    )
                    + "TIVA + Stouffer + R-index + I² together form the "
                    "publication-grade meta-analytic integrity check."
                ),
                p_value=p_combined,
                test_statistic=chi2,
                test_name=f"TIVA χ²({df}) + Stouffer + R-index + I²",
                evidence={
                    "label": data.label,
                    "n_studies": k,
                    "z_values": zs,
                    "tiva_observed_variance": ov,
                    "tiva_chi2": chi2,
                    "tiva_p": p_combined,
                    "stouffer_z": stouffer_z,
                    "stouffer_p": stouffer_p,
                    "success_rate": success_rate,
                    "median_post_hoc_power": median_power,
                    "r_index": r_index,
                    "cochran_q": q_stat,
                    "cochran_q_p": q_p,
                    "i_squared": i_sq,
                    "meta_signals_triggered": meta_signals,
                    "low_power_note": low_power,
                },
                innocent_explanations=[
                    "所有研究共享同一稳定真实效应（罕见且应有强先验）",
                    "Meta-analytic 漏报：本工具假设所有研究都独立同分布",
                    "数据来自高度相关的子样本（不应作为独立 z 喂入 TIVA）",
                    "样本量极大，效应量极稳定，z 值自然集中（说明会反驳）",
                    "R-index 假设 power 计算用 normal approximation,小样本不准",
                ],
                academic_reference=(
                    "Schimmack (2014) TIVA; Stouffer et al. (1949) "
                    "method of combining test results; Schimmack (2016) "
                    "Replicability-Index; Higgins & Thompson (2002) "
                    "Quantifying heterogeneity (I²)."
                ),
            )
        ]
