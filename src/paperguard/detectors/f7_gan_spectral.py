"""F7 — GAN / diffusion-model generated image detection via spectral signature.

Academic basis
--------------
Three independent results converged in 2019-2024:

1. **Zhang et al. (2019, "Detecting and Simulating Artifacts in GAN Fake
   Images")** showed that GANs leak a characteristic high-frequency
   spectral ridge at multiples of the generator's transposed-convolution
   stride. The ridge is invisible in the spatial domain but stands out
   in the radial-averaged log-magnitude FFT.
2. **Wang et al. (2020, "CNN-generated images are surprisingly easy to
   spot...")** demonstrated the ridge persists across StyleGAN, BigGAN,
   ProGAN, and image-to-image translation models, and survives JPEG
   compression at quality ≥ 80.
3. **Corvi et al. (2023, "On the detection of synthetic images generated
   by diffusion models")** showed that diffusion models (DALL-E,
   Stable Diffusion, Midjourney) leave a different, complementary
   signature — a low-residual after bilateral filtering, because their
   denoising-step training implicitly smooths the high-frequency noise
   floor real photos retain.

F7 implements both signals in one detector. Neither requires a trained
ML model; both are pure scipy / opencv DSP.

Algorithm
---------
For each image:

1. **GAN ridge probe.** 2D FFT → radial-averaged log magnitude →
   compute peak-to-baseline ratio in the high-frequency band
   (frequency ≥ 0.6 × Nyquist). A real photo has a smooth 1/f-style
   decay; a GAN-generated image often has a measurable peak.

2. **Diffusion residual probe.** Apply a bilateral filter with
   moderate spatial / colour sigmas, compute the per-pixel residual
   |original − filtered|, take the mean. Real photos retain noise →
   residual is high; diffusion-generated images have already been
   "denoised by construction" → residual is low.

3. Combine into a single per-image score and aggregate across the
   paper's images as max.

Failure modes (always silent, never raise):
- opencv / numpy not installed → not applicable
- image grayscale / single-channel → still works (uses luminance)
- image too small (< 64 × 64) → not applicable

Severity tiers (default thresholds tuned on a balanced 50+50
synthetic GAN-vs-real corpus, see `docs/recall_f7_calibration.md`):

- both signals subthreshold                              → no finding
- one signal moderate (GAN ridge z ≥ 3 OR residual ≤ 0.5)→ NOTE
- one signal strong (z ≥ 5 OR residual ≤ 0.3)            → CONCERN
- both signals fire                                      → SUSPICIOUS
- both signals strong                                    → CRITICAL

Every finding ships ≥ 5 innocent_explanations per the iron rule.

Scope and known limitations
---------------------------
- F7 is tuned against **typical** GAN / diffusion artefacts circa 2020-
  2024. State-of-the-art 2024+ models (Stable Diffusion 3+, Midjourney
  v6+) increasingly suppress the spectral ridge; F7's GAN-ridge
  signal will weaken on newer outputs.
- The diffusion-residual signal is robust across architectures but
  also fires on **legitimately heavily-denoised** real photos (e.g.
  low-light astronomy plates with strong wavelet denoising applied).
- F7 does **not** claim a flagged image is fraud. As with every
  PaperGuard detector, the finding ships with five innocent
  explanations and is appropriate as a triage input, not a verdict.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

import numpy as np

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity

logger = logging.getLogger(__name__)


# Default thresholds — see module docstring for calibration source.
_DEFAULT_RIDGE_Z_NOTE = 3.0
_DEFAULT_RIDGE_Z_STRONG = 5.0
_DEFAULT_RESIDUAL_NOTE = 0.5
_DEFAULT_RESIDUAL_STRONG = 0.3
_MIN_DIM = 64  # smaller images cannot give a stable spectrum


@dataclass
class GanSpectralInput:
    """Input contract.

    ``image_paths`` is a list of file paths to image files; F7 reads
    each via opencv.

    Thresholds are exposed as overridable instance attributes for
    calibration on a specific corpus.
    """

    image_paths: list[Path]
    ridge_z_note: float = _DEFAULT_RIDGE_Z_NOTE
    ridge_z_strong: float = _DEFAULT_RIDGE_Z_STRONG
    residual_note: float = _DEFAULT_RESIDUAL_NOTE
    residual_strong: float = _DEFAULT_RESIDUAL_STRONG
    per_image_results: list[dict[str, Any]] = field(default_factory=list)


def _radial_average(power_2d: np.ndarray) -> np.ndarray:
    """Mean power as a function of radial frequency (1-D)."""
    h, w = power_2d.shape
    y, x = np.indices(power_2d.shape)
    cy, cx = h // 2, w // 2
    r = np.hypot(x - cx, y - cy).astype(int)
    nbins = int(r.max()) + 1
    radial_sum = np.bincount(r.ravel(), power_2d.ravel(), minlength=nbins)
    radial_count = np.bincount(r.ravel(), minlength=nbins)
    radial_count = np.where(radial_count == 0, 1, radial_count)
    return radial_sum / radial_count


def _gan_ridge_z(luminance: np.ndarray) -> float:
    """Robust z-score of the maximum high-freq radial peak."""
    h, w = luminance.shape
    if h < _MIN_DIM or w < _MIN_DIM:
        return 0.0
    f = np.fft.fftshift(np.fft.fft2(luminance.astype(np.float64)))
    log_mag = np.log1p(np.abs(f))
    rad = _radial_average(log_mag)
    cutoff = int(0.6 * len(rad))
    high = rad[cutoff:]
    if high.size < 3:
        return 0.0
    median = float(np.median(high))
    mad = float(np.median(np.abs(high - median)))
    if mad < 1e-9:
        return 0.0
    peak = float(high.max())
    return (peak - median) / (1.4826 * mad)


def _bilateral_residual(image_bgr: np.ndarray) -> float:
    """Mean per-pixel residual after bilateral filtering, scaled to [0, 1]."""
    try:
        import cv2
    except ImportError:
        return float("nan")
    if image_bgr.ndim == 2:
        image_bgr = image_bgr[..., None].repeat(3, axis=-1)
    img = image_bgr.astype(np.uint8)
    filtered = cv2.bilateralFilter(img, d=9, sigmaColor=75, sigmaSpace=75)
    diff = np.abs(img.astype(np.int32) - filtered.astype(np.int32))
    mean_residual = float(diff.mean())
    return float(min(1.0, mean_residual / 25.0))


def _process_one_image(path: Path) -> dict[str, Any] | None:
    try:
        import cv2
    except ImportError:
        return None
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        return None
    h, w = img.shape[:2]
    if h < _MIN_DIM or w < _MIN_DIM:
        return None
    luminance = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    ridge_z = _gan_ridge_z(luminance)
    residual = _bilateral_residual(img)
    return {
        "image_path": str(path),
        "shape": (h, w),
        "ridge_z": float(ridge_z),
        "bilateral_residual": float(residual),
    }


class F7GanSpectralDetector(BaseDetector):
    """F7 — GAN / diffusion-model image spectral-signature detector."""

    id: ClassVar[str] = "F7"
    name: ClassVar[str] = "GAN / diffusion image spectral signature"
    description: ClassVar[str] = (
        "Combines a high-frequency FFT ridge probe (GAN signature, "
        "Zhang+ 2019 / Wang+ 2020) with a bilateral-filter residual "
        "probe (diffusion-model signature, Corvi+ 2023) to flag "
        "synthetically-generated figures."
    )
    academic_basis: ClassVar[str] = (
        "Zhang et al. (2019) 'Detecting and Simulating Artifacts in "
        "GAN Fake Images'; Wang et al. (2020) 'CNN-generated images "
        "are surprisingly easy to spot...'; Corvi et al. (2023) 'On "
        "the detection of synthetic images generated by diffusion "
        "models'."
    )
    data_requirements: ClassVar[list[str]] = ["image_files"]
    assumption_cluster: ClassVar[str] = "image_synthesis_forensics"

    def check_applicability(self, data: Any) -> tuple[bool, str]:
        if not isinstance(data, GanSpectralInput):
            return False, "Expected GanSpectralInput"
        if not data.image_paths:
            return False, "No image paths provided"
        try:
            import cv2  # noqa: F401  type: ignore[import-untyped]
        except ImportError:
            return False, "opencv-python not installed; F7 requires cv2"
        return True, ""

    def _detect(self, data: GanSpectralInput, seed: int) -> list[Finding]:
        findings: list[Finding] = []
        per_image: list[dict[str, Any]] = []
        for path in data.image_paths:
            row = _process_one_image(path)
            if row is None:
                continue
            per_image.append(row)
        data.per_image_results = per_image
        if not per_image:
            return findings

        for r in per_image:
            ridge_z = r["ridge_z"]
            residual = r["bilateral_residual"]
            ridge_fires = ridge_z >= data.ridge_z_note
            residual_fires = (
                np.isfinite(residual) and residual <= data.residual_note
            )
            ridge_strong = ridge_z >= data.ridge_z_strong
            residual_strong = (
                np.isfinite(residual) and residual <= data.residual_strong
            )

            severity: Severity | None = None
            if ridge_strong and residual_strong:
                severity = Severity.CRITICAL
            elif ridge_fires and residual_fires:
                severity = Severity.SUSPICIOUS
            elif ridge_strong or residual_strong:
                severity = Severity.CONCERN
            elif ridge_fires or residual_fires:
                severity = Severity.NOTE

            if severity is None:
                continue

            findings.append(
                Finding(
                    detector_id=self.id,
                    detector_name=self.name,
                    severity=severity,
                    summary=(
                        f"Spectral signature consistent with synthetic "
                        f"generation in {Path(r['image_path']).name} "
                        f"(ridge z={ridge_z:.2f}, "
                        f"bilateral residual={residual:.3f})"
                    ),
                    detail=(
                        f"FFT high-frequency ridge probe yielded a "
                        f"robust z-score of {ridge_z:.2f} (threshold "
                        f"{data.ridge_z_note:.1f} for NOTE, "
                        f"{data.ridge_z_strong:.1f} for strong). "
                        f"Bilateral-filter residual measured "
                        f"{residual:.3f} (lower = more denoised; "
                        f"thresholds {data.residual_note:.2f} for "
                        f"NOTE, {data.residual_strong:.2f} for strong). "
                        "Image dimensions "
                        f"{r['shape'][1]}×{r['shape'][0]} pixels.\n\n"
                        "The ridge probe is the Zhang+ 2019 / Wang+ "
                        "2020 spectral signature for GAN outputs; the "
                        "residual probe is the Corvi+ 2023 signature "
                        "for diffusion-model outputs. Both signals "
                        "are circumstantial — see innocent "
                        "explanations."
                    ),
                    test_statistic=max(ridge_z, 10 * (1.0 - residual)),
                    test_name="combined spectral z-score",
                    evidence={
                        "image_path": r["image_path"],
                        "shape": list(r["shape"]),
                        "ridge_z": ridge_z,
                        "bilateral_residual": residual,
                        "ridge_z_note_threshold": data.ridge_z_note,
                        "ridge_z_strong_threshold": data.ridge_z_strong,
                        "residual_note_threshold": data.residual_note,
                        "residual_strong_threshold": data.residual_strong,
                    },
                    innocent_explanations=[
                        "Aggressive in-camera or post-processing "
                        "denoising (e.g. low-light astronomy plates, "
                        "wavelet-denoised microscopy) reduces "
                        "high-frequency noise to a level "
                        "indistinguishable from diffusion-model "
                        "output.",
                        "JPEG compression at moderate quality "
                        "(60-80) introduces 8×8 DCT block boundaries "
                        "that produce a high-frequency spectral peak "
                        "mistakable for a GAN ridge.",
                        "Some scientific instruments (e.g. SEM, TEM, "
                        "confocal microscopy) generate images that "
                        "are *natively* low-noise because the "
                        "acquisition is digital and integrative; "
                        "these may flag the residual probe.",
                        "Synthetic data generated for legitimate "
                        "didactic or illustrative purposes (e.g. a "
                        "schematic figure produced by an AI tool, "
                        "clearly labelled as such in the figure "
                        "caption) is appropriate and disclosed use.",
                        "The spectral signature is a population-level "
                        "statistical pattern; a single image's "
                        "z-score is only weakly informative on its "
                        "own. Confirm via multi-detector co-firing "
                        "and a trained-eye review per Bik 2016's "
                        "methodology.",
                    ],
                    academic_reference=self.academic_basis,
                    applicability_notes=(
                        "FFT ridge probe: radial-average log "
                        "magnitude, peak / robust-baseline z-score "
                        "computed on the high-frequency half. "
                        "Bilateral residual: cv2.bilateralFilter "
                        "(d=9, σ_colour=75, σ_space=75); per-pixel "
                        "mean absolute residual normalised by 25.0. "
                        "Re-tune via GanSpectralInput.{ridge_z_*, "
                        "residual_*}."
                    ),
                )
            )
        return findings
