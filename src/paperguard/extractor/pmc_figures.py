"""Fetch real per-figure images from the PMC Open-Access package.

The page-as-raster fallback in ``extractor.images`` is fine for "is there a
figure on this page", but it is useless for image forensics: F3/F6/F7 need an
individual figure *panel* (a blot, a micrograph, a plot), not a whole rendered
page of mixed text + sub-figures (see ``docs/recall_validation_figures.md``).

The PMC Open-Access subset publishes each article as a ``.tar.gz`` that contains
the original figure image files. We resolve the package URL through NCBI's OA
service (``oa.fcgi``), download it, and extract the image members. This is the
input the forensics detectors were actually designed for.

OA only — ``oa.fcgi`` returns a package URL *only* for articles in the
open-access subset, so this never touches paywalled content. Best-effort: any
failure (not in OA subset, network error, malformed archive) returns ``[]``.
"""
from __future__ import annotations

import io
import tarfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET

import httpx

USER_AGENT = (
    "PaperGuard/2.17.0 (figure fetcher; "
    "https://github.com/exergyleizhou-ux/PaperGuard)"
)
OA_SERVICE = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".tif", ".tiff", ".bmp"}
# Below this many bytes a "figure" is almost always an icon / equation glyph /
# publisher logo, not a data panel — same rationale as extractor.images.
_MIN_IMAGE_BYTES = 8192


def _oa_package_url(pmcid: str, timeout: float) -> str | None:
    """Resolve the .tar.gz OA package URL for a PMCID via NCBI oa.fcgi.

    Returns an https URL, or None if the article is not in the OA subset.
    """
    pmcid = pmcid if pmcid.startswith("PMC") else f"PMC{pmcid}"
    try:
        r = httpx.get(
            OA_SERVICE,
            params={"id": pmcid},
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )
        r.raise_for_status()
        root = ET.fromstring(r.text)
    except (httpx.HTTPError, ET.ParseError):
        return None

    # <OA><records><record><link format="tgz" href="ftp://.../PMCxxxx.tar.gz"/>
    for link in root.iter("link"):
        if link.get("format") == "tgz":
            href = link.get("href")
            if href:
                # OA service hands back ftp:// links; the same path is served
                # over https, which httpx can fetch.
                return href.replace("ftp://", "https://", 1)
    return None


def _safe_image_members(tar: tarfile.TarFile) -> list[tarfile.TarInfo]:
    """Image members only, guarded against path traversal."""
    out: list[tarfile.TarInfo] = []
    for m in tar.getmembers():
        if not m.isfile():
            continue
        # tar member names are always POSIX — parse them as such so the
        # absolute / traversal guard is correct regardless of host OS (on
        # Windows, pathlib.Path("/abs/x") is NOT .is_absolute()).
        name = PurePosixPath(m.name)
        if name.suffix.lower() not in _IMAGE_SUFFIXES:
            continue
        # reject absolute paths / .. traversal / leading-slash — we only ever
        # use the basename, but never trust a malicious archive member name.
        if name.is_absolute() or m.name.startswith("/") or ".." in name.parts:
            continue
        out.append(m)
    return out


def extract_figures_from_targz(
    raw: bytes,
    out_dir: Path,
    *,
    min_bytes: int = _MIN_IMAGE_BYTES,
) -> list[Path]:
    """Extract figure images from in-memory ``.tar.gz`` bytes.

    Split out from the network path so it is unit-testable offline. Never
    raises: a malformed archive or write error returns whatever was written
    so far.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tar:
            for idx, member in enumerate(_safe_image_members(tar)):
                fh = tar.extractfile(member)
                if fh is None:
                    continue
                data = fh.read()
                if len(data) < min_bytes:
                    continue
                # flat, collision-proof name from basename + index
                base = Path(member.name).name
                dest = out_dir / f"{idx:03d}_{base}"
                dest.write_bytes(data)
                written.append(dest)
    except (tarfile.TarError, OSError):
        return written
    return sorted(written)


def fetch_pmc_figure_images(
    pmcid: str,
    out_dir: Path,
    *,
    timeout: float = 60.0,
    min_bytes: int = _MIN_IMAGE_BYTES,
) -> list[Path]:
    """Download a PMC OA package and extract its figure images.

    Args:
        pmcid: PMC identifier (``PMC1234567`` or ``1234567``).
        out_dir: directory to write extracted images into (created if absent).
        timeout: per-request timeout in seconds.
        min_bytes: drop images smaller than this (icons / glyphs).

    Returns:
        Sorted list of extracted image paths. ``[]`` if the article is not in
        the OA subset or anything fails — never raises.
    """
    url = _oa_package_url(pmcid, timeout)
    if not url:
        return []

    try:
        r = httpx.get(
            url,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )
        r.raise_for_status()
        raw = r.content
    except httpx.HTTPError:
        return []

    return extract_figures_from_targz(raw, out_dir, min_bytes=min_bytes)
