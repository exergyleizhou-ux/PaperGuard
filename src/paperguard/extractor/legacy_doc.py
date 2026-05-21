"""Legacy Word format (.doc / .docb) image + text extraction.

The modern ``.docx`` (Office Open XML) format is a zip with a clean
XML tree; PaperGuard's main pipeline handles it via ``python-docx``.

The pre-2007 ``.doc`` format and the encrypted/binary ``.docb`` format
are **OLE Compound Documents** — a Microsoft-proprietary binary
container. ``olefile`` reads the structure; embedded images live in
dedicated streams (``WordDocument`` and any ``ObjectPool/_NNN/Ole10Native``
or ``Pictures`` substream).

This module ships two public helpers:

- ``extract_legacy_doc_images(path, out_dir)`` — best-effort scan for
  embedded image streams; writes them to ``out_dir`` as ``image_N.bin``
  (the file extension is left raw because OLE doesn't carry MIME type
  reliably). Returns a list of written paths.
- ``extract_legacy_doc_text(path)`` — best-effort plain-text extraction
  from the ``WordDocument`` stream; strips OLE control bytes via a
  conservative ASCII / UTF-16 heuristic. Returns a single string.

Failure modes (all silent, never raise):

- File is not an OLE document → returns ``[]`` / ``""``
- olefile not installed → returns ``[]`` / ``""``
- Encrypted ``.docb`` we cannot decrypt → returns what plaintext we
  can extract, may be empty
- Embedded image stream too small to be an image → skipped

Scope note
----------
This is **not** a full Word binary parser. We do not reconstruct
formatting, fields, comments, or revisions. The goal is to feed
existing PaperGuard detectors (F1-F6 image forensics, T6 lexical
LLM-text) on the parts of a legacy ``.doc`` that they can reason
about.

When you have control over the document source, ``.docx`` is
strictly preferable — modern detectors work better on it.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Minimum byte size to consider a stream a candidate image (below this
# it's almost certainly an OLE metadata blob, not a picture).
_MIN_IMAGE_BYTES = 1024

# Common image-format magic prefixes — used to detect embedded images
# in raw OLE streams when the stream name doesn't tell us.
_IMAGE_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"BM", "bmp"),
    (b"II*\x00", "tif"),
    (b"MM\x00*", "tif"),
    (b"\x00\x00\x01\x00", "ico"),
)


def _detect_image_format(blob: bytes) -> str | None:
    """Return file extension if ``blob`` starts with a known image magic."""
    for magic, ext in _IMAGE_MAGIC:
        if blob.startswith(magic):
            return ext
    # Some Word docs prepend an OLE picture descriptor before the actual
    # image bytes. Scan the first 256 bytes for any of our magics.
    head = blob[:256]
    for magic, ext in _IMAGE_MAGIC:
        idx = head.find(magic)
        if idx >= 0:
            return ext
    return None


def extract_legacy_doc_images(
    path: Path,
    out_dir: Path,
    *,
    max_images: int = 200,
) -> list[Path]:
    """Best-effort extraction of embedded images from a legacy .doc/.docb.

    Returns a list of written file paths. Empty list on any failure.
    """
    try:
        import olefile  # type: ignore[import-untyped]
    except ImportError:
        logger.warning(
            "extract_legacy_doc_images: olefile not installed; skipping"
        )
        return []

    if not path.exists():
        return []
    try:
        if not olefile.isOleFile(str(path)):
            return []
    except Exception as e:  # noqa: BLE001
        logger.warning("extract_legacy_doc_images: %s not OLE: %s", path, e)
        return []

    try:
        ole = olefile.OleFileIO(str(path))
    except Exception as e:  # noqa: BLE001
        logger.warning("extract_legacy_doc_images: open failed: %s", e)
        return []

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    try:
        for stream_path in ole.listdir():
            if len(written) >= max_images:
                break
            try:
                with ole.openstream(stream_path) as fh:
                    blob = fh.read()
            except Exception:  # noqa: BLE001
                continue
            if len(blob) < _MIN_IMAGE_BYTES:
                continue
            ext = _detect_image_format(blob)
            if ext is None:
                continue
            # Strip up to 256-byte OLE picture header — find the magic
            # position and start the file from there.
            offset = 0
            for magic, fmt in _IMAGE_MAGIC:
                if fmt == ext:
                    offset = blob[:256].find(magic)
                    if offset < 0:
                        offset = 0
                    break
            payload = blob[offset:]
            slug = "_".join(stream_path).replace("/", "_").replace("\\", "_")
            dst = out_dir / f"img_{len(written):04d}_{slug[:40]}.{ext}"
            try:
                dst.write_bytes(payload)
                written.append(dst)
            except OSError as e:
                logger.warning(
                    "extract_legacy_doc_images: write %s failed: %s", dst, e
                )
                continue
    finally:
        ole.close()
    return written


def extract_legacy_doc_text(path: Path) -> str:
    """Best-effort plain-text extraction from a legacy .doc/.docb.

    Heuristic:
      1. Open the ``WordDocument`` stream.
      2. Try UTF-16-LE decode (Word 2003+).
      3. If that produces mostly control characters, fall back to
         ASCII strict + filter to printable.
      4. Collapse runs of whitespace.

    Returns "" on any failure.
    """
    try:
        import olefile
    except ImportError:
        return ""
    if not path.exists():
        return ""
    try:
        if not olefile.isOleFile(str(path)):
            return ""
    except Exception:  # noqa: BLE001
        return ""

    try:
        ole = olefile.OleFileIO(str(path))
    except Exception:  # noqa: BLE001
        return ""

    text = ""
    try:
        if ole.exists("WordDocument"):
            with ole.openstream("WordDocument") as fh:
                blob = fh.read()
            text = _best_effort_decode(blob)
    finally:
        ole.close()
    return text


def _best_effort_decode(blob: bytes) -> str:
    """Try UTF-16-LE first, then ASCII filter. Return collapsed printable text."""
    candidates: list[str] = []
    try:
        utf16 = blob.decode("utf-16-le", errors="ignore")
        candidates.append(utf16)
    except Exception:  # noqa: BLE001
        pass
    try:
        ascii_filt = "".join(chr(b) for b in blob if 32 <= b < 127 or b in (9, 10, 13))
        candidates.append(ascii_filt)
    except Exception:  # noqa: BLE001
        pass

    # Pick the candidate with the highest *English-letter density* —
    # this distinguishes real prose from random OLE control bytes.
    def score(s: str) -> float:
        if not s:
            return 0.0
        letters = sum(1 for c in s if c.isalpha())
        return letters / len(s)

    best = max(candidates, key=score, default="")
    # Collapse run-on whitespace; keep paragraph breaks.
    import re

    return re.sub(r"\s+", " ", best).strip()
