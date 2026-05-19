"""B7 — P-Curve 分布检测（p-hacking 签名）。

学术依据：
Simonsohn, Nelson & Simmons (2014) "P-Curve: A Key to the File-Drawer."
Journal of Experimental Psychology: General, 143(2), 534-547.

原理：在真实效应下，p-curve（显著 p 值分布）应右偏（更多 0.01 比
0.04）；p-hacking 下分布左偏或在 0.045-0.05 堆积。

检验：
- 取所有 p < 0.05 的报告
- 比较"低区间"(p < 0.025) vs "高区间"(0.025-0.05) 的频数
- 若高区间 ≥ 低区间 → 左偏 → 提示 p-hacking
- 单独检查"近 α 堆积"：(0.045 ≤ p ≤ 0.05) / (0.04 ≤ p ≤ 0.045) 比例
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from scipy import stats

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity


@dataclass
class PCurveInput:
    p_values: list[float]
    label: str = ""


class B7PCurveDetector(BaseDetector):
    """P-Curve：检测 p 值分布的左偏 / 近 α 堆积。"""

    id: ClassVar[str] = "B7"
    name: ClassVar[str] = "P-Curve Distribution"
    description: ClassVar[str] = (
        "对一组显著 p 值做 p-curve 形状检验；左偏或近 0.05 堆积 → p-hacking。"
    )
    academic_basis: ClassVar[str] = (
        "Simonsohn, Nelson & Simmons (2014). P-Curve: A Key to the "
        "File-Drawer. J Exp Psychol Gen, 143(2), 534-547."
    )
    data_requirements: ClassVar[list[str]] = ["multi_study_p_values"]
    assumption_cluster: ClassVar[str] = "publication_bias"

    MIN_SIG_P: ClassVar[int] = 5  # 至少需要 5 个 p < 0.05 才有意义

    def check_applicability(self, data: Any) -> tuple[bool, str]:
        if not isinstance(data, PCurveInput):
            return False, "Expected PCurveInput"
        sig = [p for p in data.p_values if 0 < p < 0.05]
        if len(sig) < self.MIN_SIG_P:
            return False, f"Need at least {self.MIN_SIG_P} significant p values"
        return True, ""

    def _detect(self, data: PCurveInput, seed: int) -> list[Finding]:
        sig = sorted([p for p in data.p_values if 0 < p < 0.05])
        n = len(sig)

        # Bin counts
        low_n = sum(1 for p in sig if p <= 0.025)
        high_n = sum(1 for p in sig if 0.025 < p < 0.05)
        near_alpha_n = sum(1 for p in sig if 0.045 <= p < 0.05)
        far_alpha_n = sum(1 for p in sig if 0.040 <= p < 0.045)

        # 1) 左偏检验：H0 = 真实效应（右偏），H1 = 左偏
        # 用一项 binomial 检验：在真实效应下 p < 0.025 概率应该 ≥ 0.5
        # 这里用单尾 binomial p；left-skewed 时 low_n 远小于 high_n
        try:
            # left-tail binomial: P(X ≤ low_n | n, p=0.5)
            p_left_skew = float(stats.binom.cdf(low_n, n, 0.5))
        except Exception:  # noqa: BLE001
            p_left_skew = 1.0

        # 2) 近 α 堆积：在均匀分布下 [0.045, 0.05) 与 [0.040, 0.045) 频数应相近
        if far_alpha_n > 0:
            ratio_near_far = near_alpha_n / far_alpha_n
        else:
            ratio_near_far = float("inf") if near_alpha_n > 0 else 1.0

        signals: list[str] = []
        severity = Severity.PASS

        if p_left_skew < 0.001:
            signals.append(
                f"left-skewed p-curve (binomial left-tail p={p_left_skew:.4f})"
            )
            severity = max(severity, Severity.SUSPICIOUS)
        elif p_left_skew < 0.05:
            signals.append(
                f"weak left-skew (binomial left-tail p={p_left_skew:.4f})"
            )
            severity = max(severity, Severity.CONCERN)

        if far_alpha_n >= 3 and ratio_near_far >= 2.5:
            signals.append(
                f"near-α pile-up: {near_alpha_n}/{far_alpha_n} = "
                f"{ratio_near_far:.2f}x"
            )
            severity = max(severity, Severity.CONCERN)

        if severity < Severity.CONCERN:
            return []

        return [
            Finding(
                detector_id=self.id,
                detector_name=self.name,
                severity=severity,
                summary=(
                    f"{data.label or 'Set of'} {n} significant p-values: "
                    + "; ".join(signals)
                ),
                detail=(
                    f"P-curve analysis on {n} significant p values. "
                    f"Low bin (p ≤ 0.025): {low_n}; "
                    f"High bin (0.025 < p < 0.05): {high_n}. "
                    f"Near-α [0.045, 0.05): {near_alpha_n}; "
                    f"Far-α [0.040, 0.045): {far_alpha_n}. "
                    "Under a true effect the curve right-skews "
                    "(more low p values than high). "
                    "Left-skew or near-α pile-up is the canonical "
                    "p-hacking signature."
                ),
                p_value=p_left_skew,
                test_statistic=float(low_n - high_n),
                test_name="low−high bin difference",
                evidence={
                    "label": data.label,
                    "n_significant": n,
                    "low_bin_count": low_n,
                    "high_bin_count": high_n,
                    "near_alpha_count": near_alpha_n,
                    "far_alpha_count": far_alpha_n,
                    "binomial_left_tail_p": p_left_skew,
                    "near_far_ratio": ratio_near_far,
                },
                innocent_explanations=[
                    "样本量小（n < 30 显著 p）时 p-curve 不稳定",
                    "本研究领域真实效应量本就接近零（很多 p 落在 0.04-0.05 是合法）",
                    "Meta-analysis 已对效应量异质性做校正",
                    "p 值都来自同一研究的多个 outcome（应独立同分布抽样）",
                ],
                academic_reference=self.academic_basis,
            )
        ]
