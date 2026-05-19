"""F1 图像重复测试。"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from paperguard.core.types import Severity
from paperguard.detectors.f1_image_duplication import (
    F1ImageDuplicationDetector,
    ImageDuplicationInput,
)


def _save_solid_color(path: Path, color: tuple[int, int, int]) -> None:
    img = Image.new("RGB", (64, 64), color)
    img.save(path)


def test_f1_flags_identical_copies(tmp_path: Path) -> None:
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    _save_solid_color(a, (128, 64, 200))
    _save_solid_color(b, (128, 64, 200))  # 完全相同
    inp = ImageDuplicationInput(image_paths=[a, b])
    result = F1ImageDuplicationDetector().detect(inp, seed=42)
    assert result.applicable
    assert len(result.findings) >= 1
    assert result.findings[0].severity == Severity.CRITICAL


def test_f1_distinct_images_pass(tmp_path: Path) -> None:
    """生成两张差异极大的图（噪声 vs 渐变），pHash 应区分。"""
    import numpy as np

    rng = np.random.default_rng(42)
    a_arr = (rng.random((128, 128, 3)) * 255).astype("uint8")
    Image.fromarray(a_arr).save(tmp_path / "noise.png")

    b_arr = np.tile(np.linspace(0, 255, 128, dtype="uint8")[:, None, None], (1, 128, 3))
    Image.fromarray(b_arr).save(tmp_path / "gradient.png")

    inp = ImageDuplicationInput(
        image_paths=[tmp_path / "noise.png", tmp_path / "gradient.png"]
    )
    result = F1ImageDuplicationDetector().detect(inp, seed=42)
    assert result.applicable
    # 两张完全不同的图：可能 hamming 较大，不应触发
    assert len(result.findings) == 0


def test_f1_inapplicable_single_image(tmp_path: Path) -> None:
    a = tmp_path / "a.png"
    _save_solid_color(a, (0, 0, 0))
    inp = ImageDuplicationInput(image_paths=[a])
    result = F1ImageDuplicationDetector().detect(inp, seed=42)
    assert not result.applicable
