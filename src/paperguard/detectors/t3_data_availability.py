"""T3 — Data Availability + Ethics Statement 审计。

学术依据：
- ICMJE 数据共享声明要求
- FAIR Data Principles (Wilkinson et al. 2016)
- ORI 调查工具中的伦理审批合规检查清单

策略（启发式，不联网）：
对 manuscript 全文做正则扫描，识别：
1. 是否存在 data availability statement
2. 是否含可验证的访问标识（DOI / 仓库 URL / accession）
3. 是否含模糊托辞（"available upon reasonable request"，已被多项研究
   证实约 80% 实际无法兑现 — Gabelica et al. 2022 BMC Med Res Methodol）
4. 是否声明伦理审批号（IRB / ethics approval / 伦理委员会）
5. 是否声明利益冲突
6. 临床试验是否预注册（NCT ID 或等价物）
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, ClassVar

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity


@dataclass
class DataAvailabilityInput:
    text: str
    is_clinical_trial: bool = False  # 临床试验需要更严格的检查
    is_human_subjects: bool = False  # 人类受试者需要 IRB
    is_animal_study: bool = False    # 动物研究需要 IACUC / ethics
    paper_year: int | None = None    # 出版年（用于年代分层 severity）


# 政策时间线（用于按年代分层 severity） ----------------------------------
# - 临床试验预注册（NCT/ISRCTN/...）: ICMJE 2005 起要求
# - 数据可用性声明（DAS）: ICMJE 2018 起强制推荐
# - 伦理审批声明: 长期惯例,无明确生效年
_TRIAL_REG_REQUIRED_YEAR = 2005    # 此前不应触发 case-3
_TRIAL_REG_STRICT_YEAR = 2010      # 2005-2010 CONCERN, 2010+ SUSPICIOUS
_DATA_AVAIL_REQUIRED_YEAR = 2018   # 此前不应触发 case-1


_DATA_STMT_PATTERNS = (
    r"data\s+availability",
    r"data\s+sharing",
    r"availability\s+of\s+(?:data|materials)",
    r"data\s+and\s+code\s+availability",
    r"数据可用性",
    r"数据共享",
)

_VAGUE_AVAILABILITY = (
    r"available\s+(?:from|upon)\s+(?:the\s+)?(?:corresponding\s+)?author",
    r"available\s+on\s+(?:reasonable\s+)?request",
    r"available\s+upon\s+reasonable\s+request",
)

_VERIFIABLE_ACCESSIONS = (
    # 仓库或 DOI 占位
    r"\b10\.\d{4,9}/[^\s\)\]\}]+",  # DOI
    r"\bGSE\d+\b",                   # GEO
    r"\bSRA\d+\b|\bSRP\d+\b",        # SRA
    r"\bPRJ[NEDA][A-Z]\d+\b",        # BioProject
    r"\bE-MTAB-\d+\b",               # ArrayExpress
    r"\bGCF_\d+\.\d+\b|\bGCA_\d+\.\d+\b",  # NCBI assemblies
    r"\bENS[A-Z]+\d+\b",             # Ensembl
    r"\bzenodo\.org/record/\d+\b",
    r"\bfigshare\.com/[a-z]+/\d+\b",
    r"\bdryad\.\w+/[\w\.]+\b",
    r"\bgithub\.com/[\w\-]+/[\w\-]+",
    r"\bdoi\.org/[\w\./\-]+",
)

_ETHICS_APPROVAL = (
    r"approved\s+by\s+(?:the\s+)?[\w\s]+(?:committee|board|IRB|IACUC)",
    r"ethics?\s+(?:committee|board|approval)\s+(?:number|no\.?)\s*[:#]?\s*\S+",
    r"IRB\s+(?:approval|number|protocol)",
    r"institutional\s+review\s+board",
    r"institutional\s+animal\s+care\s+and\s+use\s+committee",
    r"伦理(?:委员会|审查|批件|审批)",
    r"动物实验伦理",
)

_COI_DISCLOSURE = (
    r"(?:competing|conflict(?:s)?\s+of)\s+interests?",
    r"declarations?\s+of\s+interest",
    r"financial\s+disclosures?",
    r"利益冲突",
)

_TRIAL_REGISTRATION = (
    r"\bNCT\d{8}\b",                      # ClinicalTrials.gov
    r"\bISRCTN\d+\b",                      # ISRCTN
    r"\bChiCTR-?[\w]+\b",                  # 中国临床试验注册
    r"\bACTRN\d+\b",                       # ANZCTR
    r"\bEudraCT\s*\d{4}-\d{6}-\d{2}\b",   # EU CTR
    r"\bDRKS\d+\b",                        # German trials
    r"trial\s+registration:?\s*\S+",
    r"registered\s+(?:at|in|with)\s+\S+",
)


def _has_match(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def _find_all(text: str, patterns: tuple[str, ...]) -> list[str]:
    hits: list[str] = []
    for p in patterns:
        hits.extend(re.findall(p, text, re.IGNORECASE))
    return hits


class T3DataAvailabilityDetector(BaseDetector):
    """审计 manuscript 文本中的数据/伦理/COI/试验注册声明完整性。"""

    id: ClassVar[str] = "T3"
    name: ClassVar[str] = "Data Availability & Ethics Audit"
    description: ClassVar[str] = (
        "检查数据可用性声明、伦理审批、利益冲突、试验注册的完整性。"
    )
    academic_basis: ClassVar[str] = (
        "ICMJE data sharing guidelines; Gabelica et al. (2022) BMC Med Res "
        "Methodol on 'available on request' compliance; FAIR Data Principles "
        "(Wilkinson et al. 2016)."
    )
    data_requirements: ClassVar[list[str]] = ["manuscript_text"]
    assumption_cluster: ClassVar[str] = "compliance"

    def check_applicability(self, data: Any) -> tuple[bool, str]:
        if isinstance(data, DataAvailabilityInput):
            return (len(data.text) >= 200, "Text too short")
        if isinstance(data, str):
            return (len(data) >= 200, "Text too short")
        return False, "Expected DataAvailabilityInput or str"

    def _detect(
        self, data: DataAvailabilityInput | str, seed: int
    ) -> list[Finding]:
        if isinstance(data, str):
            data = DataAvailabilityInput(text=data)

        text = data.text
        findings: list[Finding] = []

        has_stmt = _has_match(text, _DATA_STMT_PATTERNS)
        has_vague = _has_match(text, _VAGUE_AVAILABILITY)
        accessions = _find_all(text, _VERIFIABLE_ACCESSIONS)
        # 过滤 DOI 自身（出现在引文里的几十个 DOI 不算"data accession"）
        non_ref_accessions = [
            a for a in accessions
            if not (a.startswith("10.") and len(a) < 40)
        ]

        # 1) 完全缺数据声明
        # 年代分层: ICMJE 2018 起强制推荐 DAS; 此前不应触发
        # 没提供年份时 default 视作"现代" (触发,保持向后兼容)
        year = data.paper_year
        if not has_stmt and (year is None or year >= _DATA_AVAIL_REQUIRED_YEAR):
            findings.append(
                Finding(
                    detector_id=self.id,
                    detector_name=self.name,
                    severity=Severity.CONCERN,
                    summary="未检测到 Data Availability 声明",
                    detail=(
                        "Manuscript 全文中未匹配到任何 'data availability / "
                        "data sharing / 数据可用性' 类声明。ICMJE 自 2018 起"
                        "要求绝大多数生物医学投稿提供该声明。"
                        + (
                            f" 本论文年份 {year},处于 ICMJE 强制期内。"
                            if year is not None
                            else ""
                        )
                    ),
                    evidence={"has_statement": False, "paper_year": year},
                    innocent_explanations=[
                        "数据声明在 SI 而非 main text",
                        "本论文是 perspective / review / commentary，无数据",
                        "声明用了非常规措辞，正则未匹配",
                    ],
                    academic_reference=self.academic_basis,
                )
            )
        elif has_vague and not non_ref_accessions:
            # 2) 只有"available on request"，无可验证 accession
            findings.append(
                Finding(
                    detector_id=self.id,
                    detector_name=self.name,
                    severity=Severity.CONCERN,
                    summary=(
                        "Data availability 声明使用了 'available on request' "
                        "类托辞且无可验证 accession"
                    ),
                    detail=(
                        "Gabelica et al. 2022 经实证发现约 80% 此类承诺最终"
                        "无法兑现。若数据真实存在，应给出 DOI / 仓库 ID / "
                        "GitHub 链接等可验证标识。"
                    ),
                    evidence={
                        "has_statement": True,
                        "has_vague_phrasing": True,
                        "verifiable_accessions": [],
                    },
                    innocent_explanations=[
                        "数据涉及隐私 / 商业 / 安全限制不可公开（应说明限制原因）",
                        "数据规模过大不便托管（应至少给元数据 + DOI）",
                        "Accession 在 SI 或 figure caption 中（提取层未捕获）",
                    ],
                    academic_reference=self.academic_basis,
                )
            )

        # 3) 临床试验未注册
        # 年代分层:
        #   pre-2005:        不触发 (NCT 注册体系 2005 才建立)
        #   2005 - 2009:     CONCERN (要求已发布但执行松)
        #   2010 +:          SUSPICIOUS (严格执行期)
        #   未知年:          SUSPICIOUS (向后兼容)
        if data.is_clinical_trial:
            trial_ids = _find_all(text, _TRIAL_REGISTRATION)
            if not trial_ids:
                if year is not None and year < _TRIAL_REG_REQUIRED_YEAR:
                    trial_severity: Severity | None = None
                elif year is not None and year < _TRIAL_REG_STRICT_YEAR:
                    trial_severity = Severity.CONCERN
                else:
                    trial_severity = Severity.SUSPICIOUS
                if trial_severity is not None:
                    findings.append(
                        Finding(
                            detector_id=self.id,
                            detector_name=self.name,
                            severity=trial_severity,
                            summary="临床试验论文未发现注册号",
                            detail=(
                                "Manuscript 自报为临床试验但未匹配 NCT/ISRCTN/"
                                "ChiCTR/EudraCT 等任一注册号格式。ICMJE 自 2005 起"
                                "要求所有干预性临床试验必须公开预注册才能发表。"
                                + (
                                    f" 本论文年份 {year}。"
                                    if year is not None
                                    else ""
                                )
                            ),
                            evidence={
                                "trial_ids_found": [],
                                "paper_year": year,
                                "severity_tier": (
                                    "strict"
                                    if trial_severity == Severity.SUSPICIOUS
                                    else "early"
                                ),
                            },
                            innocent_explanations=[
                                "注册号在 SI 或方法学小节中（提取层未捕获）",
                                "本试验在公开注册体系建立之前已完成（应在论文中说明）",
                                "属于回顾性观察研究（不需注册，应明确声明）",
                            ],
                            academic_reference=self.academic_basis,
                        )
                    )

        # 4) 涉及人/动物但无伦理审批
        if (data.is_human_subjects or data.is_animal_study) and not _has_match(
            text, _ETHICS_APPROVAL
        ):
            subject = "human subjects" if data.is_human_subjects else "animal study"
            findings.append(
                Finding(
                    detector_id=self.id,
                    detector_name=self.name,
                    severity=Severity.CONCERN,
                    summary=(
                        f"涉及 {subject} 但未检测到伦理审批号 / IRB / IACUC 声明"
                    ),
                    detail=(
                        f"Manuscript 自报涉及 {subject}，但全文未匹配到任何"
                        "伦理审批 / IRB / IACUC / 委员会审查的表述。"
                        " 注意:N=100+100 召回率研究 (docs/recall_test_v2.md)"
                        " 发现该 finding 在已撤稿和未撤稿两组论文之间触发率几乎"
                        "相同 (~60-65%),主要原因是 PDF 提取常常漏掉 SI/末尾"
                        "的伦理声明,而非真造假信号。因此从 SUSPICIOUS 降为 CONCERN。"
                    ),
                    evidence={"ethics_match": False},
                    innocent_explanations=[
                        "审批信息在 Methods 子节用了非常规措辞",
                        "本研究属于豁免审批的类型（如完全匿名问卷），应说明",
                        "审批信息只在 SI 中（main text 提取缺失）",
                    ],
                    academic_reference=self.academic_basis,
                )
            )

        # 5) 利益冲突未声明
        if not _has_match(text, _COI_DISCLOSURE):
            findings.append(
                Finding(
                    detector_id=self.id,
                    detector_name=self.name,
                    severity=Severity.NOTE,
                    summary="未检测到利益冲突声明",
                    detail=(
                        "全文未匹配 'competing interests' / 'conflict of interest' / "
                        "'declarations of interest' / '利益冲突' 等措辞。"
                    ),
                    evidence={"coi_match": False},
                    innocent_explanations=[
                        "声明在投稿系统中而非 manuscript 文件里（很多期刊如此）",
                        "声明在版权页 / footnote / acknowledgements 中",
                        "本提取仅扫描 main text",
                    ],
                    academic_reference=self.academic_basis,
                )
            )

        return findings
