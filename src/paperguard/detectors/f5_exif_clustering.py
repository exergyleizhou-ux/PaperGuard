"""F5 — EXIF 时序聚类（跨图一致性）。

学术依据：标准数字图像取证 + ORI 调查实践。

补充 G1（单图 vs 声称时间线）：F5 关注**多图之间的时序关系**。
真实实验拍摄的多张图通常：
- 在合理时间窗口（同一天 / 同一周）
- 来自同一相机（Make + Model 一致）
- DateTimeOriginal 时间间隔合理（不会同一秒拍 50 张）

异常信号：
1. 图像时间跨度 > 5 年（旧图与新图混用）
2. 同一论文图像来自 ≥ 3 个不同相机型号
3. 多张图 DateTimeOriginal 完全相同（同步伪造时间）
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity
from paperguard.detectors.g1_exif_temporal import _extract_image_exif, _parse_exif_dt


@dataclass
class ExifClusteringInput:
    image_paths: list[Path]
    max_span_years: float = 5.0
    max_camera_models: int = 2
    label: str = ""


class F5ExifClusteringDetector(BaseDetector):
    """跨图 EXIF 一致性检查。"""

    id: ClassVar[str] = "F5"
    name: ClassVar[str] = "EXIF Cross-Image Clustering"
    description: ClassVar[str] = (
        "检查论文多图 EXIF 的时间跨度、相机一致性、相同时间戳异常。"
    )
    academic_basis: ClassVar[str] = (
        "Standard EXIF forensics; ORI image-audit checklist."
    )
    data_requirements: ClassVar[list[str]] = ["image_files"]
    assumption_cluster: ClassVar[str] = "metadata_forensics"

    def check_applicability(self, data: Any) -> tuple[bool, str]:
        if not isinstance(data, ExifClusteringInput):
            return False, "Expected ExifClusteringInput"
        if len(data.image_paths) < 3:
            return False, "Need ≥ 3 images for cross-image clustering"
        return True, ""

    def _detect(
        self, data: ExifClusteringInput, seed: int
    ) -> list[Finding]:
        findings: list[Finding] = []
        timestamps: list[datetime] = []
        models: list[str] = []
        per_image: list[dict[str, Any]] = []

        for img in data.image_paths:
            exif = _extract_image_exif(img)
            dt = _parse_exif_dt(exif.get("DateTimeOriginal") or exif.get("DateTime") or "")
            model = str(exif.get("Model") or exif.get("Make") or "").strip()
            per_image.append({
                "image": img.name,
                "datetime": dt.isoformat() if dt else None,
                "model": model,
            })
            if dt:
                timestamps.append(dt)
            if model:
                models.append(model)

        # 检查 1：时间跨度
        if len(timestamps) >= 2:
            span = (max(timestamps) - min(timestamps)).total_seconds() / (365.25 * 86400)
            if span > data.max_span_years:
                findings.append(
                    Finding(
                        detector_id=self.id,
                        detector_name=self.name,
                        severity=Severity.CONCERN,
                        summary=(
                            f"Image timestamps span {span:.1f} years "
                            f"(threshold {data.max_span_years})"
                        ),
                        detail=(
                            f"图像 EXIF DateTimeOriginal 跨度 = "
                            f"{span:.2f} 年（最早 {min(timestamps).isoformat()}, "
                            f"最晚 {max(timestamps).isoformat()}）。"
                            "跨度过大提示混合了旧项目图与新数据。"
                        ),
                        test_statistic=span,
                        test_name="span (years)",
                        evidence={
                            "n_images_with_exif_time": len(timestamps),
                            "earliest": min(timestamps).isoformat(),
                            "latest": max(timestamps).isoformat(),
                            "span_years": span,
                        },
                        innocent_explanations=[
                            "长期纵向研究（合法但应在 Methods 声明）",
                            "对照图来自历史档案（应引用原数据 DOI）",
                            "相机日期设置错误",
                        ],
                        academic_reference=self.academic_basis,
                    )
                )

        # 检查 2：相机型号多样性
        if models:
            distinct = set(models)
            if len(distinct) > data.max_camera_models:
                model_counts = Counter(models)
                findings.append(
                    Finding(
                        detector_id=self.id,
                        detector_name=self.name,
                        severity=Severity.NOTE,
                        summary=(
                            f"Images come from {len(distinct)} different "
                            f"camera models (threshold {data.max_camera_models})"
                        ),
                        detail=(
                            f"在 {len(models)} 张含 EXIF 的图像中发现 "
                            f"{len(distinct)} 种不同相机/仪器型号: "
                            f"{dict(model_counts.most_common(5))}。"
                        ),
                        evidence={
                            "distinct_models": sorted(distinct),
                            "model_counts": dict(model_counts),
                        },
                        innocent_explanations=[
                            "多机构合作（多个实验室仪器）",
                            "部分图像是参考资料或对照图",
                            "Make/Model 字段格式不一致（'Nikon Corp.' vs 'NIKON')",
                        ],
                        academic_reference=self.academic_basis,
                    )
                )

        # 检查 3：相同时间戳重复
        if len(timestamps) >= 3:
            ts_counts = Counter(t.isoformat(timespec="seconds") for t in timestamps)
            duplicates = {t: c for t, c in ts_counts.items() if c >= 3}
            if duplicates:
                findings.append(
                    Finding(
                        detector_id=self.id,
                        detector_name=self.name,
                        severity=Severity.SUSPICIOUS,
                        summary=(
                            f"{sum(duplicates.values())} images share "
                            f"identical DateTimeOriginal "
                            f"(in {len(duplicates)} group(s))"
                        ),
                        detail=(
                            "Identical EXIF DateTimeOriginal (to the second) "
                            "across multiple distinct images is unusual—real "
                            "shutter timing differs by at least one second "
                            "between captures. May indicate batch metadata "
                            "tampering."
                        ),
                        evidence={
                            "duplicate_timestamps": duplicates,
                        },
                        innocent_explanations=[
                            "Camera firmware doesn't record sub-second precision",
                            "Time-lapse / multi-shot mode using stored timestamp",
                            "Images regenerated from RAW with default timestamp",
                            "Bulk-edited via Lightroom 'apply same metadata'",
                        ],
                        academic_reference=self.academic_basis,
                    )
                )

        return findings
