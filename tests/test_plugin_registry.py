"""插件加载系统测试。"""
from __future__ import annotations

from typing import Any, ClassVar
from unittest.mock import MagicMock, patch

import pytest

from paperguard.core.base_detector import BaseDetector
from paperguard.core.registry import DetectorRegistry
from paperguard.core.types import Finding


class _FakePlugin(BaseDetector):
    id: ClassVar[str] = "FAKE1"
    name: ClassVar[str] = "Fake Plugin Detector"
    description: ClassVar[str] = "test"
    academic_basis: ClassVar[str] = "test"
    data_requirements: ClassVar[list[str]] = ["raw_numeric_values"]
    assumption_cluster: ClassVar[str] = "test"

    def check_applicability(self, data: Any) -> tuple[bool, str]:
        return False, "test stub"

    def _detect(self, data: Any, seed: int) -> list[Finding]:
        return []


class _BadPlugin:
    """不是 BaseDetector 子类 → 应该被忽略。"""


def _make_ep(name: str, target: type) -> MagicMock:
    ep = MagicMock()
    ep.name = name
    ep.load.return_value = target
    return ep


def test_plugin_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_entry_points(group: str = "") -> list[MagicMock]:  # noqa: ARG001
        return [_make_ep("fake", _FakePlugin)]

    with patch("paperguard.core.registry.entry_points", fake_entry_points):
        reg = DetectorRegistry()
        loaded = reg.load_plugins()

    assert "FAKE1" in loaded
    assert reg.get("FAKE1") is not None


def test_plugin_rejects_non_basedetector(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_entry_points(group: str = "") -> list[MagicMock]:  # noqa: ARG001
        return [_make_ep("bad", _BadPlugin)]

    with patch("paperguard.core.registry.entry_points", fake_entry_points):
        reg = DetectorRegistry()
        loaded = reg.load_plugins()

    assert loaded == []


def test_plugin_handles_load_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    bad_ep = MagicMock()
    bad_ep.name = "broken"
    bad_ep.load.side_effect = ImportError("missing dependency")

    def fake_entry_points(group: str = "") -> list[MagicMock]:  # noqa: ARG001
        return [bad_ep]

    with patch("paperguard.core.registry.entry_points", fake_entry_points):
        reg = DetectorRegistry()
        # 不应抛出
        loaded = reg.load_plugins()
    assert loaded == []


def test_register_default_with_plugins_disabled() -> None:
    reg = DetectorRegistry().register_default(load_plugins=False)
    # 32 built-ins: 30 through 2.0.13 + E1 ICC (2.0.14) + T7 perplexity (2.0.15)
    assert len(reg.all()) == 32
