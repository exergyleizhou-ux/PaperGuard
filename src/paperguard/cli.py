"""CLI 入口。"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from paperguard import __version__
from paperguard.config import get_settings
from paperguard.core.audit import AuditLog
from paperguard.core.registry import DetectorRegistry
from paperguard.core.types import AuditReport, DetectorResult, Finding, Severity
from paperguard.detectors.g4_metadata_forensics import MetadataForensicsInput
from paperguard.evidence.combiner import combine_evidence
from paperguard.extractor.docx_tables import parse_docx_tables
from paperguard.extractor.excel import parse_data_file
from paperguard.extractor.inline_numbers import extract_text_from_docx
from paperguard.extractor.pdf_text import extract_pdf_tables, extract_pdf_text
from paperguard.fetcher.crossref import CrossRefClient
from paperguard.fetcher.openalex import OpenAlexClient
from paperguard.fetcher.pubpeer import PubPeerClient
from paperguard.fetcher.unpaywall import UnpaywallClient
from paperguard.reporter.html_export import export_html
from paperguard.reporter.json_export import export_json
from paperguard.reporter.terminal import print_report
from paperguard.utils.hash import sha256_file


def _safe_pdf_tables(file_path: Path) -> tuple[dict[str, Any], str | None]:
    """Wrap ``extract_pdf_tables`` to never crash on malformed PDFs.

    Returns ``(sheets, error_message_or_None)``. Empty dict + message
    when the parser raises. Saves callers from having to know which
    publisher PDFs trip up pdfplumber/pdfminer.
    """
    try:
        return dict(extract_pdf_tables(file_path)), None
    except Exception as e:  # noqa: BLE001
        return {}, f"{type(e).__name__}: {e}"


def _safe_pdf_text(file_path: Path) -> tuple[str, str | None]:
    """Wrap ``extract_pdf_text`` to never crash on malformed PDFs."""
    try:
        return extract_pdf_text(file_path), None
    except Exception as e:  # noqa: BLE001
        return "", f"{type(e).__name__}: {e}"


def _run_detectors_on_file(
    file_path: Path,
    registry: DetectorRegistry,
    report: AuditReport,
    seed: int,
    audit: AuditLog | None = None,
    console: Console | None = None,
) -> None:
    """Run the common detector flow on a single file.

    Used by both the interactive ``scan`` command (with audit + console)
    and the headless ``_scan_single_file`` helper (without either).
    Single source of truth for which detectors run on which file types
    — historically these two paths had drifted apart and bugs had to
    be fixed twice. Keep them in sync by routing both through here.

    The audit log and console are optional; pass ``None`` for headless
    use (e.g. multi-tenant Web UI scan submissions).
    """
    suffix = file_path.suffix.lower()

    # --- 1) Table-data detectors (A1/A2/A3/A5/A6/A7/D1/D2) ----------------
    sheets: dict[str, Any] = {}
    if suffix in {".xlsx", ".xlsm", ".csv", ".tsv"}:
        sheets = dict(parse_data_file(file_path))
    elif suffix == ".docx":
        sheets = dict(parse_docx_tables(file_path))
    elif suffix == ".pdf":
        sheets, pdf_table_err = _safe_pdf_tables(file_path)
        if pdf_table_err is not None:
            if console is not None:
                console.print(
                    f"[yellow]  PDF table extraction failed for "
                    f"{file_path.name}: {pdf_table_err}[/]"
                )
            if audit is not None:
                audit.log_event(
                    "pdf_table_extract_failed",
                    {"file": str(file_path), "error": pdf_table_err},
                )

    if sheets and console is not None:
        console.print(
            f"[dim]  Extracted {len(sheets)} table(s) from {file_path.name}[/]"
        )

    for sheet_name, df in sheets.items():
        if audit is not None:
            audit.log_event(
                "sheet_processed",
                {
                    "file": str(file_path),
                    "sheet": sheet_name,
                    "rows": len(df),
                    "cols": [str(c) for c in df.columns],
                },
            )
        for d_id in ("A1", "A2", "A3", "A5", "A6", "A7", "D1", "D2"):
            detector = registry.get(d_id)
            if detector is None:
                continue
            result = detector.detect(df, seed=seed)
            report.detector_results.append(result)
            report.all_findings.extend(result.findings)

    # --- 2) Full-text detectors (B4 / T3 / T4 / T5 / T6) ------------------
    text = ""
    if suffix == ".docx":
        text = extract_text_from_docx(file_path)
    elif suffix == ".pdf":
        text, pdf_text_err = _safe_pdf_text(file_path)
        if pdf_text_err is not None:
            if console is not None:
                console.print(
                    f"[yellow]  PDF text extraction failed for "
                    f"{file_path.name}: {pdf_text_err}[/]"
                )
            if audit is not None:
                audit.log_event(
                    "pdf_text_extract_failed",
                    {"file": str(file_path), "error": pdf_text_err},
                )

    if text:
        if audit is not None:
            audit.log_event(
                "text_extracted",
                {"file": str(file_path), "chars": len(text)},
            )
        # T3 wants paper_year for year-stratified severity (since 2.0.7).
        # Build a DataAvailabilityInput so the year is plumbed through;
        # other text detectors take raw text.
        from paperguard.detectors.t3_data_availability import (
            DataAvailabilityInput,
        )

        for d_id in ("B4", "T3", "T4", "T5", "T6"):
            detector = registry.get(d_id)
            if detector is None:
                continue
            if d_id == "T3":
                t3_input = DataAvailabilityInput(
                    text=text,
                    paper_year=report.paper_year,
                )
                result = detector.detect(t3_input, seed=seed)
            else:
                result = detector.detect(text, seed=seed)
            report.detector_results.append(result)
            report.all_findings.extend(result.findings)

    # --- 3) Metadata / forensics (G3 docx, G4 file metadata) --------------
    g3 = registry.get("G3")
    if g3 is not None and suffix == ".docx":
        result = g3.detect(file_path, seed=seed)
        report.detector_results.append(result)
        report.all_findings.extend(result.findings)

    g4 = registry.get("G4")
    if g4 is not None:
        g4_input = MetadataForensicsInput(
            file_path=file_path,
            claimed_authors=report.paper_authors,
        )
        result = g4.detect(g4_input, seed=seed)
        report.detector_results.append(result)
        report.all_findings.extend(result.findings)

    # --- 4) Image forensics (F1 intra-paper + F4 cross-paper) -------------
    f1 = registry.get("F1")
    f4 = registry.get("F4")
    if (f1 is not None or f4 is not None) and suffix in {".docx", ".pdf"}:
        from tempfile import TemporaryDirectory

        from paperguard.detectors.f1_image_duplication import (
            ImageDuplicationInput,
        )
        from paperguard.detectors.f4_cross_paper_image import (
            CrossPaperImageInput,
        )
        from paperguard.extractor.images import (
            extract_docx_images,
            extract_pdf_images,
        )

        with TemporaryDirectory() as tdir:
            tdir_path = Path(tdir)
            imgs = (
                extract_docx_images(file_path, tdir_path)
                if suffix == ".docx"
                else extract_pdf_images(file_path, tdir_path)
            )
            if audit is not None and imgs:
                audit.log_event(
                    "images_extracted",
                    {"file": str(file_path), "n_images": len(imgs)},
                )

            # F1: intra-paper duplication (needs ≥ 2 images)
            if f1 is not None and len(imgs) >= 2:
                result = f1.detect(
                    ImageDuplicationInput(image_paths=imgs), seed=seed
                )
                report.detector_results.append(result)
                report.all_findings.extend(result.findings)

            # F4: cross-paper duplication via persistent corpus.
            # Auto-builds at ~/.paperguard/image_corpus.db. Every scan
            # both reads and writes the corpus, so over time hits
            # accumulate signal across papers without manual setup.
            if f4 is not None and imgs:
                from paperguard.config import get_settings as _gs

                corpus_path = _gs().cache_dir / "image_corpus.db"
                paper_id = report.paper_identifier
                authors = list(report.paper_authors)
                f4_input = CrossPaperImageInput(
                    image_paths=imgs,
                    store_path=corpus_path,
                    current_paper_id=paper_id,
                    current_authors=authors or None,
                )
                try:
                    result = f4.detect(f4_input, seed=seed)
                except Exception as e:  # noqa: BLE001
                    if audit is not None:
                        audit.log_event(
                            "f4_failed",
                            {"file": str(file_path), "error": str(e)},
                        )
                else:
                    report.detector_results.append(result)
                    report.all_findings.extend(result.findings)
                    if audit is not None:
                        audit.log_event(
                            "f4_ran",
                            {
                                "corpus_path": str(corpus_path),
                                "n_images_indexed": len(imgs),
                                "n_findings": len(result.findings),
                            },
                        )

    # --- 5) PDF-specific: C1 Carlisle on auto-extracted baseline tables ---
    if suffix == ".pdf":
        from paperguard.detectors.c1_carlisle import CarlisleInput
        from paperguard.extractor.baseline_tables import extract_baseline_tables

        c1 = registry.get("C1")
        if c1 is not None:
            try:
                baselines = extract_baseline_tables(file_path)
            except Exception as e:  # noqa: BLE001
                if audit is not None:
                    audit.log_event(
                        "baseline_extract_failed",
                        {"file": str(file_path), "error": str(e)},
                    )
                baselines = []
            for bt in baselines:
                if len(bt.variables) < 5:
                    continue
                inp = CarlisleInput(
                    trial_id=f"{file_path.name}#p{bt.page_number}",
                    variables=bt.variables,
                )
                result = c1.detect(inp, seed=seed)
                report.detector_results.append(result)
                report.all_findings.extend(result.findings)
                if audit is not None:
                    audit.log_event(
                        "c1_auto_run",
                        {
                            "page": bt.page_number,
                            "n_variables": len(bt.variables),
                            "caption": bt.caption[:80],
                        },
                    )


@click.group()
@click.version_option(version=__version__)
def main() -> None:
    """PaperGuard — 学术论文数据诚信审查工具。"""


@main.command()
@click.option(
    "--file",
    "-f",
    "files",
    multiple=True,
    type=click.Path(exists=True, path_type=Path),
    help="本地数据文件路径（可多次使用）。",
)
@click.option("--doi", help="论文 DOI（可选，用于获取元数据 + 撤稿状态）。")
@click.option(
    "--output-json",
    type=click.Path(path_type=Path),
    help="将报告导出为 JSON。",
)
@click.option(
    "--output-html",
    type=click.Path(path_type=Path),
    help="将报告导出为自包含 HTML。",
)
@click.option("--seed", type=int, default=42, show_default=True)
@click.option(
    "--lang",
    type=click.Choice(["en", "zh-CN", "es", "ja", "de"]),
    default=None,
    help="报告语言（默认读 $PAPERGUARD_LANG，否则 en）。",
)
@click.option(
    "--check-paper-mill",
    is_flag=True,
    default=False,
    help=(
        "Run M1 paper-mill citation-graph detector. Requires --doi. "
        "Fetches a 2-hop citation subgraph (≤ 200 nodes) via OpenAlex. "
        "Will trigger many cached API calls on first run."
    ),
)
@click.option(
    "--paper-year",
    type=int,
    default=None,
    help=(
        "Publication year, used for year-stratified severity in T3 "
        "(ICMJE data-availability mandate 2018; NCT trial-reg 2005). "
        "Auto-filled from DOI metadata when --doi is given."
    ),
)
def scan(
    files: tuple[Path, ...],
    doi: str | None,
    output_json: Path | None,
    output_html: Path | None,
    seed: int,
    lang: str | None,
    check_paper_mill: bool,
    paper_year: int | None,
) -> None:
    """扫描本地数据文件 + 可选 DOI 元数据。"""
    console = Console(legacy_windows=False)
    settings = get_settings()
    run_id = uuid.uuid4().hex[:12]
    audit_dir = settings.cache_dir / "audits" / run_id
    audit = AuditLog(run_id=run_id, output_dir=audit_dir)

    report = AuditReport(
        paper_identifier=doi or (str(files[0]) if files else "local"),
        seed=seed,
    )
    if paper_year is not None:
        report.paper_year = paper_year

    if doi:
        _fetch_metadata(report, audit, doi, settings.email, console)
        # If --paper-year was not explicitly passed, fall back to what
        # the DOI lookup populated (OpenAlex provides publication_year).
        if paper_year is None and report.paper_year:
            console.print(
                f"[dim]  paper_year auto-filled from DOI: {report.paper_year}[/]"
            )

    # 如果给了 --doi 但没给 -f，尝试通过 Unpaywall 自动拉 OA PDF
    if doi and not files:
        with console.status(f"[cyan]Looking up OA PDF for {doi}..."):
            up = UnpaywallClient(email=settings.email)
            try:
                tmp_pdf = settings.cache_dir / "auto_pdf" / f"{doi.replace('/', '_')}.pdf"
                downloaded = up.download_oa_pdf(doi, tmp_pdf)
            finally:
                up.close()
        if downloaded:
            console.print(f"[green]Downloaded OA PDF → {downloaded}[/]")
            files = (downloaded,)
            audit.log_event("oa_pdf_downloaded", {"doi": doi, "path": str(downloaded)})
        else:
            console.print(
                "[yellow]No OA PDF available via Unpaywall; "
                "scan will report DOI-only metadata.[/]"
            )

    registry = DetectorRegistry().register_default()

    for file_path in files:
        console.print(f"[cyan]Processing {file_path.name}...[/]")
        file_hash = sha256_file(file_path)
        report.file_hashes[str(file_path)] = file_hash
        audit.log_event(
            "file_loaded",
            {"path": str(file_path), "sha256": file_hash},
        )
        _run_detectors_on_file(
            file_path, registry, report, seed, audit=audit, console=console
        )

    # Auto-NCT → T2 trial outcome consistency
    # If a NCT/ISRCTN ID was found in any extracted text, auto-run T2 (best effort)
    # NOTE: T2 needs `reported_primary_outcomes` which we can't reliably extract
    # automatically yet, so we just log the trial ID for now.
    from paperguard.extractor.trial_ids import extract_trial_ids

    combined_text_for_ids = " ".join(
        str((r.findings[0].evidence or {}).get("raw_text", ""))
        for r in report.detector_results
        if r.findings
    )
    # 更简单：从已抽 text 重新扫
    nct_ids_found: list[str] = []
    for file_path in files:
        suffix2 = file_path.suffix.lower()
        try:
            if suffix2 == ".pdf":
                text_for_id = extract_pdf_text(file_path)
            elif suffix2 == ".docx":
                text_for_id = extract_text_from_docx(file_path)
            else:
                text_for_id = ""
        except Exception:  # noqa: BLE001
            text_for_id = ""
        for tid in extract_trial_ids(text_for_id):
            if tid not in nct_ids_found:
                nct_ids_found.append(tid)
    if nct_ids_found:
        console.print(
            f"[cyan]Found {len(nct_ids_found)} trial registration ID(s): "
            f"{', '.join(nct_ids_found[:3])}"
            + (f" (+{len(nct_ids_found) - 3} more)" if len(nct_ids_found) > 3 else "")
            + "[/]"
        )
        audit.log_event("trial_ids_extracted", {"ids": nct_ids_found})

        # Live verify NCT IDs against ClinicalTrials.gov v2 API.
        # If a paper claims NCT123… and the registry returns 404, that's
        # a SUSPICIOUS finding (fabricated trial id is a real fraud pattern).
        from paperguard.fetcher.clinicaltrials import ClinicalTrialsClient

        nct_only = [n for n in nct_ids_found if n.upper().startswith("NCT")]
        if nct_only:
            with console.status(
                f"[cyan]Verifying {len(nct_only)} NCT ID(s) against ClinicalTrials.gov..."
            ):
                ct_client = ClinicalTrialsClient(email=settings.email)
                missing: list[str] = []
                verified: list[str] = []
                try:
                    for nct in nct_only:
                        try:
                            study = ct_client.get_study(nct)
                        except Exception as e:  # noqa: BLE001
                            audit.log_event(
                                "ct_gov_lookup_failed",
                                {"nct": nct, "error": str(e)},
                            )
                            continue
                        if study is None:
                            missing.append(nct)
                        else:
                            verified.append(nct)
                finally:
                    ct_client.close()
            if verified:
                console.print(
                    f"[green]  ✓ {len(verified)} NCT verified in registry[/]"
                )
                audit.log_event("ct_gov_verified", {"nct_ids": verified})
            if missing:
                console.print(
                    f"[red]  ✗ {len(missing)} NCT NOT FOUND in registry: "
                    f"{', '.join(missing[:3])}"
                    + (
                        f" (+{len(missing) - 3} more)"
                        if len(missing) > 3
                        else ""
                    )
                    + "[/]"
                )
                audit.log_event("ct_gov_missing", {"nct_ids": missing})
                missing_findings: list[Finding] = []
                for nct in missing:
                    missing_findings.append(
                        Finding(
                            detector_id="T2",
                            detector_name="Clinical Trial Outcome Consistency",
                            severity=Severity.SUSPICIOUS,
                            summary=(
                                f"Claimed trial registration {nct} does not "
                                "exist in ClinicalTrials.gov"
                            ),
                            detail=(
                                f"The manuscript references {nct} as a "
                                "trial-registration identifier, but the "
                                "ClinicalTrials.gov v2 API returns 404. A "
                                "registered, ICMJE-compliant trial must "
                                "have a resolvable record. An unresolvable "
                                "NCT in a published article is a strong "
                                "signal worth investigating."
                            ),
                            evidence={"nct_id": nct, "ct_gov_status": "404"},
                            innocent_explanations=[
                                "OCR misread the NCT number (off by 1-2 digits)",
                                "The trial actually registered with a non-US "
                                "registry (ISRCTN/ChiCTR/ACTRN/EudraCT) and "
                                "the NCT-like format is coincidental",
                                "Very recent registration not yet indexed "
                                "in the v2 API (rare; takes 24-48 h)",
                                "Registry record was withdrawn by the "
                                "submitter (rare; usually leaves a stub)",
                            ],
                            academic_reference=(
                                "ICMJE 2005: required pre-registration of "
                                "all interventional trials. Live API check "
                                "against https://clinicaltrials.gov/api/v2"
                            ),
                        )
                    )
                if missing_findings:
                    report.detector_results.append(
                        DetectorResult(
                            detector_id="T2",
                            applicable=True,
                            findings=missing_findings,
                        )
                    )
                    report.all_findings.extend(missing_findings)
    _ = combined_text_for_ids  # silence linter

    # M1 — paper-mill citation-graph (opt-in via --check-paper-mill)
    if check_paper_mill and doi:
        m1 = registry.get("M1")
        if m1 is not None:
            from paperguard.fetcher.citation_graph import build_citation_subgraph

            with console.status(
                f"[cyan]Fetching 2-hop citation subgraph for {doi}..."
            ):
                try:
                    graph = build_citation_subgraph(
                        doi, max_hops=2, max_nodes=200, email=settings.email
                    )
                except Exception as e:  # noqa: BLE001
                    console.print(f"[yellow]Citation graph build failed: {e}[/]")
                    graph = None
            if graph is not None and graph.number_of_nodes() >= 8:
                result = m1.detect(graph, seed=seed)
                report.detector_results.append(result)
                report.all_findings.extend(result.findings)
                audit.log_event(
                    "m1_citation_graph",
                    {
                        "n_nodes": graph.number_of_nodes(),
                        "n_edges": graph.number_of_edges(),
                        "n_findings": len(result.findings),
                    },
                )
                console.print(
                    f"[dim]M1 ran on subgraph: "
                    f"{graph.number_of_nodes()} nodes, "
                    f"{graph.number_of_edges()} edges → "
                    f"{len(result.findings)} finding(s)[/]"
                )

    combine_evidence(report)
    audit.log_event(
        "evidence_combined",
        {
            "overall_severity": report.overall_severity.label,
            "total_findings": len(report.all_findings),
        },
    )

    print_report(report, console, lang=lang)

    if output_json:
        export_json(report, output_json)
        console.print(f"[green]JSON report saved to {output_json}[/]")
    if output_html:
        export_html(report, output_html, lang=lang)
        console.print(f"[green]HTML report saved to {output_html}[/]")

    audit_file = audit.save()
    console.print(f"[dim]Audit log: {audit_file}[/]")


def _fetch_metadata(
    report: AuditReport,
    audit: AuditLog,
    doi: str,
    email: str,
    console: Console,
) -> None:
    """通过 OpenAlex + CrossRef 填充论文元数据 + 撤稿状态。"""
    with console.status(f"[cyan]Fetching metadata for {doi}..."):
        try:
            oa = OpenAlexClient(email=email)
            work: dict[str, Any] | None = oa.get_work_by_doi(doi)
            if work:
                title = work.get("title") or work.get("display_name") or ""
                report.paper_title = title
                year = work.get("publication_year")
                if isinstance(year, int):
                    report.paper_year = year
                primary = work.get("primary_location") or {}
                source = primary.get("source") or {}
                report.paper_journal = source.get("display_name") or ""
                auths = work.get("authorships") or []
                report.paper_authors = [
                    (a.get("author") or {}).get("display_name") or ""
                    for a in auths[:10]
                ]
            oa.close()
            audit.log_event("openalex_fetched", {"doi": doi, "found": bool(work)})

            cr = CrossRefClient(email=email)
            retraction = cr.check_retraction(doi)
            if retraction:
                report.retraction_status = "Retracted"
                audit.log_event("retraction_detected", retraction)
            cr.close()

            pp = PubPeerClient(email=email)
            pp_result = pp.get_comments(doi)
            if pp_result:
                count = int(pp_result.get("comment_count", 0) or 0)
                report.pubpeer_concerns_count = count
                audit.log_event("pubpeer_checked", pp_result)
                if count > 0:
                    console.print(
                        f"[yellow]PubPeer has {count} comment(s) on this DOI: "
                        f"{pp_result.get('search_url')}[/]"
                    )
                    # Emit a finding so PubPeer commentary affects
                    # overall_severity. The tier mapping is informed by
                    # empirical observation: most papers have 0; a
                    # handful of comments is normal scholarly discourse;
                    # double-digit threads (e.g. Bik-flagged image
                    # duplication papers) reliably precede or follow
                    # retraction.
                    if count >= 10:
                        pp_sev = Severity.CRITICAL
                    elif count >= 3:
                        pp_sev = Severity.SUSPICIOUS
                    else:
                        pp_sev = Severity.CONCERN
                    pp_finding = Finding(
                        detector_id="PUBPEER",
                        detector_name="PubPeer Commentary Signal",
                        severity=pp_sev,
                        summary=(
                            f"PubPeer has {count} public comment(s) on "
                            f"this DOI"
                        ),
                        detail=(
                            f"PubPeer (https://pubpeer.com) hosts public "
                            f"anonymous and signed commentary on published "
                            f"papers. This DOI has {count} comment(s) "
                            "indexed. PubPeer threads frequently precede "
                            "retractions (Bik et al. 2016 used PubPeer to "
                            "catalogue image-duplication retractions). The "
                            "specific comments may concern statistics, "
                            "image integrity, methodology, or be routine "
                            "post-publication review. Read the thread "
                            "before forming a judgement.\n"
                            f"Tier mapping: 1-2 → CONCERN, 3-9 → "
                            "SUSPICIOUS, 10+ → CRITICAL."
                        ),
                        evidence={
                            "pubpeer_comment_count": count,
                            "pubpeer_url": pp_result.get("search_url"),
                            "doi": doi,
                        },
                        innocent_explanations=[
                            "Routine post-publication discussion (e.g. "
                            "methods clarification, citation requests)",
                            "Anonymous commentary may be from competitors "
                            "or actors with non-integrity motives",
                            "Authors may have already addressed the "
                            "comments in a correction or response",
                            "High comment count can reflect topical "
                            "importance rather than concerns",
                        ],
                        academic_reference=(
                            "Bik EM et al. (2016) The Prevalence of "
                            "Inappropriate Image Duplication in "
                            "Biomedical Research Publications. mBio. "
                            "PubPeer's commentary is one of the primary "
                            "sources for that catalogue."
                        ),
                    )
                    pp_result_obj = DetectorResult(
                        detector_id="PUBPEER",
                        applicable=True,
                        findings=[pp_finding],
                    )
                    report.detector_results.append(pp_result_obj)
                    report.all_findings.append(pp_finding)
            pp.close()
        except Exception as e:  # noqa: BLE001
            console.print(f"[yellow]Metadata fetch failed: {e}[/]")


@main.command("webui")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", type=int, default=8765, show_default=True)
@click.option("--reload", is_flag=True, help="Auto-reload on code change (dev).")
def webui_cmd(host: str, port: int, reload: bool) -> None:
    """Run the FastAPI Web UI on http://<host>:<port>/ (dev mode)."""
    try:
        import uvicorn
    except ImportError as e:
        raise click.ClickException(
            "Web UI requires 'fastapi' + 'uvicorn'. Install with:\n"
            "    pip install paperguard[webui]"
        ) from e

    uvicorn.run(
        "paperguard.webui.app:create_app",
        host=host,
        port=port,
        reload=reload,
        factory=True,
    )


