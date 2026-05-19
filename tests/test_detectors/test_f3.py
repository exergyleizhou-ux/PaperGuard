"""F3 splice / copy-move 测试。"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from paperguard.core.types import Severity
from paperguard.detectors.f3_splice_forensics import (
    F3SpliceForensicsDetector,
    SpliceForensicsInput,
)


def test_f3_flags_copy_move(tmp_path: Path) -> None:
    """造一张图：右上块复制到左下块。"""
    rng = np.random.default_rng(0)
    img = (rng.random((400, 400, 3)) * 255).astype("uint8")
    # 把 (50:150, 250:350) 复制到 (250:350, 50:150)
    img[250:350, 50:150] = img[50:150, 250:350]
    Image.fromarray(img).save(tmp_path / "copy_move.png")

    inp = SpliceForensicsInput(image_paths=[tmp_path / "copy_move.png"])
    result = F3SpliceForensicsDetector().detect(inp, seed=42)
    assert result.applicable
    # 至少触发 NOTE 或更高
    assert any(f.severity >= Severity.NOTE for f in result.findings)


def test_f3_natural_image_no_finding(tmp_path: Path) -> None:
    """纯噪声图，相似块应稀疏。"""
    rng = np.random.default_rng(1)
    img = (rng.random((400, 400, 3)) * 255).astype("uint8")
    Image.fromarray(img).save(tmp_path / "noise.png")

    inp = SpliceForensicsInput(image_paths=[tmp_path / "noise.png"])
    result = F3SpliceForensicsDetector().detect(inp, seed=42)
    assert result.applicable
    # 纯噪声很难凑够 ≥10 对高相似 patch
    assert all(f.severity < Severity.CONCERN for f in result.findings)


def test_f3_inapplicable_empty() -> None:
    inp = SpliceForensicsInput(image_paths=[])
    result = F3SpliceForensicsDetector().detect(inp, seed=42)
    assert not result.applicable
