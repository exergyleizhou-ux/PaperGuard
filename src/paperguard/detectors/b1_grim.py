"""B1 — GRIM (Granularity-Related Inconsistency of Means).

学术依据：
Brown & Heathers (2017). The GRIM Test: A simple technique detects
numerous anomalies in the reporting of results in psychology.
Social Psychological and Personality Science, 8(4), 363-369.

输入：报告的均值 mean、样本量 N、小数位数 decimal_places。
输出：mean × N 是否能合理对应一个整数总和。

注意：GRIM 仅适用于"整数数据的均值"（如 Likert 量表）。
本实现要求调用者明确声明这是整数数据。
"""
from __future__ import annotations

from typing import Any, ClassVar

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity


class GRIMInput:
    """GRIM 检测的输入结构。"""

    def __init__(
        self,
        mean: float,
        n: int,
        decimal_places: int,
        scale_items: int = 1,
        label: str = "",
    ) -> None:
        self.mean = mean
        self.n = n
        self.decimal_places = decimal_places
        self.scale_items = scale_items
        self.label = label


class B1GRIMDetector(BaseDetector):
    """报告的整数数据均值必须能由整数总和除以 N 得到。"""

    id: ClassVar[str] = "B1"
    name: ClassVar[str] = "GRIM Test"
    description: ClassVar[str] = "整数数据的报告均值必须能由整数总和除以 N 得到。"
    academic_basis: ClassVar[str] = (
        "Brown & Heathers (2017). The GRIM Test. "
        "Social Psychological and Personality Science, 8(4), 363-369."
    )
    data_requirements: ClassVar[list[str]] = ["reported_means_with_n"]
    assumption_cluster: ClassVar[str] = "summary_statistic_consistency"

    def check_applicability(self, data: Any) -> tuple[bool, str]:
        if not isinstance(data, list):
            return False, "Expected list[GRIMInput]"
        if not all(isinstance(x, GRIMInput) for x in data):
            return False, "All items must be GRIMInput instances"
        if len(data) == 0:
            return False, "Empty input list"
        return True, ""

    def _detect(self, data: list[GRIMInput], seed: int) -> list[Finding]:
        findings: list[Finding] = []

        for item in data:
            mean = item.mean
            n = item.n
            decimals = item.decimal_places
            items = item.scale_items
            effective_n = n * items

            implied_sum = mean * effective_n
            tolerance = 0.5 * (10**-decimals) * effective_n

            nearest_int = round(implied_sum)
            error = abs(implied_sum - nearest_int)

            grim_inconsistent = error > tolerance

            if grim_inconsistent:
                violation_ratio = error / tolerance if tolerance > 0 else float("inf")

                if violation_ratio > 10:
                    severity = Severity.SUSPICIOUS
                else:
                    severity = Severity.CONCERN

                findings.append(
                    Finding(
                        detector_id=self.id,
                        detector_name=self.name,
                        severity=severity,
                        summary=(
                            f"{item.label or 'Reported mean'}={mean} with N={n} "
                            f"violates GRIM (sum error {error:.4f} > tol {tolerance:.4f})"
                        ),
                        detail=(
                            f"报告均值 {mean}（{decimals} 位小数）× N={effective_n} "
                            f"= {implied_sum:.6f}，最接近整数为 {nearest_int}，"
                            f"差距 {error:.6f}。允许的舍入容差为 {tolerance:.6f}。"
                            f"在整数数据假设下，该均值不可能由 N={n} 个整数得到。"
                        ),
                        p_value=None,
                        test_statistic=error,
                        test_name="GRIM sum error",
                        evidence={
                            "label": item.label,
                            "mean": mean,
                            "n": n,
                            "scale_items": items,
                            "decimal_places": decimals,
                            "implied_sum": implied_sum,
                            "nearest_integer": nearest_int,
                            "error": error,
                            "tolerance": tolerance,
                            "violation_ratio": violation_ratio,
                        },
                        innocent_explanations=[
                            "样本量报告错误（实际 N 与文中描述不一致）",
                            "排除了某些数据点但未声明",
                            "均值是从子集计算的（如缺失数据剔除）",
                            "数据不是整数（GRIM 不适用 — 调用者错误）",
                        ],
                        academic_reference=self.academic_basis,
                    )
                )

        return findings
