"""Generate JSON Schema for AuditReport.

Used to validate downstream consumers' expectations + power IDE
auto-complete on report JSON files.

Run:
    python -m paperguard.reporter.schema > schema.json
"""
from __future__ import annotations

import json
import sys
from typing import Any

from paperguard.core.types import AuditReport


def render_schema() -> dict[str, Any]:
    schema: dict[str, Any] = AuditReport.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "https://paperguard.example/schema/audit-report.json"
    schema["title"] = "PaperGuard Audit Report"
    return schema


def main() -> None:
    sys.stdout.write(json.dumps(render_schema(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
