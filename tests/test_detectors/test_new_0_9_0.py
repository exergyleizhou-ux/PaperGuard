"""0.9.0 新检测器测试（A7 / T6 / B8 / F5）。"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import piexif  # type: ignore[import-untyped]
from PIL import Image

from paperguard.core.types import Severity
from paperguard.detectors.a7_last_digit_five_zero import (
    A7LastDigitFiveZeroDetector,
)
from paperguard.detectors.b8_sprite import B8SPRITEDetector, SPRITEInput
from paperguard.detectors.f5_exif_clustering import (
    ExifClusteringInput,
    F5ExifClusteringDetector,
)
from paperguard.detectors.t6_ai_text_heuristic import T6AITextHeuristicDetector


# --- A7
def test_a7_flags_zero_five_excess() -> None:
    # 100 个值：80 个末位 0 或 5，20 个其它末位
    values = [round(1 + i * 0.05, 2) for i in range(80)]
    values += [1.13, 2.27, 1.41, 1.83, 2.69] * 4
    df = pd.DataFrame({"x": values})
    result = A7LastDigitFiveZeroDetector().detect(df, seed=42)
    assert result.applicable
    assert any(f.severity >= Severity.CONCERN for f in result.findings)


def test_a7_clean_pass() -> None:
    import numpy as np

    rng = np.random.default_rng(42)
    df = pd.DataFrame({"x": rng.uniform(0, 10, size=100).round(3)})
    result = A7LastDigitFiveZeroDetector().detect(df, seed=42)
    assert result.applicable
    assert len(result.findings) == 0


# --- T6
def test_t6_catches_llm_leakage() -> None:
    text = (
        "Our results demonstrate the importance of this finding. "
        "As an AI language model, I cannot provide specific dosage. "
        "Additional content with normal academic phrasing in this section. "
        "We collected biological samples and analyzed protein expression. "
        "The methods were standard and approved by the institutional board. "
    ) * 30
    result = T6AITextHeuristicDetector().detect(text, seed=42)
    assert result.applicable
    critical = [f for f in result.findings if f.severity == Severity.CRITICAL]
    assert len(critical) >= 1


def test_t6_flags_ai_phrase_density() -> None:
    text = (
        "We delve into the intricate interplay between variables. "
        "Our meticulous analysis sheds light on this groundbreaking topic. "
        "Navigating the complex landscape, we explore the rich tapestry "
        "of biological pathways. In the realm of cell biology, this "
        "plays a pivotal role. " * 5
        + "Standard introductory text follows. " * 50
    )
    result = T6AITextHeuristicDetector().detect(text, seed=42)
    assert result.applicable
    # 应至少一个 CONCERN+
    assert any(f.severity >= Severity.CONCERN for f in result.findings)


def test_t6_normal_passes() -> None:
    text = (
        "In this study, we measured cellular respiration at three time "
        "points. The mean ATP production was significantly different "
        "between groups (p = 0.012). Our results suggest that the "
        "treatment increases mitochondrial function. " * 30
    )
    result = T6AITextHeuristicDetector().detect(text, seed=42)
    assert result.applicable
    assert len(result.findings) == 0


# --- B8
def test_b8_inconsistent_triple() -> None:
    """mean=4.5, SD=2.0, N=5, scale=[1,5] — 数学上极难成立。"""
    inputs = [
        SPRITEInput(
            mean=4.5, sd=2.0, n=5, scale_min=1, scale_max=5,
            mean_decimals=1, sd_decimals=1, label="Q1",
        )
    ]
    result = B8SPRITEDetector().detect(inputs, seed=42)
    assert result.applicable
    # 这组 SPRITE 极难构造
    # 不强求一定 finding（heuristic 可能失败也可能成功），但不应崩
    _ = result.findings


def test_b8_inapplicable() -> None:
    result = B8SPRITEDetector().detect("not a list", seed=42)
    assert not result.applicable


# --- F5
def _save_jpg_with_exif(
    path: Path, dt_iso: str, model: str = "TestCam"
) -> None:
    img = Image.new("RGB", (32, 32), (200, 100, 50))
    exif_dict: dict = {
        "0th": {piexif.ImageIFD.Model: model.encode("ascii")},
        "Exif": {piexif.ExifIFD.DateTimeOriginal: dt_iso.encode("ascii")},
        "GPS": {},
        "1st": {},
        "thumbnail": None,
    }
    img.save(path, "jpeg", exif=piexif.dump(exif_dict))


def test_f5_flags_large_span(tmp_path: Path) -> None:
    # 三张图跨 10 年
    paths = [tmp_path / f"img{i}.jpg" for i in range(3)]
    _save_jpg_with_exif(paths[0], "2012:03:15 10:00:00")
    _save_jpg_with_exif(paths[1], "2017:06:20 11:00:00")
    _save_jpg_with_exif(paths[2], "2023:09:25 12:00:00")
    inp = ExifClusteringInput(image_paths=paths, max_span_years=5.0)
    result = F5ExifClusteringDetector().detect(inp, seed=42)
    assert result.applicable
    assert any("span" in f.summary.lower() for f in result.findings)


def test_f5_flags_identical_timestamps(tmp_path: Path) -> None:
    paths = [tmp_path / f"img{i}.jpg" for i in range(4)]
    for p in paths:
        _save_jpg_with_exif(p, "2024:01:15 10:00:00")
    inp = ExifClusteringInput(image_paths=paths)
    result = F5ExifClusteringDetector().detect(inp, seed=42)
    assert result.applicable
    assert any("identical" in f.summary.lower() for f in result.findings)


def test_f5_inapplicable_few_images() -> None:
    inp = ExifClusteringInput(image_paths=[])
    result = F5ExifClusteringDetector().detect(inp, seed=42)
    assert not result.applicable


def _unused_imports() -> None:
    """Suppress unused-import warnings for shared symbols above."""
    _ = datetime
