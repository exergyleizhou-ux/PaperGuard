"""A5 — 小数位一致性检测。

核心思想：N 个独立连续测量的小数部分应高度多样。
若 N=64 个值全部具有相同的小数部分（如全是 .48），
随机概率约为 (1/100)^63 ≈ 10⁻¹²⁶ —— 几乎不可能。
"""
from __future__ import annotations

from collections import Counter
from typing import ClassVar

import numpy as np
import pandas as pd
from scipy import stats as scistats

from paperguard.config import get_settings
from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity


class A5DecimalConsistencyDetector(BaseDetector):
    """检测同一列数值的小数部分是否异常一致。"""

    id: ClassVar[str] = "A5"
    name: ClassVar[str] = "Decimal Fraction Consistency"
    description: ClassVar[str] = "检测同一组数据的小数部分是否异常一致。"
    academic_basis: ClassVar[str] = (
        "独立连续测量的小数部分应展现充分多样性；"
        "重复出现的固定小数部分是已知造假签名之一。"
    )
    data_requirements: ClassVar[list[str]] = ["raw_numeric_values"]
    assumption_cluster: ClassVar[str] = "digit_distribution"

    def check_applicability(self, data: pd.DataFrame) -> tuple[bool, str]:
        if not isinstance(data, pd.DataFrame):
            return False, "Expected pd.DataFrame"
        numeric_cols = data.select_dtypes(include=[np.number]).columns
        if not len(numeric_cols):
            return False, "无数值列"
        return True, ""

    @staticmethod
    def _fractional_str(value: float) -> str:
        """提取小数部分字符串（去除符号、整数部分、末尾零）。"""
        s = repr(float(value))
        if "." not in s:
            return "0"
        frac = s.split(".")[1]
        if "e" in frac or "E" in frac:
            return "0"
        return frac.rstrip("0") or "0"

    def _detect(self, data: pd.DataFrame, seed: int) -> list[Finding]:
        settings = get_settings()
        findings: list[Finding] = []

        for col in data.select_dtypes(include=[np.number]).columns:
            values = data[col].dropna()
            n = len(values)
            if n < 20:
                continue

            if (values == values.astype(int)).all():
                continue

            frac_parts = [self._fractional_str(v) for v in values]
            counter = Counter(frac_parts)
            unique_count = len(counter)
            unique_ratio = unique_count / n

            if unique_ratio > settings.a5_max_unique_ratio:
                continue

            most_common = counter.most_common(1)[0]
            dominant_frac, dominant_count = most_common
            dominant_ratio = dominant_count / n

            p_dominant = float(
                1 - scistats.binom.cdf(dominant_count - 1, n, 0.01)
            )

            if dominant_ratio == 1.0:
                severity = Severity.CRITICAL
            elif dominant_ratio >= 0.5:
                severity = Severity.SUSPICIOUS
            elif unique_ratio < 0.15:
                severity = Severity.CONCERN
            else:
                continue

            findings.append(
                Finding(
                    detector_id=self.id,
                    detector_name=self.name,
                    severity=severity,
                    summary=(
                        f"列 '{col}' 共 {n} 个值仅有 {unique_count} 个不同的"
                        f"小数部分 (唯一比 {unique_ratio:.1%})"
                    ),
                    detail=(
                        f"对 {col} 列的 {n} 个值提取小数部分，发现 "
                        f"'.{dominant_frac}' 重复出现 {dominant_count} 次 "
                        f"({dominant_ratio:.1%})。在小数后两位均匀独立的假设下，"
                        f"如此高的重复概率 p ≈ {p_dominant:.2e}。"
                    ),
                    p_value=p_dominant,
                    test_statistic=dominant_ratio,
                    test_name="dominant fraction ratio",
                    evidence={
                        "column": str(col),
                        "n": n,
                        "unique_count": unique_count,
                        "unique_ratio": unique_ratio,
                        "dominant_fraction": dominant_frac,
                        "dominant_count": dominant_count,
                        "top_5_fractions": dict(counter.most_common(5)),
                    },
                    innocent_explanations=[
                        "数据被四舍五入到极少的精度（如 0.5 步长）",
                        "数据来自有限的离散集合而非连续测量",
                        "数据是计算得出，公式只产生有限种小数形式",
                    ],
                    academic_reference=self.academic_basis,
                )
            )
        return findings