@main.command("server")
@click.option("--host", default="0.0.0.0", show_default=True)
@click.option("--port", type=int, default=8765, show_default=True)
@click.option(
    "--workers", type=int, default=2, show_default=True,
    help="Uvicorn worker processes.",
)
@click.option(
    "--api-token", default=None,
    help="If set, requires X-API-Token header on POST endpoints. "
         "Can also be set via PAPERGUARD_API_TOKEN env var.",
)
def server_cmd(host: str, port: int, workers: int, api_token: str | None) -> None:
    """Run the Web UI in production mode (multi-worker, no reload, with auth)."""
    try:
        import uvicorn
    except ImportError as e:
        raise click.ClickException(
            "Server requires 'fastapi' + 'uvicorn'. Install with:\n"
            "    pip install paperguard[webui]"
        ) from e

    import os

    if api_token:
        os.environ["PAPERGUARD_API_TOKEN"] = api_token
        click.echo("[security] API token enabled; clients must send X-API-Token header.")
    else:
        click.echo(
            "[warning] No API token set. Server accepts unauthenticated requests. "
            "Set --api-token or PAPERGUARD_API_TOKEN for production.",
            err=True,
        )

    uvicorn.run(
        "paperguard.webui.app:create_app",
        host=host,
        port=port,
        workers=workers,
        factory=True,
        log_level="info",
    )


