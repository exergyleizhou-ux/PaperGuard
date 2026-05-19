"""F4 — Cross-Paper Image Duplication（持久 pHash 库）。

学术依据：Masliah 案（2024 NIH）、Hwang 案（2005 Science）— 跨论文
图像复用是已知造假签名之一，单论文 F1/F2/F3 抓不到。

策略：
- 用户指定一个本地 SQLite 库存历史扫过的图像 pHash + 来源论文标签
- 每次 detect() 时把当前图像 pHash 入库
- 同时查库中是否有其它论文的图像 hamming 距离 ≤ 阈值
- 命中 → SUSPICIOUS（同作者跨论文）/ CRITICAL（不同作者跨论文）

注意：CLI 不强制持久化；用户必须显式提供 store_path 才启用，避免
默认情况下产生"幽灵库"。
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity


@dataclass
class CrossPaperImageInput:
    image_paths: list[Path]
    store_path: Path          # 本地 SQLite 库
    current_paper_id: str     # 当前论文标识（DOI 或文件路径）
    current_authors: list[str] | None = None
    hamming_concern: int = 8
    hamming_suspicious: int = 5
    hamming_critical: int = 2


def _open_store(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute(
        """CREATE TABLE IF NOT EXISTS images (
            phash TEXT PRIMARY KEY,
            paper_id TEXT NOT NULL,
            authors TEXT,
            added_utc TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    return conn


def _hamming(a: str, b: str) -> int:
    if len(a) != len(b):
        return 999
    # imagehash phash 默认是 64-bit, hex 16 字符
    try:
        ai = int(a, 16)
        bi = int(b, 16)
    except ValueError:
        return 999
    return bin(ai ^ bi).count("1")


def _phash_of(path: Path) -> str | None:
    try:
        import imagehash
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(path) as img:
            return str(imagehash.phash(img))
    except Exception:  # noqa: BLE001
        return None


class F4CrossPaperImageDetector(BaseDetector):
    """跨论文图像 pHash 比对，依赖用户维护的本地 SQLite 库。"""

    id: ClassVar[str] = "F4"
    name: ClassVar[str] = "Cross-Paper Image Duplication"
    description: ClassVar[str] = (
        "在本地持久库中查当前图像是否曾出现于其它论文。"
    )
    academic_basis: ClassVar[str] = (
        "Masliah investigation (NIH 2024); Hwang affair (2005); "
        "Bik et al. (2016) cross-publication image reuse studies."
    )
    data_requirements: ClassVar[list[str]] = ["image_files", "persistent_store"]
    assumption_cluster: ClassVar[str] = "image_forensics"

    def check_applicability(self, data: Any) -> tuple[bool, str]:
        if not isinstance(data, CrossPaperImageInput):
            return False, "Expected CrossPaperImageInput"
        if not data.image_paths:
            return False, "No images"
        try:
            import imagehash  # noqa: F401
        except ImportError:
            return False, "imagehash not installed"
        return True, ""

    def _detect(
        self, data: CrossPaperImageInput, seed: int
    ) -> list[Finding]:
        conn = _open_store(data.store_path)
        cur = conn.cursor()
        findings: list[Finding] = []

        current_authors_set = {
            a.lower() for a in (data.current_authors or [])
        }

        for img in data.image_paths:
            phash = _phash_of(img)
            if phash is None:
                continue
            # 查库（全表扫描；规模 < 10k 时足够快）
            cur.execute(
                "SELECT phash, paper_id, authors FROM images WHERE paper_id != ?",
                (data.current_paper_id,),
            )
            for row_phash, row_paper, row_authors in cur.fetchall():
                dist = _hamming(phash, row_phash)
                if dist > data.hamming_concern:
                    continue
                # 同作者？
                row_authors_set = {
                    a.strip().lower()
                    for a in (row_authors or "").split(";")
                    if a.strip()
                }
                shared_authors = current_authors_set & row_authors_set
                same_lab = bool(shared_authors)

                if dist <= data.hamming_critical:
                    severity = (
                        Severity.SUSPICIOUS if same_lab else Severity.CRITICAL
                    )
                    tag = "near-identical"
                elif dist <= data.hamming_suspicious:
                    severity = (
                        Severity.CONCERN if same_lab else Severity.SUSPICIOUS
                    )
                    tag = "highly similar"
                else:
                    severity = Severity.CONCERN
                    tag = "similar"

                findings.append(
                    Finding(
                        detector_id=self.id,
                        detector_name=self.name,
                        severity=severity,
                        summary=(
                            f"Image '{img.name}' {tag} across papers "
                            f"(hamming={dist}, prior paper: {row_paper})"
                        ),
                        detail=(
                            f"图像 '{img.name}' 在本地库中与论文 "
                            f"'{row_paper}' 的某图 pHash Hamming 距离为 "
                            f"{dist}。同实验室作者重叠数: "
                            f"{len(shared_authors)}。"
                            "Hwang 2005 / Masliah 2024 调查都把跨论文图像复用"
                            "作为造假的核心证据。"
                        ),
                        test_statistic=float(dist),
                        test_name="pHash Hamming distance",
                        evidence={
                            "current_image": str(img),
                            "current_paper_id": data.current_paper_id,
                            "matched_paper_id": row_paper,
                            "matched_authors": row_authors,
                            "shared_authors": sorted(shared_authors),
                            "hamming_distance": dist,
                            "same_lab": same_lab,
                        },
                        innocent_explanations=[
                            "同一作者团队在合法的后续/扩展研究中复用图像"
                            "（应在 Methods 显式声明）",
                            "图像是仪器自动生成的标尺/对照图，多次研究重复出现",
                            "Conference + journal 双投稿（同一图在两份合法记录里）",
                            "pHash 假阳性（低对比度图像）",
                        ],
                        academic_reference=self.academic_basis,
                    )
                )

            # 入库本次图像（即使触发也入库，方便后续审计）
            authors_str = ";".join(data.current_authors or [])
            try:
                cur.execute(
                    "INSERT OR REPLACE INTO images "
                    "(phash, paper_id, authors) VALUES (?, ?, ?)",
                    (phash, data.current_paper_id, authors_str),
                )
            except sqlite3.IntegrityError:
                pass

        conn.commit()
        conn.close()
        return findings
