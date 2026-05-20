"""核心数据类型 — 所有检测器共享的 Finding/Severity/Result 结构。"""
from __future__ import annotations

from datetime import UTC, datetime
from enum import IntEnum
from typing import Any

from pydantic import BaseModel, Field


class Severity(IntEnum):
    """证据严重性分级。

    PASS:        无异常
    NOTE:        微小异常，仅备查
    CONCERN:     值得关注（p < 0.01 单检测器）
    SUSPICIOUS:  高度可疑（≥2 个独立检测器 CONCERN+）
    CRITICAL:    紧急关注（≥3 个跨范畴 OR 不可能性证明成立）
    """

    PASS = 0
    NOTE = 1
    CONCERN = 2
    SUSPICIOUS = 3
    CRITICAL = 4

    @property
    def label(self) -> str:
        return self.name

    @property
    def color(self) -> str:
        """Rich 终端颜色。"""
        return {
            Severity.PASS: "green",
            Severity.NOTE: "blue",
            Severity.CONCERN: "yellow",
            Severity.SUSPICIOUS: "magenta",
            Severity.CRITICAL: "red bold",
        }[self]


class Finding(BaseModel):
    """单个检测发现。"""

    detector_id: str = Field(..., description="检测器 ID，如 'A1'")
    detector_name: str = Field(..., description="人类可读名称")
    severity: Severity
    summary: str = Field(..., description="单句总结，≤80 字符")
    detail: str = Field(..., description="详细说明")
    p_value: float | None = Field(None, description="原始 p 值")
    p_value_adjusted: float | None = Field(None, description="BH-FDR 校正后")
    test_statistic: float | None = None
    test_name: str = ""
    effect_size: float | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    innocent_explanations: list[str] = Field(default_factory=list)
    academic_reference: str = ""
    applicability_notes: str = ""

    model_config = {"arbitrary_types_allowed": True}


class DetectorResult(BaseModel):
    """单个检测器对单个数据集的运行结果。"""

    detector_id: str
    applicable: bool
    skip_reason: str | None = None
    findings: list[Finding] = Field(default_factory=list)
    runtime_seconds: float = 0.0
    seed: int = 42


class AuditReport(BaseModel):
    """完整审查报告。"""

    paper_identifier: str = Field(..., description="DOI 或本地路径")
    paper_title: str = ""
    paper_authors: list[str] = Field(default_factory=list)
    paper_year: int | None = None
    paper_journal: str = ""

    retraction_status: str | None = None
    pubpeer_concerns_count: int = 0

    detector_results: list[DetectorResult] = Field(default_factory=list)
    all_findings: list[Finding] = Field(default_factory=list)

    overall_severity: Severity = Severity.PASS
    combined_evidence_strength: str = ""

    # 2.0.14: single-number integrity score via Stouffer's method
    # across all finding p-values (BH-FDR adjusted). Lower = more
    # concerning. None when no p-valued findings exist.
    integrity_score: float | None = None
    integrity_z: float | None = None

    file_hashes: dict[str, str] = Field(default_factory=dict)
    run_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    paperguard_version: str = "0.1.0"
    seed: int = 42

    def summary_text(self) -> str:
        """返回纯文本摘要供日志使用。"""
        n_findings_by_sev: dict[str, int] = {}
        for f in self.all_findings:
            n_findings_by_sev[f.severity.label] = n_findings_by_sev.get(f.severity.label, 0) + 1
        return (
            f"Paper: {self.paper_identifier}\n"
            f"Overall: {self.overall_severity.label}\n"
            f"Findings: {n_findings_by_sev}"
        )