@main.command("batch")
@click.option(
    "--glob",
    "patterns",
    multiple=True,
    required=True,
    help="文件 glob 模式，可多次使用。例如：--glob 'data/*.csv'。",
)
@click.option(
    "--out-dir",
    type=click.Path(path_type=Path),
    default=Path("batch_reports"),
    show_default=True,
    help="批量报告输出目录。每个文件输出一个 .json 和一个 .html。",
)
@click.option("--seed", type=int, default=42, show_default=True)
def batch(patterns: tuple[str, ...], out_dir: Path, seed: int) -> None:
    """批量扫描：按 glob 展开所有匹配的文件，逐个 scan。"""
    import glob as glob_mod

    console = Console(legacy_windows=False)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_files: list[Path] = []
    for pattern in patterns:
        all_files.extend(Path(p) for p in glob_mod.glob(pattern, recursive=True))
    all_files = [p for p in all_files if p.is_file()]

    if not all_files:
        console.print("[yellow]No files matched.[/]")
        return

    console.print(f"[cyan]Batch scanning {len(all_files)} file(s)...[/]")

    summary: list[dict[str, Any]] = []
    for fp in all_files:
        report = _scan_single_file(fp, seed=seed)
        base = out_dir / fp.stem
        export_json(report, base.with_suffix(".json"))
        export_html(report, base.with_suffix(".html"))
        summary.append(
            {
                "file": str(fp),
                "overall": report.overall_severity.label,
                "n_findings": len(report.all_findings),
                "json": str(base.with_suffix(".json")),
                "html": str(base.with_suffix(".html")),
            }
        )
        console.print(
            f"  [{report.overall_severity.color}]{report.overall_severity.label}[/] "
            f"{fp.name}  ({len(report.all_findings)} findings)"
        )

    summary_path = out_dir / "summary.json"
    import json as _json

    summary_path.write_text(_json.dumps(summary, indent=2, ensure_ascii=False))
    console.print(f"[green]Summary -> {summary_path}[/]")


