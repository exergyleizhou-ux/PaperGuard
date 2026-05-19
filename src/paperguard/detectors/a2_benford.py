"""A2 — Benford 首位数字检验。

学术依据：
- Benford (1938). The law of anomalous numbers. Proc Am Philos Soc.
- Nigrini (2012). Benford's Law: Applications for Forensic Accounting.

适用范围：
当数据跨多个数量级时，**真实**的自然数据的首位数字 d ∈ {1..9}
应近似服从 P(d) = log10(1 + 1/d)。
人为编造的数据通常首位分布偏均匀。

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
            if len(values) < self.MIN_N:
                continue
            positives = values[values > 0]
            if len(positives) < 2:
                continue
            ratio = positives.max() / positives.min()
            if ratio > 0 and math.log10(ratio) >= self.MIN_DECADES:
                return True, ""
        return False, (
            f"无满足 N ≥ {self.MIN_N} 且动态范围 ≥ "
            f"{self.MIN_DECADES} 数量级的数值列"
        )

    def _detect(self, data: pd.DataFrame, seed: int) -> list[Finding]:
        findings: list[Finding] = []
        numeric_cols = data.select_dtypes(include=[np.number]).columns

        for col in numeric_cols:
            values = data[col].dropna()
            values = values[values != 0]
            if len(values) < self.MIN_N:
                continue
            positives = values[values > 0]
            if len(positives) < 2:
                continue
            ratio = float(positives.max() / positives.min())
            decades = math.log10(ratio) if ratio > 0 else 0
            if decades < self.MIN_DECADES:
                continue

            digits = [_first_digit(v) for v in values]
            digits_clean = [d for d in digits if d is not None]
            n = len(digits_clean)
            if n < self.MIN_N:
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

        return findings
