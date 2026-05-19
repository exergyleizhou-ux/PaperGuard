"""T2 — 临床试验注册一致性（outcome switching 检测）。

学术依据：
Goldacre et al. (2019) Compare Trials Project. 系统性发现：
~50% 的发表 RCT 存在 primary outcome 与注册时不符的现象。

策略：
1. 用户提供 NCT ID + 论文中实际报告的 primary outcome（字符串列表）
2. PaperGuard 从 ClinicalTrials.gov 取注册的 primary outcome
3. 用 token 集合比较 → 找不到对应的注册 outcome 即视为 switching
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, ClassVar

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity


@dataclass
class TrialConsistencyInput:
    nct_id: str
    reported_primary_outcomes: list[str]


_WORD_RE = re.compile(r"[A-Za-z]+")


def _tokens(s: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(s) if len(w) > 2}


def _token_overlap(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


class T2TrialConsistencyDetector(BaseDetector):
    """检测论文 primary outcome 是否与 ClinicalTrials.gov 注册一致。"""

    id: ClassVar[str] = "T2"
    name: ClassVar[str] = "Clinical Trial Outcome Consistency"
    description: ClassVar[str] = (
        "比对论文 primary outcome 与 ClinicalTrials.gov 注册记录。"
    )
    academic_basis: ClassVar[str] = (
        "Goldacre et al. (2019). COMPare: a prospective cohort study correcting "
        "and monitoring 58 misreported trials in real time. Trials, 20(118)."
    )
    data_requirements: ClassVar[list[str]] = ["clinical_trial_metadata"]
    assumption_cluster: ClassVar[str] = "trial_consistency"

    OVERLAP_THRESHOLD = 0.4  # 任一注册 outcome 与报告 outcome 的 token 重叠率

    def check_applicability(self, data: Any) -> tuple[bool, str]:
        if not isinstance(data, TrialConsistencyInput):
            return False, "Expected TrialConsistencyInput"
        if not data.nct_id.upper().startswith("NCT"):
            return False, f"Not a valid NCT ID: {data.nct_id}"
        if not data.reported_primary_outcomes:
            return False, "No reported outcomes provided"
        return True, ""

    def _detect(self, data: TrialConsistencyInput, seed: int) -> list[Finding]:
        from paperguard.fetcher.clinicaltrials import ClinicalTrialsClient

        client = ClinicalTrialsClient()
        try:
            registered = client.primary_outcomes(data.nct_id)
        finally:
            client.close()

        if not registered:
            return []

        findings: list[Finding] = []
        for reported in data.reported_primary_outcomes:
            best_overlap = max(
                (_token_overlap(reported, r) for r in registered),
                default=0.0,
            )
            if best_overlap >= self.OVERLAP_THRESHOLD:
                continue

            findings.append(
                Finding(
                    detector_id=self.id,
                    detector_name=self.name,
                    severity=Severity.SUSPICIOUS,
                    summary=(
                        f"Reported primary outcome '{reported[:60]}' "
                        f"未在 {data.nct_id} 注册中找到匹配（最高 token 重叠 "
                        f"{best_overlap:.0%}）"
                    ),
                    detail=(
                        f"论文报告 primary outcome：'{reported}'\n"
                        f"ClinicalTrials.gov 注册（{data.nct_id}）的 primary outcomes：\n"
                        + "\n".join(f"  - {r}" for r in registered)
                        + f"\n最佳 token 重叠率仅 {best_overlap:.2f}，"
                        "提示 outcome switching。"
                    ),
                    test_statistic=best_overlap,
                    test_name="best token overlap",
                    evidence={
                        "nct_id": data.nct_id,
                        "reported_outcome": reported,
                        "registered_outcomes": registered,
                        "best_overlap": best_overlap,
                    },
                    innocent_explanations=[
                        "Outcome 文字描述发生变化但内容相同（同义改写）",
                        "Outcome 在试验进行中合法修改并已在注册记录中更新",
                        "论文报告的是 secondary outcome，作者标错了 primary",
                        "注册记录本身有笔误而未及时更正",
                    ],
                    academic_reference=self.academic_basis,
                )
            )
        return findings