def _scan_single_file(
    file_path: Path,
    seed: int = 42,
    paper_year: int | None = None,
) -> AuditReport:
    """Headless single-file scan, used by the multi-tenant Web UI.

    Thin wrapper over ``_run_detectors_on_file`` with no audit log
    and no console output. Identical detector coverage to the
    ``paperguard scan`` command since 2.0.6.

    ``paper_year`` (optional) is plumbed through to T3 for year-
    stratified severity (since 2.0.8).
    """
    registry = DetectorRegistry().register_default()
    report = AuditReport(paper_identifier=str(file_path), seed=seed)
    if paper_year is not None:
        report.paper_year = paper_year
    report.file_hashes[str(file_path)] = sha256_file(file_path)
    _run_detectors_on_file(file_path, registry, report, seed)
    combine_evidence(report)
    return report


@main.command("selfcheck")
@click.option(
    "--detector",
    multiple=True,
    help="只检查指定 ID（如 --detector A1 --detector B4）；默认检查全部。",
)
def selfcheck_cmd(detector: tuple[str, ...]) -> None:
    """在内置 fixtures 上跑一次 sanity check 确认安装正确。"""
    import importlib.resources as resources

    console = Console(legacy_windows=False)
    registry = DetectorRegistry().register_default(load_plugins=False)
    all_ids = [d.id for d in registry.all()]
    selected = list(detector) if detector else all_ids

    fixtures = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures"
    fabricated = fixtures / "fabricated_geng_style.csv"
    genuine = fixtures / "genuine_random.csv"
    if not (fabricated.exists() and genuine.exists()):
        # 兜底：用包资源（如果安装到 site-packages 没带 tests/）
        console.print(
            "[yellow]Fixture CSVs not found; selfcheck needs the source tree.[/]"
        )
        console.print(f"[dim]Looking at: {fixtures}[/]")
        _ = resources  # silence unused
        raise click.Abort()

    console.print(
        f"[cyan]Selfcheck: {len(selected)} detector(s) on 2 fixture(s)[/]"
    )

    import pandas as pd

    fab_df = pd.read_csv(fabricated)
    gen_df = pd.read_csv(genuine)

    ok = True
    for d_id in selected:
        det = registry.get(d_id)
        if det is None:
            console.print(f"  [red]✗[/] {d_id}: not registered")
            ok = False
            continue
        # 对每个 detector 选合适输入；不适用就 SKIP
        if d_id in {"A1", "A2", "A3", "A5", "A6", "A7", "D1", "D2"}:
            r_fab = det.detect(fab_df, seed=42)
            r_gen = det.detect(gen_df, seed=42)
            fab_findings = len(r_fab.findings)
            gen_findings = len(r_gen.findings)
            status = "✓" if r_fab.applicable else "SKIP"
            color = "green" if status == "✓" else "yellow"
            console.print(
                f"  [{color}]{status}[/] {d_id}: "
                f"fabricated={fab_findings}, genuine={gen_findings}"
            )
        else:
            console.print(
                f"  [dim]·[/] {d_id}: requires specialized input (skipped in selfcheck)"
            )

    console.print(
        f"\n[{'green' if ok else 'red'}]"
        f"{'OK — installation looks healthy' if ok else 'Issues detected'}"
        "[/]"
    )


