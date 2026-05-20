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
    # 2.0.14 新加: 反向重建 + 对比
    reported_median: float | None = None
    reported_min: float | None = None
    reported_max: float | None = None


def _grim_passes(mean: float, n: int, decimals: int) -> bool:
    """GRIM: |mean × n - round(mean × n)| ≤ 0.5 × 10^-decimals × n."""
    implied = mean * n
    tol = 0.5 * (10**-decimals) * n
    return bool(abs(implied - round(implied)) <= tol)


def _enumerate_candidate_samples(
    mean: float,
    sd: float,
    n: int,
    scale_min: int,
    scale_max: int,
    max_samples: int = 200,
    seed: int = 42,
) -> list[tuple[int, ...]]:
    """SPRITE-style reverse reconstruction.

    Enumerate (or sample) candidate integer samples of size N on
    [scale_min, scale_max] whose mean and SD match the reported values
    within tolerance. Returns at most `max_samples` candidates.

    Heathers et al. (2018) SPRITE: starts from a uniform distribution
    sample, hill-climbs by swapping +1/-1 elements to converge to the
    target (mean, SD).
    """
    import random as _random

    if scale_max <= scale_min or n <= 1:
        return []

    target_sum = round(mean * n)
    target_var = sd * sd
    rng = _random.Random(seed)
    candidates: list[tuple[int, ...]] = []
    seen: set[tuple[int, ...]] = set()

    # Each restart hill-climbs to a local minimum of (Δmean² + Δsd²)
    max_restarts = min(max_samples * 5, 1000)
    for _ in range(max_restarts):
        if len(candidates) >= max_samples:
            break
        # Initial sample: uniform draw
        sample = [
            rng.randint(scale_min, scale_max) for _ in range(n)
        ]
        # Adjust sum first: shift random elements ±1 until sum matches
        for _step in range(n * 4):
            s = sum(sample)
            if s == target_sum:
                break
            if s < target_sum:
                idx = rng.randint(0, n - 1)
                if sample[idx] < scale_max:
                    sample[idx] += 1
            else:
                idx = rng.randint(0, n - 1)
                if sample[idx] > scale_min:
                    sample[idx] -= 1
        if sum(sample) != target_sum:
            continue
        # Now hill-climb SD via paired swaps that preserve sum
        for _step in range(n * 10):
            m = sum(sample) / n
            var = sum((x - m) ** 2 for x in sample) / (n - 1)
            err = abs(var - target_var)
            if err < 0.01:
                break
            # Swap one increase + one decrease (preserves sum)
            i = rng.randint(0, n - 1)
            j = rng.randint(0, n - 1)
            if i == j:
                continue
            if sample[i] >= scale_max or sample[j] <= scale_min:
                continue
            sample[i] += 1
            sample[j] -= 1
            m2 = sum(sample) / n
            var2 = sum((x - m2) ** 2 for x in sample) / (n - 1)
            err2 = abs(var2 - target_var)
            if err2 > err:
                # Reject; revert
                sample[i] -= 1
                sample[j] += 1
        final_m = sum(sample) / n
        final_var = sum((x - final_m) ** 2 for x in sample) / (n - 1)
        if abs(final_var - target_var) < 0.05:
            key = tuple(sorted(sample))
            if key not in seen:
                seen.add(key)
                candidates.append(key)
    return candidates


