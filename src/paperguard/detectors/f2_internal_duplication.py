"""F2 — 图像**内部**重复检测（Bik 风格）。

学术依据：Bik, Casadevall, Fang (2016) mBio. 检测同一张图内重复的 patch
（同一 Western blot 条带、显微镜视野、同色斑块）。

策略：
1. 用 ORB 提取关键点（旋转 + 尺度不变）
2. 自匹配（descriptor 1 ↔ descriptor 2，同一张图）
3. 过滤掉过近的匹配（避免自身匹配自身）
4. 用 RANSAC 寻找仿射变换；如果有 ≥ N 个 inlier 匹配到非平凡偏移上，
   提示存在重复 patch
5. 输出 inlier 数 + 平移向量 + 命中位置

F2 vs F1：F1 比"两张图整体相似"，F2 比"一张图内是否有自相似 patch"。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity


@dataclass
class InternalDuplicationInput:
    image_paths: list[Path]
    min_inliers: int = 12
    min_translation_px: float = 20.0  # 平移向量长度需 > 20px 才算"非平凡"


def _analyze_one(
    path: Path, min_inliers: int, min_translation_px: float
) -> dict[str, Any] | None:
    """对单张图做自匹配分析，返回检测结果或 None。"""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None

    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    h, w = img.shape[:2]
    if min(h, w) < 50:
        return None  # 太小不分析

    orb = cv2.ORB_create(nfeatures=1500)  # type: ignore[attr-defined]
    kp, des = orb.detectAndCompute(img, None)
    if des is None or len(kp) < 30:
        return None

    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    matches = bf.knnMatch(des, des, k=3)

    # 过滤：跳过自身 + 选择第二最近作为匹配候选
    good: list[Any] = []
    for triplet in matches:
        if len(triplet) < 2:
            continue
        # triplet[0] 是自身（trainIdx == queryIdx），triplet[1] 是第二近
        m_pair = triplet[1]
        if m_pair.queryIdx == m_pair.trainIdx:
            continue
        # Lowe ratio 替代：m_pair 的距离应明显小于 m_third
        if len(triplet) >= 3 and m_pair.distance < 0.75 * triplet[2].distance:
            # 平移须 >= min_translation_px
            p1 = np.array(kp[m_pair.queryIdx].pt, dtype=float)
            p2 = np.array(kp[m_pair.trainIdx].pt, dtype=float)
            if float(np.linalg.norm(p1 - p2)) >= min_translation_px:
                good.append(m_pair)

    if len(good) < min_inliers:
        return None

    pts1 = np.array([kp[m.queryIdx].pt for m in good], dtype=np.float32)
    pts2 = np.array([kp[m.trainIdx].pt for m in good], dtype=np.float32)
    # 用仿射 RANSAC 找一致变换
    affine, mask = cv2.estimateAffinePartial2D(
        pts1.reshape(-1, 1, 2),
        pts2.reshape(-1, 1, 2),
        method=cv2.RANSAC,
        ransacReprojThreshold=4.0,
        confidence=0.99,
    )
    if mask is None:
        return None
    inliers = int(mask.sum())
    if inliers < min_inliers:
        return None

    tx, ty = (float(affine[0, 2]), float(affine[1, 2])) if affine is not None else (0.0, 0.0)
    translation_norm = float((tx**2 + ty**2) ** 0.5)
    if translation_norm < min_translation_px:
        return None

    return {
        "image": str(path),
        "width": w,
        "height": h,
        "keypoints": len(kp),
        "good_matches": len(good),
        "inliers": inliers,
        "translation_x": tx,
        "translation_y": ty,
        "translation_norm": translation_norm,
    }


class F2InternalDuplicationDetector(BaseDetector):
    """单图内部重复 patch 检测（Bik 风格）。"""

    id: ClassVar[str] = "F2"
    name: ClassVar[str] = "Internal Image Duplication"
    description: ClassVar[str] = (
        "对单张图自匹配，检测同一图内是否存在被旋转/平移的重复 patch。"
    )
    academic_basis: ClassVar[str] = (
        "Bik, Casadevall, Fang (2016). The Prevalence of Inappropriate Image "
        "Duplication in Biomedical Research Publications. mBio, 7(3)."
    )
    data_requirements: ClassVar[list[str]] = ["image_files"]
    assumption_cluster: ClassVar[str] = "image_forensics"

    def check_applicability(self, data: Any) -> tuple[bool, str]:
        if not isinstance(data, InternalDuplicationInput):
            return False, "Expected InternalDuplicationInput"
        if not data.image_paths:
            return False, "No images provided"
        try:
            import cv2  # noqa: F401
        except ImportError:
            return False, "opencv-python is not installed"
        return True, ""

    def _detect(self, data: InternalDuplicationInput, seed: int) -> list[Finding]:
        findings: list[Finding] = []
        for img in data.image_paths:
            result = _analyze_one(
                img, data.min_inliers, data.min_translation_px
            )
            if result is None:
                continue
            inliers = result["inliers"]
            # 严重性按 inlier 数升级
            if inliers >= 40:
                severity = Severity.SUSPICIOUS
            elif inliers >= 20:
                severity = Severity.CONCERN
            else:
                severity = Severity.NOTE

            findings.append(
                Finding(
                    detector_id=self.id,
                    detector_name=self.name,
                    severity=severity,
                    summary=(
                        f"图像 '{img.name}' 内部可能存在重复 patch "
                        f"({inliers} 个一致 ORB 匹配，平移 "
                        f"{result['translation_norm']:.1f}px)"
                    ),
                    detail=(
                        f"在 {img.name} ({result['width']}×{result['height']}) "
                        f"上提取 {result['keypoints']} 个 ORB 特征点，"
                        f"自匹配后保留 {result['good_matches']} 个候选，"
                        f"RANSAC 仿射变换中 {inliers} 个 inlier 一致地映射到"
                        f"位移 (Δx={result['translation_x']:.1f}, "
                        f"Δy={result['translation_y']:.1f})。"
                        f"这是同一图内存在被复制粘贴 patch 的典型签名。"
                    ),
                    test_statistic=float(inliers),
                    test_name="ORB+RANSAC inliers",
                    evidence=result,
                    innocent_explanations=[
                        "图中本来就有重复的结构（如规则网格、刻度尺、对照点）",
                        "ORB 在低纹理 / 高对称图上容易给假阳性",
                        "图像是拼图（multi-panel figure 子图边界附近的伪匹配）",
                        "拍摄时镜头视野有重叠的对照参考物",
                    ],
                    academic_reference=self.academic_basis,
                )
            )
        return findings
