"""JSON 导出 — 机器可读的完整报告。"""
from __future__ import annotations

import json
from pathlib import Path

from paperguard.core.types import AuditReport


def export_json(report: AuditReport, output_path: Path) -> None:
    """把 AuditReport 序列化为 JSON 文件。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = report.model_dump(mode="json")
    output_path.write_text(
        json.dumps(data, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )
