"""A7 — 末位 0/5 专项偏好检测（耿同学方法精细版）。

学术依据：
耿洪伟 (2025) 公开打假实践：观察到造假数据末位 0/5 频率畸高。例如某
被举报论文 2400 个数据中末位"5"出现 212 次（期望 240，但配合体重列
末位 0 几乎绝迹这一异常 → 锁定造假）。
Mosimann et al. (1995) 原始末位检验也观察到 0/5 偏好是常见 fabrication
heuristic。

A1 用 χ²(9) 检测整体末位均匀性。A7 专门针对"0+5 占比"这一具体子假设，
对小样本更敏感、对其它非 0/5 偏差不敏感（互补关系）。

策略：
1. 对每数值列提取末位有效数字
2. 期望 P(末位 ∈ {0, 5}) = 0.2
3. 单尾二项 p：观测 ≥ 期望 → 越大越可疑
4. 同时检查"反向异常"：末位 0/5 严重缺失（< 5%）也可疑（如体重末位 0 几乎绝迹）
"""
from __future__ import annotations

from collections import Counter
from typing import ClassVar

import numpy as np
import pandas as pd
from scipy import stats

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity
from paperguard.utils.float_utils import get_last_significant_digit


class A7LastDigitFiveZeroDetector(BaseDetector):
    """末位 0/5 比例的双尾偏离检验（耿同学方法）。"""

    id: ClassVar[str] = "A7"
    name: ClassVar[str] = "Last-Digit 0/5 Preference (Geng method)"
    description: ClassVar[str] = (
        "末位 0/5 比例偏离期望 20% 双尾检验，对 A1 χ² 的具体子假设补充。"
    )
    academic_basis: ClassVar[str] = (
        "Geng Hongwei (2025) public auditing practice; "
        "Mosimann et al. (1995) Accountability in Research."
    )
    data_requirements: ClassVar[list[str]] = ["raw_numeric_values"]
    assumption_cluster: ClassVar[str] = "digit_distribution"

    SMALL_N: ClassVar[int] = 10
    MIN_N: ClassVar[int] = 30
    P_CONCERN: ClassVar[float] = 0.005
    P_SUSPICIOUS: ClassVar[float] = 1e-5
    P_CRITICAL: ClassVar[float] = 1e-15

    def check_applicability(self, data: pd.DataFrame) -> tuple[bool, str]:
        if not isinstance(data, pd.DataFrame):
            return False, "Expected pd.DataFrame"
        for col in data.select_dtypes(include=[np.number]).columns:
            if len(data[col].dropna()) >= self.SMALL_N:
                return True, ""
        return False, f"No numeric column with N ≥ {self.SMALL_N}"

    def _detect(self, data: pd.DataFrame, seed: int) -> list[Finding]:
        findings: list[Finding] = []
        for col in data.select_dtypes(include=[np.number]).columns:
            values = data[col].dropna()
            n = len(values)
            if n < self.SMALL_N:
                continue
            low_power = n < self.MIN_N
            digits = [get_last_significant_digit(v) for v in values]
            counts = Counter(digits)
            zf_count = counts.get(0, 0) + counts.get(5, 0)
            zf_ratio = zf_count / n
            expected = 0.2

            # 双尾二项检验
            if zf_ratio >= expected:
                p_value = float(1 - stats.binom.cdf(zf_count - 1, n, expected))
                direction = "elevated"
            else:
                p_value = float(stats.binom.cdf(zf_count, n, expected))
                direction = "depressed"

            if p_value > self.P_CONCERN:
                continue
            if p_value < self.P_CRITICAL:
                severity = Severity.CRITICAL
            elif p_value < self.P_SUSPICIOUS:
                severity = Severity.SUSPICIOUS
            else:
                severity = Severity.CONCERN

            if low_power:
                severity = Severity.NOTE

            findings.append(
                Finding(
                    detector_id=self.id,
                    detector_name=self.name,
                    severity=severity,
                    summary=(
                        f"列 '{col}' 末位 0/5 占比 {zf_ratio:.1%} ({direction}, "
                        f"期望 20%, p={p_value:.2e})"
                    ),
                    detail=(
                        f"对 {col} 列的 {n} 个数值，末位为 0 或 5 的占 "
                        f"{zf_count}/{n} = {zf_ratio:.2%}。在末位均匀分布的 "
                        f"H0 下 P(末位 ∈ {{0,5}}) = 20%；单尾二项 p = "
                        f"{p_value:.4e}。"
                        + (
                            "末位 0/5 严重缺失同样可疑——耿同学案例中"
                            "体重列末位 0 几乎绝迹是关键证据。"
                            if direction == "depressed"
                            else "末位 0/5 异常富集是人手编造的经典签名（"
                            "人类倾向于'整齐'数字）。"
                        )
                    ),
                    p_value=p_value,
                    test_statistic=zf_ratio,
                    test_name="binomial P(last ∈ {0,5})",
                    evidence={
                        "column": str(col),
                        "n": n,
                        "zero_five_count": zf_count,
                        "zero_five_ratio": zf_ratio,
                        "direction": direction,
                        "frequency_table": {str(d): int(c) for d, c in counts.items()},
                    },
                    innocent_explanations=[
                        "数据仪器步长本就是 0.05 的倍数（如某些天平）",
                        "数据为整数计数且范围小（< 50），末位分布天然不均",
                        "数据已经过四舍五入到 0.05 或 0.1 精度",
                        "样本量小时观测频率波动较大",
                    ],
                    academic_reference=self.academic_basis,
                )
            )
        return findings
