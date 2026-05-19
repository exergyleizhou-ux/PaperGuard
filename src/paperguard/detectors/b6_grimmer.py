"""B6 — GRIMMER (Granularity-Related Inconsistency of Means Mapped to Error Repeats)。

学术依据：
Anaya (2016). The GRIMMER test: A method for testing the validity of reported
measures of variability. PeerJ Preprints.
Allard (2018). Analytic-GRIMMER algorithm.

GRIMMER 扩展 GRIM：
- GRIM 检查"报告的 mean 是否可能由 N 个整数总和除以 N 得到"
- GRIMMER 额外检查"报告的 SD 是否能由这些整数实现"

算法（Allard 2018 简化版）：
1. 先跑 GRIM；不通过 → GRIMMER 也不通过
2. 由 mean × N 反推整数总和 S = round(mean × N)
3. 用 SD 反推平方和 SS = (N-1) × SD² + N × mean²
4. 检查 SS 是否能由若干整数实现（必须为整数 ± 0.5 × N 等容差）

注意：仅适用整数数据（Likert、计数）。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, ClassVar

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity


@dataclass
class GRIMMERInput:
    mean: float
    sd: float
    n: int
    mean_decimals: int = 2
    sd_decimals: int = 2
    scale_min: int | None = None  # Likert 量表下限（如 1）
    scale_max: int | None = None  # Likert 量表上限（如 7）
    label: str = ""


def _grim_passes(mean: float, n: int, decimals: int) -> bool:
    """GRIM: |mean × n - round(mean × n)| ≤ 0.5 × 10^-decimals × n."""
    implied = mean * n
    tol = 0.5 * (10**-decimals) * n
    return bool(abs(implied - round(implied)) <= tol)


def _grimmer_passes(
    mean: float,
    sd: float,
    n: int,
    mean_decimals: int,
    sd_decimals: int,
    scale_min: int | None,
    scale_max: int | None,
) -> tuple[bool, str]:
    """简化版 GRIMMER：检查报告的 SD 是否与 GRIM-一致的整数总和兼容。

    Returns:
        (passes, reason_if_fail)
    """
    if not _grim_passes(mean, n, mean_decimals):
        return False, "GRIM 已不通过"

    # 反推整数总和
    integer_sum = round(mean * n)
    # 反推平方和：variance = SS/N - mean²  →  SS = N × (var + mean²)
    var = sd * sd
    implied_ss = n * (var + mean * mean)
    rounded_ss = round(implied_ss)

    # 容差：来自 mean 和 SD 两端的舍入
    mean_tol = 0.5 * (10**-mean_decimals)
    sd_tol = 0.5 * (10**-sd_decimals)
    # SS 的最大可能变动量约为 N × (2|mean|×mean_tol + 2×sd×sd_tol)
    ss_tol = n * (2 * abs(mean) * mean_tol + 2 * sd * sd_tol) + 1.0

    if abs(implied_ss - rounded_ss) > ss_tol:
        return False, (
            f"SS_implied = {implied_ss:.4f}; 最近整数 {rounded_ss}; "
            f"差距 {abs(implied_ss - rounded_ss):.4f} > 容差 {ss_tol:.4f}"
        )

    # Bounded-scale 检查：如果给了量表范围，检查总和是否能由 [min..max] 整数实现
    if scale_min is not None and scale_max is not None:
        min_sum = scale_min * n
        max_sum = scale_max * n
        if integer_sum < min_sum or integer_sum > max_sum:
            return False, (
                f"反推总和 {integer_sum} 超出量表范围 "
                f"[{min_sum}, {max_sum}]"
            )

    return True, ""


class B6GRIMMERDetector(BaseDetector):
    """GRIMMER: 检查整数数据的 mean+SD+N 三元组是否数学上可能。"""

    id: ClassVar[str] = "B6"
    name: ClassVar[str] = "GRIMMER Test"
    description: ClassVar[str] = (
        "整数数据的 (mean, SD, N) 三元组必须能由整数样本实现。"
    )
    academic_basis: ClassVar[str] = (
        "Anaya (2016). The GRIMMER test. PeerJ Preprints. "
        "Allard (2018) Analytic-GRIMMER algorithm."
    )
    data_requirements: ClassVar[list[str]] = ["reported_mean_sd_n_triples"]
    assumption_cluster: ClassVar[str] = "summary_statistic_consistency"

    def check_applicability(self, data: Any) -> tuple[bool, str]:
        if not isinstance(data, list):
            return False, "Expected list[GRIMMERInput]"
        if not all(isinstance(x, GRIMMERInput) for x in data):
            return False, "All items must be GRIMMERInput"
        if not data:
            return False, "Empty input"
        return True, ""

    def _detect(self, data: list[GRIMMERInput], seed: int) -> list[Finding]:
        findings: list[Finding] = []
        for item in data:
            if item.n <= 1 or item.sd <= 0:
                continue
            ok, reason = _grimmer_passes(
                item.mean,
                item.sd,
                item.n,
                item.mean_decimals,
                item.sd_decimals,
                item.scale_min,
                item.scale_max,
            )
            if ok:
                continue
            # GRIM-only failure vs GRIMMER-only failure
            grim_ok = _grim_passes(item.mean, item.n, item.mean_decimals)
            severity = (
                Severity.SUSPICIOUS if not grim_ok else Severity.CONCERN
            )
            findings.append(
                Finding(
                    detector_id=self.id,
                    detector_name=self.name,
                    severity=severity,
                    summary=(
                        f"{item.label or 'Reported'}：mean={item.mean}, "
                        f"SD={item.sd}, N={item.n} GRIMMER 不一致 ({reason})"
                    ),
                    detail=(
                        f"对报告统计量 mean={item.mean}（{item.mean_decimals} 位小数）, "
                        f"SD={item.sd}（{item.sd_decimals} 位小数）, N={item.n} "
                        "做 GRIMMER 检验。"
                        + (
                            "GRIM 已不通过——基础均值就不可能由 N 个整数得到。"
                            if not grim_ok
                            else f"GRIM 通过但 SD 不一致：{reason}"
                        )
                    ),
                    test_statistic=float(item.sd) if math.isfinite(item.sd) else None,
                    test_name="GRIMMER",
                    evidence={
                        "label": item.label,
                        "mean": item.mean,
                        "sd": item.sd,
                        "n": item.n,
                        "grim_passes": grim_ok,
                        "grimmer_reason": reason,
                    },
                    innocent_explanations=[
                        "样本量 N 报告错误（实际 N 与文中描述不一致）",
                        "排除了某些 outlier 但未声明",
                        "数据不是整数（GRIMMER 不适用——调用者应自行确认）",
                        "Mean 或 SD 在打印时小数位被错误截断",
                    ],
                    academic_reference=self.academic_basis,
                )
            )
        return findings
