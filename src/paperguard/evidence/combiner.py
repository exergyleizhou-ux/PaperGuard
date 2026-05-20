"""证据组合 — BH-FDR p 值校正 + 严重性升级规则 + Stouffer 整合指数。"""
from __future__ import annotations

import math

from paperguard.core.types import AuditReport, Severity


def benjamini_hochberg(p_values: list[float], alpha: float = 0.05) -> list[float]:
    """BH-FDR 调整 p 值。

    Args:
        p_values: 原始 p 值列表。
        alpha: 名义 FDR 水平（保留参数，便于扩展决策规则）。

    Returns:
        与输入等长的 q 值列表（与 p_values 顺序一致）。
    """
    _ = alpha  # 当前实现只返回 q 值，alpha 由调用方决定阈值
    n = len(p_values)
    if n == 0:
        return []
    indexed = sorted(enumerate(p_values), key=lambda x: x[1])
    q_values = [0.0] * n
    min_q = 1.0
    for rank, (orig_idx, p) in enumerate(reversed(indexed), start=1):
        k = n - rank + 1
        q = p * n / k
        min_q = min(min_q, q)
        q_values[orig_idx] = min(min_q, 1.0)
    return q_values


def combine_evidence(report: AuditReport) -> AuditReport:
    """汇总所有发现，做 FDR 校正，确定总体严重性。

    严重性升级规则：
      1. 任一 CRITICAL → 总体 CRITICAL
      2. ≥ 3 个跨 assumption_cluster 的 CONCERN+ → CRITICAL
      3. ≥ 1 个 SUSPICIOUS 或 ≥ 2 个跨 cluster CONCERN+ → SUSPICIOUS
      4. ≥ 1 个 CONCERN → CONCERN
      5. 仅 NOTE → NOTE
      6. 否则 PASS
    """
    findings_with_p = [f for f in report.all_findings if f.p_value is not None]
    if findings_with_p:
        ps: list[float] = [
            f.p_value for f in findings_with_p if f.p_value is not None
        ]
        qs = benjamini_hochberg(ps)
        for f, q in zip(findings_with_p, qs, strict=True):
            f.p_value_adjusted = q

    has_critical = any(f.severity == Severity.CRITICAL for f in report.all_findings)
    has_suspicious = any(
        f.severity == Severity.SUSPICIOUS for f in report.all_findings
    )
    concern_or_higher = [
        f for f in report.all_findings if f.severity >= Severity.CONCERN
    ]

    # 解析每个 finding 对应的 assumption_cluster
    from paperguard.core.registry import DetectorRegistry

    registry = DetectorRegistry().register_default()
    clusters: set[str] = set()
    for f in concern_or_higher:
        d = registry.get(f.detector_id)
        if d and d.assumption_cluster:
            clusters.add(d.assumption_cluster)

    cross_cluster_concerns = len(clusters)

    if has_critical or cross_cluster_concerns >= 3:
        report.overall_severity = Severity.CRITICAL
    elif has_suspicious or cross_cluster_concerns >= 2:
        report.overall_severity = Severity.SUSPICIOUS
    elif len(concern_or_higher) >= 1:
        report.overall_severity = Severity.CONCERN
    elif any(f.severity == Severity.NOTE for f in report.all_findings):
        report.overall_severity = Severity.NOTE
    else:
        report.overall_severity = Severity.PASS

    n_total = len(report.all_findings)
    n_critical = sum(1 for f in report.all_findings if f.severity == Severity.CRITICAL)
    n_suspicious = sum(
        1 for f in report.all_findings if f.severity == Severity.SUSPICIOUS
    )
    n_concern = sum(1 for f in report.all_findings if f.severity == Severity.CONCERN)

    report.combined_evidence_strength = (
        f"Total findings: {n_total} | "
        f"CRITICAL: {n_critical}, SUSPICIOUS: {n_suspicious}, "
        f"CONCERN: {n_concern} | "
        f"Independent evidence clusters: {cross_cluster_concerns}"
    )

    # --- 2.0.14: Stouffer cross-detector integrity score ---
    # Take BH-FDR-adjusted p values across all findings, convert to
    # z under the upper-tail of standard normal, and combine via
    # Stouffer's method: Z = sum(z_i) / sqrt(k). One overall integrity
    # z; smaller p → more concerning.
    # Score range: 0 (no concerns) to ~5+ (strong cumulative evidence).
    if findings_with_p:
        try:
            from scipy import stats as _stats

            z_scores: list[float] = []
            for f in findings_with_p:
                q_raw: float | None = (
                    f.p_value_adjusted
                    if f.p_value_adjusted is not None
                    else f.p_value
                )
                if q_raw is None or q_raw <= 0 or q_raw >= 1:
                    continue
                q = float(q_raw)
                # Upper-tail z (so smaller p → larger positive z = more
                # concerning)
                z_scores.append(float(_stats.norm.ppf(1.0 - q)))
            if z_scores:
                stouffer_z = sum(z_scores) / math.sqrt(len(z_scores))
                stouffer_p = float(1.0 - _stats.norm.cdf(stouffer_z))
                report.integrity_z = float(stouffer_z)
                report.integrity_score = stouffer_p
        except ImportError:  # pragma: no cover
            pass

    return report
