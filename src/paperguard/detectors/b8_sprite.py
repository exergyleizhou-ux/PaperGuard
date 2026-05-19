"""B8 — SPRITE (Sample Parameter Reconstruction via Iterative TEchniques)。

学术依据：
Heathers, Anaya, van der Zee & Brown (2018) "Recovering data from
summary statistics: Sample Parameter Reconstruction via Iterative
Techniques (SPRITE)." PeerJ Preprints.

原理：给定 (mean, SD, N, scale_min, scale_max)，随机搜索能产生这些
统计量的整数样本。如果**不存在**这样的样本，报告值是数学上不可能的；
如果存在但极少（< K 种构造），分布形态被严重约束（可疑）。

简化实现：
- 计算 SS = N × (SD² + mean²)
- 用贪婪搜索尝试构造整数样本
- 找到 ≥ N_attempt 次成功 → consistent
- 完全找不到 → inconsistent → SUSPICIOUS+
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, ClassVar

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity


@dataclass
class SPRITEInput:
    mean: float
    sd: float
    n: int
    scale_min: int
    scale_max: int
    mean_decimals: int = 2
    sd_decimals: int = 2
    n_attempts: int = 200
    label: str = ""


def _try_construct(
    target_mean: float,
    target_sd: float,
    n: int,
    lo: int,
    hi: int,
    mean_tol: float,
    sd_tol: float,
    rng: random.Random,
) -> list[int] | None:
    """随机贪婪：构造一组 [lo, hi] 内整数使其 mean/sd 命中容差。

    简化实现，不是严格 SPRITE 完整算法，而是足以做 SUSPICIOUS 信号：
    """
    # 起点：所有都等于 round(mean)
    initial = round(target_mean)
    sample = [max(lo, min(hi, initial))] * n
    # 随机扰动直到 mean+sd 都满足容差或迭代上限
    max_iter = 800
    for _ in range(max_iter):
        m = sum(sample) / n
        s = (sum((x - m) ** 2 for x in sample) / (n - 1)) ** 0.5
        if abs(m - target_mean) <= mean_tol and abs(s - target_sd) <= sd_tol:
            return sample
        # 选一个值上下移
        idx = rng.randint(0, n - 1)
        old = sample[idx]
        # 根据当前误差方向选择移动
        if m < target_mean and old < hi:
            sample[idx] = old + 1
        elif m > target_mean and old > lo:
            sample[idx] = old - 1
        else:
            # 调 SD：把一个值往极端推
            far_idx = max(range(n), key=lambda i: abs(sample[i] - target_mean))
            if s < target_sd and sample[far_idx] > lo and sample[far_idx] < hi:
                if sample[far_idx] >= target_mean:
                    sample[far_idx] = min(hi, sample[far_idx] + 1)
                else:
                    sample[far_idx] = max(lo, sample[far_idx] - 1)
            elif s > target_sd:
                # 把最极端的拉回均值
                if sample[far_idx] > target_mean:
                    sample[far_idx] -= 1
                else:
                    sample[far_idx] += 1
    return None


class B8SPRITEDetector(BaseDetector):
    """SPRITE: 检查 (mean, SD, N) 是否能由 [lo, hi] 整数实现。"""

    id: ClassVar[str] = "B8"
    name: ClassVar[str] = "SPRITE plausibility"
    description: ClassVar[str] = (
        "对 bounded-scale 整数数据，验证 (mean, SD, N) 是否可由真实样本生成。"
    )
    academic_basis: ClassVar[str] = (
        "Heathers, Anaya, van der Zee & Brown (2018) SPRITE: "
        "Recovering data from summary statistics."
    )
    data_requirements: ClassVar[list[str]] = ["reported_mean_sd_n_scale"]
    assumption_cluster: ClassVar[str] = "summary_statistic_consistency"

    def check_applicability(self, data: Any) -> tuple[bool, str]:
        if not isinstance(data, list):
            return False, "Expected list[SPRITEInput]"
        if not all(isinstance(x, SPRITEInput) for x in data):
            return False, "All items must be SPRITEInput"
        if not data:
            return False, "Empty input"
        return True, ""

    def _detect(self, data: list[SPRITEInput], seed: int) -> list[Finding]:
        rng = random.Random(seed)
        findings: list[Finding] = []
        for item in data:
            if item.n <= 1 or item.scale_max <= item.scale_min:
                continue
            mean_tol = 0.5 * (10 ** -item.mean_decimals)
            sd_tol = 0.5 * (10 ** -item.sd_decimals)

            # 尝试少量构造
            successes = 0
            attempts = min(item.n_attempts, 50)
            for _ in range(attempts):
                result = _try_construct(
                    item.mean, item.sd, item.n,
                    item.scale_min, item.scale_max,
                    mean_tol, sd_tol, rng,
                )
                if result is not None:
                    successes += 1
                    break  # 找到一个就足够说明 plausible

            if successes > 0:
                continue

            findings.append(
                Finding(
                    detector_id=self.id,
                    detector_name=self.name,
                    severity=Severity.SUSPICIOUS,
                    summary=(
                        f"{item.label or 'Reported'} (mean={item.mean}, "
                        f"SD={item.sd}, N={item.n}, scale=[{item.scale_min},"
                        f"{item.scale_max}]) — SPRITE could not construct"
                        " a valid integer sample"
                    ),
                    detail=(
                        f"在 [{item.scale_min}, {item.scale_max}] 整数尺度上，"
                        f"经 {attempts} 次随机构造均未找到 mean ≈ {item.mean} "
                        f"（容差 {mean_tol}）且 SD ≈ {item.sd}（容差 "
                        f"{sd_tol}）的样本。这说明报告值在数学上不可能 "
                        f"或几乎不可能由 N = {item.n} 个量表取值生成。"
                    ),
                    test_statistic=float(successes),
                    test_name="SPRITE constructions found",
                    evidence={
                        "label": item.label,
                        "mean": item.mean,
                        "sd": item.sd,
                        "n": item.n,
                        "scale_min": item.scale_min,
                        "scale_max": item.scale_max,
                        "attempts": attempts,
                        "successes": successes,
                    },
                    innocent_explanations=[
                        "Reported decimal precision is lower than the true "
                        "statistics (try smaller tolerances)",
                        "Sample N is misreported",
                        "Data is not actually integer-valued (continuous)",
                        "Reconstruction is a heuristic random walk; may "
                        "fail to find rare valid samples (false negative)",
                    ],
                    academic_reference=self.academic_basis,
                )
            )
        return findings
