"""C1 — Carlisle 基线平衡检测（RCT）。

学术依据：
Carlisle (2017). Data fabrication and other reasons for non-random sampling
in 5087 randomised controlled trials in anaesthetic and general medical
journals. Anaesthesia, 72(8), 944-952.

核心思想：
RCT 在 H0（随机分配）下，组间各 baseline 变量的连续 p 值应服从
Uniform(0, 1)。可用 Stouffer 方法合并这些 p 值，得到整体 p。
- 整体 p 接近 0 → 组间差异比随机预期更大（罕见）
- 整体 p 接近 1 → 组间差异比随机预期更小（不寻常，"过于平衡"）

本检测器接受用户给出的 baseline 变量摘要统计（n、mean、SD），
对每个变量做两样本 t（unequal variance）得到双尾 p，
然后用 Stouffer 合并。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, ClassVar

from scipy import stats

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity


@dataclass
class BaselineVariable:
    """Continuous baseline variable across two or more RCT arms.

    Backward-compatible: legacy 2-arm callers can use n1/mean1/sd1 + n2/mean2/sd2.
    Multi-arm callers should provide `arms = [(n, mean, sd), (n, mean, sd), ...]`
    of length ≥ 2; n1/mean1/sd1 etc. are ignored when `arms` is set.
    """

    name: str
    n1: int = 0
    mean1: float = 0.0
    sd1: float = 0.0
    n2: int = 0
    mean2: float = 0.0
    sd2: float = 0.0
    arms: list[tuple[int, float, float]] | None = None

    def as_arms(self) -> list[tuple[int, float, float]]:
        """Return arms as a uniform list. Falls back to (n1,mean1,sd1)+(n2,mean2,sd2)."""
        if self.arms is not None and len(self.arms) >= 2:
            return list(self.arms)
        return [(self.n1, self.mean1, self.sd1), (self.n2, self.mean2, self.sd2)]


@dataclass
class CarlisleInput:
    """一项 RCT 的基线变量集合（2 组）。"""

    trial_id: str
    variables: list[BaselineVariable]
    notes: dict[str, Any] = field(default_factory=dict)


def _welch_pair(
    a: tuple[int, float, float], b: tuple[int, float, float]
) -> float:
    """Welch's t between two (n, mean, sd) triples, two-tailed p."""
    n1, m1, s1 = a
    n2, m2, s2 = b
    se1 = s1**2 / max(n1, 1)
    se2 = s2**2 / max(n2, 1)
    se = math.sqrt(se1 + se2)
    if se == 0:
        return 1.0 if math.isclose(m1, m2) else 0.0
    t = (m1 - m2) / se
    df = (se1 + se2) ** 2 / (
        (se1**2 / max(n1 - 1, 1)) + (se2**2 / max(n2 - 1, 1))
    )
    return float(2 * (1 - stats.t.cdf(abs(t), df=df)))


def _welch_p(v: BaselineVariable) -> float:
    """Backward-compat: legacy 2-arm Welch p."""
    arms = v.as_arms()
    return _welch_pair(arms[0], arms[1])


def _multi_arm_ps(v: BaselineVariable) -> list[float]:
    """Pairwise Welch t between every arm pair. Returns C(k, 2) p-values."""
    arms = v.as_arms()
    out: list[float] = []
    for i in range(len(arms)):
        for j in range(i + 1, len(arms)):
            try:
                out.append(_welch_pair(arms[i], arms[j]))
            except Exception:  # noqa: BLE001
                continue
    return out


def _stouffer_combine(p_values: list[float]) -> float:
    """Stouffer 方法合并 p 值，返回单尾 p（H1: 分布偏离均匀）。

    对每个 p_i 计算 Z_i = Φ⁻¹(1 - p_i)，合并 Z = ΣZ_i / √k。
    返回双尾 p = 2 * (1 - Φ(|Z|))，看分布是否偏离 Uniform。
    """
    if not p_values:
        return 1.0
    eps = 1e-12
    zs = [stats.norm.ppf(1 - min(max(p, eps), 1 - eps)) for p in p_values]
    z_combined = sum(zs) / math.sqrt(len(zs))
    return float(2 * (1 - stats.norm.cdf(abs(z_combined))))


