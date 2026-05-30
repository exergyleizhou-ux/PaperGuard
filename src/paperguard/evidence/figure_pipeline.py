"""Offline wiring: a document file (PDF / .docx) -> figure & table detectors.

The figure-forensics (F1/F2/F3/F5/F6/F7) and RCT-baseline (C1) detectors are
the decisive anti-fabrication families, but until now nothing connected the
existing extractors (``extractor.images``, ``extractor.baseline_tables``) to
them in a single call. This module is that connector.

It is deliberately **offline and pure orchestration**:
  * no network — the caller supplies a local file path (a downloaded OA PDF,
    a submitted manuscript, etc.);
  * no new detection logic — it only builds the typed ``*Input`` objects each
    detector already expects and collects their ``DetectorResult``s;
  * heavy optional deps (pymupdf, pdfplumber, imagehash, opencv) are imported
    lazily *inside* the extractors, so importing this module is always safe.

IRON RULE unchanged: detectors still emit anomaly signals + innocent
explanations only; this module never adds verdict language.
"""
from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from paperguard.core.types import DetectorResult
from paperguard.detectors.c1_carlisle import C1CarlisleDetector, CarlisleInput
from paperguard.detectors.f1_image_duplication import (
    F1ImageDuplicationDetector,
    ImageDuplicationInput,
)
from paperguard.detectors.f2_internal_duplication import (
    F2InternalDuplicationDetector,
    InternalDuplicationInput,
)
from paperguard.detectors.f3_splice_forensics import (
    F3SpliceForensicsDetector,
    SpliceForensicsInput,
)
from paperguard.detectors.f5_exif_clustering import (
    ExifClusteringInput,
    F5ExifClusteringDetector,
)
from paperguard.detectors.f6_patch_splice import (
    F6PatchSpliceDetector,
    PatchSpliceInput,
)
from paperguard.detectors.f7_gan_spectral import (
    F7GanSpectralDetector,
    GanSpectralInput,
)


@dataclass
class FigurePipelineResult:
    """Everything the pipeline produced for one document.

    ``image_paths`` and the baseline-table count are surfaced so callers can
    audit *what was fed* to the detectors (important for honest reporting — an
    empty ``image_paths`` means "no figures extracted", not "no manipulation").
    """

    source: Path
    image_paths: list[Path] = field(default_factory=list)
    n_baseline_tables: int = 0
    results: list[DetectorResult] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _extract_images(source: Path, work_dir: Path) -> list[Path]:
    """Extract figure images from a PDF or .docx. Returns [] on any failure."""
    suffix = source.suffix.lower()
    out_dir = work_dir / "images"
    try:
        if suffix == ".pdf":
            from paperguard.extractor.images import extract_pdf_images

            return extract_pdf_images(source, out_dir)
        if suffix == ".docx":
            from paperguard.extractor.images import extract_docx_images

            return extract_docx_images(source, out_dir)
    except Exception:  # noqa: BLE001 - extraction is best-effort, never fatal
        return []
    return []


def _run_image_detectors(image_paths: list[Path]) -> list[DetectorResult]:
    """Feed extracted images to every figure-forensics detector.

    Each detector self-skips (``applicable=False``) when it needs >= 2 images
    or a missing optional dep, so callers get a uniform ``DetectorResult`` list
    regardless of how many images were found.
    """
    return [
        F1ImageDuplicationDetector().detect(ImageDuplicationInput(image_paths)),
        F2InternalDuplicationDetector().detect(
            InternalDuplicationInput(image_paths)
        ),
        F3SpliceForensicsDetector().detect(SpliceForensicsInput(image_paths)),
        F5ExifClusteringDetector().detect(ExifClusteringInput(image_paths)),
        F6PatchSpliceDetector().detect(PatchSpliceInput(image_paths)),
        F7GanSpectralDetector().detect(GanSpectralInput(image_paths)),
    ]


def _run_baseline_detector(source: Path) -> tuple[int, list[DetectorResult]]:
    """Extract RCT baseline tables from a PDF and feed C1 (Carlisle).

    Returns (n_tables_found, results). Non-PDF or extraction failure -> (0, []).
    """
    if source.suffix.lower() != ".pdf":
        return 0, []
    try:
        from paperguard.extractor.baseline_tables import extract_baseline_tables

        tables = extract_baseline_tables(source)
    except Exception:  # noqa: BLE001 - best-effort, never fatal
        return 0, []

    results: list[DetectorResult] = []
    c1 = C1CarlisleDetector()
    for idx, table in enumerate(tables):
        if not table.variables:
            continue
        trial_id = f"{source.stem}-table{table.page_number or idx}"
        results.append(
            c1.detect(CarlisleInput(trial_id=trial_id, variables=table.variables))
        )
    return len(tables), results


def run_figure_pipeline(
    source: Path | str,
    *,
    work_dir: Path | str | None = None,
) -> FigurePipelineResult:
    """Run figure-forensics + RCT-baseline detectors on one local document.

    Args:
        source: local path to a ``.pdf`` or ``.docx`` (already downloaded;
            this function performs no network I/O).
        work_dir: where to write extracted images. A temp dir is created and
            left in place when ``None`` (caller owns cleanup); pass an explicit
            dir for deterministic tests.

    Returns:
        A :class:`FigurePipelineResult` bundling the extracted artefacts and
        every detector's :class:`DetectorResult`. Detectors that cannot run
        (too few images, missing optional dep, non-PDF for C1) appear as
        ``applicable=False`` results rather than being silently dropped — the
        absence of evidence is reported, never hidden.
    """
    source = Path(source)
    result = FigurePipelineResult(source=source)

    if not source.exists():
        result.notes.append(f"source not found: {source}")
        return result

    if work_dir is not None:
        wd = Path(work_dir)
    else:
        wd = Path(tempfile.mkdtemp(prefix="paperguard_fig_"))

    images = _extract_images(source, wd)
    result.image_paths = images
    if not images:
        result.notes.append("no figure images extracted")
    else:
        result.results.extend(_run_image_detectors(images))

    n_tables, baseline_results = _run_baseline_detector(source)
    result.n_baseline_tables = n_tables
    if source.suffix.lower() == ".pdf" and n_tables == 0:
        result.notes.append("no RCT baseline tables extracted")
    result.results.extend(baseline_results)

    return result
