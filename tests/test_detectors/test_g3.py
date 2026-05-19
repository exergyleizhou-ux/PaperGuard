"""G3 rsid forensics 测试。"""
from __future__ import annotations

import zipfile
from pathlib import Path

from paperguard.core.types import Severity
from paperguard.detectors.g3_rsid_forensics import (
    G3RsidForensicsDetector,
    _collect_rsids_from_docx,
)


def _make_docx_no_rsid(path: Path) -> None:
    """python-docx 风格的 docx：完全没有 rsid。"""
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    main_ct = (
        "application/vnd.openxmlformats-officedocument."
        "wordprocessingml.document.main+xml"
    )
    rels_ct = "application/vnd.openxmlformats-package.relationships+xml"
    doc_rel_type = (
        "http://schemas.openxmlformats.org/officeDocument/2006/"
        "relationships/officeDocument"
    )
    content_types = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="rels" ContentType="{rels_ct}"/>
  <Override PartName="/word/document.xml" ContentType="{main_ct}"/>
</Types>"""
    rels = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="{doc_rel_type}" Target="word/document.xml"/>
</Relationships>"""
    document = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{w}">
  <w:body><w:p><w:r><w:t>hi</w:t></w:r></w:p></w:body>
</w:document>"""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", document)


def _make_docx_many_rsids(path: Path) -> None:
    """模拟真实 Word 编辑：多个不同 rsid。"""
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    main_ct = (
        "application/vnd.openxmlformats-officedocument."
        "wordprocessingml.document.main+xml"
    )
    rels_ct = "application/vnd.openxmlformats-package.relationships+xml"
    doc_rel_type = (
        "http://schemas.openxmlformats.org/officeDocument/2006/"
        "relationships/officeDocument"
    )
    content_types = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="rels" ContentType="{rels_ct}"/>
  <Override PartName="/word/document.xml" ContentType="{main_ct}"/>
</Types>"""
    rels = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="{doc_rel_type}" Target="word/document.xml"/>
</Relationships>"""
    rsids = [
        0x00112233,
        0x00445566,
        0x00778899,
        0x00AABBCC,
        0x00DDEEFF,
        0x00112299,
    ]
    paragraphs = "".join(
        f'<w:p w:rsidR="{rsid:08X}"><w:r w:rsidR="{rsid:08X}">'
        f"<w:t>p{i}</w:t></w:r></w:p>"
        for i, rsid in enumerate(rsids, start=1)
    )
    document = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{w}">
  <w:body>{paragraphs}</w:body>
</w:document>"""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", document)


def test_g3_no_rsid_concern(tmp_path: Path) -> None:
    p = tmp_path / "tool_generated.docx"
    _make_docx_no_rsid(p)
    info = _collect_rsids_from_docx(p)
    assert info["unique_rsids"] == 0
    result = G3RsidForensicsDetector().detect(p, seed=42)
    assert result.applicable
    assert len(result.findings) == 1
    assert result.findings[0].severity == Severity.CONCERN


def test_g3_many_rsids_pass(tmp_path: Path) -> None:
    p = tmp_path / "word_edited.docx"
    _make_docx_many_rsids(p)
    info = _collect_rsids_from_docx(p)
    assert info["unique_rsids"] >= 5
    result = G3RsidForensicsDetector().detect(p, seed=42)
    assert result.applicable
    assert len(result.findings) == 0


def test_g3_inapplicable_non_docx(tmp_path: Path) -> None:
    p = tmp_path / "not.txt"
    p.write_text("hello")
    result = G3RsidForensicsDetector().detect(p, seed=42)
    assert not result.applicable
