"""F2 内部重复检测测试。"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from paperguard.core.types import Severity
from paperguard.detectors.f2_internal_duplication import (
    F2InternalDuplicationDetector,
    InternalDuplicationInput,
)


def _save_with_duplicated_patch(path: Path) -> None:
    """造一张图：右半边是左半边复制粘贴。"""
    rng = np.random.default_rng(42)
    left = (rng.random((200, 200, 3)) * 255).astype("uint8")
    img = np.zeros((200, 400, 3), dtype="uint8")
    img[:, :200] = left
    img[:, 200:] = left  # 复制
    Image.fromarray(img).save(path)


def _save_pure_noise(path: Path) -> None:
    rng = np.random.default_rng(0)
    arr = (rng.random((400, 400, 3)) * 255).astype("uint8")
    Image.fromarray(arr).save(path)


def test_f2_detects_internal_copy(tmp_path: Path) -> None:
    p = tmp_path / "duped.png"
    _save_with_duplicated_patch(p)
    inp = InternalDuplicationInput(image_paths=[p], min_inliers=10)
    result = F2InternalDuplicationDetector().detect(inp, seed=42)
    assert result.applicable
    assert any(f.severity >= Severity.CONCERN for f in result.findings)


def test_f2_pure_noise_no_finding(tmp_path: Path) -> None:
    p = tmp_path / "noise.png"
    _save_pure_noise(p)
    inp = InternalDuplicationInput(image_paths=[p], min_inliers=12)
    result = F2InternalDuplicationDetector().detect(inp, seed=42)
    assert result.applicable
    # 纯噪声不应该有大量一致 patch
    assert len(result.findings) == 0


def test_f2_inapplicable_no_images() -> None:
    inp = InternalDuplicationInput(image_paths=[])
    result = F2InternalDuplicationDetector().detect(inp, seed=42)
    assert not result.applicable
