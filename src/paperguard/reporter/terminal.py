"""终端 Rich 报告。"""
from __future__ import annotations

from rich.console import Console
from rich.panel import Panel

from paperguard.core.types import AuditReport
from paperguard.i18n import t


def print_report(
    report: AuditReport,
    console: Console | None = None,
    lang: str | None = None,
) -> None:
    """渲染 AuditReport 到终端。"""
    console = console or Console()

    sev = report.overall_severity
    authors_line = ", ".join(report.paper_authors[:3])
    if len(report.paper_authors) > 3:
        authors_line += " et al."

    header = Panel(
        f"[{sev.color}]{t('report.overall', lang)}: "
        f"{t(f'severity.{sev.label}', lang)}[/{sev.color}]\n"
        f"{t('report.paper', lang)}: {report.paper_identifier}\n"
        f"{report.paper_title}\n"
        f"{authors_line}",
        title=t("report.title", lang),
        border_style=sev.color,
    )
    console.print(header)

    if report.retraction_status:
        console.print(
            f"[red bold]⚠ {t('report.retraction', lang)}: "
            f"{report.retraction_status}[/]"
        )
    if report.pubpeer_concerns_count > 0:
        console.print(
            f"[yellow]{t('report.pubpeer', lang)}: "
            f"{report.pubpeer_concerns_count}[/]"
        )

    console.print(f"\n[dim]{report.combined_evidence_strength}[/]\n")

    if not report.all_findings:
        console.print(f"[green]{t('report.no_anomalies', lang)}[/]")
        _print_disclaimer(console, lang)
        return

    sorted_findings = sorted(report.all_findings, key=lambda f: -f.severity.value)

    for f in sorted_findings:
        color = f.severity.color
        panel_content = f"[bold]{f.summary}[/bold]\n\n{f.detail}\n"
        if f.p_value is not None:
            panel_content += f"\n[dim]p-value: {f.p_value:.2e}"
            if f.p_value_adjusted is not None:
                panel_content += f" (FDR-adjusted: {f.p_value_adjusted:.2e})"
            panel_content += "[/]"
        if f.test_statistic is not None:
            panel_content += f"\n[dim]{f.test_name}: {f.test_statistic:.4f}[/]"

        if f.innocent_explanations:
            panel_content += f"\n\n[dim]{t('report.innocent', lang)}:[/]\n"
            for ie in f.innocent_explanations:
                panel_content += f"  • [dim]{ie}[/]\n"

        panel = Panel(
            panel_content,
            title=f"[{color}]{f.detector_id} — {f.detector_name}[/{color}]",
            subtitle=(
                f"[{color}]{t(f'severity.{f.severity.label}', lang)}[/{color}]"
            ),
            border_style=color,
        )
        console.print(panel)

    _print_disclaimer(console, lang)


def _print_disclaimer(console: Console, lang: str | None = None) -> None:
    console.print(f"\n[dim italic]{t('report.disclaimer', lang)}[/]")
