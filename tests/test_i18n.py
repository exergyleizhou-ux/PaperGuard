"""i18n 系统测试。"""
from __future__ import annotations

import os

import pytest

from paperguard.i18n import available_languages, t


def test_default_is_english() -> None:
    assert t("report.title") == "PaperGuard Audit Report"


def test_chinese_translation() -> None:
    assert t("report.title", lang="zh-CN") == "PaperGuard 审查报告"


def test_zh_alias() -> None:
    """'zh' 应自动归一化到 zh-CN。"""
    assert t("report.title", lang="zh") == "PaperGuard 审查报告"


def test_unknown_key_returns_key() -> None:
    assert t("nonexistent.key") == "nonexistent.key"


def test_severity_translations() -> None:
    assert t("severity.CRITICAL", lang="en") == "CRITICAL"
    assert t("severity.CRITICAL", lang="zh-CN") == "紧急"
    assert t("severity.PASS", lang="zh-CN") == "通过"


def test_disclaimer_contains_required_word() -> None:
    en = t("report.disclaimer", lang="en")
    zh = t("report.disclaimer", lang="zh-CN")
    assert "anomalies" in en.lower()
    assert "异常" in zh


def test_env_var_override() -> None:
    """PAPERGUARD_LANG 环境变量在 lang=None 时生效。"""
    old = os.environ.get("PAPERGUARD_LANG")
    try:
        os.environ["PAPERGUARD_LANG"] = "zh-CN"
        assert t("report.title") == "PaperGuard 审查报告"
    finally:
        if old is None:
            os.environ.pop("PAPERGUARD_LANG", None)
        else:
            os.environ["PAPERGUARD_LANG"] = old


def test_available_languages() -> None:
    langs = available_languages()
    assert "en" in langs
    assert "zh-CN" in langs


@pytest.mark.parametrize(
    "key",
    [
        "report.title",
        "report.overall",
        "report.no_anomalies",
        "report.disclaimer",
        "severity.PASS",
        "severity.CRITICAL",
    ],
)
def test_all_keys_have_both_langs(key: str) -> None:
    assert t(key, lang="en") != key
    assert t(key, lang="zh-CN") != key
