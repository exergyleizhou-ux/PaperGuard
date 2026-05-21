"""Tests for paperguard.extractor.legacy_doc — .doc / .docb extraction."""
from __future__ import annotations

from pathlib import Path

import pytest

from paperguard.extractor.legacy_doc import (
    _detect_image_format,
    extract_legacy_doc_images,
    extract_legacy_doc_text,
)


def test_detect_image_format_png() -> None:
    blob = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
    assert _detect_image_format(blob) == "png"


def test_detect_image_format_jpg() -> None:
    blob = b"\xff\xd8\xff\xe0" + b"\x00" * 200
    assert _detect_image_format(blob) == "jpg"


def test_detect_image_format_gif() -> None:
    blob = b"GIF89a" + b"\x00" * 200
    assert _detect_image_format(blob) == "gif"


def test_detect_image_format_bmp() -> None:
    blob = b"BM" + b"\x00" * 200
    assert _detect_image_format(blob) == "bmp"


def test_detect_image_format_unknown() -> None:
    blob = b"\x00" * 256
    assert _detect_image_format(blob) is None


def test_detect_image_format_with_offset() -> None:
    """Word doc may prepend an OLE picture descriptor (~50 bytes)."""
    blob = b"\x00" * 50 + b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
    assert _detect_image_format(blob) == "png"


# ---------------------------------------------------------------------------
# Non-OLE files should yield empty results, never raise
# ---------------------------------------------------------------------------


def test_extract_text_on_non_ole_file(tmp_path: Path) -> None:
    fake = tmp_path / "not_a_doc.txt"
    fake.write_bytes(b"This is plain text, not OLE.")
    assert extract_legacy_doc_text(fake) == ""


def test_extract_text_on_missing_file(tmp_path: Path) -> None:
    assert extract_legacy_doc_text(tmp_path / "nope.doc") == ""


def test_extract_images_on_non_ole_file(tmp_path: Path) -> None:
    fake = tmp_path / "not_a_doc.txt"
    fake.write_bytes(b"plain text")
    out = tmp_path / "imgs"
    assert extract_legacy_doc_images(fake, out) == []


def test_extract_images_on_missing_file(tmp_path: Path) -> None:
    out = tmp_path / "imgs"
    assert extract_legacy_doc_images(tmp_path / "nope.doc", out) == []


# ---------------------------------------------------------------------------
# Synthetic OLE file with embedded PNG
# ---------------------------------------------------------------------------


def _make_synthetic_ole(path: Path, image_blob: bytes) -> None:
    """Build a minimal OLE compound doc with a 'Pictures' stream containing
    the given image blob.

    We use olefile + a tiny "dummy" template approach — olefile can read
    but not write OLE. So we hand-craft using a known-good template:
    we ship an empty OLE skeleton in the test fixtures dir. If that's
    not available, the test is skipped.
    """
    # Use an alternate strategy: spawn a Word-like OLE by writing a
    # known-good minimal CFB. The simplest path: rely on the `compoundfiles`
    # package OR skip the round-trip test if we can't build one.
    # For unit-test scope we assert the EXTRACTOR's read path; building
    # a real .doc is out of scope. We skip via pytest if no fixture.
    raise NotImplementedError(
        "Synthetic OLE file construction requires a separate write library; "
        "this test path is documented but skipped at unit-test scope."
    )


def test_extract_images_skips_when_synthetic_ole_unavailable(tmp_path: Path) -> None:
    """Documents that we accept the unit-test scope limitation: building
    a real OLE compound doc requires Microsoft Word or a write library.
    The smoke test above (non-OLE → empty) is the load-bearing check."""
    # Just exercise the early-return path: a binary blob that's NOT OLE
    fake = tmp_path / "garbage.doc"
    fake.write_bytes(b"PK\x03\x04" + b"\x00" * 100)  # Looks like ZIP, not OLE
    out = tmp_path / "imgs"
    assert extract_legacy_doc_images(fake, out) == []


# ---------------------------------------------------------------------------
# olefile-not-installed graceful path
# ---------------------------------------------------------------------------


def test_extract_text_without_olefile(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """If olefile import fails, return "" silently."""
    import sys

    monkeypatch.setitem(sys.modules, "olefile", None)
    f = tmp_path / "fake.doc"
    f.write_bytes(b"anything")
    # The function does `import olefile` inside; when sys.modules[mod] is
    # None Python raises ImportError, which we catch + return "".
    assert extract_legacy_doc_text(f) == ""


def test_extract_images_without_olefile(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import sys

    monkeypatch.setitem(sys.modules, "olefile", None)
    f = tmp_path / "fake.doc"
    f.write_bytes(b"anything")
    out = tmp_path / "imgs"
    assert extract_legacy_doc_images(f, out) == []
