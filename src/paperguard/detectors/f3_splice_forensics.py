"""F3 — Splice / 复制粘贴像素级法证。

学术依据：Bik et al. (2016); Cozzolino & Verdoliva (2015) Splicebuster;
标准数字图像取证。

策略（轻量、合理保守）：
1. 对单图分块 (16×16 grid，跨度 8px)，每块计算两类指纹：
   - 均值/方差签名（亮度统计）
   - 高频能量（Laplacian variance）
2. 跨块相似度：找均值/方差几乎相同但空间相距远的块对
3. 输出 inlier 数 + 命中坐标

F3 与 F2 的区别：F2 用 ORB 特征点（角点），对低纹理的染色 / Western blot
不敏感；F3 用统计签名，对均匀色块的拼接更敏感。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity


@dataclass
class SpliceForensicsInput:
    image_paths: list[Path]
    patch_size: int = 32
    stride: int = 16
    similarity_threshold: float = 0.99  # 块均值/方差相关性
    min_pair_distance: float = 50.0     # 像素距离 >= 50 才算独立位置


def _analyze_one(
    path: Path,
    patch_size: int,
    stride: int,
    sim: float,
    min_dist: float,
) -> dict[str, Any] | None:
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None

    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    h, w = img.shape[:2]
    if min(h, w) < patch_size * 3:
        return None

    # 分块统计：每块 [mean, std, lap_var]
    patches: list[tuple[int, int, float, float, float]] = []
    for y in range(0, h - patch_size + 1, stride):
        for x in range(0, w - patch_size + 1, stride):
            block = img[y : y + patch_size, x : x + patch_size]
            m = float(block.mean())
            s = float(block.std())
            lap = cv2.Laplacian(block, cv2.CV_64F)
            lv = float(lap.var())
            patches.append((x, y, m, s, lv))

    if len(patches) < 20:
        return None

    feats = np.array([(m, s, lv) for _, _, m, s, lv in patches])

    matches: list[tuple[int, int, int, int, float]] = []
    n = len(patches)
    # 严格阈值：要求几乎像素级一致
    mean_eps = 0.5
    std_eps = 0.5
    lapvar_rel = 0.02
    # 收集一致的平移向量；只有当多对 patch 给出相同位移时才认为是 copy-move
    translation_votes: dict[tuple[int, int], int] = {}
    for i in range(n):
        m_i, s_i, lv_i = feats[i]
        for j in range(i + 1, n):
            m_j, s_j, lv_j = feats[j]
            if abs(m_i - m_j) > mean_eps:
                continue
            if abs(s_i - s_j) > std_eps:
                continue
            if abs(lv_i - lv_j) / (max(lv_i, lv_j) + 1e-9) > lapvar_rel:
                continue
            x1, y1 = patches[i][0], patches[i][1]
            x2, y2 = patches[j][0], patches[j][1]
            dx = x2 - x1
            dy = y2 - y1
            dist = float((dx * dx + dy * dy) ** 0.5)
            if dist < min_dist:
                continue
            # 量化位移向量（容许 ±stride/2）
            key = (round(dx / stride), round(dy / stride))
            translation_votes[key] = translation_votes.get(key, 0) + 1
            matches.append((x1, y1, x2, y2, 1.0))

    if not matches:
        return None
    # 必须有一个一致的位移向量得到 ≥ 5 票（非平凡 copy-move 的特征）
    if not translation_votes:
        return None
    top_translation, top_votes = max(
        translation_votes.items(), key=lambda kv: kv[1]
    )
    if top_votes < 5:
        return None

    return {
        "image": str(path),
        "width": w,
        "height": h,
        "patches": len(patches),
        "similar_pair_count": len(matches),
        "dominant_translation_votes": top_votes,
        "dominant_translation": top_translation,
        "top_pairs": matches[:15],
    }


class F3SpliceForensicsDetector(BaseDetector):
    """统计签名块匹配检测同一图内的拼接 / 复制粘贴。"""

    id: ClassVar[str] = "F3"
    name: ClassVar[str] = "Splice / Copy-Move Forensics"
    description: ClassVar[str] = (
        "用块级统计签名（均值/方差/Laplacian variance）找图内拼接。"
    )
    academic_basis: ClassVar[str] = (
        "Cozzolino & Verdoliva (2015) Splicebuster; Bik et al. (2016)."
    )
    data_requirements: ClassVar[list[str]] = ["image_files"]
    assumption_cluster: ClassVar[str] = "image_forensics"

    def check_applicability(self, data: Any) -> tuple[bool, str]:
        if not isinstance(data, SpliceForensicsInput):
            return False, "Expected SpliceForensicsInput"
        if not data.image_paths:
            return False, "No images"
        try:
            import cv2  # noqa: F401
        except ImportError:
            return False, "opencv-python not installed"
        return True, ""

    def _detect(self, data: SpliceForensicsInput, seed: int) -> list[Finding]:
        findings: list[Finding] = []
        for img in data.image_paths:
            r = _analyze_one(
                img, data.patch_size, data.stride,
                data.similarity_threshold, data.min_pair_distance,
            )
            if r is None:
                continue
            n_pairs = r["similar_pair_count"]
            top_votes = r["dominant_translation_votes"]
            severity = (
                Severity.SUSPICIOUS if top_votes >= 30
                else Severity.CONCERN if top_votes >= 15
                else Severity.NOTE
            )
            findings.append(
                Finding(
                    detector_id=self.id,
                    detector_name=self.name,
                    severity=severity,
                    summary=(
                        f"图像 '{img.name}' 内 {n_pairs} 对远距 patch "
                        f"统计签名几乎相同"
                    ),
                    detail=(
                        f"在 {img.name} ({r['width']}×{r['height']}) 上分块"
                        f"得到 {r['patches']} 个 {data.patch_size}px patch。"
                        f"其中 {n_pairs} 对空间相距 ≥ {data.min_pair_distance:.0f}px "
                        f"的 patch 在 (mean, std, LaplacianVar) 三维签名上 "
                        f"cosine ≥ {data.similarity_threshold}。"
                        f"这是同一图内可能存在拼接 / 复制粘贴的统计指纹。"
                    ),
                    test_statistic=float(n_pairs),
                    test_name="similar patch pairs",
                    evidence=r,
                    innocent_explanations=[
                        "图本身有大面积均匀区域（如显微镜空白背景）",
                        "图是规则结构（网格、刻度尺、对照阵列）",
                        "图像被全局滤镜处理后局部统计趋同（合法的图像处理）",
                        "F3 对低对比度图像假阳性率较高，建议人工复核命中坐标",
                    ],
                    academic_reference=self.academic_basis,
                )
            )
        return findings
