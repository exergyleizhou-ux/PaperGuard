"""轻量 i18n — 不依赖 gettext，直接 dict 查表。

只翻译报告框架文案（标题、列标签、免责声明等）。
检测器自己的 summary/detail 是中文，保持原样——翻译它们需要逐个改
detector 文件，工作量大且不影响 GitHub 用户阅读（report 的标题/分级
英文是国际惯例）。

支持的语言：
- en (default)
- zh-CN
"""
from __future__ import annotations

import os
from typing import Final

_DEFAULT_LANG: Final[str] = "en"
_SUPPORTED: Final[set[str]] = {"en", "zh-CN", "zh", "es", "ja", "de"}

_STRINGS: dict[str, dict[str, str]] = {
    "report.title": {
        "en": "PaperGuard Audit Report",
        "zh-CN": "PaperGuard 审查报告",
        "es": "Informe de Auditoría PaperGuard",
        "ja": "PaperGuard 監査レポート",
        "de": "PaperGuard Prüfbericht",
    },
    "report.overall": {
        "en": "Overall",
        "zh-CN": "总体严重性",
        "es": "General",
        "ja": "総合",
        "de": "Gesamt",
    },
    "report.paper": {
        "en": "Paper",
        "zh-CN": "文件",
        "es": "Documento",
        "ja": "ファイル",
        "de": "Datei",
    },
    "report.no_anomalies": {
        "en": "No anomalies detected.",
        "zh-CN": "未检测到异常。",
        "es": "No se detectaron anomalías.",
        "ja": "異常は検出されませんでした。",
        "de": "Keine Anomalien festgestellt.",
    },
    "report.processing": {
        "en": "Processing",
        "zh-CN": "正在处理",
        "es": "Procesando",
        "ja": "処理中",
        "de": "Verarbeitung",
    },
    "report.retraction": {
        "en": "Retraction status",
        "zh-CN": "撤稿状态",
        "es": "Estado de retractación",
        "ja": "撤回状況",
        "de": "Rücknahmestatus",
    },
    "report.pubpeer": {
        "en": "PubPeer concerns",
        "zh-CN": "PubPeer 公开质疑数",
        "es": "Preocupaciones en PubPeer",
        "ja": "PubPeer の懸念",
        "de": "PubPeer-Bedenken",
    },
    "report.innocent": {
        "en": "Possible innocent explanations",
        "zh-CN": "可能的合法解释",
        "es": "Posibles explicaciones inocentes",
        "ja": "正当な説明の可能性",
        "de": "Mögliche harmlose Erklärungen",
    },
    "report.reference": {
        "en": "Reference",
        "zh-CN": "学术依据",
        "es": "Referencia",
        "ja": "学術的根拠",
        "de": "Referenz",
    },
    "report.disclaimer": {
        "en": (
            "Disclaimer. This report flags statistical anomalies, not fraud "
            "or misconduct. Anomalies can arise from instrument behavior, "
            "data-cleaning choices, legitimate experimental constraints, or "
            "honest error. Any concern about authorship integrity should be "
            "raised through journal editors or institutional investigation "
            "channels, not on the basis of this tool's output alone."
        ),
        "zh-CN": (
            "免责声明：本报告标记的是统计异常，不构成对学术造假的指控。"
            "异常可能源自仪器特性、数据处理流程、合理的实验条件或诚实错误。"
            "任何对作者的质疑都应通过期刊编辑或机构调查渠道，"
            "而非基于本工具的输出。"
        ),
        "es": (
            "Descargo de responsabilidad. Este informe señala anomalías "
            "estadísticas, no fraude ni mala conducta. Las anomalías pueden "
            "surgir del comportamiento del instrumento, opciones de limpieza "
            "de datos, restricciones experimentales legítimas o errores "
            "honestos. Cualquier preocupación sobre la integridad de la "
            "autoría debe plantearse a través de los editores de la revista "
            "o canales de investigación institucionales, no únicamente con "
            "base en la salida de esta herramienta."
        ),
        "ja": (
            "免責事項：本レポートは統計的異常を示すものであり、不正行為や "
            "ミスコンダクトを示すものではありません。異常は装置の挙動、デー "
            "タクリーニングの選択、正当な実験上の制約、または誠実な誤りに "
            "よって生じる可能性があります。著者の誠実性に関するいかなる懸 "
            "念も、本ツールの出力のみに基づくのではなく、ジャーナル編集者 "
            "または機関による調査を通じて提起すべきです。"
        ),
        "de": (
            "Haftungsausschluss. Dieser Bericht weist auf statistische "
            "Anomalien hin, nicht auf Betrug oder Fehlverhalten. Anomalien "
            "können durch Instrumentenverhalten, Entscheidungen zur "
            "Datenbereinigung, legitime experimentelle Einschränkungen oder "
            "ehrliche Fehler entstehen. Bedenken hinsichtlich der "
            "Autorenintegrität sollten über die Zeitschriftenredaktion oder "
            "institutionelle Untersuchungskanäle vorgebracht werden, nicht "
            "allein auf Grundlage der Ausgabe dieses Werkzeugs."
        ),
    },
    "severity.PASS": {
        "en": "PASS", "zh-CN": "通过", "es": "OK", "ja": "合格", "de": "OK",
    },
    "severity.NOTE": {
        "en": "NOTE", "zh-CN": "备注", "es": "NOTA", "ja": "注記", "de": "HINWEIS",
    },
    "severity.CONCERN": {
        "en": "CONCERN", "zh-CN": "关注", "es": "PREOCUPACIÓN",
        "ja": "懸念", "de": "BEDENKEN",
    },
    "severity.SUSPICIOUS": {
        "en": "SUSPICIOUS", "zh-CN": "高度可疑", "es": "SOSPECHOSO",
        "ja": "要注意", "de": "VERDÄCHTIG",
    },
    "severity.CRITICAL": {
        "en": "CRITICAL", "zh-CN": "紧急", "es": "CRÍTICO",
        "ja": "重大", "de": "KRITISCH",
    },
}


def _resolve(lang: str | None) -> str:
    """归一化语言代码。"""
    if not lang:
        lang = os.environ.get("PAPERGUARD_LANG") or _DEFAULT_LANG
    if lang.lower().startswith("zh"):
        return "zh-CN"
    if lang in _SUPPORTED:
        return lang
    return _DEFAULT_LANG


def t(key: str, lang: str | None = None) -> str:
    """翻译 key 到目标语言；找不到时回落 en。"""
    norm = _resolve(lang)
    entry = _STRINGS.get(key)
    if not entry:
        return key
    return entry.get(norm) or entry.get(_DEFAULT_LANG) or key


def available_languages() -> list[str]:
    return sorted(_SUPPORTED)
