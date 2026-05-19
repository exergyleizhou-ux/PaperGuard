"""文件元数据提取的统一接口。"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def extract_metadata(path: Path) -> dict[str, Any]:
    """返回任何支持文件类型的元数据字典。"""
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        from paperguard.detectors.g4_metadata_forensics import extract_excel_metadata

        return extract_excel_metadata(path)
    elif suffix == ".docx":
        from paperguard.detectors.g4_metadata_forensics import extract_docx_metadata

        return extract_docx_metadata(path)
    elif suffix == ".pdf":
        from paperguard.detectors.g4_metadata_forensics import extract_pdf_metadata

        return extract_pdf_metadata(path)
    else:
        raise ValueError(f"Cannot extract metadata from {suffix}")
