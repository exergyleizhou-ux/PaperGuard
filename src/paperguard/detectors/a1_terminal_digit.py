"""A1 — 末位数字分布检测。

学术依据：
- Mosimann et al. (1995) Accountability in Research, 4(1)
- Al-Marzouki et al. (2005) J Clin Epidemiology
"""
from __future__ import annotations

from collections import Counter
from typing import ClassVar

import numpy as np
import pandas as pd
from scipy import stats

from paperguard.config import get_settings
from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity
from paperguard.utils.float_utils import get_last_significant_digit


class A1TerminalDigitDetector(BaseDetector):
    """末位有效数字应近似均匀。系统偏向某些数字提示人工编造。"""

    id: ClassVar[str] = "A1"
    name: ClassVar[str] = "Terminal Digit Distribution Analysis"
    description: ClassVar[str] = (
        "末位数字应近似均匀分布。系统偏向某些数字提示人工编造。"
    )
    academic_basis: ClassVar[str] = (
        "Mosimann et al. (1995). Data fabrication: Can people generate random digits? "
        "Accountability in Research, 4(1), 31-55."
    )
    data_requirements: ClassVar[list[str]] = ["raw_numeric_values"]
    assumption_cluster: ClassVar[str] = "digit_distribution"

    def check_applicability(self, data: pd.DataFrame) -> tuple[bool, str]:
        if not isinstance(data, pd.DataFrame):
            return False, "Expected pd.DataFrame"

        settings = get_settings()
        numeric_cols = data.select_dtypes(include=[np.number]).columns
        valid_cols = [
            c for c in numeric_cols if len(data[c].dropna()) >= settings.a1_min_n
        ]
        if not valid_cols:
            return False, f"No numeric column with N ≥ {settings.a1_min_n}"
        return True, ""

    def _detect(self, data: pd.DataFrame, seed: int) -> list[Finding]:
        settings = get_settings()
        findings: list[Finding] = []
        numeric_cols = data.select_dtypes(include=[np.number]).columns

        for col in numeric_cols:
            values = data[col].dropna()
            if len(values) < settings.a1_min_n:
                continue

            digits = [get_last_significant_digit(v) for v in values]
            n = len(digits)
            counts = Counter(digits)
            observed = np.array([counts.get(d, 0) for d in range(10)])
            expected = np.full(10, n / 10.0)

            chi2 = float(np.sum((observed - expected) ** 2 / expected))
            p_value = float(1 - stats.chi2.cdf(chi2, df=9))
            cramers_v = float(np.sqrt(chi2 / (n * 9)))

            if p_value > settings.a1_p_threshold_concern:
                continue
            elif p_value > settings.a1_p_threshold_suspicious:
                severity = Severity.CONCERN
            elif p_value > 1e-20:
                severity = Severity.SUSPICIOUS
            else:
                severity = Severity.CRITICAL

            zero_five_ratio = (counts.get(0, 0) + counts.get(5, 0)) / n
            extra_note = ""
            if zero_five_ratio > 0.4:
                extra_note = (
                    f" 末位 0 和 5 合计占 {zero_five_ratio:.1%}"
                    f"（期望 20%），强烈提示人工编造。"
                )

            findings.append(
                Finding(
                    detector_id=self.id,
                    detector_name=self.name,
                    severity=severity,
                    summary=(
                        f"列 '{col}' 末位数字分布非均匀 "
                        f"(χ²={chi2:.2f}, p={p_value:.2e})"
                    ),
                    detail=(
                        f"对 {col} 列的 {n} 个数值提取末位有效数字，"
                        f"χ²(9) 拟合优度检验拒绝均匀分布假设。"
                        f"Cramér's V = {cramers_v:.3f}（效应量）。"
                        f"{extra_note}"
                    ),
                    p_value=p_value,
                    test_statistic=chi2,
                    test_name="χ²(9) goodness-of-fit",
                    effect_size=cramers_v,
                    evidence={
                        "column": str(col),
                        "n": n,
                        "frequency_table": {str(d): int(c) for d, c in counts.items()},
                        "expected_per_digit": n / 10,
                        "zero_five_ratio": zero_five_ratio,
                    },
                    innocent_explanations=[
                        "仪器量化（如显示步长为 0.05 的天平）",
                        "数据录入时人为四舍五入到特定精度",
                        "自报数据中的文化数字偏好（如体重、收入）",
                        "数据来源是计算值而非直接测量（公式可能限制了末位）",
                    ],
                    academic_reference=self.academic_basis,
                    applicability_notes=(
                        f"应用于 N={n} 的数值列。当 N ≥ 50 时检验最可靠。"
                    ),
                )
            )

        return findings