@main.command("explain")
@click.option(
    "--json",
    "report_json",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="先前 paperguard scan --output-json 产生的报告。",
)
@click.option(
    "--finding-index",
    type=int,
    default=None,
    help="只解释第 N 个 finding；不给则解释所有。",
)
def explain_cmd(report_json: Path, finding_index: int | None) -> None:
    """用 LLM 把 finding 翻译成给非专家看的语言（需 PAPERGUARD_LLM_PROVIDER）。"""
    import json as _json

    from paperguard.core.types import Finding
    from paperguard.llm.explainer import LLMExplainer

    console = Console(legacy_windows=False)
    explainer = LLMExplainer()
    if not explainer.enabled:
        console.print(
            "[yellow]LLM 解释未启用。设置 PAPERGUARD_LLM_PROVIDER="
            "openai|anthropic|ollama 并提供 API key。[/]"
        )
        raise click.Abort()

    data = _json.loads(report_json.read_text(encoding="utf-8"))
    raw_findings = data.get("all_findings", [])
    if finding_index is not None:
        if not (0 <= finding_index < len(raw_findings)):
            console.print(f"[red]finding-index 越界 (有 {len(raw_findings)} 个)[/]")
            raise click.Abort()
        targets = [raw_findings[finding_index]]
    else:
        targets = raw_findings

    for idx, fd in enumerate(targets):
        # 重建 Finding 对象（pydantic 会校验）
        try:
            finding = Finding(**fd)
        except Exception as e:  # noqa: BLE001
            console.print(f"[red]Could not parse finding #{idx}: {e}[/]")
            continue
        console.print(f"\n[bold]Finding #{idx}: {finding.summary}[/bold]")
        explanation = explainer.explain(finding)
        if explanation is None:
            console.print("  [dim]LLM call failed; skipping[/]")
            continue
        console.print(f"  [cyan]Plain summary:[/] {explanation.plain_summary}")
        console.print(f"  [cyan]Lay translation:[/] {explanation.lay_translation}")


