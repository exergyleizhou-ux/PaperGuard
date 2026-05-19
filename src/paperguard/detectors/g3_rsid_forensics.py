"""G3 — .docx rsid 取证。

学术依据：标准 OOXML 取证实践。

`w:rsidR`、`w:rsidRPr`、`w:rsidP` 等修订追踪 ID 是 Word 真实编辑过程
的指纹——每次编辑会话 Word 会分配一个新 rsid。

特征区分：
- 真实 Word 编辑的 docx：通常有 5+ 个不同的 rsid，分散在不同段落 / run
- python-docx / pandoc / docx4j 生成的文件：rsid 数量极少（常常 0–1 个），
  且整个文档段落级 rsid 完全一致
- Word 编辑过但被工具清洗过的：表面 metadata 正常，但 rsid 多样性会暴露

本检测器只看证据，不做指控；innocent_explanations 列出合法情况。
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any, ClassVar

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity

# 各种 rsid 属性
_RSID_ATTRS = ("rsidR", "rsidRPr", "rsidRDefault", "rsidP", "rsidTr", "rsidSect")
_RSID_RE = re.compile(rb"w:rsid[A-Za-z]+=\"([0-9A-Fa-f]+)\"")


def _collect_rsids_from_docx(path: Path) -> dict[str, Any]:
    """从 docx 抽取所有 rsid 出现次数。"""
    counts: dict[str, int] = {}
    paragraph_rsids: set[str] = set()
    run_rsids: set[str] = set()
    with zipfile.ZipFile(path) as z:
        for name in ("word/document.xml", "word/settings.xml"):
            if name not in z.namelist():
                continue
            data = z.read(name)
            for m in _RSID_RE.finditer(data):
                rsid = m.group(1).decode("ascii").lower()
                counts[rsid] = counts.get(rsid, 0) + 1
        # 段落级 rsid：在 <w:pPr> 内或 <w:p w:rsidR=...> 上
        if "word/document.xml" in z.namelist():
            doc = z.read("word/document.xml")
            for m in re.finditer(rb"<w:p[^>]*\sw:rsidR=\"([0-9A-Fa-f]+)\"", doc):
                paragraph_rsids.add(m.group(1).decode("ascii").lower())
            for m in re.finditer(rb"<w:r[^>]*\sw:rsidR=\"([0-9A-Fa-f]+)\"", doc):
                run_rsids.add(m.group(1).decode("ascii").lower())
    return {
        "total_rsid_occurrences": int(sum(counts.values())),
        "unique_rsids": len(counts),
        "paragraph_level_unique": len(paragraph_rsids),
        "run_level_unique": len(run_rsids),
        "top_rsids": dict(sorted(counts.items(), key=lambda kv: -kv[1])[:5]),
    }


class G3RsidForensicsDetector(BaseDetector):
    """检查 docx rsid 多样性以推断文件来源。"""

    id: ClassVar[str] = "G3"
    name: ClassVar[str] = "Docx rsid Forensics"
    description: ClassVar[str] = "通过 rsid 多样性识别 docx 是否由真实 Word 编辑产生。"
    academic_basis: ClassVar[str] = (
        "OOXML 修订追踪规范 (ECMA-376 §17.15.1.55); "
        "标准数字取证实践。"
    )
    data_requirements: ClassVar[list[str]] = ["docx_file_path"]
    assumption_cluster: ClassVar[str] = "metadata_forensics"

    def check_applicability(self, data: Any) -> tuple[bool, str]:
        if not isinstance(data, Path):
            return False, "Expected Path to a .docx file"
        if not data.exists():
            return False, f"File not found: {data}"
        if data.suffix.lower() != ".docx":
            return False, f"Not a .docx file: {data.suffix}"
        return True, ""

    def _detect(self, data: Path, seed: int) -> list[Finding]:
        info = _collect_rsids_from_docx(data)
        unique = info["unique_rsids"]
        paragraphs = info["paragraph_level_unique"]
        findings: list[Finding] = []

        # 阈值经验值：
        # - unique == 0 → 极强：完全没 rsid，肯定不是 Word 编辑
        # - unique <= 2 且段落 == 0 → 提示工具生成
        # - 3 <= unique <= 4 → 偏少，NOTE
        if unique == 0:
            severity = Severity.CONCERN
            summary = "docx 不包含任何 w:rsid 修订标识"
            detail = (
                f"在 {data.name} 中未找到任何 w:rsid 属性。"
                "Word 编辑过程会在每次保存时给段落/run 分配 rsid。"
                "完全没有 rsid 是 python-docx / pandoc 等工具直接生成的典型特征。"
            )
        elif unique <= 2 and paragraphs == 0:
            severity = Severity.NOTE
            summary = f"docx 仅含 {unique} 个 rsid，且无段落级 rsid"
            detail = (
                f"在 {data.name} 中只发现 {unique} 个唯一 rsid，"
                "且段落级别完全没有 rsid 多样性。"
                "Word 真实编辑通常每段都有自己的 rsidR。这种均一性提示"
                "文档由模板/工具一次性生成。"
            )
        elif unique <= 4:
            severity = Severity.NOTE
            summary = f"docx 仅含 {unique} 个唯一 rsid，多样性较低"
            detail = (
                f"在 {data.name} 中找到 {unique} 个唯一 rsid，"
                f"段落级 {paragraphs} 个、run 级 {info['run_level_unique']} 个。"
                "对于长期编辑的论文文档，rsid 数量通常远高于此。"
            )
        else:
            return findings  # 多样性正常，不报告

        findings.append(
            Finding(
                detector_id=self.id,
                detector_name=self.name,
                severity=severity,
                summary=summary,
                detail=detail,
                evidence={
                    "file": str(data),
                    **info,
                },
                innocent_explanations=[
                    "文档由 pandoc / LaTeX→docx / python-docx 等工具生成（合法用法）",
                    "作者使用了 LibreOffice / WPS / Google Docs 等不写 rsid 的编辑器",
                    "Word 文档曾经被复制/重命名，但内容来自单次粘贴",
                    "投稿前作者主动 Inspect → Remove personal info 清洗过",
                ],
                academic_reference=self.academic_basis,
            )
        )
        return findings
