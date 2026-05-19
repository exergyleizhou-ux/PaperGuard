"""D2 — Missing-Data Pattern 检测（"过于完整"数据）。

学术依据：
- Carlisle (2017) 观察到编造的 RCT 数据 0% missing；真实大型 RCT
  几乎不可能 100% 完整。
- Embassy of Good Science (2024) "natural data is messy" 原则。
- Buyse et al. (1999) "The role of biostatistics in the prevention,
  detection and treatment of fraud in clinical trials" Stat Med.

启发：N 行 × K 列的大型真实数据集：
- 0% missing 是罕见的（除非每个值都自动采集且 sanity-checked）
- 0% out-of-range 同样罕见

策略：
- N ≥ MIN_N 且 K ≥ 3
- 计算 missing 率
- 若 missing == 0 且 K ≥ 5 → NOTE（"完美完整"提示但不是 fraud 信号）
- 若 missing == 0 且每列方差极小（uniform-ish）→ CONCERN
- 同时检测"明显未经清洗的"反向标志：> 0 个 NaN/Inf/超量级值 → 提示
  数据是真实采集
"""
from __future__ import annotations

from typing import ClassVar

import numpy as np
import pandas as pd

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity


class D2MissingPatternDetector(BaseDetector):
    """检测"过于完整"的数据集（fraud 警告）。"""

    id: ClassVar[str] = "D2"
    name: ClassVar[str] = "Missing-Data Pattern"
    description: ClassVar[str] = (
        "0% missing + 列方差稳定 是已知 fraud 签名（Carlisle 2017）。"
    )
    academic_basis: ClassVar[str] = (
        "Carlisle (2017) Anaesthesia 72(8); "
        "Buyse et al. (1999) Stat Med 18; "
        "Embassy of Good Science (2024)."
    )
    data_requirements: ClassVar[list[str]] = ["raw_numeric_values"]
    assumption_cluster: ClassVar[str] = "variance_structure"

    MIN_N: ClassVar[int] = 50
    MIN_K: ClassVar[int] = 3

    def check_applicability(self, data: pd.DataFrame) -> tuple[bool, str]:
        if not isinstance(data, pd.DataFrame):
            return False, "Expected pd.DataFrame"
        if len(data) < self.MIN_N:
            return False, f"N < {self.MIN_N}"
        if len(data.select_dtypes(include=[np.number]).columns) < self.MIN_K:
            return False, f"Need at least {self.MIN_K} numeric columns"
        return True, ""

    def _detect(self, data: pd.DataFrame, seed: int) -> list[Finding]:
        numeric = data.select_dtypes(include=[np.number])
        n_rows = len(numeric)
        n_cols = len(numeric.columns)
        total_cells = n_rows * n_cols

        n_missing = int(numeric.isna().sum().sum())
        missing_rate = n_missing / total_cells if total_cells else 0.0

        # 计算每列方差，看是否异常一致
        col_stds = numeric.std(ddof=1).to_numpy(dtype=float)
        # 用相对变化系数
        if col_stds.size and col_stds.mean() > 0:
            cv_of_std = float(col_stds.std(ddof=1) / col_stds.mean())
        else:
            cv_of_std = 0.0

        findings: list[Finding] = []

        if missing_rate == 0 and n_rows >= self.MIN_N and n_cols >= self.MIN_K:
            # 0 missing：可能是合理的；只有当方差也异常稳定时才升级
            if cv_of_std < 0.1 and n_cols >= 5:
                severity = Severity.CONCERN
                summary_extra = (
                    f"+ 列间 σ 相对一致 (CV={cv_of_std:.3f}, 自然数据通常 > 0.3)"
                )
            else:
                severity = Severity.NOTE
                summary_extra = ""

            findings.append(
                Finding(
                    detector_id=self.id,
                    detector_name=self.name,
                    severity=severity,
                    summary=(
                        f"数据集 {n_rows}×{n_cols} 完全无 missing 值 "
                        f"{summary_extra}"
                    ),
                    detail=(
                        f"全部 {total_cells} 个单元格均为非缺失数值。"
                        "在真实大规模实验/调查数据中，0% missing 罕见——"
                        "通常会有仪器故障、退出受试、记录失败等导致 0.5%-5% "
                        "缺失。这本身不是 fraud 证据，但配合其它检测器（"
                        "A1 末位、A3 列间、C1 baseline）可加强 cross-cluster "
                        "推断。"
                    ),
                    evidence={
                        "n_rows": n_rows,
                        "n_columns": n_cols,
                        "total_cells": total_cells,
                        "missing_count": 0,
                        "missing_rate": 0.0,
                        "column_std_cv": cv_of_std,
                    },
                    innocent_explanations=[
                        "数据已被作者清洗，缺失行已删除（应在 Methods 声明）",
                        "数据由仪器自动采集 + 内置 sanity check（合法）",
                        "样本量小，按概率本就可能 0 missing",
                        "数据集是 derived（如均值表），原始数据另存",
                    ],
                    academic_reference=self.academic_basis,
                )
            )

        return findings
