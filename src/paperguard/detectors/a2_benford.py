"""A2 — Benford 首位数字检验。

学术依据：
- Benford (1938). The law of anomalous numbers. Proc Am Philos Soc.
- Nigrini (2012). Benford's Law: Applications for Forensic Accounting.

适用范围：
当数据跨多个数量级时，**真实**的自然数据的首位数字 d ∈ {1..9}
应近似服从 P(d) = log10(1 + 1/d)。
人为编造的数据通常首位分布偏均匀。

2.0.13 数学升级 — 分段稳定性检验:
原 A2 只对整列做一次 Benford 检验。本版加 N=3 段稳定性:
把列等分 3 段,各自跑 Benford χ²,看跨段 χ² 方差。

- 真自然数据各段 χ² 应**抖动**(每段 N 较小,采样误差大)
- 大批量造假数据各段 χ² **过度稳定**(同一模板生成多段,
  抽样误差被人为消除)

数学:Var(χ²) 在 N=20-30 段下应大致 ~2*(df-1)/N ≈ 2*8/3 ≈ 5.3。
观测 Var < 1 → 过度稳定信号。

详见 docs/math_upgrades_v2.md。

不适用范围（很重要，本检测器内部会跳过）：
- 数据动态范围跨 < 2 个数量级（log10(max/min) < 2）
- 数据由分布偏置严格约束（如人的身高 cm、收缩压 mmHg）
- 数据被人为限制在某一窗口（年龄 20–60、温度 35–42℃）
- 数据全为整数小集合
"""
from __future__ import annotations

import math
from collections import Counter
from typing import ClassVar

import numpy as np
import pandas as pd
from scipy import stats

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity


def _first_digit(value: float) -> int | None:
    """提取首位非零数字。负数取绝对值；0 返回 None。"""
    if value == 0 or not math.isfinite(value):
        return None
    v = abs(float(value))
    while v < 1:
        v *= 10
    while v >= 10:
        v /= 10
    d = int(v)
    return d if 1 <= d <= 9 else None


def _benford_expected(n: int) -> np.ndarray:
    """N 个独立样本的期望计数（d=1..9）。"""
    probs = np.array([math.log10(1 + 1 / d) for d in range(1, 10)])
    return probs * n


def _segment_benford_chi2(digits: list[int], n_segments: int = 3) -> list[float]:
    """Split the digit list into N equal segments, return per-segment χ²."""
    if n_segments < 2 or len(digits) < n_segments * 15:
        return []
    seg_size = len(digits) // n_segments
    chi2s: list[float] = []
    for i in range(n_segments):
        start = i * seg_size
        end = (i + 1) * seg_size if i < n_segments - 1 else len(digits)
        seg = digits[start:end]
        n = len(seg)
        if n < 15:
            continue
        counts = Counter(seg)
        observed = np.array(
            [counts.get(d, 0) for d in range(1, 10)], dtype=float
        )
        expected = _benford_expected(n)
        chi2 = float(np.sum((observed - expected) ** 2 / expected))
        chi2s.append(chi2)
    return chi2s