def _candidate_summary(
    candidates: list[tuple[int, ...]],
) -> dict[str, object]:
    """Compute the (min/max/median) implied by the candidate set."""
    if not candidates:
        return {}
    all_mins = [c[0] for c in candidates]
    all_maxes = [c[-1] for c in candidates]
    all_medians = []
    for c in candidates:
        n = len(c)
        all_medians.append(
            (c[n // 2 - 1] + c[n // 2]) / 2.0 if n % 2 == 0 else float(c[n // 2])
        )
    return {
        "n_candidates": len(candidates),
        "min_range": [min(all_mins), max(all_mins)],
        "max_range": [min(all_maxes), max(all_maxes)],
        "median_range": [min(all_medians), max(all_medians)],
    }


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

            # --- 2.0.14: reverse reconstruction + comparison ---
            # If user provided reported_median / min / max AND the
            # scale is bounded, enumerate candidate samples and check
            # whether ANY candidate matches the reported summary stats.
            recon_finding: Finding | None = None
            if (
                ok
                and item.scale_min is not None
                and item.scale_max is not None
                and (
                    item.reported_median is not None
                    or item.reported_min is not None
                    or item.reported_max is not None
                )
            ):
                candidates = _enumerate_candidate_samples(
                    item.mean,
                    item.sd,
                    item.n,
                    item.scale_min,
                    item.scale_max,
                    max_samples=50,
                    seed=seed,
                )
                if candidates:
                    summary = _candidate_summary(candidates)
                    mismatches: list[str] = []
                    median_range = summary.get("median_range")
                    if (
                        item.reported_median is not None
                        and isinstance(median_range, list)
                        and len(median_range) == 2
                    ):
                        lo_m = float(median_range[0])
                        hi_m = float(median_range[1])
                        if item.reported_median < lo_m or item.reported_median > hi_m:
                            mismatches.append(
                                f"reported median {item.reported_median} "
                                f"outside reconstructed [{lo_m}, {hi_m}]"
                            )
                    min_range = summary.get("min_range")
                    if (
                        item.reported_min is not None
                        and isinstance(min_range, list)
                        and len(min_range) == 2
                    ):
                        lo_n = float(min_range[0])
                        hi_n = float(min_range[1])
                        if item.reported_min < lo_n or item.reported_min > hi_n:
                            mismatches.append(
                                f"reported min {item.reported_min} "
                                f"outside reconstructed [{lo_n}, {hi_n}]"
                            )
                    max_range = summary.get("max_range")
                    if (
                        item.reported_max is not None
                        and isinstance(max_range, list)
                        and len(max_range) == 2
                    ):
                        lo_x = float(max_range[0])
                        hi_x = float(max_range[1])
                        if item.reported_max < lo_x or item.reported_max > hi_x:
                            mismatches.append(
                                f"reported max {item.reported_max} "
                                f"outside reconstructed [{lo_x}, {hi_x}]"
                            )
                    if mismatches:
                        recon_finding = Finding(
                            detector_id=self.id,
                            detector_name=self.name + " — reverse reconstruction",
                            severity=Severity.CRITICAL,
                            summary=(
                                f"{item.label or 'Reported'}: reconstructed "
                                f"samples (N={item.n} candidates) cannot "
                                "explain reported summary statistics"
                            ),
                            detail=(
                                "SPRITE-style enumeration produced "
                                f"{summary['n_candidates']} candidate "
                                "integer samples matching the reported "
                                f"mean and SD. However: "
                                + "; ".join(mismatches)
                                + ". A consistent dataset would have its "
                                "reported min/median/max fall inside the "
                                "ranges spanned by the reconstructed "
                                "candidates."
                            ),
                            evidence={
                                "label": item.label,
                                "mean": item.mean,
                                "sd": item.sd,
                                "n": item.n,
                                "reconstruction_summary": summary,
                                "mismatches": mismatches,
                            },
                            innocent_explanations=[
                                "Reported median/extremes come from a "
                                "different subset than mean/SD were "
                                "computed on",
                                "Outliers excluded before reporting "
                                "but not described in methods",
                                "Reconstruction failed to enumerate a "
                                "rare valid candidate (algorithm is "
                                "heuristic, not exhaustive)",
                                "Scale bounds were misspecified by the "
                                "user (try wider scale_min/scale_max)",
                            ],
                            academic_reference=(
                                "Heathers et al. (2018) SPRITE: "
                                "sample-recreation-via-iterative-tweaking. "
                                "Reverse enumeration + reported-stat "
                                "consistency check."
                            ),
                        )
            if recon_finding is not None:
                findings.append(recon_finding)

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
