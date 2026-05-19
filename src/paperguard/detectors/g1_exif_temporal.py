"""G1 — 图像 EXIF 时序异常。

学术依据：标准 EXIF 取证。

每张数码相机或显微镜图像通常带 EXIF：
- DateTimeOriginal: 拍摄时间
- DateTimeDigitized: 数字化时间
- Software: 处理软件（PS、ImageJ 等）

异常信号：
- DateTimeOriginal 早于论文声称的实验开始时间
- DateTimeOriginal 晚于论文投稿时间
- 同一论文多张图的相机型号 / Make 字段差异巨大但作者只说一台仪器
- Software 字段透露被 Photoshop / GIMP 处理过（不必然造假但需要说明）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity


@dataclass
class ExifInput:
    image_paths: list[Path]
    claimed_experiment_start: datetime | None = None
    claimed_experiment_end: datetime | None = None
    paper_submission_date: datetime | None = None
    expected_make: str | None = None
    expected_model: str | None = None
    notes: dict[str, Any] = field(default_factory=dict)


def _extract_image_exif(path: Path) -> dict[str, Any]:
    """读 EXIF（含 Exif IFD 子组）。失败返回 {}。"""
    try:
        from PIL import ExifTags, Image
    except ImportError:
        return {}
    try:
        with Image.open(path) as img:
            raw = img.getexif()
            if not raw:
                return {}
            out: dict[str, Any] = {}
            # 顶层 (Image IFD)
            for k, v in raw.items():
                tag = ExifTags.TAGS.get(k, str(k))
                out[tag] = v
            # Exif IFD（含 DateTimeOriginal 等）
            try:
                exif_ifd = raw.get_ifd(0x8769)
                for k, v in exif_ifd.items():
                    tag = ExifTags.TAGS.get(k, str(k))
                    out[tag] = v
            except KeyError:
                pass
            # 标准化字节串
            for tag_name, val in list(out.items()):
                if isinstance(val, bytes):
                    try:
                        out[tag_name] = val.decode("ascii").rstrip("\x00")
                    except UnicodeDecodeError:
                        pass
            return out
    except Exception:  # noqa: BLE001
        return {}


def _parse_exif_dt(value: str) -> datetime | None:
    """EXIF 时间格式 'YYYY:MM:DD HH:MM:SS'。"""
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value.strip(), "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None


_EDIT_SOFTWARE_KEYWORDS = (
    "adobe photoshop",
    "gimp",
    "imagej",
    "fiji",
    "snapseed",
    "lightroom",
)


class G1ExifTemporalDetector(BaseDetector):
    """图像 EXIF 时序与软件检查。"""

    id: ClassVar[str] = "G1"
    name: ClassVar[str] = "Image EXIF Temporal Forensics"
    description: ClassVar[str] = "比对图像 EXIF 拍摄时间 / 软件签名 与论文声称的时间线。"
    academic_basis: ClassVar[str] = "标准 EXIF 取证；ORI 工具集图像审计部分。"
    data_requirements: ClassVar[list[str]] = ["image_files", "claimed_timeline"]
    assumption_cluster: ClassVar[str] = "metadata_forensics"

    def check_applicability(self, data: Any) -> tuple[bool, str]:
        if not isinstance(data, ExifInput):
            return False, "Expected ExifInput"
        if not data.image_paths:
            return False, "No images provided"
        return True, ""

    def _detect(self, data: ExifInput, seed: int) -> list[Finding]:
        findings: list[Finding] = []
        makes: set[str] = set()
        models: set[str] = set()
        edit_software_hits: list[tuple[Path, str]] = []

        for img_path in data.image_paths:
            exif = _extract_image_exif(img_path)
            if not exif:
                continue

            make = (exif.get("Make") or "").strip()
            model = (exif.get("Model") or "").strip()
            if make:
                makes.add(make)
            if model:
                models.add(model)

            sw = (exif.get("Software") or "").strip().lower()
            if any(k in sw for k in _EDIT_SOFTWARE_KEYWORDS):
                edit_software_hits.append((img_path, sw))

            dto = _parse_exif_dt(exif.get("DateTimeOriginal") or "")
            if dto is None:
                dto = _parse_exif_dt(exif.get("DateTime") or "")
            if dto is None:
                continue

            # 时序检查 1：拍摄早于声称实验
            if data.claimed_experiment_start and dto < data.claimed_experiment_start:
                gap_days = (data.claimed_experiment_start - dto).days
                if gap_days > 1:
                    findings.append(
                        Finding(
                            detector_id=self.id,
                            detector_name=self.name,
                            severity=Severity.CRITICAL,
                            summary=(
                                f"图像 EXIF 拍摄时间 {dto.isoformat()} 早于"
                                f"声称的实验开始 {data.claimed_experiment_start.isoformat()}"
                            ),
                            detail=(
                                f"图像 {img_path.name} 的 EXIF DateTimeOriginal "
                                f"为 {dto}，但论文声称实验始于 "
                                f"{data.claimed_experiment_start}。"
                                f"差距 {gap_days} 天。"
                            ),
                            evidence={
                                "image": str(img_path),
                                "exif_datetime": dto.isoformat(),
                                "claimed_start": data.claimed_experiment_start.isoformat(),
                                "gap_days": gap_days,
                            },
                            innocent_explanations=[
                                "数码相机日期未设置或错误",
                                "图像是从前期项目重用（应在论文中声明）",
                                "EXIF 是图像被复制时保留的源数据，与本图无关",
                            ],
                            academic_reference=self.academic_basis,
                        )
                    )
            # 时序检查 2：拍摄晚于论文投稿
            if (
                data.paper_submission_date
                and dto > data.paper_submission_date
            ):
                gap_days = (dto - data.paper_submission_date).days
                if gap_days > 1:
                    findings.append(
                        Finding(
                            detector_id=self.id,
                            detector_name=self.name,
                            severity=Severity.CRITICAL,
                            summary=(
                                f"图像 EXIF 拍摄时间 {dto.isoformat()} 晚于"
                                f"论文投稿 {data.paper_submission_date.isoformat()}"
                            ),
                            detail=(
                                f"图像 {img_path.name} 的拍摄时间晚于投稿日期 "
                                f"{gap_days} 天。"
                            ),
                            evidence={
                                "image": str(img_path),
                                "exif_datetime": dto.isoformat(),
                                "submission_date": data.paper_submission_date.isoformat(),
                                "gap_days": gap_days,
                            },
                            innocent_explanations=[
                                "投稿后重做实验补图（应在 revision letter 中说明）",
                                "图像被作者后续替换（修订版本）",
                                "相机时间设置错误",
                            ],
                            academic_reference=self.academic_basis,
                        )
                    )

        # 跨图一致性：多个 Make 但论文只声称一台仪器
        expected_make_lower = (data.expected_make or "").lower()
        makes_lower = {m.lower() for m in makes}
        if (
            len(makes) > 1
            and data.expected_make
            and expected_make_lower not in makes_lower
        ):
            findings.append(
                Finding(
                    detector_id=self.id,
                    detector_name=self.name,
                    severity=Severity.CONCERN,
                    summary=f"图像 EXIF Make 字段不一致：发现 {sorted(makes)}",
                    detail=(
                        f"声明的仪器制造商为 '{data.expected_make}'，"
                        f"但 EXIF 中发现 {len(makes)} 种不同的 Make: {sorted(makes)}。"
                    ),
                    evidence={"makes_found": sorted(makes), "expected": data.expected_make},
                    innocent_explanations=[
                        "对照图来自不同仪器（合作单位提供等）",
                        "Make 字段格式差异（'Nikon Corp.' vs 'NIKON CORPORATION'）",
                        "图像编辑软件改写了 EXIF",
                    ],
                    academic_reference=self.academic_basis,
                )
            )

        # 编辑软件签名
        if edit_software_hits:
            severity = (
                Severity.CONCERN
                if any("photoshop" in sw for _, sw in edit_software_hits)
                else Severity.NOTE
            )
            findings.append(
                Finding(
                    detector_id=self.id,
                    detector_name=self.name,
                    severity=severity,
                    summary=(
                        f"{len(edit_software_hits)} 张图像 EXIF 显示曾被"
                        f"图像编辑软件处理"
                    ),
                    detail=(
                        "以下图像 Software 字段含编辑软件签名：\n"
                        + "\n".join(f"  - {p.name}: {sw}" for p, sw in edit_software_hits)
                        + "\n图像编辑本身合法（裁剪、调色），但应在 Methods 中声明"
                        "所有处理步骤，且不应改变定量信息。"
                    ),
                    evidence={
                        "edited_images": [
                            {"file": str(p), "software": sw} for p, sw in edit_software_hits
                        ]
                    },
                    innocent_explanations=[
                        "Photoshop 用于排版/拼图，未修改像素定量内容",
                        "ImageJ / Fiji 是标准生物图像分析工具，使用即合法",
                        "图像在导出时经过软件压缩，软件签名是副产品",
                    ],
                    academic_reference=self.academic_basis,
                )
            )

        return findings