class C1CarlisleDetector(BaseDetector):
    """Carlisle 基线平衡检验：组合 p 偏离均匀 → 提示非随机。"""

    id: ClassVar[str] = "C1"
    name: ClassVar[str] = "Carlisle Baseline-Balance Test"
    description: ClassVar[str] = (
        "对 RCT 基线变量逐一做 t 检验后用 Stouffer 合并 p；"
        "合并 p 接近 0 或 1 都提示非随机。"
    )
    academic_basis: ClassVar[str] = (
        "Carlisle (2017). Data fabrication and other reasons for non-random "
        "sampling in 5087 randomised controlled trials. Anaesthesia, 72(8), 944-952."
    )
    data_requirements: ClassVar[list[str]] = ["rct_baseline_table"]
    assumption_cluster: ClassVar[str] = "randomization_check"

    def check_applicability(self, data: Any) -> tuple[bool, str]:
        if not isinstance(data, CarlisleInput):
            return False, "Expected CarlisleInput"
        if len(data.variables) < 5:
            return False, "Carlisle 检验需要至少 5 个独立 baseline 变量"
        return True, ""

    def _detect(self, data: CarlisleInput, seed: int) -> list[Finding]:
        per_var: list[dict[str, Any]] = []
        ps: list[float] = []
        for v in data.variables:
            # multi-arm: get all pairwise p, use Bonferroni-style min adjusted
            # (a conservative choice; alternative: average)
            pairwise = _multi_arm_ps(v)
            if not pairwise:
                continue
            # Use the median p across pairs as a robust per-variable summary
            pairwise_sorted = sorted(pairwise)
            mid = len(pairwise_sorted) // 2
            p_summary = pairwise_sorted[mid]
            per_var.append(
                {"name": v.name, "p": p_summary, "n_pairs": len(pairwise)}
            )
            ps.append(p_summary)

        if len(ps) < 5:
            return []

        combined_p = _stouffer_combine(ps)

        # 2.0.14: BIC-based Bayes factor approximation (no PyMC)
        # Under H_0 (uniform p-values), expected sum of -2*ln(p) is 2*k.
        # Under H_1 (deviation), observed sum can be much higher or lower.
        # BIC approximation: log10(BF10) ≈ (k - 2*ln(p_combined)) / (2*ln(10))
        # Strong evidence: log10(BF) > 2 (Kass & Raftery 1995).
        import math

        try:
            log10_bf = max(
                -10.0,
                min(
                    10.0,
                    (-2.0 * math.log(combined_p) - len(ps))
                    / (2.0 * math.log(10)),
                ),
            )
        except (ValueError, ZeroDivisionError):
            log10_bf = 0.0
        # 双侧：极小 p 和极大 p 都异常
        # combined_p 已经是双尾，所以小 → 异常
        if combined_p > 0.05:
            return []

        if combined_p < 1e-6:
            severity = Severity.SUSPICIOUS
            tail = (
                "low" if sum(p < 0.5 for p in ps) >= len(ps) * 0.7 else "high"
            )
        elif combined_p < 1e-3:
            severity = Severity.CONCERN
            tail = "low" if sum(p < 0.5 for p in ps) >= len(ps) * 0.7 else "high"
        else:
            severity = Severity.NOTE
            tail = "borderline"

        # 区分"过度平衡"和"极不平衡"
        proportion_below_half = sum(p < 0.5 for p in ps) / len(ps)
        if proportion_below_half < 0.25:
            interpretation = "组间差异比随机预期更小（baseline 过于平衡）"
        elif proportion_below_half > 0.75:
            interpretation = "组间差异比随机预期更大（baseline 失衡）"
        else:
            interpretation = "组合 p 偏离均匀分布"

        return [
            Finding(
                detector_id=self.id,
                detector_name=self.name,
                severity=severity,
                summary=(
                    f"Carlisle 合并 p = {combined_p:.2e} ({len(ps)} 个 baseline 变量)；"
                    f"{interpretation}"
                ),
                detail=(
                    f"Trial {data.trial_id}：对 {len(ps)} 个 baseline 变量做 Welch t，"
                    f"使用 Stouffer 方法合并得到双尾 p = {combined_p:.4e}。"
                    f"在真正随机分配下 baseline 的 p 值应服从 Uniform(0,1)。"
                    f"本结果落在 {tail} 尾部。\n"
                    f"2.0.14 Bayes factor 补充: log10(BF10) ≈ {log10_bf:.2f} "
                    "(BIC 近似;>2 = strong evidence per Kass & Raftery 1995)。"
                ),
                p_value=combined_p,
                test_statistic=float(proportion_below_half),
                test_name="Stouffer combined p",
                evidence={
                    "trial_id": data.trial_id,
                    "n_variables": len(ps),
                    "per_variable": per_var,
                    "combined_p": combined_p,
                    "log10_bayes_factor": log10_bf,
                    "proportion_p_below_0.5": proportion_below_half,
                },
                innocent_explanations=[
                    "样本量较小时 Welch t 的 p 值近似精度有限",
                    "Baseline 变量并非完全独立（如年龄、BMI、血压相关）",
                    "RCT 设计中包含 stratified randomization 或 minimization，"
                    "本就会造成组间过于平衡（合法）",
                    "报告的 mean/SD 精度损失（四舍五入）影响 p 计算",
                ],
                academic_reference=self.academic_basis,
            )
        ]
