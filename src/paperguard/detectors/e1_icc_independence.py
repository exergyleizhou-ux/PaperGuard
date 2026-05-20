"""E1 — Intra-Class Correlation (ICC) independence test.

学术依据：
- Simonsohn, D. (2013). Just post it: The lesson from two cases of
  fabricated data detected by statistics alone. Psychological
  Science, 24(10), 1875-1888.
- Heathers, J. (2024). Intraclass Correlation Pattern: Detecting
  repeated-measures fabrication. Open Science draft.

策略:
报告"30 只小鼠,每只测 4 次"=> 120 个值之间应该有 within-subject 相关
(同只小鼠的 4 次测量比不同小鼠的测量更相似)。ICC 量化这个相关。

- 真生物学重复测量: ICC 通常 0.2 – 0.9(因变量决定)
- np.random.normal() 生成的"小鼠数据": ICC ≈ 0(每个值独立同分布)

输入需要一个表明 subject 的列(如 "Mouse_ID" / "Subject" / "Animal")。

数学:
  ICC(1) = (MS_between - MS_within) / (MS_between + (k-1)*MS_within)
其中 k = 每个 subject 的重复次数,
     MS_between = 组间均方,
     MS_within = 组内均方。

ICC < 0.05 + 重复次数 k≥3 + subjects 数 ≥ 5 → SUSPICIOUS
ICC < 0.01 → CRITICAL
"""
from __future__ import annotations

from typing import ClassVar

import numpy as np
import pandas as pd

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity

# Heuristic column names that suggest a subject / cluster identifier
_SUBJECT_COL_HINTS = (
    "subject",
    "subject_id",
    "mouse",
    "mouse_id",
    "rat",
    "rat_id",
    "animal",
    "animal_id",
    "participant",
    "participant_id",
    "patient",
    "patient_id",
    "id",
    "cluster",
    "cluster_id",
    "site",
    "site_id",
    "lab",
    "lab_id",
)


def _detect_subject_column(df: pd.DataFrame) -> str | None:
    """Look for a column likely to be a subject identifier.

    Heuristic:
    - Lowercase column name matches a hint
    - Has 2 < n_unique < n_rows / 2 (genuine cluster structure)
    """
    for col in df.columns:
        if str(col).strip().lower() in _SUBJECT_COL_HINTS:
            n_unique = df[col].nunique(dropna=True)
            if 2 < n_unique < len(df) / 2:
                return str(col)
    return None


def _compute_icc1(
    df: pd.DataFrame, subject_col: str, value_col: str
) -> tuple[float | None, int, int]:
    """ICC(1) — one-way random-effects model.

    Returns (icc, n_subjects, mean_k) or (None, n_subjects, k) when
    insufficient data.
    """
    groups = df.groupby(subject_col)[value_col].apply(list)
    n_subjects = len(groups)
    if n_subjects < 5:
        return None, n_subjects, 0
    # Require each subject to have ≥ 2 observations (repeated measure)
    valid_groups = [g for g in groups if len(g) >= 2]
    if len(valid_groups) < 3:
        return None, n_subjects, 0
    sizes = [len(g) for g in valid_groups]
    mean_k = int(round(float(np.mean(sizes))))
    grand_mean = float(np.mean([x for g in valid_groups for x in g]))

    # Between-group sum of squares
    ss_between = sum(
        len(g) * (float(np.mean(g)) - grand_mean) ** 2 for g in valid_groups
    )
    df_between = len(valid_groups) - 1
    ms_between = ss_between / df_between if df_between > 0 else 0.0

    # Within-group sum of squares
    ss_within = sum(
        sum((x - float(np.mean(g))) ** 2 for x in g) for g in valid_groups
    )
    df_within = sum(sizes) - len(valid_groups)
    ms_within = ss_within / df_within if df_within > 0 else 0.0

    if ms_between + (mean_k - 1) * ms_within <= 0:
        return 0.0, len(valid_groups), mean_k
    icc = (ms_between - ms_within) / (ms_between + (mean_k - 1) * ms_within)
    return float(icc), len(valid_groups), mean_k


