"""G4 — 文件元数据取证。

学术依据：标准数字取证实践 (NIST SP 800-101)；ORI 调查工具集。
文件元数据是物理事实，不是统计推断。

核心检查：
1. 文件创建时间是否早于声称的实验时间
2. creator/author 字段是否与作者名单一致
3. revision 计数是否提示一次性写入
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity


class MetadataForensicsInput:
    """G4 输入结构。"""

    def __init__(
        self,
        file_path: Path,
        claimed_experiment_start: datetime | None = None,
        claimed_experiment_end: datetime | None = None,
        claimed_authors: list[str] | None = None,
        paper_submission_date: datetime | None = None,
    ) -> None:
        self.file_path = file_path
        self.claimed_experiment_start = claimed_experiment_start
        self.claimed_experiment_end = claimed_experiment_end
        self.claimed_authors = claimed_authors or []
        self.paper_submission_date = paper_submission_date


def extract_excel_metadata(path: Path) -> dict[str, Any]:
    """从 Excel 文件提取核心属性。"""
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True)
    props = wb.properties
    return {
        "creator": props.creator,
        "last_modified_by": props.lastModifiedBy,
        "created": props.created,
        "modified": props.modified,
        "title": props.title,
        "subject": props.subject,
        "description": props.description,
        "keywords": props.keywords,
        "category": props.category,
        "revision": props.revision,
        "version": getattr(props, "version", None),
    }


def extract_docx_metadata(path: Path) -> dict[str, Any]:
    """从 .docx 文件提取 OOXML core properties + app properties。

    .docx 是 zip 包，docProps/core.xml 含 dc:creator、cp:lastModifiedBy、
    dcterms:created、dcterms:modified、cp:revision 等；docProps/app.xml 含
    Application、AppVersion、TotalTime（编辑总分钟数）等。
    """
    import zipfile
    from datetime import datetime
    from xml.etree import ElementTree as ET

    ns = {
        "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
        "dc": "http://purl.org/dc/elements/1.1/",
        "dcterms": "http://purl.org/dc/terms/",
        "ep": "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties",
    }

    def _parse_dt(s: str | None) -> datetime | str | None:
        if not s:
            return None
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return s

    out: dict[str, Any] = {
        "creator": None,
        "last_modified_by": None,
        "created": None,
        "modified": None,
        "title": None,
        "subject": None,
        "description": None,
        "keywords": None,
        "category": None,
        "revision": None,
        "application": None,
        "app_version": None,
        "total_edit_minutes": None,
    }

    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        if "docProps/core.xml" in names:
            with z.open("docProps/core.xml") as f:
                root = ET.parse(f).getroot()

            def _text(tag: str, namespace: str) -> str | None:
                el = root.find(f"{{{ns[namespace]}}}{tag}")
                return el.text if el is not None else None

            out["creator"] = _text("creator", "dc")
            out["last_modified_by"] = _text("lastModifiedBy", "cp")
            out["created"] = _parse_dt(_text("created", "dcterms"))
            out["modified"] = _parse_dt(_text("modified", "dcterms"))
            out["title"] = _text("title", "dc")
            out["subject"] = _text("subject", "dc")
            out["description"] = _text("description", "dc")
            out["keywords"] = _text("keywords", "cp")
            out["category"] = _text("category", "cp")
            rev = _text("revision", "cp")
            if rev is not None:
                try:
                    out["revision"] = int(rev)
                except ValueError:
                    out["revision"] = rev

        if "docProps/app.xml" in names:
            with z.open("docProps/app.xml") as f:
                root = ET.parse(f).getroot()
            for child in root:
                tag = child.tag.split("}", 1)[-1]
                if tag == "Application":
                    out["application"] = child.text
                elif tag == "AppVersion":
                    out["app_version"] = child.text
                elif tag == "TotalTime":
                    try:
                        out["total_edit_minutes"] = int(child.text or "0")
                    except (ValueError, TypeError):
                        pass

    return out


def extract_pdf_metadata(path: Path) -> dict[str, Any]:
    """从 PDF 文件提取核心属性。"""
    import pymupdf

    doc = pymupdf.open(path)  # type: ignore[no-untyped-call]
    meta = doc.metadata or {}
    doc.close()  # type: ignore[no-untyped-call]
    return {
        "creator": meta.get("creator"),
        "producer": meta.get("producer"),
        "author": meta.get("author"),
        "creationDate": meta.get("creationDate"),
        "modDate": meta.get("modDate"),
        "title": meta.get("title"),
        "subject": meta.get("subject"),
        "keywords": meta.get("keywords"),
    }


class G4MetadataForensicsDetector(BaseDetector):
    """检查文件元数据与声称的实验时间线是否一致。"""

    id: ClassVar[str] = "G4"
    name: ClassVar[str] = "File Metadata Forensics"
    description: ClassVar[str] = "检查文件元数据与声称的实验时间线是否一致。"
    academic_basis: ClassVar[str] = "标准数字取证实践 (NIST SP 800-101)；ORI 调查工具集。"
    data_requirements: ClassVar[list[str]] = ["data_file_path", "claimed_timeline"]
    assumption_cluster: ClassVar[str] = "metadata_forensics"

    def check_applicability(self, data: Any) -> tuple[bool, str]:
        if not isinstance(data, MetadataForensicsInput):
            return False, "Expected MetadataForensicsInput"
        if not data.file_path.exists():
            return False, f"File not found: {data.file_path}"
        suffix = data.file_path.suffix.lower()
        if suffix not in {".xlsx", ".xlsm", ".pdf", ".docx"}:
            return False, f"Unsupported file type: {suffix}"
        return True, ""

    def _detect(self, data: MetadataForensicsInput, seed: int) -> list[Finding]:
        findings: list[Finding] = []
        suffix = data.file_path.suffix.lower()

        if suffix in {".xlsx", ".xlsm"}:
            meta = extract_excel_metadata(data.file_path)
        elif suffix == ".docx":
            meta = extract_docx_metadata(data.file_path)
        elif suffix == ".pdf":
            meta = extract_pdf_metadata(data.file_path)
        else:
            return findings

        created = meta.get("created") or meta.get("creationDate")

        # 检查 1：创建时间早于声称的实验开始时间
        if data.claimed_experiment_start and created:
            created_dt: datetime | None
            if isinstance(created, str):
                try:
                    created_dt = datetime.fromisoformat(
                        created.replace("Z", "+00:00")
                    )
                except ValueError:
                    created_dt = None
            elif isinstance(created, datetime):
                created_dt = created
            else:
                created_dt = None

            if created_dt is not None:
                exp_start = data.claimed_experiment_start
                # 归一化 naive vs aware 比较
                if (created_dt.tzinfo is None) != (exp_start.tzinfo is None):
                    if created_dt.tzinfo is not None:
                        created_dt = created_dt.replace(tzinfo=None)
                    if exp_start.tzinfo is not None:
                        exp_start = exp_start.replace(tzinfo=None)
                gap_days = (exp_start - created_dt).days
                if gap_days > 1:
                    findings.append(
                        Finding(
                            detector_id=self.id,
                            detector_name=self.name,
                            severity=Severity.CRITICAL,
                            summary=(
                                f"文件创建于 {created_dt.isoformat()}，"
                                f"早于声称的实验开始时间 {exp_start.isoformat()}"
                            ),
                            detail=(
                                f"文件 '{data.file_path.name}' 的元数据 creation "
                                f"timestamp 为 {created_dt}，但声称实验始于 {exp_start}。"
                                f"该数据文件不可能在 {exp_start} 时存在于其当前形式。"
                                f"这是元数据层面的时间线矛盾，"
                                f"无法用四舍五入或数据清洗解释。"
                            ),
                            p_value=None,
                            evidence={
                                "file": str(data.file_path),
                                "file_created": created_dt.isoformat(),
                                "claimed_exp_start": exp_start.isoformat(),
                                "gap_days": gap_days,
                                "raw_metadata": {k: str(v) for k, v in meta.items()},
                            },
                            innocent_explanations=[
                                "文件创建时间被系统时间错误污染（操作系统时钟错误）",
                                "数据是从更早的项目重新利用（应在论文中声明）",
                                "原始数据被复制到新文件，但仪器输出确实更晚",
                                "文件创建时间是模板创建时间，数据填充更晚",
                            ],
                            academic_reference=self.academic_basis,
                        )
                    )

        # 检查 2：作者信息一致性
        # 跳过已知出版商/排版工具 creator，避免对发表 PDF 的假阳性
        publisher_creators = {
            "springer", "elsevier", "wiley", "oxford university press",
            "cambridge university press", "sage", "taylor & francis",
            "nature publishing group", "frontiers", "mdpi", "plos",
            "ieee", "acm", "apa", "ams", "rsc", "acs", "aip", "iop",
            "biomed central", "hindawi", "emerald", "informa", "bmj",
            "the lancet", "cell press", "arxiv.org", "biorxiv", "medrxiv",
            "latex", "pdflatex", "xelatex", "acrobat distiller",
            "microsoft® word", "microsoft word", "libreoffice",
            "pages", "openoffice", "ghostscript",
        }
        creator = meta.get("creator") or meta.get("author")
        creator_str = str(creator or "").strip().lower()
        is_publisher_artifact = any(
            pub in creator_str for pub in publisher_creators
        )
        if creator and data.claimed_authors and not is_publisher_artifact:
            authors_lower = [a.lower() for a in data.claimed_authors]
            matches = any(
                creator_str in a or a in creator_str for a in authors_lower
            )
            if not matches:
                findings.append(
                    Finding(
                        detector_id=self.id,
                        detector_name=self.name,
                        severity=Severity.CONCERN,
                        summary=f"文件 creator '{creator}' 不在作者名单中",
                        detail=(
                            f"文件元数据中的 creator 字段为 '{creator}'，"
                            f"但论文作者列表为 {data.claimed_authors}。"
                            f"这可能意味着数据由非作者准备，"
                            f"或文件经过他人之手。需要解释。"
                        ),
                        evidence={
                            "file": str(data.file_path),
                            "creator_in_metadata": str(creator),
                            "claimed_authors": data.claimed_authors,
                        },
                        innocent_explanations=[
                            "学生/技术员准备数据但未列为作者（学术规范问题但非造假）",
                            "原文件由模板提供，creator 是模板作者",
                            "文件在共用电脑上创建，登录用户不是实际操作者",
                            "公司/机构邮箱与个人邮箱不同",
                        ],
                        academic_reference=self.academic_basis,
                    )
                )

        # 检查 3：修订次数与数据量关系
        revision = meta.get("revision")
        if revision is not None:
            try:
                revision_int = int(revision)
                if revision_int <= 2:
                    findings.append(
                        Finding(
                            detector_id=self.id,
                            detector_name=self.name,
                            severity=Severity.NOTE,
                            summary=(
                                f"文件 revision 数仅为 {revision_int}，提示一次性写入"
                            ),
                            detail=(
                                f"Excel 文件的 revision 计数为 {revision_int}，"
                                f"意味着文件几乎没有经过多次保存。"
                                f"长期收集的实验数据通常会有数十次保存历史。"
                            ),
                            evidence={
                                "file": str(data.file_path),
                                "revision_count": revision_int,
                            },
                            innocent_explanations=[
                                "数据是从其他文件复制过来的最终版本（合理）",
                                "数据是自动导出的（仪器软件直接输出）",
                                "作者使用了不保存中间版本的工作流",
                            ],
                            academic_reference=self.academic_basis,
                        )
                    )
            except (ValueError, TypeError):
                pass

        return findings
