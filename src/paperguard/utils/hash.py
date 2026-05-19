"""SHA-256 工具 — 每个输入文件必须有哈希用于审计。"""
from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: Path) -> str:
    """计算文件的 SHA-256 hex digest。"""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    """计算字节串的 SHA-256 hex digest。"""
    return hashlib.sha256(data).hexdigest()
