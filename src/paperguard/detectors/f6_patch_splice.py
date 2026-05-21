"""F6 — Per-channel histogram patch-splice forensics (Bik 2016 style).

Academic basis
--------------
Elisabeth Bik's 2016 PNAS paper *"The Prevalence of Inappropriate Image
Duplication in Biomedical Research Publications"* manually screened
20,000+ papers for image manipulation. The single most-discriminating
*visual* signal Bik trained on was **per-channel colour-histogram
discontinuities** between adjacent regions — a patch grafted into an
image carries its source's colour balance, which differs subtly from
the recipient even when the luminance has been corrected.

This detector mechanises that signal.

Algorithm
---------
1. Read the image as a 3-channel BGR array.
2. Divide it into ``patch_size × patch_size`` patches on a stride.
3. For each patch compute three 16-bin histograms (one per channel),
   normalised to sum to 1.
4. For each patch P with 4-neighbourhood N(P), compute the
   Jensen-Shannon divergence (JSD) between P's per-channel histogram
   and each neighbour's, summed across the 3 channels.
5. Robust z-score: ``(jsd_P - median) / (1.4826 × MAD)``. Z ≥ 4 is
   the conservative outlier cutoff.
6. **Spatial coherence**: outlier patches that form a connected
   component (8-connected) of size ≥ 4 indicate a candidate inserted
   region. We report the largest such component.

Failure modes (always silent, never raise):
- opencv not installed → returns None, detector skipped
- image too small → not applicable
- image is grayscale → falls back to luminance-only histogram

Severity tiers (defaults):
- max_z < 4                        → no finding
- 4 ≤ max_z < 6, no cluster        → NOTE
- max_z ≥ 6 or cluster ≥ 4 patches → CONCERN
- both                             → SUSPICIOUS

The detector emits ≥ 4 innocent_explanations on every finding per the
privacy iron rule.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity


@dataclass
class PatchSpliceInput:
    """Input contract for F6.

    ``image_paths`` may include any mix of PNG / JPG / TIFF / BMP. The
    detector scans each image independently and aggregates findings.
    """

    image_paths: list[Path]
    patch_size: int = 32
    stride: int = 32      # non-overlapping by default
    n_bins: int = 16      # per channel
    z_threshold: float = 4.0
    min_cluster_size: int = 4


def _jsd(p: Any, q: Any) -> float:
    """Jensen-Shannon divergence between two probability distributions.

    Returns a float in [0, ln(2)] ≈ [0, 0.693]. Higher = more different.
    """
    import numpy as np

    eps = 1e-12
    p = np.asarray(p, dtype=float) + eps
    q = np.asarray(q, dtype=float) + eps
    p = p / p.sum()
    q = q / q.sum()
    m = 0.5 * (p + q)
    return float(
        0.5 * (p * np.log(p / m)).sum() + 0.5 * (q * np.log(q / m)).sum()
    )


def _analyse_one(
    path: Path,
    patch_size: int,
    stride: int,
    n_bins: int,
    z_threshold: float,
    min_cluster_size: int,
) -> dict[str, Any] | None:
    """Per-image analysis. Returns dict or None if image unreadable."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None

    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        return None
    h, w = img.shape[:2]
    if min(h, w) < patch_size * 4:
        return None

    # Build patch grid + per-channel histograms.
    n_y = (h - patch_size) // stride + 1
    n_x = (w - patch_size) // stride + 1
    if n_y < 3 or n_x < 3:
        return None

    n_channels = 1 if img.ndim == 2 or img.shape[2] == 1 else img.shape[2]
    # Histograms: shape (n_y, n_x, n_channels, n_bins)
    hists = np.zeros((n_y, n_x, n_channels, n_bins), dtype=np.float64)
    bins = np.linspace(0, 256, n_bins + 1)
    for iy in range(n_y):
        for ix in range(n_x):
            y = iy * stride
            x = ix * stride
            block = img[y : y + patch_size, x : x + patch_size]
            for c in range(n_channels):
                channel = block[..., c] if n_channels > 1 else block
                hist, _ = np.histogram(channel.ravel(), bins=bins)
                hists[iy, ix, c] = hist

    # JSD to 4-neighbours, summed across channels.
    jsd_map = np.zeros((n_y, n_x), dtype=np.float64)
    for iy in range(n_y):
        for ix in range(n_x):
            neighbours = []
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                ny, nx = iy + dy, ix + dx
                if 0 <= ny < n_y and 0 <= nx < n_x:
                    neighbours.append((ny, nx))
            if not neighbours:
                continue
            total = 0.0
            for ny, nx in neighbours:
                for c in range(n_channels):
                    total += _jsd(hists[iy, ix, c], hists[ny, nx, c])
            jsd_map[iy, ix] = total / len(neighbours)

    # Robust z-score (median / MAD).
    flat = jsd_map.ravel()
    median = float(np.median(flat))
    mad = float(np.median(np.abs(flat - median))) or 1e-9
    z_map = (jsd_map - median) / (1.4826 * mad)
    max_z = float(z_map.max())

    # Outlier mask + connected components.
    outlier_mask = (z_map >= z_threshold).astype("uint8")
    # 8-connectivity component analysis (no scipy dependency)
    n_outliers = int(outlier_mask.sum())
    largest_component = _largest_connected_component_size(outlier_mask)

    return {
        "image_path": str(path),
        "n_patches": int(n_y * n_x),
        "n_outlier_patches": n_outliers,
        "max_z": max_z,
        "median_jsd": median,
        "mad": mad,
        "largest_cluster": int(largest_component),
        "grid": (int(n_y), int(n_x)),
    }


