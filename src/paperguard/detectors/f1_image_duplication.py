"""F1 — 图像重复检测（perceptual hash）。

学术依据：Bik et al. (2016) 系列；标准 pHash 文献。

策略：
- 对一组图像计算 pHash（Perceptual Hash）
- 两两比较 Hamming 距离
- 距离 ≤ 5 → 高度相似（可能旋转/裁剪/亮度变体）
- 距离 = 0 → 完全相同
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any, ClassVar

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity


@dataclass
class ImageDuplicationInput:
    image_paths: list[Path]
    hamming_concern: int = 8
    hamming_suspicious: int = 5
    hamming_critical: int = 2


def _compute_phash(path: Path) -> Any:
    """计算单张图像的 pHash。失败返回 None。"""
    try:
        import imagehash
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(path) as img:
            return imagehash.phash(img)
    except Exception:  # noqa: BLE001
        return None


class F1ImageDuplicationDetector(BaseDetector):
    """通过 pHash 检测一组图像之间的相似 / 重复。"""

    id: ClassVar[str] = "F1"
    name: ClassVar[str] = "Image Duplication (pHash)"
    description: ClassVar[str] = "对一组图像计算 perceptual hash，找出疑似重复或近似变体。"
    academic_basis: ClassVar[str] = (
        "Bik et al. (2016) Inappropriate image duplication studies; "
        "standard perceptual-hash forensics."
    )
    data_requirements: ClassVar[list[str]] = ["image_files"]
    assumption_cluster: ClassVar[str] = "image_forensics"

    def check_applicability(self, data: Any) -> tuple[bool, str]:
        if not isinstance(data, ImageDuplicationInput):
            return False, "Expected ImageDuplicationInput"
        if len(data.image_paths) < 2:
            return False, "Need at least 2 images"
        return True, ""

    def _detect(self, data: ImageDuplicationInput, seed: int) -> list[Finding]:
        hashes: list[tuple[Path, Any]] = []
        for p in data.image_paths:
            h = _compute_phash(p)
            if h is not None:
                hashes.append((p, h))

        if len(hashes) < 2:
            return []

        findings: list[Finding] = []
        for (p1, h1), (p2, h2) in combinations(hashes, 2):
            dist = int(h1 - h2)  # imagehash overloads __sub__ as hamming
            if dist > data.hamming_concern:
                continue

            if dist <= data.hamming_critical:
                severity = Severity.CRITICAL
                tag = "near-identical"
            elif dist <= data.hamming_suspicious:
                severity = Severity.SUSPICIOUS
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
                        f"图像疑似 {tag}：{p1.name} ↔ {p2.name} "
                        f"(pHash Hamming={dist})"
                    ),
                    detail=(
                        f"图像 '{p1.name}' 与 '{p2.name}' 的 perceptual hash "
                        f"Hamming 距离为 {dist}（阈值 critical≤"
                        f"{data.hamming_critical}, suspicious≤"
                        f"{data.hamming_suspicious}, concern≤{data.hamming_concern}）。"
                        f"较小的距离表示视觉上几乎相同。"
                    ),
                    test_statistic=float(dist),
                    test_name="pHash Hamming distance",
                    evidence={
                        "image_1": str(p1),
                        "image_2": str(p2),
                        "phash_1": str(h1),
                        "phash_2": str(h2),
                        "hamming_distance": dist,
                    },
                    innocent_explanations=[
                        "两张图本来就应该几乎相同（如 Western blot 控制条带的多次曝光）",
                        "图像来自同一原始素材的不同标注/调色版本（合法的可视化处理）",
                        "图像是同一时间点的不同放大倍数（局部裁剪）",
                        "pHash 对低纹理图像（如均匀背景的染色图）容易假阳性",
                    ],
                    academic_reference=self.academic_basis,
                )
            )

        return findings
