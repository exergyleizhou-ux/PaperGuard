"""Extra i18n 测试 — es / ja / de 语言包。"""
from __future__ import annotations

import pytest

from paperguard.i18n import available_languages, t


@pytest.mark.parametrize("lang", ["es", "ja", "de"])
def test_full_coverage(lang: str) -> None:
    for key in (
        "report.title",
        "report.overall",
        "report.no_anomalies",
        "report.disclaimer",
        "severity.PASS",
        "severity.CRITICAL",
        "report.innocent",
        "report.reference",
    ):
        translated = t(key, lang=lang)
        assert translated != key, f"{lang} missing translation for {key}"


def test_supported_languages_complete() -> None:
    langs = available_languages()
    for lang in ("en", "zh-CN", "es", "ja", "de"):
        assert lang in langs


def test_specific_translations() -> None:
    assert "Crítico".upper() in t("severity.CRITICAL", lang="es").upper()
    assert "重大" in t("severity.CRITICAL", lang="ja")
    assert "KRITISCH" in t("severity.CRITICAL", lang="de").upper()
