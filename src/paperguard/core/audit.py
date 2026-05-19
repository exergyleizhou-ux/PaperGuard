"""审计日志：每次运行的不可变记录。"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class AuditEntry:
    timestamp: str
    event: str
    details: dict[str, Any]


class AuditLog:
    """单次运行的不可变审计日志。

    每个 PaperGuard 运行实例创建一个 AuditLog，
    所有重要事件（数据下载、检测调用、结果生成）都记录。
    完成后写入 JSON 文件，作为可复现性证据。
    """

    def __init__(self, run_id: str, output_dir: Path) -> None:
        self.run_id = run_id
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.entries: list[AuditEntry] = []
        self.log_event("audit_initialized", {"run_id": run_id})

    def log_event(self, event: str, details: dict[str, Any]) -> None:
        entry = AuditEntry(
            timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            event=event,
            details=details,
        )
        self.entries.append(entry)

    def save(self) -> Path:
        output_path = self.output_dir / f"audit_{self.run_id}.json"
        with output_path.open("w", encoding="utf-8") as f:
            json.dump([asdict(e) for e in self.entries], f, indent=2, ensure_ascii=False)
        return output_path
