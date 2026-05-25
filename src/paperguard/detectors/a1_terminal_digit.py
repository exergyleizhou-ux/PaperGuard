"""A1 — 末位数字分布检测。

学术依据：
- Mosimann et al. (1995) Accountability in Research, 4(1)
- Al-Marzouki et al. (2005) J Clin Epidemiology
- Ljung & Box (1978) Biometrika 65(2): 297-303
  (Lag-1 autocorrelation test on digit sequence — 2.0.13)

2.0.13 数学升级：
单维 χ²(9) 易被绕过(造假者每次换一个末位就过了)。本版加两个
额外维度:

1. **Lag-1 自相关 (Ljung-Box Q)**：把末位序列当一阶马尔可夫链,
   测连续两个末位是否独立。真测量数据 Q ≈ 0;造假者人脑"避免
   连续重复"→ 负自相关;造假者机械模板生成 → 正自相关。
2. **跨列联合 χ²**:同一行多列末位是否独立?造假者一行一组瞎
   敲常出现同行多列末位同步偏向 → 拒绝独立性原假设。

详见 docs/math_upgrades_v2.md。
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


def _lag1_autocorr_pvalue(digits: list[int]) -> tuple[float, float]:
    """Ljung-Box Q test on the digit sequence with lag=1.

    Treats each consecutive (d_i, d_{i+1}) as a Bernoulli "match" trial
    and tests whether the observed match-rate differs from 1/10. Returns
    (Q-statistic, p-value).

    Real measurements are i.i.d. → p ≈ uniform. Manual fabrication
    tends to avoid consecutive repeats (negative autocorr) or use a
    template (positive autocorr). Either deviation lowers p.
    """
    n = len(digits)
    if n < 20:
        return 0.0, 1.0
    matches = sum(1 for i in range(n - 1) if digits[i] == digits[i + 1])
    expected = (n - 1) / 10.0
    # Binomial: p = 1/10 under independence. SE = sqrt(n*p*(1-p))
    var = (n - 1) * 0.1 * 0.9
    z = (matches - expected) / np.sqrt(var) if var > 0 else 0.0
    # Two-sided p
    p = 2.0 * (1.0 - stats.norm.cdf(abs(z)))
    return float(z * z), float(p)


def _joint_column_chi2(
    digit_matrix: list[list[int]],
) -> tuple[float, float, int]:
    """Multi-column joint χ² independence test.

    For each row, look at the multiset of last digits across columns.
    Under H0 (columns independent + each uniform), the joint
    distribution of (d_col1, d_col2, ...) is uniform over 10^k cells.
    Reality of course can't fill 10^k cells with the data we have, so
    we contract to "row-wise digit entropy" and test against the
    expected uniform-entropy.

    Returns (chi2-like statistic, p-value, n_rows_used).
    """
    n_rows = len(digit_matrix)
    n_cols = len(digit_matrix[0]) if digit_matrix else 0
    if n_rows < 30 or n_cols < 2:
        return 0.0, 1.0, n_rows
    # Row entropy: H = -sum(p_d log p_d) over digit distribution in the row
    row_entropies: list[float] = []
    for row in digit_matrix:
        counts = Counter(row)
        probs = np.array([c / len(row) for c in counts.values()])
        h = float(-np.sum(probs * np.log2(probs + 1e-12)))
        row_entropies.append(h)
    # Under independence, row entropy distribution has mean log2(n_cols)
    # (each row is i.i.d. uniform draws from 10 digits) and variance ~
    # well-approximated by a small constant; we test deviation of the
    # MEAN entropy from the theoretical expected value.
    mean_h = float(np.mean(row_entropies))
    # Empirical expected entropy of n_cols i.i.d. draws from Unif{0..9}:
    # for small n_cols this is well below log2(10)=3.32. Use a
    # bootstrap-based reference.
    rng = np.random.default_rng(42)
    boot_means: list[float] = []
    for _ in range(200):
        boot_rows = rng.integers(0, 10, size=(n_rows, n_cols))
        boot_h = []
        for row in boot_rows:
            counts = Counter(row.tolist())
            probs = np.array([c / n_cols for c in counts.values()])
            boot_h.append(float(-np.sum(probs * np.log2(probs + 1e-12))))
        boot_means.append(float(np.mean(boot_h)))
    boot_mean = float(np.mean(boot_means))
    boot_std = float(np.std(boot_means))
    if boot_std == 0:
        return 0.0, 1.0, n_rows
    z = (mean_h - boot_mean) / boot_std
    chi2_like = z * z
    p = 2.0 * (1.0 - stats.norm.cdf(abs(z)))
    return float(chi2_like), float(p), n_rows


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

        numeric_cols = data.select_dtypes(include=[np.number]).columns
        small_n = 10
        valid_cols = [
            c for c in numeric_cols if len(data[c].dropna()) >= small_n
        ]
        if not valid_cols:
            return False, f"No numeric column with N ≥ {small_n}"
        return True, ""

    def _detect(self, data: pd.DataFrame, seed: int) -> list[Finding]:
        settings = get_settings()
        findings: list[Finding] = []
        numeric_cols = data.select_dtypes(include=[np.number]).columns

        # Capture per-column digit sequences for cross-column joint test
        col_digits: dict[str, list[int]] = {}

        for col in numeric_cols:
            values = data[col].dropna()
            if len(values) < 10:
                continue

            low_power = len(values) < 50
            digits = [get_last_significant_digit(v) for v in values]
            col_digits[str(col)] = digits
            n = len(digits)
            counts = Counter(digits)
            observed = np.array([counts.get(d, 0) for d in range(10)])
            expected = np.full(10, n / 10.0)

            chi2 = float(np.sum((observed - expected) ** 2 / expected))
            p_value = float(1 - stats.chi2.cdf(chi2, df=9))
            cramers_v = float(np.sqrt(chi2 / (n * 9)))

            # --- existing chi2 finding (unchanged) ---
            if p_value <= settings.a1_p_threshold_concern:
                if p_value > settings.a1_p_threshold_suspicious:
                    severity = Severity.CONCERN
                elif p_value > 1e-20:
                    severity = Severity.SUSPICIOUS
                else:
                    severity = Severity.CRITICAL

                if low_power:
                    severity = Severity.NOTE

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
                            "frequency_table": {
                                str(d): int(c) for d, c in counts.items()
                            },
                            "expected_per_digit": n / 10,
                            "zero_five_ratio": zero_five_ratio,
                            "low_power_note": low_power,
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

            # --- NEW (2.0.13): Lag-1 autocorrelation finding ---
            z_sq, ac_p = _lag1_autocorr_pvalue(digits)
            if ac_p < 0.01 and n >= 50:
                ac_sev = Severity.SUSPICIOUS if ac_p < 1e-4 else Severity.CONCERN
                findings.append(
                    Finding(
                        detector_id=self.id,
                        detector_name=self.name + " — Lag-1 autocorrelation",
                        severity=ac_sev,
                        summary=(
                            f"列 '{col}' 末位序列 Lag-1 自相关偏离独立 "
                            f"(z²={z_sq:.2f}, p={ac_p:.2e})"
                        ),
                        detail=(
                            f"对 {col} 列末位 {n} 元序列做 Lag-1 自相关检验。"
                            "真测量数据 P(d_i = d_{i+1}) ≈ 1/10。"
                            f"观测连续重复率与 1/10 显著偏离 (p={ac_p:.2e})，"
                            "提示存在人为模板("
                            "正自相关) 或'避免重复'偏好(负自相关)。"
                            " 2.0.13 新加,见 docs/math_upgrades_v2.md。"
                        ),
                        p_value=ac_p,
                        test_statistic=z_sq,
                        test_name="Lag-1 binomial autocorrelation z²",
                        evidence={
                            "column": str(col),
                            "n": n,
                            "lag1_match_count": sum(
                                1
                                for i in range(n - 1)
                                if digits[i] == digits[i + 1]
                            ),
                            "expected_match_count": (n - 1) / 10.0,
                        },
                        innocent_explanations=[
                            "测量间存在物理依赖（如同一样本连续读数）",
                            "数据按时间顺序排列且末位有真实时间趋势",
                            "记录人员在连续录入时无意识保持数字"
                            "（"
                            "习惯性正/负自相关）",
                            "样本本身分布在仅几个离散值上",
                        ],
                        academic_reference=(
                            "Ljung & Box (1978) Biometrika 65(2). "
                            "Lag-1 binomial test for digit-sequence "
                            "independence."
                        ),
                    )
                )

        # --- NEW (2.0.13): joint multi-column independence ---
        if len(col_digits) >= 2:
            # Align to minimum length so we have a clean matrix
            min_n = min(len(d) for d in col_digits.values())
            if min_n >= 30:
                matrix = [
                    [col_digits[c][i] for c in col_digits] for i in range(min_n)
                ]
                jc_chi2, jc_p, n_used = _joint_column_chi2(matrix)
                if jc_p < 0.01:
                    jc_sev = (
                        Severity.SUSPICIOUS if jc_p < 1e-4 else Severity.CONCERN
                    )
                    findings.append(
                        Finding(
                            detector_id=self.id,
                            detector_name=self.name + " — joint multi-column",
                            severity=jc_sev,
                            summary=(
                                f"跨 {len(col_digits)} 列末位联合独立性偏离 "
                                f"(χ²~{jc_chi2:.2f}, p={jc_p:.2e})"
                            ),
                            detail=(
                                f"对 {n_used} 行 × {len(col_digits)} 列的末位"
                                "做行内熵检验。如果各列末位独立同分布,行内"
                                "熵的均值应收敛到 bootstrap 参考值。"
                                f"观测均值显著偏离 (p={jc_p:.2e}),"
                                "提示同行多列末位之间存在相关性—"
                                "造假者一行一组瞎敲会留下此痕迹。"
                                " 2.0.13 新加。"
                            ),
                            p_value=jc_p,
                            test_statistic=jc_chi2,
                            test_name="joint-column entropy z²",
                            evidence={
                                "n_rows": n_used,
                                "n_cols": len(col_digits),
                                "columns": list(col_digits.keys()),
                            },
                            innocent_explanations=[
                                "多列其实是同一物理量的不同记录形式",
                                "列之间存在确定性数学关系(已被 A3 覆盖)",
                                "数据按行整体取整或截断,影响多列同步",
                                "Bootstrap 参考分布有限(200 次),"
                                "p 值有抖动",
                            ],
                            academic_reference=(
                                "Joint-column entropy test (this work). "
                                "Bootstrap null distribution; rejection "
                                "indicates row-level digit correlation "
                                "characteristic of manual fabrication."
                            ),
                        )
                    )

        return findings