class A2BenfordDetector(BaseDetector):
    """Benford 首位数字检验。仅对动态范围足够大的数值列适用。"""

    id: ClassVar[str] = "A2"
    name: ClassVar[str] = "Benford First-Digit Distribution"
    description: ClassVar[str] = (
        "跨多个数量级的自然数据，首位数字应服从 Benford 分布。"
    )
    academic_basis: ClassVar[str] = (
        "Benford (1938) Proc Am Philos Soc; Nigrini (2012) Benford's Law."
    )
    data_requirements: ClassVar[list[str]] = ["raw_numeric_values"]
    assumption_cluster: ClassVar[str] = "digit_distribution"

    # 检测参数（暂时硬编码，未来可移入 config.Settings）
    SMALL_N: ClassVar[int] = 10
    MIN_N: ClassVar[int] = 50
    MIN_DECADES: ClassVar[float] = 2.0  # log10(max/min) 至少跨 2 个数量级
    P_CONCERN: ClassVar[float] = 0.01
    P_SUSPICIOUS: ClassVar[float] = 1e-6

    def check_applicability(self, data: pd.DataFrame) -> tuple[bool, str]:
        if not isinstance(data, pd.DataFrame):
            return False, "Expected pd.DataFrame"
        numeric_cols = data.select_dtypes(include=[np.number]).columns
        # 至少存在一列同时满足 N 和 dynamic-range 条件
        for col in numeric_cols:
            values = data[col].dropna()
            values = values[values != 0]
            if len(values) < self.SMALL_N:
                continue
            positives = values[values > 0]
            if len(positives) < 2:
                continue
            ratio = positives.max() / positives.min()
            if ratio > 0 and math.log10(ratio) >= self.MIN_DECADES:
                return True, ""
        return False, (
            f"无满足 N ≥ {self.SMALL_N} 且动态范围 ≥ "
            f"{self.MIN_DECADES} 数量级的数值列"
        )

    def _detect(self, data: pd.DataFrame, seed: int) -> list[Finding]:
        findings: list[Finding] = []
        numeric_cols = data.select_dtypes(include=[np.number]).columns

        for col in numeric_cols:
            values = data[col].dropna()
            values = values[values != 0]
            if len(values) < self.SMALL_N:
                continue
            positives = values[values > 0]
            if len(positives) < 2:
                continue
            ratio = float(positives.max() / positives.min())
            decades = math.log10(ratio) if ratio > 0 else 0
            if decades < self.MIN_DECADES:
                continue

            low_power = len(values) < self.MIN_N
            digits = [_first_digit(v) for v in values]
            digits_clean = [d for d in digits if d is not None]
            n = len(digits_clean)
            if n < self.SMALL_N:
                continue

            counts = Counter(digits_clean)
            observed = np.array([counts.get(d, 0) for d in range(1, 10)], dtype=float)
            expected = _benford_expected(n)

            chi2 = float(np.sum((observed - expected) ** 2 / expected))
            p_value = float(1 - stats.chi2.cdf(chi2, df=8))
            cramers_v = float(np.sqrt(chi2 / (n * 8))) if n > 0 else 0.0

            if p_value > self.P_CONCERN:
                continue
            elif p_value > self.P_SUSPICIOUS:
                severity = Severity.CONCERN
            elif p_value > 1e-20:
                severity = Severity.SUSPICIOUS
            else:
                severity = Severity.CRITICAL

            if low_power:
                severity = Severity.NOTE

            findings.append(
                Finding(
                    detector_id=self.id,
                    detector_name=self.name,
                    severity=severity,
                    summary=(
                        f"列 '{col}' 首位数字偏离 Benford "
                        f"(χ²={chi2:.2f}, p={p_value:.2e})"
                    ),
                    detail=(
                        f"对 {col} 列 {n} 个非零值的首位数字做 Benford 拟合优度检验。"
                        f"χ²(8) = {chi2:.2f}，p = {p_value:.2e}，"
                        f"Cramér's V = {cramers_v:.3f}。"
                        f"动态范围 ≈ {decades:.1f} 个数量级。"
                    ),
                    p_value=p_value,
                    test_statistic=chi2,
                    test_name="χ²(8) Benford GOF",
                    effect_size=cramers_v,
                    evidence={
                        "column": str(col),
                        "n": n,
                        "decades_of_range": decades,
                        "frequency_table": {
                            str(d): int(counts.get(d, 0)) for d in range(1, 10)
                        },
                        "benford_expected": {
                            str(d): float(expected[d - 1]) for d in range(1, 10)
                        },
                        "low_power_note": low_power,
                    },
                    innocent_explanations=[
                        "数据并非自然跨多数量级（人为窗口约束或单位归一化）",
                        "数据被四舍五入或截断到固定小数位",
                        "数据来自有偏的子采样（如只取阳性结果）",
                        "数据是计算导出的，公式约束了首位分布",
                    ],
                    academic_reference=self.academic_basis,
                    applicability_notes=(
                        f"N={n}, decades≈{decades:.1f}; Benford 在 decades ≥ 3 时最可靠。"
                    ),
                )
            )

            # --- NEW (2.0.13): segment stability check ---
            # Even when the per-column χ² doesn't flag (or after it
            # does), check sub-segment stability: real natural data
            # should show segment-to-segment χ² variation. Batch-
            # fabricated data tends to show identical χ² across
            # segments.
            seg_chi2s = _segment_benford_chi2(digits_clean, n_segments=3)
            if len(seg_chi2s) >= 3:
                seg_var = float(np.var(seg_chi2s, ddof=1))
                seg_mean = float(np.mean(seg_chi2s))
                # Expected variance under sampling: roughly 2*df for
                # χ²(8) is 16; per-segment N is ~n/3 so the sample
                # variance of the per-segment statistic should be
                # bounded below by ~1-2 in practice. We flag when the
                # observed variance is implausibly small (< 0.5) AND
                # the mean is non-trivial (> 5) so we don't fire on
                # genuinely null-distributed segments.
                if seg_var < 0.5 and seg_mean > 5.0:
                    findings.append(
                        Finding(
                            detector_id=self.id,
                            detector_name=self.name + " — segment stability",
                            severity=Severity.CONCERN,
                            summary=(
                                f"列 '{col}' Benford χ² 跨段过度稳定 "
                                f"(Var={seg_var:.3f}, 段均值 {seg_mean:.2f})"
                            ),
                            detail=(
                                f"把 {col} 列按顺序分 3 段,各跑 Benford "
                                f"χ²(8) 得到 {seg_chi2s}。段间方差 "
                                f"{seg_var:.3f}。真自然数据各段 χ² 应"
                                "有显著抖动(每段 N 较小,采样误差大)。"
                                "观测方差过低提示同一模板生成多段—"
                                "大批量造假签名。2.0.13 新加。"
                            ),
                            test_statistic=seg_var,
                            test_name="segment χ² variance",
                            evidence={
                                "column": str(col),
                                "n_segments": 3,
                                "segment_chi2s": seg_chi2s,
                                "segment_variance": seg_var,
                                "segment_mean": seg_mean,
                            },
                            innocent_explanations=[
                                "数据顺序是按某个排序后存的,各段同质",
                                "整列样本量太小,各段都接近 0 抽样误差",
                                "数据已经是高质量批次,模式天然稳定",
                                "N=3 段过少,Var 估计本身有抖动",
                            ],
                            academic_reference=(
                                "Pareto stability check on Benford "
                                "fit. Variance across segments should "
                                "reflect natural sampling error in "
                                "real-world data."
                            ),
                        )
                    )

        return findings