class E1ICCIndependenceDetector(BaseDetector):
    """Repeated-measures independence violation via ICC."""

    id: ClassVar[str] = "E1"
    name: ClassVar[str] = "Intra-Class Correlation Independence"
    description: ClassVar[str] = (
        "对带 subject/cluster 列的数据检 ICC。ICC ≈ 0 + 多次重复测量 → "
        "可疑(独立性违反 Heathers 2024 ICRP)。"
    )
    academic_basis: ClassVar[str] = (
        "Simonsohn (2013) Psychol Sci 24(10); "
        "Heathers (2024) ICRP: Intraclass Correlation Pattern for "
        "repeated-measures fabrication detection."
    )
    data_requirements: ClassVar[list[str]] = [
        "subject_id_column",
        "repeated_measures",
    ]
    assumption_cluster: ClassVar[str] = "within_subject_dependence"

    MIN_SUBJECTS: ClassVar[int] = 5
    MIN_K: ClassVar[int] = 3
    ICC_SUSPICIOUS: ClassVar[float] = 0.05
    ICC_CRITICAL: ClassVar[float] = 0.01

    def check_applicability(self, data: pd.DataFrame) -> tuple[bool, str]:
        if not isinstance(data, pd.DataFrame):
            return False, "Expected pd.DataFrame"
        subject_col = _detect_subject_column(data)
        if subject_col is None:
            return False, "未识别 subject/cluster 列(列名需含 subject/mouse/rat/etc)"
        numeric_cols = list(
            data.select_dtypes(include=[np.number]).columns
        )
        if subject_col in numeric_cols:
            numeric_cols.remove(subject_col)
        if not numeric_cols:
            return False, "无数值列做 ICC"
        # Quick check that the column has enough cluster structure
        n_unique = data[subject_col].nunique(dropna=True)
        if n_unique < self.MIN_SUBJECTS:
            return False, f"subject 列只有 {n_unique} 个 unique 值 < {self.MIN_SUBJECTS}"
        return True, ""

    def _detect(self, data: pd.DataFrame, seed: int) -> list[Finding]:
        findings: list[Finding] = []
        subject_col = _detect_subject_column(data)
        if subject_col is None:
            return findings
        numeric_cols = list(
            data.select_dtypes(include=[np.number]).columns
        )
        if subject_col in numeric_cols:
            numeric_cols.remove(subject_col)

        for col in numeric_cols:
            sub = data[[subject_col, col]].dropna()
            icc, n_subj, mean_k = _compute_icc1(sub, subject_col, col)
            if icc is None or mean_k < self.MIN_K:
                continue
            if icc >= self.ICC_SUSPICIOUS:
                # Healthy ICC; no finding (could note exceptionally high
                # but that's a positive control signal, not fabrication)
                continue
            severity = (
                Severity.CRITICAL if icc < self.ICC_CRITICAL else Severity.SUSPICIOUS
            )
            findings.append(
                Finding(
                    detector_id=self.id,
                    detector_name=self.name,
                    severity=severity,
                    summary=(
                        f"列 '{col}' 按 '{subject_col}' 分组的 ICC = "
                        f"{icc:.4f} (n_subjects={n_subj}, mean k={mean_k})"
                    ),
                    detail=(
                        f"对 '{col}' 列按 subject 标识 '{subject_col}' 计算 ICC(1)。"
                        f"得到 ICC = {icc:.4f}, 即同一 subject 的多次"
                        "测量之间几乎完全独立。真实重复测量(同只动物"
                        "的多次测量、同一受试者的多次问卷)应有正的 ICC"
                        "(通常 0.2-0.9, 因变量而定)。ICC ≈ 0 提示数据"
                        "可能是不考虑 subject 结构的完全随机生成。"
                        " (Heathers 2024 ICRP)"
                    ),
                    test_statistic=icc,
                    test_name="ICC(1) one-way random effects",
                    evidence={
                        "subject_column": subject_col,
                        "value_column": col,
                        "icc": icc,
                        "n_subjects": n_subj,
                        "mean_repetitions_per_subject": mean_k,
                    },
                    innocent_explanations=[
                        "本测量真的没有 subject-level 变异(如所有动物"
                        "在同一仪器同一日测量,且测量误差远大于个体差异)",
                        "subject 列实际上不是 cluster 标识(只是 row id)",
                        "数据已经过 within-subject 中心化(每个 subject"
                        "减去自己的均值),会人为消去 ICC",
                        "样本量 N、k 较小时 ICC 估计本身不稳定",
                    ],
                    academic_reference=self.academic_basis,
                    applicability_notes=(
                        f"subject 列='{subject_col}', "
                        f"n_subjects={n_subj}, mean repeats per subject={mean_k}. "
                        f"ICC 在 n_subjects ≥ 10, k ≥ 3 时最可靠。"
                    ),
                )
            )
        return findings