@main.command("diff")
@click.argument("before", type=click.Path(exists=True, path_type=Path))
@click.argument("after", type=click.Path(exists=True, path_type=Path))
def diff_cmd(before: Path, after: Path) -> None:
    """对比两次 paperguard scan --output-json 报告，列出新增/消失的 finding。"""
    import json as _json

    console = Console(legacy_windows=False)
    a = _json.loads(before.read_text(encoding="utf-8"))
    b = _json.loads(after.read_text(encoding="utf-8"))

    def fingerprint(f: dict[str, Any]) -> str:
        return f"{f.get('detector_id')}::{f.get('summary')}"

    a_fps = {fingerprint(f): f for f in a.get("all_findings", [])}
    b_fps = {fingerprint(f): f for f in b.get("all_findings", [])}

    added = [b_fps[k] for k in b_fps if k not in a_fps]
    removed = [a_fps[k] for k in a_fps if k not in b_fps]

    console.print(f"[bold]Diff:[/] {before.name} → {after.name}\n")
    console.print(f"  Before overall: {a.get('overall_severity')}")
    console.print(f"  After overall:  {b.get('overall_severity')}\n")

    if not added and not removed:
        console.print("[green]No changes in findings.[/]")
        return

    if added:
        console.print(f"[red]+ {len(added)} new findings:[/]")
        for f in added:
            console.print(f"    + [{f.get('detector_id')}] {f.get('summary')}")
    if removed:
        console.print(f"\n[green]- {len(removed)} resolved findings:[/]")
        for f in removed:
            console.print(f"    - [{f.get('detector_id')}] {f.get('summary')}")


