"""HTML 报告导出 — 适合分享给合作者或编辑。"""
from __future__ import annotations

import html
from pathlib import Path

from paperguard.core.types import AuditReport, Severity
from paperguard.i18n import t

_SEV_COLOR = {
    Severity.PASS: "#1f7a3d",        # WCAG AA on white: 5.71:1
    Severity.NOTE: "#0a4a8a",        # 6.86:1
    Severity.CONCERN: "#a05e00",     # 5.21:1（替换原偏黄）
    Severity.SUSPICIOUS: "#a8174e",  # 7.20:1
    Severity.CRITICAL: "#a1140a",    # 7.31:1
}

_SEV_ICON = {
    Severity.PASS: "✓",
    Severity.NOTE: "ℹ",
    Severity.CONCERN: "!",
    Severity.SUSPICIOUS: "!!",
    Severity.CRITICAL: "✕",
}


def _h(s: str) -> str:
    return html.escape(s, quote=True)


def render_html(report: AuditReport, lang: str | None = None) -> str:
    """生成自包含的 HTML 字符串（WCAG 2.1 AA 兼容）。"""
    overall = report.overall_severity
    color = _SEV_COLOR[overall]

    sorted_findings = sorted(report.all_findings, key=lambda f: -f.severity.value)

    finding_html: list[str] = []
    for f in sorted_findings:
        fc = _SEV_COLOR[f.severity]
        icon = _SEV_ICON[f.severity]
        evidence_items = ""
        if f.evidence:
            rows = "\n".join(
                f"<tr><th scope='row'>{_h(str(k))}</th>"
                f"<td><code>{_h(str(v))}</code></td></tr>"
                for k, v in f.evidence.items()
            )
            evidence_items = (
                f"<table class='evidence' "
                f"aria-label='Evidence for {_h(f.detector_id)}'>{rows}</table>"
            )
        innocent_items = ""
        if f.innocent_explanations:
            lis = "\n".join(
                f"<li>{_h(ie)}</li>" for ie in f.innocent_explanations
            )
            innocent_items = (
                "<div class='innocent'>"
                f"<h4>{_h(t('report.innocent', lang))}</h4>"
                f"<ul>{lis}</ul></div>"
            )
        pval = ""
        if f.p_value is not None:
            pval = f"<div class='pval'>p = {f.p_value:.4e}"
            if f.p_value_adjusted is not None:
                pval += f" (FDR-adjusted: {f.p_value_adjusted:.4e})"
            pval += "</div>"

        ref_label = _h(t("report.reference", lang))
        ref_block = (
            f"<p class='ref'>{ref_label}: {_h(f.academic_reference)}</p>"
            if f.academic_reference
            else ""
        )
        sev_label = _h(t(f"severity.{f.severity.label}", lang))
        # ARIA: badge 用 aria-label 给屏幕阅读器读完整严重性名而非图标
        finding_html.append(
            f"""
            <section class='finding' style='border-left-color: {fc};'
                     aria-labelledby='heading-{id(f)}'>
              <header>
                <span class='badge' style='background: {fc};'
                      role='status'
                      aria-label='Severity: {sev_label}'>
                  <span aria-hidden='true'>{icon}</span> {sev_label}
                </span>
                <span class='det-id'>{_h(f.detector_id)} — {_h(f.detector_name)}</span>
              </header>
              <h3 id='heading-{id(f)}'>{_h(f.summary)}</h3>
              <p>{_h(f.detail)}</p>
              {pval}
              {evidence_items}
              {innocent_items}
              {ref_block}
            </section>
            """
        )

    overall_label = _h(t(f"severity.{overall.label}", lang))
    overall_text = _h(t("report.overall", lang))
    title_text = _h(t("report.title", lang))
    no_anomalies_text = _h(t("report.no_anomalies", lang))
    disclaimer_text = _h(t("report.disclaimer", lang))

    pubpeer_block = ""
    if report.pubpeer_concerns_count > 0:
        pubpeer_label = _h(t("report.pubpeer", lang))
        pubpeer_block = (
            f"<p class='pubpeer'><strong>⚠ {pubpeer_label}:</strong> "
            f"{report.pubpeer_concerns_count}</p>"
        )

    retraction_block = ""
    if report.retraction_status:
        retraction_label = _h(t("report.retraction", lang))
        retraction_block = (
            f"<p class='retraction'><strong>⚠ {retraction_label}:</strong> "
            f"{_h(report.retraction_status)}</p>"
        )

    body_findings = (
        "".join(finding_html)
        if finding_html
        else f"<p style='color: green;'>{no_anomalies_text}</p>"
    )

    lang_attr = (lang or "en").split("-")[0]
    return f"""<!DOCTYPE html>
<html lang="{lang_attr}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PaperGuard — {_h(report.paper_identifier)}</title>
<style>
  /* WCAG 2.1 AA: focus outlines, color contrast >= 4.5:1, prefers-color-scheme respect */
  body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 900px;
          margin: 2em auto; padding: 0 1em; color: #1a1a1a;
          line-height: 1.5; font-size: 16px; }}
  :focus-visible {{ outline: 3px solid #0a4a8a; outline-offset: 2px; }}
  a {{ color: #0a4a8a; }}
  a:hover {{ text-decoration: underline; }}
  @media (prefers-reduced-motion: reduce) {{
    * {{ animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }}
  }}
  .header {{ border-left: 8px solid {color}; padding: 0.6em 1em;
             background: #f6f8fa; }}
  .header h1 {{ margin: 0 0 0.3em; }}
  .overall {{ color: {color}; font-weight: bold; font-size: 1.2em; }}
  .summary-line {{ color: #555; }}
  .finding {{ border-left: 6px solid #ccc; background: #fafbfc;
              padding: 0.6em 1em; margin: 1em 0; border-radius: 4px; }}
  .finding header {{ font-size: 0.9em; margin-bottom: 0.4em; }}
  .badge {{ color: white; padding: 0.1em 0.6em; border-radius: 4px;
            font-size: 0.85em; font-weight: bold; }}
  .det-id {{ color: #666; margin-left: 0.6em; }}
  .pval {{ font-family: monospace; color: #666; margin: 0.4em 0; }}
  table.evidence {{ font-size: 0.85em; margin: 0.4em 0;
                    border-collapse: collapse; }}
  table.evidence th {{ text-align: left; padding: 0.2em 0.6em; color: #555;
                       font-weight: normal; white-space: nowrap; }}
  table.evidence td {{ padding: 0.2em 0.6em; }}
  .innocent {{ background: #fff8e1; padding: 0.4em 0.8em; border-radius: 3px;
               margin: 0.4em 0; }}
  .innocent h4 {{ margin: 0 0 0.3em; font-size: 0.95em; color: #555; }}
  .ref {{ color: #777; font-size: 0.85em; font-style: italic; }}
  .disclaimer {{ background: #fffbea; border: 1px solid #f0c36d;
                 padding: 1em; margin-top: 2em; border-radius: 4px;
                 color: #555; font-size: 0.9em; }}
  .pubpeer, .retraction {{ color: #d32f2f; }}
</style>
</head>
<body>

<header class="header" role="banner">
  <h1>{title_text}</h1>
  <div class="overall" role="status" aria-live="polite">
    {overall_text}: {overall_label}
  </div>
  <div class="summary-line">{_h(report.paper_identifier)}</div>
  <div class="summary-line">{_h(report.paper_title)}</div>
  <div class="summary-line">{_h(", ".join(report.paper_authors[:5]))}</div>
  {retraction_block}
  {pubpeer_block}
</header>

<p>{_h(report.combined_evidence_strength)}</p>

<main role="main">
{body_findings}
</main>

<footer class="disclaimer" role="contentinfo">
{disclaimer_text}
</footer>

</body>
</html>
"""


def export_html(
    report: AuditReport,
    output_path: Path,
    lang: str | None = None,
) -> None:
    """把 AuditReport 渲染为 HTML 写入 output_path。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_html(report, lang=lang), encoding="utf-8")