def _largest_connected_component_size(mask: Any) -> int:
    """8-connected CC labelling on a binary mask. Pure python BFS."""
    import numpy as np

    arr = np.asarray(mask)
    h, w = arr.shape
    seen = np.zeros_like(arr, dtype=bool)
    largest = 0
    for iy in range(h):
        for ix in range(w):
            if not arr[iy, ix] or seen[iy, ix]:
                continue
            # BFS
            queue = [(iy, ix)]
            seen[iy, ix] = True
            size = 0
            while queue:
                y, x = queue.pop()
                size += 1
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dy == 0 and dx == 0:
                            continue
                        ny, nx = y + dy, x + dx
                        if (
                            0 <= ny < h
                            and 0 <= nx < w
                            and arr[ny, nx]
                            and not seen[ny, nx]
                        ):
                            seen[ny, nx] = True
                            queue.append((ny, nx))
            if size > largest:
                largest = size
    return largest


class F6PatchSpliceDetector(BaseDetector):
    """Per-channel histogram discontinuity (Bik 2016 style)."""

    id: ClassVar[str] = "F6"
    name: ClassVar[str] = "Patch Splice (per-channel histogram)"
    description: ClassVar[str] = (
        "Detects spliced/inserted image regions by per-channel colour-"
        "histogram discontinuity between adjacent 32×32 patches "
        "(Bik 2016 manual screening, mechanised)."
    )
    academic_basis: ClassVar[str] = (
        "Bik EM, Casadevall A, Fang FC (2016) The Prevalence of "
        "Inappropriate Image Duplication in Biomedical Research "
        "Publications. mBio 7(3):e00809-16."
    )
    data_requirements: ClassVar[list[str]] = ["image_paths"]
    assumption_cluster: ClassVar[str] = "image_forensics"

    def check_applicability(self, data: Any) -> tuple[bool, str]:
        if not isinstance(data, PatchSpliceInput):
            return False, "Expected PatchSpliceInput"
        if not data.image_paths:
            return False, "No image paths supplied"
        try:
            import cv2  # noqa: F401
        except ImportError:
            return False, "opencv-python not installed; F6 requires cv2"
        return True, ""

    def _detect(self, data: PatchSpliceInput, seed: int) -> list[Finding]:
        results: list[dict[str, Any]] = []
        for path in data.image_paths:
            r = _analyse_one(
                path,
                patch_size=data.patch_size,
                stride=data.stride,
                n_bins=data.n_bins,
                z_threshold=data.z_threshold,
                min_cluster_size=data.min_cluster_size,
            )
            if r is not None:
                results.append(r)

        findings: list[Finding] = []
        for r in results:
            max_z = r["max_z"]
            cluster = r["largest_cluster"]
            has_cluster = cluster >= data.min_cluster_size
            severity = None
            if max_z < data.z_threshold:
                continue
            if max_z >= 6.0 and has_cluster:
                severity = Severity.SUSPICIOUS
            elif max_z >= 6.0 or has_cluster:
                severity = Severity.CONCERN
            elif max_z >= data.z_threshold:
                severity = Severity.NOTE
            if severity is None:
                continue
            findings.append(
                Finding(
                    detector_id=self.id,
                    detector_name=self.name,
                    severity=severity,
                    summary=(
                        f"Per-channel histogram discontinuity in "
                        f"{Path(r['image_path']).name} "
                        f"(max z={max_z:.2f}, cluster={cluster} patches)"
                    ),
                    detail=(
                        f"Image divided into {r['n_patches']} patches of "
                        f"{data.patch_size}×{data.patch_size} (grid "
                        f"{r['grid'][0]}×{r['grid'][1]}). "
                        f"{r['n_outlier_patches']} patches have JSD-to-"
                        f"4-neighbours ≥ {data.z_threshold} robust "
                        f"z-score above the median, with the largest "
                        f"connected outlier cluster spanning {cluster} "
                        f"patches.\n\n"
                        "This signal is what Bik et al. (2016) used as "
                        "their primary visual cue for splicing. It is "
                        "*not* a verdict — many legitimate causes can "
                        "produce the same pattern (see innocent "
                        "explanations)."
                    ),
                    test_statistic=max_z,
                    test_name="patch histogram robust z-score",
                    evidence={
                        "image_path": r["image_path"],
                        "n_patches": r["n_patches"],
                        "n_outlier_patches": r["n_outlier_patches"],
                        "max_z": max_z,
                        "median_jsd": r["median_jsd"],
                        "mad": r["mad"],
                        "largest_cluster": cluster,
                        "grid": r["grid"],
                        "z_threshold": data.z_threshold,
                    },
                    innocent_explanations=[
                        "Strong content edges (object boundaries, "
                        "tissue interfaces, well plate borders) "
                        "naturally produce high per-channel "
                        "histogram discontinuities.",
                        "JPEG compression artefacts at high "
                        "quantisation can introduce blocking that "
                        "looks like patch-level discontinuity.",
                        "Locally-applied contrast / brightness "
                        "adjustments (allowed under most journal "
                        "policies, but require disclosure) produce "
                        "the same signal as splicing.",
                        "Fluorescent microscopy panel composition: "
                        "legitimate side-by-side composition with "
                        "different acquisition channels can show "
                        "the same patch discontinuity at the panel "
                        "boundary.",
                        "Bik 2016 herself emphasised that the visual "
                        "cue is necessary but not sufficient — "
                        "manual review by a trained eye is required "
                        "to confirm.",
                    ],
                    academic_reference=self.academic_basis,
                    applicability_notes=(
                        f"Patch size = {data.patch_size}×{data.patch_size}, "
                        f"stride = {data.stride}, "
                        f"{data.n_bins}-bin histograms per channel, "
                        "robust z = (jsd − median) / (1.4826 · MAD). "
                        "Re-tune via PatchSpliceInput.z_threshold and "
                        "PatchSpliceInput.min_cluster_size."
                    ),
                )
            )
        return findings
