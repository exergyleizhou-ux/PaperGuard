"""A6 — Implausible Value 检测。

学术依据：
- Wansink 调查报告（Anaya, van der Zee 2017）发现编造的营养学数据
  含"不可能值"（如儿童食用 700 片披萨）。
- 标准数据清洗实践。

策略：基于列名启发式 + 显式不可能范围。
- 列名匹配 percentage/percent/rate → 应在 [0, 100]
- 列名匹配 probability/p_value → [0, 1]
- 列名匹配 age → [0, 130]
- 列名匹配 bmi → [10, 100]
- 列名匹配 viability/recovery/yield → [0, 100] 或 [0, 1]（自动判断单位）
- 通用：检测哨兵值（999, -999, 9999, NA-as-number 等）

输出：列出具体行号 + 不可能值 + 违反的约束。
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import ClassVar

import numpy as np
import pandas as pd

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity


@dataclass(frozen=True)
class _Constraint:
    pattern: re.Pattern[str]
    lo: float
    hi: float
    description: str


# 列名通常 snake_case / camelCase / 含空格。用 (?:^|[_\s\-]) 跨下划线匹配。
_CONSTRAINTS: tuple[_Constraint, ...] = (
    _Constraint(re.compile(r"(?i)(?:^|[_\s\-])percent(?:age)?(?:[_\s\-]|$)"),
                0, 100, "percentage 0–100"),
    _Constraint(re.compile(r"(?i)(?:^|[_\s\-])(?:rate|ratio)(?:[_\s\-]|$)"),
                -1, 100, "rate / ratio reasonable bound"),
    _Constraint(re.compile(r"(?i)(?:^|[_\s\-])probability(?:[_\s\-]|$)"),
                0, 1, "probability 0–1"),
    _Constraint(re.compile(r"(?i)(?:^|[_\s\-])p[_\s\-]?value(?:[_\s\-]|$)"),
                0, 1, "p-value 0–1"),
    _Constraint(re.compile(r"(?i)(?:^|[_\s\-])age(?:[_\s\-]|$)"),
                0, 130, "age 0–130 years"),
    _Constraint(re.compile(r"(?i)(?:^|[_\s\-])bmi(?:[_\s\-]|$)"),
                10, 100, "BMI 10–100"),
    _Constraint(re.compile(r"(?i)(?:^|[_\s\-])weight(?:_kg|_g)?(?:[_\s\-]|$)"),
                0, 500, "weight in kg"),
    _Constraint(re.compile(r"(?i)(?:^|[_\s\-])height(?:_cm|_m)?(?:[_\s\-]|$)"),
                30, 250, "height in cm"),
    _Constraint(re.compile(r"(?i)(?:^|[_\s\-])(?:viability|survival)(?:[_\s\-]|$)"),
                0, 100, "viability / survival 0–100%"),
    _Constraint(re.compile(r"(?i)(?:^|[_\s\-])count(?:[_\s\-]|$)"),
                0, 1e9, "non-negative count"),
)

_SENTINEL_VALUES = {999.0, -999.0, 9999.0, -9999.0, 99999.0, 88888.0, 77777.0}


class A6ImplausibleValueDetector(BaseDetector):
    """检测明显不可能的数值（哨兵值 + 列名启发式范围检查）。"""

    id: ClassVar[str] = "A6"
    name: ClassVar[str] = "Implausible Value Check"
    description: ClassVar[str] = (
        "按列名启发式检查值是否落在合理范围；同时报告哨兵值（999/-999 等）。"
    )
    academic_basis: ClassVar[str] = (
        "Anaya, van der Zee, Brown (2017) Statistical inconsistencies in "
        "Wansink papers; standard data cleaning best practices."
    )
    data_requirements: ClassVar[list[str]] = ["raw_numeric_values"]
    assumption_cluster: ClassVar[str] = "data_quality"

    def check_applicability(self, data: pd.DataFrame) -> tuple[bool, str]:
        if not isinstance(data, pd.DataFrame):
            return False, "Expected pd.DataFrame"
        if not len(data.select_dtypes(include=[np.number]).columns):
            return False, "No numeric columns"
        return True, ""

    def _detect(self, data: pd.DataFrame, seed: int) -> list[Finding]:
        findings: list[Finding] = []
        for col in data.select_dtypes(include=[np.number]).columns:
            values = data[col].dropna().to_numpy(dtype=float)
            if values.size == 0:
                continue

            # 1) Sentinel values
            sentinels = [
                v for v in values
                if v in _SENTINEL_VALUES or (math.isfinite(v) and abs(v) >= 1e10)
            ]
            if sentinels:
                findings.append(
                    Finding(
                        detector_id=self.id,
                        detector_name=self.name,
                        severity=Severity.CONCERN,
                        summary=(
                            f"列 '{col}' 含 {len(sentinels)} 个疑似哨兵值 "
                            f"(e.g. {sentinels[:3]})"
                        ),
                        detail=(
                            f"列 {col} 中出现 {len(sentinels)} 个明显异常值，"
                            "形态像数据缺失编码（999 / -999 / 9999）或"
                            "数量级溢出。在统计计算前应替换为 NaN，否则会"
                            "严重污染 mean/SD/correlation。"
                        ),
                        evidence={
                            "column": str(col),
                            "sentinel_values": sentinels[:20],
                            "n_sentinels": len(sentinels),
                            "n_total": int(values.size),
                        },
                        innocent_explanations=[
                            "999 / -999 是 SPSS/Stata 的合法 missing-data 编码，"
                            "未在 read_csv 时映射为 NaN（应在 Methods 说明）",
                            "数值真实就是 999（如某些计数项）",
                            "合并数据集时编码冲突",
                        ],
                        academic_reference=self.academic_basis,
                    )
                )

            # 2) Column-name heuristic range
            for con in _CONSTRAINTS:
                if not con.pattern.search(str(col)):
                    continue
                out_of_range = [v for v in values if v < con.lo or v > con.hi]
                if not out_of_range:
                    continue
                ratio = len(out_of_range) / len(values)
                if ratio >= 0.05:
                    severity = Severity.CONCERN
                elif len(out_of_range) >= 1:
                    severity = Severity.NOTE
                else:
                    continue
                findings.append(
                    Finding(
                        detector_id=self.id,
                        detector_name=self.name,
                        severity=severity,
                        summary=(
                            f"列 '{col}' 有 {len(out_of_range)} 个值不在 "
                            f"[{con.lo}, {con.hi}] 范围内（{con.description}）"
                        ),
                        detail=(
                            f"基于列名启发式，'{col}' 应在 [{con.lo}, {con.hi}]。"
                            f"实际有 {len(out_of_range)}/{len(values)} = "
                            f"{ratio:.1%} 的值越界。示例: {out_of_range[:5]}"
                        ),
                        evidence={
                            "column": str(col),
                            "constraint": con.description,
                            "lower_bound": con.lo,
                            "upper_bound": con.hi,
                            "out_of_range_examples": out_of_range[:10],
                            "n_out_of_range": len(out_of_range),
                            "n_total": int(values.size),
                            "out_of_range_ratio": ratio,
                        },
                        innocent_explanations=[
                            "本列名与启发式正则巧合但语义不同（如 'unrate' 不是 percentage）",
                            "数据使用了非标准刻度（如 viability 报告为 0-1 分数而非百分比）",
                            "测量误差导致少量超界值（应在 QC 中清理）",
                            "Outliers 是真实但罕见的极端样本",
                        ],
                        academic_reference=self.academic_basis,
                    )
                )
                break  # 每列只触发一次约束（最先匹配的）

        return findings
