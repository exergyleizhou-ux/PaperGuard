"""Offline tests for the PMC OA figure extractor.

The network path (``fetch_pmc_figure_images``) is not exercised here; we test
``extract_figures_from_targz`` against in-memory archives, plus the OA-URL
parser against a canned oa.fcgi XML response (httpx.get monkeypatched).
"""
from __future__ import annotations

import io
import random
import tarfile
from pathlib import Path

import httpx
import pytest

from paperguard.extractor import pmc_figures
from paperguard.extractor.pmc_figures import extract_figures_from_targz


def _png_bytes(seed: int, size: int = 256) -> bytes:
    """High-entropy PNG that won't compress below the 8KB icon threshold."""
    from PIL import Image

    rng = random.Random(seed)
    img = Image.new("RGB", (size, size))
    img.putdata(
        [
            (rng.randrange(256), rng.randrange(256), rng.randrange(256))
            for _ in range(size * size)
        ]
    )
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_targz(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def test_extracts_only_large_images(tmp_path: Path) -> None:
    try:
        big1 = _png_bytes(1)
        big2 = _png_bytes(2)
    except ImportError:
        pytest.skip("Pillow not installed")

    raw = _make_targz(
        {
            "PMC1/fig1.png": big1,
            "PMC1/fig2.png": big2,
            "PMC1/icon.png": b"\x89PNG\r\n" + b"x" * 100,  # < 8KB -> dropped
            "PMC1/methods.xml": b"<x/>",  # non-image -> dropped
        }
    )
    out = extract_figures_from_targz(raw, tmp_path / "imgs")
    assert len(out) == 2
    assert all(p.suffix == ".png" for p in out)
    assert all(p.stat().st_size >= 8192 for p in out)


def test_rejects_path_traversal(tmp_path: Path) -> None:
    try:
        big = _png_bytes(7)
    except ImportError:
        pytest.skip("Pillow not installed")

    raw = _make_targz(
        {
            "../evil.png": big,
            "/abs/evil.png": big,
            "PMC2/ok.png": big,
        }
    )
    out = extract_figures_from_targz(raw, tmp_path / "imgs")
    # only the safe member survives; nothing written outside out_dir
    assert len(out) == 1
    assert (tmp_path / "imgs") in out[0].parents
    assert not (tmp_path / "evil.png").exists()


def test_malformed_archive_returns_empty(tmp_path: Path) -> None:
    out = extract_figures_from_targz(b"not a tarball", tmp_path / "imgs")
    assert out == []


def test_oa_url_parses_tgz_link_and_https_rewrite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    xml = (
        '<OA><records><record id="PMC9"><link format="pdf" '
        'href="ftp://ftp.ncbi.nlm.nih.gov/x.pdf"/>'
        '<link format="tgz" '
        'href="ftp://ftp.ncbi.nlm.nih.gov/pub/pmc/PMC9.tar.gz"/>'
        "</record></records></OA>"
    )

    class _Resp:
        text = xml

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(httpx, "get", lambda *_a, **_k: _Resp())
    url = pmc_figures._oa_package_url("PMC9", timeout=5.0)
    assert url == "https://ftp.ncbi.nlm.nih.gov/pub/pmc/PMC9.tar.gz"


def test_oa_url_none_when_no_tgz(monkeypatch: pytest.MonkeyPatch) -> None:
    xml = (
        '<OA><records><record><link format="pdf" href="ftp://x.pdf"/>'
        "</record></records></OA>"
    )

    class _Resp:
        text = xml

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(httpx, "get", lambda *_a, **_k: _Resp())
    assert pmc_figures._oa_package_url("PMC9", timeout=5.0) is None
