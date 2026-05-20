"""A3 — 列间固定算术关系检测。

学术依据：
- Mosimann fabrication heuristics (1995)
- 公开方法论：当两列数据互相独立测量时，它们的差/比应展示
  累积测量误差。若 σ(diff) ≪ 单测量噪声，则两列之间存在
  确定性关系。

2.0.13 数学升级:
原 A3 只查两两列的恒定差/比,但造假者经常用 3+ 列的线性组合
(`col4 = 2 * col1 + col2 - 0.3`),pair-wise 检测看不到。本版加:

**多元线性回归 (numpy lstsq) + 稀疏性后处理**:
对每个数值列,把其它列作特征做 OLS 回归;计算 R² 和系数稀疏性。
- R² > 0.999 + 残差 σ < 1e-5 → 列可被其它列线性合成 (CRITICAL)
- R² > 0.99 + 非零系数 ≤ 2 → 简单组合合成 (SUSPICIOUS)
- R² > 0.95 → 强相关 (CONCERN,可能合法)

避免引入 sklearn 大依赖;稀疏性靠"绝对值显著的系数个数"近似。
详见 docs/math_upgrades_v2.md。
"""
from __future__ import annotations

from itertools import combinations
from typing import ClassVar

import numpy as np
import pandas as pd

from paperguard.config import get_settings
from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity


def _multivariate_synthetic_check(
    data: pd.DataFrame,
    cols: list[str],
    *,
    r2_threshold_critical: float = 0.99999,
    r2_threshold_suspicious: float = 0.9999,
    r2_threshold_concern: float = 0.999,
    residual_threshold: float = 1e-5,
    sparsity_threshold: int = 2,
) -> list[dict[str, object]]:
    """For each col, regress it on the others; flag synthetic combinations.

    Returns a list of dicts (one per flagged column) with:
      target, predictors, r2, residual_std, n_nonzero_coefs, coefs

    Sparsity here is approximated as "number of coefficients whose
    absolute value is at least 1% of the largest coefficient's
    absolute value". A real Lasso would set small ones to exactly 0;
    this proxy is close enough for the fabrication patterns we care
    about and avoids the scikit-learn dependency.
    """
    if len(cols) < 3:
        return []
    out: list[dict[str, object]] = []
    n_rows = len(data)
    if n_rows < 20:
        return []

    for target in cols:
        predictors = [c for c in cols if c != target]
        y = data[target].to_numpy(dtype=float)
        if np.any(np.isnan(y)):
            continue
        x = data[predictors].to_numpy(dtype=float)
        if np.any(np.isnan(x)):
            continue
        # Augment with intercept column
        x_aug = np.column_stack([x, np.ones(n_rows)])
        try:
            coef, residuals, rank, _ = np.linalg.lstsq(x_aug, y, rcond=None)
        except np.linalg.LinAlgError:
            continue
        y_pred = x_aug @ coef
        resid = y - y_pred
        residual_std = float(np.std(resid, ddof=1))
        y_var = float(np.var(y, ddof=1))
        if y_var < 1e-12:
            continue
        r2 = 1.0 - (np.var(resid, ddof=1) / y_var)
        if r2 < r2_threshold_concern:
            continue
        # Sparsity proxy: count predictor coefficients (skip intercept)
        # whose abs is >= 1% of max abs predictor coef.
        predictor_coefs = coef[:-1]
        if len(predictor_coefs) == 0:
            continue
        max_abs = float(np.max(np.abs(predictor_coefs)))
        if max_abs < 1e-12:
            continue
        n_nonzero = int(np.sum(np.abs(predictor_coefs) >= 0.01 * max_abs))

        # Severity logic
        if (
            r2 >= r2_threshold_critical
            and residual_std < residual_threshold
        ):
            severity = "CRITICAL"
        elif (
            r2 >= r2_threshold_suspicious
            and n_nonzero <= sparsity_threshold
        ):
            severity = "SUSPICIOUS"
        else:
            severity = "CONCERN"

        out.append(
            {
                "target": target,
                "predictors": predictors,
                "r2": float(r2),
                "residual_std": residual_std,
                "n_nonzero_coefs": n_nonzero,
                "coefs": {
                    p: float(c)
                    for p, c in zip(predictors, predictor_coefs, strict=False)
                },
                "intercept": float(coef[-1]),
                "severity_label": severity,
            }
        )
    return out


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

        # --- 2.0.13 multivariate synthetic-combination check ---
        # Run BEFORE pairwise loop because if col3 = 2*col1 + col2 the
        # pairwise loop will miss it but the multivariate one will catch.
        mv_hits = _multivariate_synthetic_check(
            data.dropna(subset=numeric_cols), numeric_cols
        )
        for hit in mv_hits:
            label = str(hit["severity_label"])
            sev_map = {
                "CRITICAL": Severity.CRITICAL,
                "SUSPICIOUS": Severity.SUSPICIOUS,
                "CONCERN": Severity.CONCERN,
            }
            severity = sev_map.get(label, Severity.CONCERN)
            coefs_obj = hit["coefs"]
            assert isinstance(coefs_obj, dict)
            coefs_str = " + ".join(
                f"{v:.4f}·{k}"
                for k, v in coefs_obj.items()
                if abs(v) >= 0.01
            ) or "0"
            findings.append(
                Finding(
                    detector_id=self.id,
                    detector_name=self.name + " — multivariate synthetic",
                    severity=severity,
                    summary=(
                        f"列 '{hit['target']}' 可由其它列线性合成 "
                        f"(R²={hit['r2']:.6f}, σ_resid={hit['residual_std']:.2e}, "
                        f"≤{hit['n_nonzero_coefs']} 非零系数)"
                    ),
                    detail=(
                        f"对列 {hit['target']} 用其它列作特征跑 OLS:\n"
                        f"  {hit['target']} ≈ {coefs_str} + {hit['intercept']:.4f}\n"
                        f"R² = {hit['r2']:.6f},残差标准差 "
                        f"{hit['residual_std']:.2e}\n"
                        f"真测量列之间不会有如此精确的线性关系。\n"
                        "2.0.13 新加;比 pair-wise 差/比检验更广。"
                    ),
                    test_statistic=float(hit["r2"]),  # type: ignore[arg-type]
                    test_name="multivariate OLS R²",
                    evidence={
                        "target": str(hit["target"]),
                        "predictors": list(hit["predictors"]),  # type: ignore[call-overload]
                        "r2": float(hit["r2"]),  # type: ignore[arg-type]
                        "residual_std": float(hit["residual_std"]),  # type: ignore[arg-type]
                        "n_nonzero_coefs": int(hit["n_nonzero_coefs"]),  # type: ignore[call-overload]
                        "coefs": coefs_obj,
                        "intercept": float(hit["intercept"]),  # type: ignore[arg-type]
                    },
                    innocent_explanations=[
                        f"列 {hit['target']} 实际就是由其它列计算得到("
                        "如总和、平均、衍生指标),并非独立测量",
                        "高维数据各列之间天然存在多重共线性(物理上"
                        "相关的量,如温度↔压强↔体积)",
                        "数据规模化或归一化的副产物",
                        "OLS 系数稀疏性是近似估计,真 Lasso 会更精确",
                    ],
                    academic_reference=(
                        "Multivariate linear regression sanity check. "
                        "Independent measurements should not exhibit "
                        "near-perfect linear coupling across columns."
                    ),
                )
            )

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
