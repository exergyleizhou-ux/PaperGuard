"""A3 — 列间固定算术关系检测。

学术依据：
- Mosimann fabrication heuristics (1995)
- 公开方法论：当两列数据互相独立测量时，它们的差/比应展示
  累积测量误差。若 σ(diff) ≪ 单测量噪声，则两列之间存在
  确定性关系。
"""
from __future__ import annotations

from itertools import combinations
from typing import ClassVar

import numpy as np
import pandas as pd

from paperguard.config import get_settings
from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity


class A3ArithmeticRelationDetector(BaseDetector):
    """检测列间是否存在精确的恒定差值或比值。"""

    id: ClassVar[str] = "A3"
    name: ClassVar[str] = "Inter-Column Arithmetic Relation"
    description: ClassVar[str] = "检测列间是否存在精确的恒定差值/比值。"
    academic_basis: ClassVar[str] = (
        "Mosimann et al. (1995) fabrication heuristics; "
        "independent measurements should accumulate noise in differences/ratios."
    )
    data_requirements: ClassVar[list[str]] = ["raw_numeric_values_multi_column"]
    assumption_cluster: ClassVar[str] = "inter_column_relation"

    def check_applicability(self, data: pd.DataFrame) -> tuple[bool, str]:
        if not isinstance(data, pd.DataFrame):
            return False, "Expected pd.DataFrame"
        settings = get_settings()
        numeric_cols = data.select_dtypes(include=[np.number]).columns
        if len(numeric_cols) < 2:
            return False, "需要至少 2 个数值列"
        if len(data) < settings.a3_min_rows:
            return False, f"需要至少 {settings.a3_min_rows} 行"
        return True, ""

    def _detect(self, data: pd.DataFrame, seed: int) -> list[Finding]:
        settings = get_settings()
        findings: list[Finding] = []
        numeric_cols = list(data.select_dtypes(include=[np.number]).columns)

        for col_a, col_b in combinations(numeric_cols, 2):
            common_idx = data[[col_a, col_b]].dropna().index
            a = data.loc[common_idx, col_a].to_numpy(dtype=float)
            b = data.loc[common_idx, col_b].to_numpy(dtype=float)
            n = len(a)
            if n < settings.a3_min_rows:
                continue

            # 检查 1：恒定差值
            diff = a - b
            diff_mean = float(np.mean(diff))
            diff_std = float(np.std(diff, ddof=1))
            mean_abs = max(abs(diff_mean), abs(float(np.mean(a))), 1.0)
            eps = max(
                settings.a3_eps_absolute,
                settings.a3_eps_relative * mean_abs,
            )

            if diff_std < eps:
                exact_matches = int(
                    np.sum(np.abs(diff - diff_mean) < settings.a3_eps_absolute)
                )
                match_ratio = exact_matches / n

                if match_ratio == 1.0:
                    severity = Severity.CRITICAL
                elif match_ratio >= 0.95:
                    severity = Severity.SUSPICIOUS
                else:
                    severity = Severity.CONCERN

                findings.append(
                    Finding(
                        detector_id=self.id,
                        detector_name=self.name,
                        severity=severity,
                        summary=(
                            f"列 '{col_a}' 与 '{col_b}' 存在恒定差值 "
                            f"{diff_mean:.4f}（精确度 σ={diff_std:.2e}）"
                        ),
                        detail=(
                            f"在 {n} 行数据中，{col_a} - {col_b} 的均值为 "
                            f"{diff_mean:.4f}，标准差仅 {diff_std:.2e}。"
                            f"{exact_matches}/{n} ({match_ratio:.1%}) 行完全精确成立。"
                            f"真实独立测量的列间差值应表现出测量误差累积，"
                            f"标准差不应低于单次测量噪声的 √2 倍。"
                        ),
                        p_value=None,
                        test_statistic=diff_std,
                        test_name="σ(difference)",
                        evidence={
                            "col_a": str(col_a),
                            "col_b": str(col_b),
                            "n": n,
                            "diff_mean": diff_mean,
                            "diff_std": diff_std,
                            "exact_match_count": exact_matches,
                            "exact_match_ratio": match_ratio,
                            "epsilon_used": eps,
                        },
                        innocent_explanations=[
                            f"实验设计中存在确定性计算（如 {col_b} = {col_a} + 校正值）",
                            f"数据录入时使用了电子表格公式（如 ={col_a}单元格 + 常数）",
                            "仪器有固定的零点校准偏移",
                            "其中一列是从另一列派生而非独立测量",
                        ],
                        academic_reference=self.academic_basis,
                    )
                )

            # 检查 2：恒定比值
            if np.all(np.abs(b) > 1e-12):
                ratio = a / b
                ratio_mean = float(np.mean(ratio))
                ratio_std = float(np.std(ratio, ddof=1))
                ratio_eps = max(1e-9, settings.a3_eps_relative * abs(ratio_mean))

                if ratio_std < ratio_eps and ratio_mean != 1.0:
                    exact = int(np.sum(np.abs(ratio - ratio_mean) < 1e-9))
                    match_ratio = exact / n
                    if match_ratio >= 0.95:
                        severity = Severity.SUSPICIOUS
                    else:
                        severity = Severity.CONCERN

                    findings.append(
                        Finding(
                            detector_id=self.id,
                            detector_name=self.name + " (ratio)",
                            severity=severity,
                            summary=(
                                f"列 '{col_a}' / '{col_b}' 存在恒定比值 "
                                f"{ratio_mean:.6f}"
                            ),
                            detail=(
                                f"{exact}/{n} 行的比值精确为 {ratio_mean:.6f}。"
                                f"真实独立测量不应有如此一致的比值。"
                            ),
                            test_statistic=ratio_std,
                            test_name="σ(ratio)",
                            evidence={
                                "col_a": str(col_a),
                                "col_b": str(col_b),
                                "ratio_mean": ratio_mean,
                                "ratio_std": ratio_std,
                                "exact_match_ratio": match_ratio,
                            },
                            innocent_explanations=[
                                "化学计量比或物理常数",
                                "归一化操作（如百分比转换）",
                                "其中一列是另一列乘以常数得到",
                            ],
                            academic_reference=self.academic_basis,
                        )
                    )

        return findings