@main.command("list-detectors")
@click.option("--cluster", default=None, help="Only list detectors in this cluster.")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["table", "json", "ids"]),
    default="table",
    show_default=True,
)
def list_detectors_cmd(cluster: str | None, fmt: str) -> None:
    """List all registered detectors (built-in + plugins)."""
    console = Console(legacy_windows=False)
    registry = DetectorRegistry().register_default()
    detectors = registry.all()
    if cluster:
        detectors = [d for d in detectors if d.assumption_cluster == cluster]

    if fmt == "ids":
        for d in detectors:
            click.echo(d.id)
        return
    if fmt == "json":
        import json as _json

        click.echo(
            _json.dumps(
                [
                    {
                        "id": d.id,
                        "name": d.name,
                        "description": d.description,
                        "cluster": d.assumption_cluster,
                        "data_requirements": d.data_requirements,
                        "academic_basis": d.academic_basis,
                    }
                    for d in detectors
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    tbl = Table(show_header=True, header_style="bold")
    tbl.add_column("ID", width=5)
    tbl.add_column("Name", max_width=40)
    tbl.add_column("Cluster", max_width=25)
    tbl.add_column("Data requirements", max_width=35)
    for d in detectors:
        tbl.add_row(
            d.id, d.name, d.assumption_cluster, ", ".join(d.data_requirements)
        )
    console.print(tbl)
    console.print(f"\n[dim]{len(detectors)} detector(s).[/]")


@main.command("fetch-rw")
@click.option(
    "--url",
    default="https://gitlab.com/crossref/retraction-watch-data/-/raw/main/retraction_watch.csv",
    show_default=True,
    help="Retraction Watch CSV URL.",
)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=None,
    help="Output path. Default: <cache_dir>/retraction_watch.csv.",
)
def fetch_rw_cmd(url: str, out: Path | None) -> None:
    """Download a fresh Retraction Watch CSV snapshot to local cache."""
    import httpx

    console = Console(legacy_windows=False)
    settings = get_settings()
    dst = out or settings.cache_dir / "retraction_watch.csv"
    dst.parent.mkdir(parents=True, exist_ok=True)
    console.print(f"[cyan]Downloading {url}...[/]")
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=120.0) as r:
            r.raise_for_status()
            with dst.open("wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
    except httpx.HTTPError as e:
        console.print(f"[red]Download failed: {e}[/]")
        raise click.Abort() from e
    console.print(
        f"[green]Saved {dst} ({dst.stat().st_size / 1024:.1f} KB).[/]\n"
        f"[dim]Use it with: paperguard.fetcher.retraction_watch."
        f"lookup_retraction(doi, Path('{dst}'))[/]"
    )


@main.command("fetch-ori")
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=None,
    help="Output path. Default: <cache_dir>/ori_sanctions.csv.",
)
def fetch_ori_cmd(out: Path | None) -> None:
    """Create a template ORI sanctions CSV (you must fill it in manually).

    PaperGuard does not scrape ORI's HTML pages (HTML changes break scrapers).
    Curate the CSV from https://ori.hhs.gov/case-summaries.
    """
    console = Console(legacy_windows=False)
    settings = get_settings()
    dst = out or settings.cache_dir / "ori_sanctions.csv"
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        console.print(f"[yellow]{dst} already exists; not overwriting.[/]")
        return
    template = (
        "Name,Institution,ActionDate,ActionEnd,Findings,URL\n"
        "# Example row (delete this line + fill from "
        "https://ori.hhs.gov/case-summaries):\n"
        "# Doe Jane,Example U,2024-01-15,2027-01-15,Falsification,"
        "https://ori.hhs.gov/case/jane-doe\n"
    )
    dst.write_text(template, encoding="utf-8")
    console.print(
        f"[green]Wrote template {dst}.[/]\n"
        "[dim]Now fill in real entries from "
        "https://ori.hhs.gov/case-summaries[/]"
    )


@main.command()
@click.option("--author", required=True, help="作者姓名。")
@click.option("--affiliation", default="", help="机构名过滤（模糊匹配）。")
@click.option("--year-from", type=int, default=None)
@click.option("--year-to", type=int, default=None)
@click.option("--limit", type=int, default=20, show_default=True)
def search(
    author: str,
    affiliation: str,
    year_from: int | None,
    year_to: int | None,
    limit: int,
) -> None:
    """通过作者名搜索论文。"""
    console = Console(legacy_windows=False)
    settings = get_settings()
    oa = OpenAlexClient(email=settings.email)
    try:
        works = oa.search_works(
            author=author,
            institution=affiliation,
            year_from=year_from,
            year_to=year_to,
            per_page=limit,
        )
        if not works:
            console.print("[yellow]No works found.[/]")
            return

        table = Table(show_header=True, header_style="bold")
        table.add_column("Year", width=6)
        table.add_column("Title")
        table.add_column("Venue", max_width=30)
        table.add_column("DOI", max_width=40)
        for w in works:
            title = (w.get("title") or w.get("display_name") or "")[:80]
            year = str(w.get("publication_year") or "")
            primary = w.get("primary_location") or {}
            source = primary.get("source") or {}
            venue = (source.get("display_name") or "")[:30]
            doi = (w.get("doi") or "").replace("https://doi.org/", "")
            table.add_row(year, title, venue, doi)
        console.print(table)
    finally:
        oa.close()


if __name__ == "__main__":
    main()
