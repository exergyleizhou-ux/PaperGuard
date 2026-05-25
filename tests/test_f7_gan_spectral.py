"""Unit tests for the F7 GAN / diffusion spectral-signature detector (2.7.0)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from paperguard.core.types import Severity
from paperguard.detectors.f7_gan_spectral import (
    F7GanSpectralDetector,
    GanSpectralInput,
    _gan_ridge_z,
)


def _write_image(path: Path, arr: np.ndarray) -> None:
    cv2 = pytest.importorskip("cv2")
    cv2.imwrite(str(path), arr)


def _real_photo_like(rng: np.random.Generator, h: int = 256, w: int = 256) -> np.ndarray:
    """Approximate a real photo: smooth structure + 1/f noise + sensor noise."""
    base = rng.uniform(80, 180, size=(h, w)).astype(np.float64)
    noise = rng.normal(0, 20, size=(h, w))
    cv2 = pytest.importorskip("cv2")
    smooth = cv2.GaussianBlur(base, (31, 31), sigmaX=10)
    out = smooth + noise
    out = np.clip(out, 0, 255).astype(np.uint8)
    return np.stack([out, out, out], axis=-1)


def _gan_ridge_synthetic(rng: np.random.Generator, h: int = 256, w: int = 256) -> np.ndarray:
    """Synthetic image with a strong high-frequency periodic component.

    Mimics the checkerboard / stride-aliasing ridge GANs leak in the FFT.
    """
    yy, xx = np.indices((h, w))
    pattern = 40 * np.sin(2 * np.pi * yy / 8) * np.sin(2 * np.pi * xx / 8)
    base = rng.uniform(100, 150, size=(h, w))
    out = np.clip(base + pattern, 0, 255).astype(np.uint8)
    return np.stack([out, out, out], axis=-1)


def _denoised_synthetic(h: int = 256, w: int = 256) -> np.ndarray:
    """Heavily-denoised image — mimics diffusion-model output's low residual."""
    yy, _xx = np.indices((h, w))
    out = (128 + 30 * np.sin(2 * np.pi * yy / 80)).astype(np.uint8)
    out = np.clip(out, 0, 255)
    return np.stack([out, out, out], axis=-1)


def test_inapplicable_without_paths() -> None:
    det = F7GanSpectralDetector()
    result = det.detect(GanSpectralInput(image_paths=[]))
    assert not result.applicable


def test_no_finding_on_real_photo_like(tmp_path: Path) -> None:
    pytest.importorskip("cv2")
    rng = np.random.default_rng(42)
    img_path = tmp_path / "real.png"
    _write_image(img_path, _real_photo_like(rng))

    det = F7GanSpectralDetector()
    result = det.detect(GanSpectralInput(image_paths=[img_path]))
    assert result.applicable, result.skip_reason
    # Real-photo-like should not produce CRITICAL on default thresholds.
    for f in result.findings:
        assert f.severity != Severity.CRITICAL


def test_diffusion_residual_fires_on_denoised(tmp_path: Path) -> None:
    pytest.importorskip("cv2")
    img_path = tmp_path / "denoised.png"
    _write_image(img_path, _denoised_synthetic())

    det = F7GanSpectralDetector()
    result = det.detect(GanSpectralInput(image_paths=[img_path]))
    assert result.applicable
    assert result.findings, "expected at least one finding on noiseless image"
    f = result.findings[0]
    assert f.evidence["bilateral_residual"] <= 0.5
    assert len(f.innocent_explanations) >= 5


def test_ridge_z_detects_periodic_pattern() -> None:
    """Unit test of the ridge-z function in isolation."""
    rng = np.random.default_rng(7)
    real = _real_photo_like(rng)[..., 0].astype(np.float64)
    gan = _gan_ridge_synthetic(rng)[..., 0].astype(np.float64)
    z_real = _gan_ridge_z(real)
    z_gan = _gan_ridge_z(gan)
    assert z_gan > z_real, f"z_gan {z_gan:.2f} should exceed z_real {z_real:.2f}"


def test_finding_has_iron_rule_innocent_explanations(tmp_path: Path) -> None:
    pytest.importorskip("cv2")
    img_path = tmp_path / "denoised.png"
    _write_image(img_path, _denoised_synthetic())

    det = F7GanSpectralDetector()
    result = det.detect(GanSpectralInput(image_paths=[img_path]))
    assert result.findings
    for f in result.findings:
        assert len(f.innocent_explanations) >= 5
        text = (
            (f.summary or "") + " " + (f.detail or "")
            + " " + " ".join(f.innocent_explanations)
        ).lower()
        for word in ("fraud", "fabrication", "misconduct"):
            assert word not in text, f"forbidden word {word!r} in F7 finding"


def test_too_small_image_is_skipped(tmp_path: Path) -> None:
    pytest.importorskip("cv2")
    tiny = np.zeros((32, 32, 3), dtype=np.uint8) + 128
    img_path = tmp_path / "tiny.png"
    _write_image(img_path, tiny)
    det = F7GanSpectralDetector()
    result = det.detect(GanSpectralInput(image_paths=[img_path]))
    assert result.applicable
    assert result.findings == []
